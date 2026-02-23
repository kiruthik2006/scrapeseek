# 🚀 ScrapeSeek: DeepSeek Web-to-API Bridge

[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.110.0-009688.svg?style=flat&logo=FastAPI&logoColor=white)](https://fastapi.tiangolo.com)
[![Selenium](https://img.shields.io/badge/Selenium-4.18.1-43B02A.svg?style=flat&logo=Selenium&logoColor=white)](https://www.selenium.dev/)

**ScrapeSeek** is a fully autonomous, local API bridge that transforms the **DeepSeek Consumer Web UI** into a **100% OpenAI-compatible API endpoint**.

Built specifically for agentic frameworks like **OpenHands, Zed, AutoGen, and CrewAI**, this bridge uses a Selenium-controlled browser to submit prompts, capture DeepSeek responses, and translate custom JSON outputs into official OpenAI Tool Calls format.

---

## ✨ Features

| Feature | Description |
|---------|-------------|
| 🔌 **Drop-in OpenAI Replacement** | Perfectly mimics the `/v1/chat/completions` endpoint |
| 🛠️ **Native Tool Calling** | Translates AI JSON into strict OpenAI `tool_calls` payloads |
| 🌊 **Streaming Support** | Server-Sent Events (SSE) streaming to prevent agent timeouts |
| 🧠 **Memory & Context** | Compiles conversation histories and tool results into prompts |
| 🛡️ **Crash-Proof Fallbacks** | Permissive Pydantic schemas absorb unexpected agent payloads |

---

## 📦 Installation

### Prerequisites
- **Python 3.11+**
- **Google Chrome** browser installed

### Step 1: Clone the Repository
```bash
git clone https://github.com/kiruthik2006/scrapeseek.git
cd scrapeseek
```

### Step 2: Create Virtual Environment
```bash
python3 -m venv venv
source venv/bin/activate        # macOS / Linux
# OR
venv\Scripts\activate           # Windows
```

### Step 3: Install Dependencies
```bash
pip install -r requirements.txt
```

---

## 🚀 Quick Start

### Start the API Server

The api_v3.py has auto login features in it. but the env file must be initialised beforehand.

**Option A: Using uvicorn (recommended)**
```bash
uvicorn api_v2:app --host 0.0.0.0 --port 8000
```

**Option B: Run directly**
```bash
python api.py
```

When the server starts, a Chrome browser window will launch automatically. **Log into your DeepSeek account manually on the first run.** Once you see the "Message DeepSeek" textarea, the API is ready to accept requests.

### Verify the Connection
```bash
curl http://localhost:8000/v1/models
```

Expected response:
```json
{
  "object": "list",
  "data": [
    {
      "id": "deepseek-web",
      "object": "model",
      "created": 1234567890,
      "owned_by": "custom"
    }
  ]
}
```

---

## 🤖 Connecting to AI Agents

Configure your agentic framework's LLM provider settings:

| Setting | Value |
|---------|-------|
| **Base URL** | `http://localhost:8000/v1` |
| **Model Name** | `deepseek-web` |
| **API Key** | `dummy-key` (ignored by bridge, but required by SDKs) |
| **Timeout** | `300` seconds (accounts for browser typing speed) |

### Example: OpenHands Configuration
```yaml
LLM_CONFIG:
  model: "deepseek-web"
  api_key: "dummy-key"
  base_url: "http://localhost:8000/v1"
  timeout: 300
```

---

## 🏗️ How It Works

ScrapeSeek acts as a **real-time translator** between agentic frameworks and DeepSeek's web UI:

```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│  Agent Framework │────▶│   ScrapeSeek    │────▶│  DeepSeek Web   │
│  (OpenAI SDK)   │◀────│    (Bridge)     │◀────│    (Browser)    │
└─────────────────┘     └─────────────────┘     └─────────────────┘
        │                       │                       │
   OpenAI API            DOM Scraping /           Web UI Response
   Compatible            XHR Interception
```

### The Translation Pipeline

1. **Receive Request** → Accepts standard OpenAI `chat/completions` payload
2. **Inject Tools** → Converts OpenAI tool definitions into JSON schema in the prompt
3. **Submit to UI** → Types the prompt into DeepSeek's textarea via Selenium
4. **Capture Response** → Waits for generation completion, extracts output
5. **Parse JSON** → Uses `json_repair` to handle malformed AI JSON
6. **Format Output** → Translates into OpenAI-compatible response with `tool_calls`

---

## 📁 API Versions Explained

ScrapeSeek provides two API implementations with different response detection strategies:

### `api.py` — DOM Polling (Stable)

**Detection Method:** Polls the DOM for new `.ds-markdown` elements and waits for text stabilization.

**How it works:**
1. Submits prompt to DeepSeek textarea
2. Polls for new response containers every 0.5 seconds
3. Monitors text length every 0.25 seconds
4. Declares completion when text hasn't changed for 5 seconds (20 stable polls)

**Characteristics:**
| Aspect | Detail |
|--------|--------|
| ✅ Reliability | High — works even if XHR behavior changes |
| ⏱️ Latency | Higher — waits 5 seconds after completion |
| 🎯 Use Case | General use, maximum compatibility |

```bash
uvicorn api:app --host 0.0.0.0 --port 8000
```

---

### `api_v2.py` — XHR Interception (Fast)

**Detection Method:** Injects JavaScript to intercept `XMLHttpRequest` calls and detects when DeepSeek's streaming endpoint completes.

**How it works:**
1. Injects XHR interceptor via Chrome DevTools Protocol (CDP)
2. Intercepts all POST requests to `/chat/completion`
3. Sets `window._deepseekStreamFinished = true` when XHR reaches `readyState 4`
4. Polls this flag instead of DOM text stability
5. Includes argument sanitization to remove UI artifacts

**Additional Features:**
- **Context Compression:** Only sends last 3 messages to avoid overwhelming the UI
- **Title Interception:** Short-circuits DeepSeek's auto-title generation requests
- **UI Artifact Cleaning:** Strips "Copy" and "Download" button text from responses
- **Greedy JSON Extraction:** Finds first `{` and last `}` for robust parsing

**Characteristics:**
| Aspect | Detail |
|--------|--------|
| ✅ Speed | Faster — detects completion immediately after XHR finishes |
| ⚠️ Fragility | May break if DeepSeek changes their API endpoints |
| 🎯 Use Case | Production use, lower latency requirements |

```bash
uvicorn api_v2:app --host 0.0.0.0 --port 8000
```

---

### Version Comparison

| Feature | `api.py` | `api_v2.py` |
|---------|----------|-------------|
| Completion Detection | DOM text stability | XHR readyState |
| Post-completion Delay | ~5 seconds | ~1 second |
| Context Handling | Full history | Last 3 messages |
| Artifact Cleaning | Basic | Advanced regex |
| Title Request Handling | Standard | Intercepted |
| Recommended For | Testing, stability | Production, speed |

---

## 🧪 Testing the API

### Basic Chat Completion
```bash
curl -X POST http://localhost:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "deepseek-web",
    "messages": [{"role": "user", "content": "Hello, world!"}]
  }'
```

### With Streaming
```bash
curl -X POST http://localhost:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "deepseek-web",
    "messages": [{"role": "user", "content": "Count to 10"}],
    "stream": true
  }'
```

### With Tool Calling
```bash
curl -X POST http://localhost:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "deepseek-web",
    "messages": [{"role": "user", "content": "Create a file called hello.txt"}],
    "tools": [
      {
        "type": "function",
        "function": {
          "name": "write_file",
          "parameters": {
            "type": "object",
            "properties": {
              "path": {"type": "string"},
              "content": {"type": "string"}
            }
          }
        }
      }
    ]
  }'
```

---

## ⚠️ Limitations & Caveats

| Limitation | Description |
|------------|-------------|
| **Rate Limits** | Subject to DeepSeek's consumer web rate limits |
| **Speed** | DOM/XHR detection is slower than native API |
| **CAPTCHAs** | Long-running sessions may trigger Cloudflare Turnstile |
| **Session Required** | Requires manual login on first run |
| **Single Session** | Only one browser instance; requests are serialized |

---

## 📄 License

MIT License — use freely for personal and commercial projects.

---

## 🤝 Contributing

Contributions welcome! Please open an issue or submit a pull request.

1. Fork the repository
2. Create your feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request
