from selenium import webdriver
import time
import json
import json_repair  # 🔥 Auto-fixes broken LLM JSON
import re
import sys
from typing import Optional, Dict
from pydantic import BaseModel, ValidationError

from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager


# ==========================
# 🔒 Structured Output Schema
# ==========================

class StructuredResponse(BaseModel):
    tool_name: Optional[str] = None
    arguments: Optional[Dict] = None
    response: Optional[str] = None


def build_prompt(user_text: str) -> str:
    """
    Clean deterministic JSON contract without identity confusion.
    """
    return f"""
Respond ONLY with valid JSON.

Do NOT explain.
Do NOT describe yourself.
Do NOT output markdown.
Do NOT output text outside JSON.

JSON schema:

{{
  "tool_name": string | null,
  "arguments": object | null,
  "response": string | null
}}

If no tool is required:
{{
  "tool_name": null,
  "arguments": null,
  "response": "<answer>"
}}

User message:
{user_text}
""".strip()


def extract_json(text: str) -> Optional[str]:
    match = re.search(r"\{[\s\S]*?\}", text)
    return match.group(0) if match else None


# ==========================
# 🚀 Browser Setup
# ==========================

print("Launching browser...")

driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()))
driver.get("https://chat.deepseek.com")

wait = WebDriverWait(driver, 60)

print("Waiting for login + textarea...")

wait.until(
    EC.presence_of_element_located(
        (By.CSS_SELECTOR, 'textarea[placeholder="Message DeepSeek"]')
    )
)

print("Connected. Ready for input.\n")


# ==========================
# 🔁 Main Loop
# ==========================

while True:
    print("\n" + "="*50)
    print("🤖 You: (Type/Paste your message. Press Enter, type 'EOF' on a new line, and press Enter again to send. Type 'exit' to quit)")

    # 🎯 Multi-line Input Reader
    lines = []
    while True:
        try:
            line = input()
        except EOFError:
            break

        if line.strip().upper() == "EOF":
            break
        if line.strip().lower() == "exit" and len(lines) == 0:
            print("Exiting...")
            driver.quit()
            sys.exit()

        lines.append(line)

    user_input = "\n".join(lines)

    if not user_input.strip():
        continue

    structured_prompt = build_prompt(user_input)

    # 🎯 Count existing valid responses (ignoring DeepThink containers)
    answer_xpath = "//div[contains(@class, 'ds-markdown') and not(ancestor::div[contains(@class, 'ds-think-content')])]"
    existing_responses = driver.find_elements(By.XPATH, answer_xpath)
    existing_count = len(existing_responses)

    textarea = driver.find_element(
        By.CSS_SELECTOR,
        'textarea[placeholder="Message DeepSeek"]'
    )

    # 🔥 CLEAR TEXTAREA PROPERLY (OS-Agnostic)
    textarea.click()
    modifier = Keys.COMMAND if sys.platform == 'darwin' else Keys.CONTROL
    textarea.send_keys(modifier + "a")
    textarea.send_keys(Keys.DELETE)

    # 🔥 FAST INJECTION: Inject the multiline string instantly via JavaScript
    driver.execute_script("arguments[0].value = arguments[1];", textarea, structured_prompt)

    # Trigger React/Vue's event listener so the app registers the text
    textarea.send_keys(Keys.SPACE)
    textarea.send_keys(Keys.BACKSPACE)

    # Submit
    textarea.send_keys(Keys.ENTER)

    print("\n⏳ Waiting for AI to finish thinking and start responding...\n")

    # 🎯 Rock-solid wait loop using JS to filter out thought containers
    latest_container = None
    while True:
        markdown_elements = driver.find_elements(By.CSS_SELECTOR, "div.ds-markdown")

        valid_answers = []
        for el in markdown_elements:
            # Use JavaScript to accurately check if this element is inside a thought block
            is_thought = driver.execute_script(
                "return arguments[0].closest('.ds-think-content') !== null;", el
            )
            if not is_thought:
                valid_answers.append(el)

        # If we have a new valid answer box that isn't a thought box, lock onto it
        if len(valid_answers) > existing_count:
            latest_container = valid_answers[-1]
            break

        time.sleep(0.5)

    print("📡 AI (streaming):\n")

    previous_text = ""
    stable_counter = 0

    # 🎯 Stream the response
    while True:
        current_text = latest_container.text

        if len(current_text) > len(previous_text):
            new_part = current_text[len(previous_text):]
            print(new_part, end="", flush=True)
            previous_text = current_text
            stable_counter = 0
        else:
            stable_counter += 1

        # Buffer for DeepThink pauses (20 * 0.25s = 5 seconds of silence before closing)
        if stable_counter >= 20:
            break

        time.sleep(0.25)

    print("\n\n" + "-" * 50 + "\n")

    # ==========================
    # 🧠 Structured Validation
    # ==========================

    print("🛠️ Validating and repairing structured output...\n")

    json_block = extract_json(previous_text)

    if not json_block:
        print("❌ No JSON detected.\n")
        continue

    try:
        # 🔥 MAGIC: json_repair fixes rogue brackets, unescaped quotes, etc.
        parsed = json_repair.loads(json_block)

        # Pydantic validation
        validated = StructuredResponse(**parsed)

        print("✅ Structured output validated:\n")
        print(validated)
        print("\n" + "=" * 50 + "\n")

    except Exception as e:
        print("❌ Validation or Repair failed:")
        print(e)
        print("\n" + "=" * 50 + "\n")
