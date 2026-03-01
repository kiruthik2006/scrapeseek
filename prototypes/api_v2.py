import time
import json
import json_repair
import re
import sys
import threading
import uuid
import os
from typing import Optional, Dict, List, Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait

from auth import setup_and_login

# ==========================
# 🔒 OpenAI Schema Definitions (Agent Resilient)
# ==========================
class Message(BaseModel):
    role: str
    content: Any = None
    name: Optional[str] = None
    tool_call_id: Optional[str] = None
    tool_calls: Optional[List[Any]] = None

    class Config:
        extra = "allow"

class ChatCompletionRequest(BaseModel):
    model: str
    messages: List[Message]
    tools: Optional[List[Any]] = None
    stream: Optional[bool] = False

    class Config:
        extra = "allow"

class StructuredResponse(BaseModel):
    tool_name: Optional[str] = None
    arguments: Optional[Dict] = None
    response: Optional[str] = None

# ==========================
# ⚙️ ADVANCED PROMPT BUILDER
# ==========================
def build_prompt(messages: List[Message], tools: Optional[List[Any]]) -> str:
    # 1. Extract the Agent's internal System Prompt
    system_prompts = [str(m.content) for m in messages if m.role.lower() == 'system' and m.content]
    agent_system_instruction = "\n".join(system_prompts) if system_prompts else "You are an autonomous AI coding agent."

    # 2. Context Compression
    recent_messages = messages[-3:]
    history_str = ""
    for m in recent_messages:
        role = m.role.upper()
        content_str = str(m.content) if m.content else "(Tool Execution Log / System Acknowledgment)"
        history_str += f"\n[{role}]: {content_str}"

    tools_str = json.dumps(tools, indent=2) if tools else "None"

    # 3. The Ultimate Strict System Prompt (ANTI-CHATTER SHIELD)
    return f"""
<<< AGENT DIRECTIVE >>>
{agent_system_instruction}

<<< API BRIDGE INSTRUCTIONS >>>
You are operating within a strict automated machine-to-machine API.
1. ABSOLUTELY NO CONVERSATIONAL FILLER. You must output ONLY a valid JSON object.
2. DO NOT start your response with phrases like "I have analyzed...", "Here is...", or "Now that...".
3. Your response MUST begin immediately with the `{{` character and end with the `}}` character.
4. DO NOT wrap the JSON in markdown code blocks (no ```json).
5. NEVER output UI artifacts like "Copy" or "Download".

<<< AVAILABLE TOOLS >>>
{tools_str}

<<< EXPECTED JSON SCHEMA >>>
{{
  "tool_name": "<tool_name_or_null>",
  "arguments": <args_object_or_null>,
  "response": "<your_internal_thought_or_message_to_user>"
}}

<<< RECENT CONTEXT (NEW DATA) >>>{history_str}

Based STRICTLY on the recent context and tools provided, output your JSON now.
START YOUR RESPONSE DIRECTLY WITH THE {{ CHARACTER:
""".strip()

# ==========================
# 🧠 EXTRACTION & SANITIZATION
# ==========================
def extract_json(text: str) -> Optional[str]:
    text = text.strip()

    # 1. Strip markdown blocks if the AI used them
    block_match = re.search(r"```(?:json)?\s*(.*?)\s*```", text, re.DOTALL | re.IGNORECASE)
    if block_match:
        text = block_match.group(1).strip()

    # 2. HEALER 1: Missing Opening Brace
    if '{' not in text and '"tool_name"' in text:
        text = "{\n" + text[text.find('"tool_name"'):]
        print("🩹 Auto-healed missing opening brace!")

    # 3. HEALER 2: Missing Closing Brace
    if '{' in text:
        # Check if there is a closing brace AFTER the opening brace
        if '}' not in text[text.find('{'):]:
            text = text + "\n}"
            print("🩹 Auto-healed missing closing brace!")

    # 4. Final Crop (Surgically extract just the JSON)
    try:
        first_brace = text.index('{')
        last_brace = text.rindex('}')
        if first_brace != -1 and last_brace != -1 and last_brace >= first_brace:
            return text[first_brace : last_brace + 1].strip()
    except ValueError:
        pass # The text is completely unrecognizable

    return None

