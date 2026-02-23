# AGENTS.md - Coding Agent Guidelines for ScrapeSeek

## Project Overview

ScrapeSeek is a Python FastAPI application that transforms DeepSeek's consumer web UI into an OpenAI-compatible API endpoint. It uses Selenium for browser automation and acts as a bridge for agentic frameworks (OpenHands, Zed, AutoGen, CrewAI).

## Build, Run, and Test Commands

### Setup
```bash
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### Run the Server
```bash
# Primary method (recommended)
uvicorn api:app --host 0.0.0.0 --port 8000

# Alternative: run directly
python api.py

# For v2 API (enhanced version with XHR proxy)
python api_v2.py
# or
uvicorn api_v2:app --host 0.0.0.0 --port 8000
```

### Testing
```bash
# No test suite currently exists. To test manually:
curl http://localhost:8000/v1/models

# Test chat completions endpoint
curl -X POST http://localhost:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model": "deepseek-web", "messages": [{"role": "user", "content": "Hello"}]}'
```

### Linting and Type Checking
```bash
# If adding linting, use ruff or flake8:
pip install ruff
ruff check .

# Type checking with mypy:
pip install mypy
mypy api.py --ignore-missing-imports
```

## Code Style Guidelines

### Imports Organization
Imports are ordered: standard library → third-party frameworks → Selenium. No blank line separation between groups:
```python
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
```

### Type Hints
- Use explicit type hints on all function parameters and return types
- Import types from `typing` module: `Optional`, `Dict`, `List`, `Any`
- Use `Optional[T]` for nullable fields, not `T | None`
- Pydantic models use `Any` for fields that may receive varied types from agents

```python
def build_prompt(messages: List[Message], tools: Optional[List[Any]]) -> str:
def extract_json(text: str) -> Optional[str]:
def sanitize_arguments(arguments: Dict) -> Dict:
```

### Naming Conventions
- **Functions/Variables:** `snake_case` (e.g., `build_prompt`, `json_block`, `clean_text`)
- **Classes:** `PascalCase` (e.g., `Message`, `ChatCompletionRequest`, `StructuredResponse`)
- **Constants:** `UPPER_SNAKE_CASE` at module level (not currently used)
- **Private functions:** Prefix with underscore if intended as internal

### Pydantic Models Pattern
Always use `extra = "allow"` in Config to prevent crashes from unexpected agent fields:
```python
class Message(BaseModel):
    role: str
    content: Any = None
    name: Optional[str] = None
    tool_call_id: Optional[str] = None
    tool_calls: Optional[List[Any]] = None

    class Config:
        extra = "allow"
```

### Section Headers
Use emoji-prefixed comment blocks to organize large files:
```python
# ==========================
# 🔒 OpenAI Schema Definitions (Agent Compatible)
# ==========================

# ==========================
# ⚙️ Prompt Builder for Agents
# ==========================

# ==========================
# 🚀 Global Browser Setup
# ==========================

# ==========================
# 🌐 FastAPI App
# ==========================
```

### Error Handling
- Wrap endpoint logic in try/except blocks
- Raise `HTTPException` with appropriate status codes for API errors
- Log errors to console with `print()` statements using emoji prefixes (⚠️, 🔥)
- Use fallback values rather than crashing when possible

```python
try:
    # ... processing logic
except Exception as e:
    print(f"⚠️ JSON parsing failed, falling back to raw text. Error: {e}")
    message_payload["content"] = previous_text
```

### Threading and Concurrency
- Use `threading.Lock()` to protect shared resources (browser instance)
- Always use `with lock:` context manager pattern

```python
browser_lock = threading.Lock()

@app.post("/v1/chat/completions")
def chat_completions(req: ChatCompletionRequest):
    with browser_lock:
        # ... browser interactions
```

### Streaming Response Pattern
For SSE (Server-Sent Events) streaming, use generator functions:
```python
def generate_fake_stream():
    yield f"data: {json.dumps({...})}\n\n"
    yield "data: [DONE]\n\n"

return StreamingResponse(generate_fake_stream(), media_type="text/event-stream")
```

### JSON Handling
- Use `json_repair.loads()` instead of `json.loads()` to handle malformed JSON from AI
- Always validate parsed JSON with Pydantic models
- Provide fallback to raw text if parsing fails

### Platform-Specific Code
Handle macOS vs other platforms explicitly:
```python
modifier = Keys.COMMAND if sys.platform == 'darwin' else Keys.CONTROL
```

### Selenium Best Practices
- Use `WebDriverWait` with explicit conditions rather than fixed `time.sleep()` when possible
- Use CSS selectors for element location: `By.CSS_SELECTOR`
- Use `driver.execute_script()` for complex DOM operations
- Clear textareas using keyboard modifiers + delete pattern

### Response ID Generation
Use UUID hex for unique identifiers:
```python
f"chatcmpl-{uuid.uuid4().hex}"
f"call_{uuid.uuid4().hex[:16]}"
```

## File Structure
```
Selena/
├── api.py           # Main API (stable version)
├── api_v2.py        # Enhanced version with XHR proxy and optimizations
├── requirements.txt # Dependencies
├── README.md        # Documentation
├── .gitignore
└── venv/            # Virtual environment (gitignored)
```

## Dependencies
- **fastapi** (0.110.0): Web framework
- **uvicorn** (0.27.1): ASGI server
- **selenium** (4.18.1): Browser automation
- **webdriver-manager** (4.0.1): ChromeDriver management
- **pydantic** (2.5.3): Data validation
- **json-repair** (0.25.1): Malformed JSON repair

## Important Notes
- Chrome browser must be installed for Selenium webdriver
- First run requires manual login to DeepSeek
- Timeout should be set to 300+ seconds for agent clients
- Rate limits apply (consumer web limits)
