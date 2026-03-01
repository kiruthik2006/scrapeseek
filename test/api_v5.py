Selena/test/api_v5.py
import asyncio
import json
import json_repair
import os
import re
import sys
import threading
import time
import uuid
from collections import deque
from concurrent.futures import ThreadPoolExecutor
from functools import lru_cache
from typing import Optional, Dict, List, Any, Tuple

import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
from webdriver_manager.chrome import ChromeDriverManager

# ==========================
# Configuration (from environment)
# ==========================
MAX_BROWSERS = int(os.environ.get("MAX_BROWSERS", "4"))
BROWSER_POOL_TIMEOUT = int(os.environ.get("BROWSER_POOL_TIMEOUT", "30"))
REQUEST_TIMEOUT = int(os.environ.get("REQUEST_TIMEOUT", "300"))
CONTEXT_MESSAGES = int(os.environ.get("CONTEXT_MESSAGES", "3"))
UI_CLEANUP_REGEX = os.environ.get(
    "UI_CLEANUP_REGEX",
    r'^(?:javascript|typescript|text|html|css|json|python|bash|sh|jsx|tsx)?\s*Copy\s*Download\s*'
)

# ==========================
# OpenAI Schema Definitions
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
# Browser Pool Management
# ==========================
class BrowserInstance:
    def __init__(self, instance_id: int):
        self.id = instance_id
        self.driver = self._create_driver()
        self.lock = threading.Lock()
        self.in_use = False
        self.last_used = time.time()
        self._setup_xhr_interceptor()

    def _create_driver(self):
        options = Options()
        # options.add_argument("--headless")  # Uncomment for headless mode
        options.add_argument("--disable-gpu")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--window-size=1920,1080")
        return webdriver.Chrome(
            service=Service(ChromeDriverManager().install()),
            options=options
        )

    def _setup_xhr_interceptor(self):
        xhr_interceptor_js = """
        console.log(`[Browser ${this.id}] XHR Proxy injected.`);
        const originalXHR = window.XMLHttpRequest;
        window.XMLHttpRequest = function() {
            const xhr = new originalXHR();
            const originalOpen = xhr.open;
            xhr.open = function(method, url, ...args) {
                if (typeof url === 'string' && url.includes('/chat/completion') && method.toUpperCase() === 'POST') {
                    window._deepseekStreamFinished = false;
                    xhr.addEventListener('readystatechange', function() {
                        if (xhr.readyState === 4 && xhr.status === 200) {
                            window._deepseekStreamFinished = true;
                        }
                    });
                }
                return originalOpen.apply(this, [method, url, ...args]);
            };
            return xhr;
        };
        """
        self.driver.execute_cdp_cmd(
            "Page.addScriptToEvaluateOnNewDocument",
            {"source": xhr_interceptor_js.replace("${this.id}", str(self.id))}
        )
        self.driver.get("https://chat.deepseek.com")
        WebDriverWait(self.driver, 60).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, 'textarea[placeholder="Message DeepSeek"]'))
        )
        print(f"✅ Browser {self.id} ready.")

    def quit(self):
        self.driver.quit()

class BrowserPool:
    def __init__(self, max_browsers=MAX_BROWSERS):
        self.max_browsers = max_browsers
        self.instances = [BrowserInstance(i) for i in range(max_browsers)]
        self._queue = asyncio.Queue()
        self._executor = ThreadPoolExecutor(max_workers=max_browsers)

    async def acquire(self, timeout=BROWSER_POOL_TIMEOUT) -> BrowserInstance:
        """Acquire a browser instance, waiting if necessary."""
        start = time.time()
        while time.time() - start < timeout:
            for inst in self.instances:
                if not inst.in_use and inst.lock.acquire(blocking=False):
                    inst.in_use = True
                    inst.last_used = time.time()
                    return inst
            await asyncio.sleep(0.1)
        raise TimeoutError("No browser instance available")

    def release(self, instance: BrowserInstance):
        instance.in_use = False
        instance.lock.release()

    async def shutdown(self):
        for inst in self.instances:
            await asyncio.get_event_loop().run_in_executor(self._executor, inst.quit)

pool = BrowserPool()

# ==========================
# Prompt Builder (optimized with caching)
# ==========================
@lru_cache(maxsize=128)
def _cached_system_prompt(messages_tuple: Tuple[Tuple[str, str], ...]) -> str:
    """Extract and cache system prompt from message history."""
    system_prompts = []
    for role, content in messages_tuple:
        if role.lower() == 'system' and content:
            system_prompts.append(content)
    return "\n".join(system_prompts) if system_prompts else "You are an autonomous AI coding agent."

