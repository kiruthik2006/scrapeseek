from selenium import webdriver
import time
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.support import expected_conditions as EC

print("Launching browser...")

driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()))
driver.get("https://chat.deepseek.com")  # adjust if needed

wait = WebDriverWait(driver, 60)

print("Waiting for login + textarea...")

textarea = wait.until(
    EC.presence_of_element_located(
        (By.CSS_SELECTOR, 'textarea[placeholder="Message DeepSeek"]')
    )
)

print("Connected. Type below. (type 'exit' to quit)\n")

while True:
    user_input = input("You: ")

    if user_input.lower() == "exit":
        break

    # Count existing AI responses
    existing_responses = driver.find_elements(By.CSS_SELECTOR, "div.ds-markdown")
    existing_count = len(existing_responses)

    textarea = driver.find_element(
        By.CSS_SELECTOR,
        'textarea[placeholder="Message DeepSeek"]'
    )

    textarea.send_keys(user_input)
    textarea.send_keys(Keys.ENTER)

    print("\nWaiting for AI response...\n")

    # Wait until new response container appears
    wait.until(
        lambda d: len(d.find_elements(By.CSS_SELECTOR, "div.ds-markdown")) > existing_count
    )

    updated_responses = driver.find_elements(By.CSS_SELECTOR, "div.ds-markdown")
    latest_container = updated_responses[-1]

    print("\nAI:\n")

    previous_text = ""
    stable_counter = 0

    while True:
        current_text = latest_container.text

        # If text grew, print only new part
        if len(current_text) > len(previous_text):
            new_part = current_text[len(previous_text):]
            print(new_part, end="", flush=True)
            previous_text = current_text
            stable_counter = 0
        else:
            stable_counter += 1

        # If text hasn't changed for ~2 seconds, assume streaming finished
        if stable_counter >= 6:
            break

        time.sleep(0.3)

    print("\n" + "-" * 50 + "\n")

driver.quit()