def sanitize_arguments(arguments: Dict) -> Dict:
    """Surgically removes UI artifacts and markdown that DeepSeek sneaks into string values."""
    if not arguments:
        return arguments

    for key, value in arguments.items():
        if isinstance(value, str):
            cleaned = re.sub(r"^```[a-zA-Z0-9-]*\n?", "", value)
            cleaned = re.sub(r"\n?```$", "", cleaned)
            ui_regex = r'^(?:javascript|typescript|text|html|css|json|python|bash|sh|jsx|tsx)?\s*Copy\s*Download\s*'
            cleaned = re.sub(ui_regex, '', cleaned, flags=re.IGNORECASE | re.MULTILINE)
            arguments[key] = cleaned.strip()

    return arguments

# ==========================
# 🚀 Global Browser Setup
# ==========================
DS_EMAIL = os.getenv("DS_EMAIL", "YOUR_EMAIL_HERE")
DS_PASSWORD = os.getenv("DS_PASSWORD", "YOUR_PASSWORD_HERE")

print("Initializing API Bridge...")
driver = setup_and_login()
wait = WebDriverWait(driver, 60)

browser_lock = threading.Lock()
app = FastAPI(title="DeepSeek Agent API")

@app.get("/v1/models")
def get_models():
    return {
        "object": "list",
        "data": [{"id": "deepseek-web", "object": "model", "created": int(time.time()), "owned_by": "custom"}]
    }