def build_prompt(messages: List[Message], tools: Optional[List[Any]]) -> str:
    # Cache system prompt using a tuple of (role, content) for immutable cache key
    msg_tuples = tuple((m.role, str(m.content) if m.content else "") for m in messages if m.role.lower() == 'system')
    agent_system_instruction = _cached_system_prompt(msg_tuples)

    # Context Compression: only last CONTEXT_MESSAGES
    recent_messages = messages[-CONTEXT_MESSAGES:]
    history_parts = []
    for m in recent_messages:
        role = m.role.upper()
        content_str = str(m.content) if m.content else "(Tool Execution Log)"
        history_parts.append(f"\n[{role}]: {content_str}")

    tools_str = json.dumps(tools, indent=2) if tools else "None"

    return f"""
<<< AGENT DIRECTIVE >>>
{agent_system_instruction}

<<< API BRIDGE INSTRUCTIONS >>>
You are operating within a strict automated agent framework.
1. You MUST respond with a SINGLE, valid JSON object. No conversational filler.
2. DO NOT wrap the JSON in markdown code blocks outside of the required structure.
3. If you write code, the string inside your JSON MUST contain ONLY the raw, runnable code. DO NOT include markdown backticks (```) or language tags inside the code string.
4. NEVER output UI artifacts like "Copy" or "Download".

<<< AVAILABLE TOOLS >>>
{tools_str}

<<< EXPECTED JSON SCHEMA >>>
{{
  "tool_name": "<tool_name_or_null>",
  "arguments": <args_object_or_null>,
  "response": "<your_internal_thought_or_message_to_user>"
}}

<<< RECENT CONTEXT (NEW DATA) >>>{"".join(history_parts)}

Based STRICTLY on the recent context and tools provided, output your JSON now:
""".strip()

# ==========================
# JSON Extraction (optimized)
# ==========================
def extract_json(text: str) -> Optional[str]:
    # First, try to parse the entire text as JSON directly
    try:
        json.loads(text)
        return text.strip()
    except json.JSONDecodeError:
        pass

    # Look for markdown block
    block_match = re.search(r"```(?:json)?\s*(.*?)\s*```", text, re.DOTALL | re.IGNORECASE)
    if block_match:
        candidate = block_match.group(1).strip()
        try:
            json.loads(candidate)
            return candidate
        except json.JSONDecodeError:
            pass

    # Greedy fallback: find first { and last }
    match = re.search(r"(\{[\s\S]*\})", text)
    if match:
        candidate = match.group(1).strip()
        try:
            json.loads(candidate)
            return candidate
        except json.JSONDecodeError:
            pass

    # Last resort: return whatever we found
    return match.group(1).strip() if match else None

def sanitize_arguments(arguments: Dict) -> Dict:
    """Remove UI artifacts from string values."""
    if not arguments:
        return arguments

    for key, value in arguments.items():
        if isinstance(value, str):
            # Strip nested markdown code block tags
            cleaned = re.sub(r"^```[a-zA-Z0-9-]*\n?", "", value)
            cleaned = re.sub(r"\n?```$", "", cleaned)
            # Remove UI artifacts
            cleaned = re.sub(UI_CLEANUP_REGEX, '', cleaned, flags=re.IGNORECASE | re.MULTILINE)
            arguments[key] = cleaned.strip()
    return arguments

# ==========================
# DOM Extraction (optimized)
# ==========================
DOM_EXTRACT_SCRIPT = """
(function() {
    // Use a more precise selector
    const selectors = ['.ds-markdown', '.prose', '.markdown-body'];
    let targetDiv = null;
    for (const sel of selectors) {
        const divs = document.querySelectorAll(sel);
        if (divs.length > 0) {
            targetDiv = divs[divs.length - 1];
            break;
        }
    }
    if (!targetDiv) return '';

    // Direct text extraction, no cloning
    const walker = document.createTreeWalker(
        targetDiv,
        NodeFilter.SHOW_TEXT,
        {
            acceptNode: function(node) {
                // Skip nodes that are inside junk elements
                if (node.parentElement.closest('div[class*="header"], div[class*="toolbar"], button, svg')) {
                    return NodeFilter.FILTER_REJECT;
                }
                return NodeFilter.FILTER_ACCEPT;
            }
        }
    );
    let text = [];
    let node;
    while (node = walker.nextNode()) {
        text.push(node.nodeValue);
    }
    return text.join('').trim();
})();
"""

def extract_clean_dom(driver) -> str:
    return driver.execute_script(DOM_EXTRACT_SCRIPT)

# ==========================
# FastAPI App
# ==========================
app = FastAPI(title="DeepSeek Agent API (v5 - Performance Optimized)")

@app.get("/v1/models")
def get_models():
    return {
        "object": "list",
        "data": [{"id": "deepseek-web", "object": "model", "created": int(time.time()), "owned_by": "custom"}]
    }

@app.post("/v1/chat/completions")
async def chat_completions(req: ChatCompletionRequest):
    # Quick path for title generation
    if req.messages:
        last_msg = str(req.messages[-1].content).lower()
        if "title" in last_msg and ("conversation" in last_msg or "short" in last_msg) and len(last_msg) < 300:
            return await _handle_title_request(req)

    # Acquire browser from pool
    try:
        browser = await pool.acquire()
    except TimeoutError:
        raise HTTPException(status_code=503, detail="No browser instance available")

    try:
        # Run browser interaction in thread pool
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            pool._executor,
            _process_request_sync,
            browser,
            req
        )
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        pool.release(browser)

