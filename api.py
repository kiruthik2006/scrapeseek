import time
import json
import json_repair
import re
import sys
import threading
import uuid
from typing import Optional, Dict, List, Any
from fastapi.responses import StreamingResponse

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager

# ==========================
# 🔒 OpenAI Schema Definitions (Agent Compatible)
# ==========================

class Message(BaseModel):
    role: str
    content: Any = None  # Changed to Any (Agents sometimes send lists instead of strings)
    name: Optional[str] = None
    tool_call_id: Optional[str] = None
    tool_calls: Optional[List[Any]] = None  # Crucial: Agents send this back in history

    class Config:
        extra = "allow"  # Tells Pydantic to ignore any unknown fields instead of crashing

class ChatCompletionRequest(BaseModel):
    model: str
    messages: List[Message]
    tools: Optional[List[Any]] = None
    stream: Optional[bool] = False  # Added to track if the agent wants a stream

    class Config:
        extra = "allow"  # Stops crashes from max_tokens, top_p, stop sequences, etc.

# Your existing schema for internal structured parsing
class StructuredResponse(BaseModel):
    tool_name: Optional[str] = None
    arguments: Optional[Dict] = None
    response: Optional[str] = None

# ==========================
# ⚙️ Prompt Builder for Agents
# ==========================

def build_prompt(messages: List[Message], tools: Optional[List[Any]]) -> str:
    # 1. Format the conversation history (Agents need to see tool outputs)
    history = []
    for m in messages:
        role = m.role.upper()
        content_str = str(m.content) if m.content else "(Tool Call Executed)"
        history.append(f"[{role}]: {content_str}")

    convo_str = "\n".join(history)

    # 2. Format the available tools
    tools_str = "None"
    if tools:
        tools_str = json.dumps(tools, indent=2)

    return f"""
You are an autonomous coding agent. Respond ONLY with valid JSON.
Do NOT output markdown outside the JSON.

AVAILABLE TOOLS:
{tools_str}

JSON SCHEMA:
{{
  "tool_name": "<name of tool to use, or null if replying with text>",
  "arguments": <object containing tool arguments, or null>,
  "response": "<your text response to the user if no tool is needed, or null>"
}}

CONVERSATION HISTORY:
{convo_str}

Based on the history, output your JSON:
""".strip()

def extract_json(text: str) -> Optional[str]:
    match = re.search(r"\{[\s\S]*?\}", text)
    return match.group(0) if match else None

# ==========================
# 🚀 Global Browser Setup
# ==========================
print("Launching headless-ready browser API...")

driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()))
driver.get("https://chat.deepseek.com")
wait = WebDriverWait(driver, 60)

print("Waiting for login + textarea...")
wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, 'textarea[placeholder="Message DeepSeek"]')))
print("✅ Browser Connected & API Ready!")

# Lock to prevent concurrent requests from typing at the same time
browser_lock = threading.Lock()

# ==========================
# 🌐 FastAPI App
# ==========================
app = FastAPI(title="DeepSeek Agent API")

# Agents often call this to verify the connection on startup
@app.get("/v1/models")
def get_models():
    return {
        "object": "list",
        "data": [
            {
                "id": "deepseek-web",
                "object": "model",
                "created": int(time.time()),
                "owned_by": "custom"
            }
        ]
    }