@app.post("/v1/chat/completions")
def chat_completions(req: ChatCompletionRequest):
    # Intercept Title Generation
    if req.messages:
        last_msg = str(req.messages[-1].content).lower()
        if "title" in last_msg and ("conversation" in last_msg or "short" in last_msg) and len(last_msg) < 300:
            dummy_title = "Agent Session"
            final_response = {
                "id": f"chatcmpl-{uuid.uuid4().hex}", "object": "chat.completion", "created": int(time.time()), "model": req.model,
                "choices": [{"index": 0, "message": {"role": "assistant", "content": dummy_title}, "finish_reason": "stop"}]
            }
            if req.stream:
                def generate_title_stream():
                    yield f"data: {json.dumps({'id': final_response['id'], 'object': 'chat.completion.chunk', 'created': final_response['created'], 'model': req.model, 'choices': [{'index': 0, 'delta': {'role': 'assistant', 'content': dummy_title}, 'finish_reason': None}]})}\n\n"
                    yield f"data: {json.dumps({'id': final_response['id'], 'object': 'chat.completion.chunk', 'created': final_response['created'], 'model': req.model, 'choices': [{'index': 0, 'delta': {}, 'finish_reason': 'stop'}]})}\n\n"
                    yield "data: [DONE]\n\n"
                return StreamingResponse(generate_title_stream(), media_type="text/event-stream")
            return final_response

    with browser_lock:
        try:
            structured_prompt = build_prompt(req.messages, req.tools)

            textarea = driver.find_element(By.CSS_SELECTOR, 'textarea[placeholder="Message DeepSeek"]')
            textarea.click()
            modifier = Keys.COMMAND if sys.platform == 'darwin' else Keys.CONTROL
            textarea.send_keys(modifier + "a")
            textarea.send_keys(Keys.DELETE)

            driver.execute_script("arguments[0].value = arguments[1];", textarea, structured_prompt)
            textarea.send_keys(Keys.SPACE)
            textarea.send_keys(Keys.BACKSPACE)

            driver.execute_script("window._deepseekStreamFinished = false;")
            textarea.send_keys(Keys.ENTER)

            print("\n⚡ Generation started! Waiting for stream to finish...")

            start_time = time.time()
            while True:
                if driver.execute_script("return window._deepseekStreamFinished;"):
                    break
                if time.time() - start_time > 180:
                    raise HTTPException(status_code=504, detail="Timeout waiting for completion")
                time.sleep(0.5)

            time.sleep(1.0)

            clean_text = driver.execute_script("""
                let markdownDivs = document.querySelectorAll('.ds-markdown, .prose');
                if (markdownDivs.length > 0) {
                    let clone = markdownDivs[markdownDivs.length - 1].cloneNode(true);
                    let junkElements = clone.querySelectorAll('div[class*="header"], div[class*="toolbar"], button, svg');
                    junkElements.forEach(el => el.remove());
                    return clone.innerText;
                }
                return "";
            """)

            print(f"✅ Snipped clean DOM output length: {len(clean_text)}")

            ui_regex = r'^(?:javascript|typescript|text|html|css|json|python|bash|sh|jsx|tsx)?\s*Copy\s*Download\s*'
            clean_text = re.sub(ui_regex, '', clean_text, flags=re.IGNORECASE | re.MULTILINE).strip()

            # 🔥 THE BULLETPROOF EXTRACTOR IN ACTION
            json_block = extract_json(clean_text)
            message_payload = {"role": "assistant"}
            finish_reason = "stop"

            if json_block:
                try:
                    parsed = json_repair.loads(json_block)
                    validated = StructuredResponse(**parsed)

                    if validated.tool_name and validated.tool_name.lower() != "null":
                        # ✅ ZED FIX 1: Send the response field as content so Zed displays the AI's thoughts
                        message_payload["content"] = validated.response if validated.response else ""

                        clean_args = sanitize_arguments(validated.arguments)
                        message_payload["tool_calls"] = [
                            {
                                "id": f"call_{uuid.uuid4().hex[:16]}",
                                "type": "function",
                                "function": {
                                    "name": validated.tool_name,
                                    "arguments": json.dumps(clean_args or {})
                                }
                            }
                        ]
                        finish_reason = "tool_calls"
                    else:
                        message_payload["content"] = validated.response or clean_text

                except Exception as e:
                    print(f"⚠️ JSON parsing failed. Error: {e}")
                    message_payload["content"] = clean_text
            else:
                message_payload["content"] = clean_text

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

            if req.stream:
                def generate_fake_stream():
                    # 1. Start the message stream
                    yield f"data: {json.dumps({'id': final_response['id'], 'object': 'chat.completion.chunk', 'created': final_response['created'], 'model': req.model, 'choices': [{'index': 0, 'delta': {'role': 'assistant', 'content': ''}, 'finish_reason': None}]})}\n\n"

                    # 2. Stream the AI's thoughts so you can read them in Zed!
                    if message_payload.get("content"):
                        yield f"data: {json.dumps({'id': final_response['id'], 'object': 'chat.completion.chunk', 'created': final_response['created'], 'model': req.model, 'choices': [{'index': 0, 'delta': {'content': message_payload['content']}, 'finish_reason': None}]})}\n\n"

                    # 3. ✅ ZED FIX 2: Strict OpenAI Tool Chunking
                    if message_payload.get("tool_calls"):
                        tc = message_payload["tool_calls"][0]

                        # Chunk A: Setup the Tool Call (ID and Name, NO arguments)
                        tool_init = {
                            "tool_calls": [{
                                "index": 0,
                                "id": tc["id"],
                                "type": "function",
                                "function": {
                                    "name": tc["function"]["name"],
                                    "arguments": ""
                                }
                            }]
                        }
                        yield f"data: {json.dumps({'id': final_response['id'], 'object': 'chat.completion.chunk', 'created': final_response['created'], 'model': req.model, 'choices': [{'index': 0, 'delta': tool_init, 'finish_reason': None}]})}\n\n"

                        # Chunk B: Stream the arguments
                        tool_args = {
                            "tool_calls": [{
                                "index": 0,
                                "function": {
                                    "arguments": tc["function"]["arguments"]
                                }
                            }]
                        }
                        yield f"data: {json.dumps({'id': final_response['id'], 'object': 'chat.completion.chunk', 'created': final_response['created'], 'model': req.model, 'choices': [{'index': 0, 'delta': tool_args, 'finish_reason': None}]})}\n\n"

                    # 4. Send the Stop Signal
                    yield f"data: {json.dumps({'id': final_response['id'], 'object': 'chat.completion.chunk', 'created': final_response['created'], 'model': req.model, 'choices': [{'index': 0, 'delta': {}, 'finish_reason': finish_reason}]})}\n\n"
                    yield "data: [DONE]\n\n"

                return StreamingResponse(generate_fake_stream(), media_type="text/event-stream")
            else:
                return final_response

        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("api:app", host="0.0.0.0", port=8000, reload=True)