async def _handle_title_request(req: ChatCompletionRequest):
    dummy_title = "Agent Session"
    final_response = {
        "id": f"chatcmpl-{uuid.uuid4().hex}",
        "object": "chat.completion",
        "created": int(time.time()),
        "model": req.model,
        "choices": [{
            "index": 0,
            "message": {"role": "assistant", "content": dummy_title},
            "finish_reason": "stop"
        }]
    }
    if req.stream:
        return StreamingResponse(_stream_title(dummy_title, final_response, req.model), media_type="text/event-stream")
    return final_response

def _stream_title(dummy_title, final_response, model):
    yield f"data: {json.dumps({'id': final_response['id'], 'object': 'chat.completion.chunk', 'created': final_response['created'], 'model': model, 'choices': [{'index': 0, 'delta': {'role': 'assistant', 'content': dummy_title}, 'finish_reason': None}]})}\n\n"
    yield f"data: {json.dumps({'id': final_response['id'], 'object': 'chat.completion.chunk', 'created': final_response['created'], 'model': model, 'choices': [{'index': 0, 'delta': {}, 'finish_reason': 'stop'}]})}\n\n"
    yield "data: [DONE]\n\n"

def _process_request_sync(browser: BrowserInstance, req: ChatCompletionRequest):
    driver = browser.driver
    structured_prompt = build_prompt(req.messages, req.tools)

    # Find and clear textarea
    textarea = driver.find_element(By.CSS_SELECTOR, 'textarea[placeholder="Message DeepSeek"]')
    textarea.click()
    modifier = Keys.COMMAND if sys.platform == 'darwin' else Keys.CONTROL
    textarea.send_keys(modifier + "a")
    textarea.send_keys(Keys.DELETE)

    # Set new prompt
    driver.execute_script("arguments[0].value = arguments[1];", textarea, structured_prompt)
    textarea.send_keys(Keys.SPACE)
    textarea.send_keys(Keys.BACKSPACE)

    # Start generation
    driver.execute_script("window._deepseekStreamFinished = false;")
    textarea.send_keys(Keys.ENTER)

    print(f"\n⚡ Browser {browser.id}: Generation started...")

    # Wait for completion
    start_time = time.time()
    while True:
        if driver.execute_script("return window._deepseekStreamFinished;"):
            break
        if time.time() - start_time > REQUEST_TIMEOUT:
            raise HTTPException(status_code=504, detail="Timeout waiting for completion")
        time.sleep(0.25)  # Reduced polling frequency

    # Small delay to ensure DOM is updated
    time.sleep(0.5)

    # Extract clean text
    clean_text = extract_clean_dom(driver)
    print(f"✅ Browser {browser.id}: Output length {len(clean_text)}")

    # Clean UI artifacts
    clean_text = re.sub(UI_CLEANUP_REGEX, '', clean_text, flags=re.IGNORECASE | re.MULTILINE).strip()

    # Extract and parse JSON
    json_block = extract_json(clean_text)
    message_payload = {"role": "assistant"}
    finish_reason = "stop"

    if json_block:
        try:
            # Use json_repair as fallback, but try standard loads first
            try:
                parsed = json.loads(json_block)
            except json.JSONDecodeError:
                parsed = json_repair.loads(json_block)

            validated = StructuredResponse(**parsed)

            if validated.tool_name and validated.tool_name.lower() != "null":
                message_payload["content"] = None
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
            print(f"⚠️ Browser {browser.id}: JSON parsing failed: {e}")
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
        "usage": {"prompt_tokens": len(structured_prompt) // 4, "completion_tokens": len(clean_text) // 4, "total_tokens": (len(structured_prompt) + len(clean_text)) // 4}
    }

    if req.stream:
        return StreamingResponse(_stream_response(final_response, message_payload, finish_reason, req.model), media_type="text/event-stream")
    return final_response

def _stream_response(final_response, message_payload, finish_reason, model):
    yield f"data: {json.dumps({'id': final_response['id'], 'object': 'chat.completion.chunk', 'created': final_response['created'], 'model': model, 'choices': [{'index': 0, 'delta': {'role': 'assistant'}, 'finish_reason': None}]})}\n\n"

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

    yield f"data: {json.dumps({'id': final_response['id'], 'object': 'chat.completion.chunk', 'created': final_response['created'], 'model': model, 'choices': [{'index': 0, 'delta': delta_payload, 'finish_reason': None}]})}\n\n"
    yield f"data: {json.dumps({'id': final_response['id'], 'object': 'chat.completion.chunk', 'created': final_response['created'], 'model': model, 'choices': [{'index': 0, 'delta': {}, 'finish_reason': finish_reason}]})}\n\n"
    yield "data: [DONE]\n\n"

@app.on_event("shutdown")
async def shutdown_event():
    await pool.shutdown()

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