@app.post("/v1/chat/completions")
def chat_completions(req: ChatCompletionRequest):
    # Only allow one request to control the browser at a time
    with browser_lock:
        try:
            # 1. Inject history and tools into the prompt
            structured_prompt = build_prompt(req.messages, req.tools)

            # 2. Interact with the DOM
            answer_xpath = "//div[contains(@class, 'ds-markdown') and not(ancestor::div[contains(@class, 'ds-think-content')])]"
            existing_responses = driver.find_elements(By.XPATH, answer_xpath)
            existing_count = len(existing_responses)

            textarea = driver.find_element(By.CSS_SELECTOR, 'textarea[placeholder="Message DeepSeek"]')

            textarea.click()
            modifier = Keys.COMMAND if sys.platform == 'darwin' else Keys.CONTROL
            textarea.send_keys(modifier + "a")
            textarea.send_keys(Keys.DELETE)

            driver.execute_script("arguments[0].value = arguments[1];", textarea, structured_prompt)
            textarea.send_keys(Keys.SPACE)
            textarea.send_keys(Keys.BACKSPACE)
            textarea.send_keys(Keys.ENTER)

            print("\n⏳ Waiting for AI to finish thinking and start responding...")

            # 3. Wait for DeepThink to finish and grab the final container
            latest_container = None
            while True:
                markdown_elements = driver.find_elements(By.CSS_SELECTOR, "div.ds-markdown")
                valid_answers = []
                for el in markdown_elements:
                    is_thought = driver.execute_script("return arguments[0].closest('.ds-think-content') !== null;", el)
                    if not is_thought:
                        valid_answers.append(el)

                if len(valid_answers) > existing_count:
                    latest_container = valid_answers[-1]
                    break
                time.sleep(0.5)

            # 4. Wait for the generation to completely finish
            previous_text = ""
            stable_counter = 0
            while True:
                current_text = latest_container.text
                if len(current_text) > len(previous_text):
                    previous_text = current_text
                    stable_counter = 0
                else:
                    stable_counter += 1

                if stable_counter >= 20: # 5 seconds of silence
                    break
                time.sleep(0.25)

            # 5. Extract, Repair, and Validate the JSON (WITH FALLBACK)
            print(f"✅ AI finished generating! Raw output length: {len(previous_text)}")

            json_block = extract_json(previous_text)

            message_payload = {"role": "assistant"}
            finish_reason = "stop"

            if json_block:
                try:
                    parsed = json_repair.loads(json_block)
                    validated = StructuredResponse(**parsed)

                    # 🔥 THE TRANSLATOR: Did DeepSeek try to use a tool?
                    if validated.tool_name and validated.tool_name.lower() != "null":
                        # YES: Format it as an official OpenAI Tool Call
                        message_payload["content"] = None
                        message_payload["tool_calls"] = [
                            {
                                "id": f"call_{uuid.uuid4().hex[:16]}",
                                "type": "function",
                                "function": {
                                    "name": validated.tool_name,
                                    "arguments": json.dumps(validated.arguments or {})
                                }
                            }
                        ]
                        finish_reason = "tool_calls"
                    else:
                        # NO: Format it as a normal chat message
                        message_payload["content"] = validated.response or previous_text

                except Exception as e:
                    print(f"⚠️ JSON parsing failed, falling back to raw text. Error: {e}")
                    message_payload["content"] = previous_text
            else:
                # AI completely ignored our JSON instructions
                print("⚠️ No JSON block found, returning raw text directly to agent.")
                message_payload["content"] = previous_text

            # 6. Format exactly like an OpenAI API Response
            # 🔥 Fix: Some strict SDKs crash if content is exactly 'null', use empty string instead
            if message_payload.get("content") is None:
                message_payload["content"] = ""

            final_response = {
                "id": f"chatcmpl-{uuid.uuid4().hex}",
                "object": "chat.completion",
                "created": int(time.time()),
                "model": req.model,
                "choices": [{
                    "index": 0,
                    "message": message_payload,
                    "finish_reason": finish_reason
                }],
                "usage": {"prompt_tokens": 100, "completion_tokens": 50, "total_tokens": 150}
            }

            print(f"📤 Agent requested streaming: {req.stream}")

            # 🔥 THE FIX: If the agent wants a stream, we fake one!
            if req.stream:
                def generate_fake_stream():
                    # Chunk 1: The Role
                    yield f"data: {json.dumps({'id': final_response['id'], 'object': 'chat.completion.chunk', 'created': final_response['created'], 'model': req.model, 'choices': [{'index': 0, 'delta': {'role': 'assistant'}, 'finish_reason': None}]})}\n\n"

                    # Chunk 2: The Content or Tool Call
                    delta_payload = {}
                    if message_payload.get("content"):
                        delta_payload["content"] = message_payload["content"]
                    if message_payload.get("tool_calls"):
                        delta_payload["tool_calls"] = [
                            {
                                "index": 0,
                                "id": message_payload["tool_calls"][0]["id"],
                                "type": "function",
                                "function": {
                                    "name": message_payload["tool_calls"][0]["function"]["name"],
                                    "arguments": message_payload["tool_calls"][0]["function"]["arguments"]
                                }
                            }
                        ]

                    yield f"data: {json.dumps({'id': final_response['id'], 'object': 'chat.completion.chunk', 'created': final_response['created'], 'model': req.model, 'choices': [{'index': 0, 'delta': delta_payload, 'finish_reason': None}]})}\n\n"

                    # Chunk 3: The Stop Signal
                    yield f"data: {json.dumps({'id': final_response['id'], 'object': 'chat.completion.chunk', 'created': final_response['created'], 'model': req.model, 'choices': [{'index': 0, 'delta': {}, 'finish_reason': finish_reason}]})}\n\n"

                    # Chunk 4: The Official OpenAI "Done" flag
                    yield "data: [DONE]\n\n"

                return StreamingResponse(generate_fake_stream(), media_type="text/event-stream")

            # If the agent didn't ask for a stream, return standard JSON
            else:
                print("📤 Sending exact payload back to Agent (No Stream):")
                print(json.dumps(final_response, indent=2))
                return final_response

        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    print("Starting Agent API server on http://localhost:8000...")
    uvicorn.run(app, host="0.0.0.0", port=8000)
