# 🚀 ScrapeSeek: DeepSeek Web-to-API Bridge

[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.110.0-009688.svg?style=flat&logo=FastAPI&logoColor=white)](https://fastapi.tiangolo.com)
[![Selenium](https://img.shields.io/badge/Selenium-4.18.1-43B02A.svg?style=flat&logo=Selenium&logoColor=white)](https://www.selenium.dev/)


ScrapeSeek is a fully autonomous, local API bridge that transforms the **DeepSeek Consumer Web UI** into a **100% OpenAI-compatible API endpoint**. 

Built specifically for Agentic frameworks like **OpenHands, Zed, AutoGen, and CrewAI**, this bridge uses a headless Selenium browser to type prompts, extract DeepThink responses, and translate custom JSON outputs into official OpenAI Tool Calls.

## ✨ Features

* 🔌 **Drop-in OpenAI Replacement:** Perfectly mimics the `chat/completions` endpoint.
* 🛠️ **Native Tool Calling:** Intercepts AI JSON and translates it into strict OpenAI `tool_calls` payloads so your agents can write files and execute bash commands.
* 🌊 **Streaming Support:** Automatically chunks responses into Server-Sent Events (SSE) to prevent strict agent frameworks from timing out.
* 🧠 **Memory & Context:** Compiles entire conversation histories and tool execution results into the browser prompt.
* 🛡️ **Crash-Proof Fallbacks:** Uses permissive Pydantic schemas to absorb massive agent payloads without crashing.

## ⚙️ Installation

**1. Clone the repository**
```bash
git clone [https://github.com/kiruthik2006/scrapeseek.git](https://github.com/kiruthik2006/scrapeseek.git)
cd scrapeseek
2. Create and activate a virtual environment

Bash
python3 -m venv venv
source venv/bin/activate  # On Windows use `venv\Scripts\activate`
3. Install dependencies

Bash
pip install -r requirements.txt
(Note: You must have Google Chrome installed on your machine for the webdriver to function).

🚀 Usage
Start the FastAPI server:

Bash
uvicorn api:app --host 0.0.0.0 --port 8000
Upon booting, a Chrome browser will launch. Log into your DeepSeek account manually the first time. Once you see the "Message DeepSeek" textarea, the API is ready to accept agent payloads!

🤖 Connecting to OpenHands / Zed
To use this bridge in your favorite AI coding agent, configure your LLM provider settings as follows:

Base URL: http://localhost:8000/v1

Model Name: deepseek-web

API Key: dummy-key (The bridge ignores this, but SDKs require it)

Timeout: Set to 300 seconds (to account for the browser typing speed)

🏗️ How it Works (The Translation Layer)
Agent frameworks demand strict adherence to the OpenAI SDK specification. Because DeepSeek's web UI doesn't natively support OpenAI tool_calls, ScrapeSeek acts as a real-time translator:

It intercepts the OpenHands system tools and injects them into the browser prompt as a JSON schema.

It forces the DeepSeek web model to output raw JSON instead of markdown.

It catches the AI's DOM output, parses it using json_repair, and dynamically formats it back into a standard finish_reason: "tool_calls" payload.

⚠️ Caveats & Limitations
Because this relies on web scraping rather than an official API:

Rate Limits: You are subject to DeepSeek's consumer web rate limits. Heavy agent loops may trigger a "Too many requests" timeout.

Speed: The DOM takes physical time to render. Expect slower response times compared to official APIs.

CAPTCHAs: Unattended long-running agents may eventually hit Cloudflare Turnstile blocks.
