import time
import json
import re
import sys
import threading
import uuid
from typing import Optional, List, Any
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys

# Import your auth logic
from auth import setup_and_login

# ==========================
# 🔒 Basic OpenAI Schema
# ==========================
class Message(BaseModel):
    role: str
    content: Any = None
    name: Optional[str] = None

    class Config:
        extra = "allow"

class ChatCompletionRequest(BaseModel):
    model: str
    messages: List[Message]
    stream: Optional[bool] = False

    class Config:
        extra = "allow"

# ==========================
# 🚀 Global Browser Setup (Uvicorn Safe)
# ==========================
driver = None
browser_lock = threading.Lock()

@asynccontextmanager
async def lifespan(app: FastAPI):
    global driver
    print("Initializing Clean API Bridge for smolagents...")
    driver = setup_and_login()

    yield

    print("Shutting down API Bridge and closing browser...")
    if driver:
        driver.quit()

app = FastAPI(title="DeepSeek Pure Text API", lifespan=lifespan)

# ==========================
# 🧠 SMART PROMPT BUILDER
# ==========================
def build_prompt(messages: List[Message]) -> str:
    global driver

    # 1. NEW TASK: If it's just System + User, clear the memory!
    if len(messages) <= 2:
        print("🧹 New task detected. Clearing DeepSeek chat memory...")
        driver.get("https://chat.deepseek.com/")
        time.sleep(2.5) # Let the blank chat load

        prompt = ""
        for msg in messages:
            role = msg.role.upper()
            content = str(msg.content) if msg.content else ""
            prompt += f"[{role}]:\n{content}\n\n"
        return prompt.strip()

    # 2. ONGOING LOOP: DeepSeek already remembers the chat. Just send the new observation!
    print("🧠 Leveraging native chat memory. Only sending the latest observation...")
    last_msg = messages[-1]
    role = last_msg.role.upper()
    content = str(last_msg.content) if last_msg.content else ""

    return f"[{role}]:\n{content}".strip()

# ==========================
# 🌐 API ENDPOINTS
# ==========================
@app.get("/v1/models")
def get_models():
    return {
        "object": "list",
        "data": [{"id": "deepseek-web", "object": "model", "created": int(time.time()), "owned_by": "custom"}]
    }

@app.post("/v1/chat/completions")
def chat_completions(req: ChatCompletionRequest):
    global driver

    # ---------------------------------------------------------
    # 🛡️ Intercept Title Generation
    # ---------------------------------------------------------
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
            # 1. Build the smart prompt
            structured_prompt = build_prompt(req.messages)

            # 2. Inject into DeepSeek UI
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

            # 3. Wait for generation to finish (Timeout after 3 minutes)
            start_time = time.time()
            while True:
                if driver.execute_script("return window._deepseekStreamFinished;"):
                    break
                if time.time() - start_time > 180:
                    raise HTTPException(status_code=504, detail="Timeout waiting for completion")
                time.sleep(0.5)

            time.sleep(1.0) # Small buffer to let the DOM settle

            # 4. Extract Text (Newline Safe!)
            clean_text = driver.execute_script(r"""
                let markdownDivs = document.querySelectorAll('.ds-markdown, .prose');
                if (markdownDivs.length > 0) {
                    let clone = markdownDivs[markdownDivs.length - 1].cloneNode(true);

                    // Nuke the UI artifacts before extracting text
                    let junkElements = clone.querySelectorAll('div[class*="header"], div[class*="toolbar"], button, svg');
                    junkElements.forEach(el => el.remove());

                    // Hack to preserve newlines in syntax-highlighted code blocks
                    let codeBlocks = clone.querySelectorAll('pre, code');
                    codeBlocks.forEach(cb => {
                        cb.innerHTML = cb.innerHTML.replace(/<\/div>/g, '</div>\n').replace(/<br\s*\/?>/gi, '\n');
                    });

                    // Fallback to textContent if innerText squashes things
                    let text = clone.innerText;
                    if (!text.includes('\n') && clone.textContent.includes('\n')) {
                        text = clone.textContent;
                    }
                    return text;
                }
                return "";
            """)

            print(f"✅ Snipped clean DOM output length: {len(clean_text)}")

            # 5. Clean up DeepSeek UI artifacts (Copy/Download buttons that leaked into text)
            ui_regex = r'^(?:javascript|typescript|text|html|css|json|python|bash|sh|jsx|tsx)?\s*Copy\s*Download\s*'
            clean_text = re.sub(ui_regex, '', clean_text, flags=re.IGNORECASE | re.MULTILINE).strip()

            # 6. Construct standard OpenAI Text Response
            final_response = {
                "id": f"chatcmpl-{uuid.uuid4().hex}",
                "object": "chat.completion",
                "created": int(time.time()),
                "model": req.model,
                "choices": [{
                    "index": 0,
                    "message": {"role": "assistant", "content": clean_text},
                    "finish_reason": "stop"
                }],
                "usage": {"prompt_tokens": 100, "completion_tokens": 50, "total_tokens": 150}
            }

            # 7. Stream the text back (smolagents expects a stream if it asked for one)
            if req.stream:
                def generate_fake_stream():
                    yield f"data: {json.dumps({'id': final_response['id'], 'object': 'chat.completion.chunk', 'created': final_response['created'], 'model': req.model, 'choices': [{'index': 0, 'delta': {'role': 'assistant'}, 'finish_reason': None}]})}\n\n"
                    yield f"data: {json.dumps({'id': final_response['id'], 'object': 'chat.completion.chunk', 'created': final_response['created'], 'model': req.model, 'choices': [{'index': 0, 'delta': {'content': clean_text}, 'finish_reason': None}]})}\n\n"
                    yield f"data: {json.dumps({'id': final_response['id'], 'object': 'chat.completion.chunk', 'created': final_response['created'], 'model': req.model, 'choices': [{'index': 0, 'delta': {}, 'finish_reason': 'stop'}]})}\n\n"
                    yield "data: [DONE]\n\n"
                return StreamingResponse(generate_fake_stream(), media_type="text/event-stream")
            else:
                return final_response

        except Exception as e:
            print(f"❌ Error during generation: {str(e)}")
            raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("naked_api:app", host="0.0.0.0", port=8000, reload=True)
