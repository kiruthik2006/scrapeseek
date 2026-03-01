import os
import time
from dotenv import load_dotenv
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager

# Load environment variables from the .env file
load_dotenv()

def setup_and_login():
    email = os.getenv("DS_EMAIL")
    password = os.getenv("DS_PASSWORD")

    if not email or not password:
        raise ValueError("❌ Credentials missing! Please set DS_EMAIL and DS_PASSWORD in your .env file.")

    print("🚀 Launching Chrome and preparing stealth proxy...")
    options = webdriver.ChromeOptions()
    # options.add_argument("--headless")
    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)

    # ---------------------------------------------------------
    # 💉 INJECT STEALTH XHR PROXY (Upgraded to capture payload)
    # ---------------------------------------------------------
    xhr_interceptor_js = """
    console.log("🟢 [PROBE] Stealth XHR Proxy injected.");
    const originalXHR = window.XMLHttpRequest;
    window.XMLHttpRequest = function() {
        const xhr = new originalXHR();
        const originalOpen = xhr.open;
        xhr.open = function(method, url, ...args) {
            if (typeof url === 'string' && url.includes('/chat/completion') && method.toUpperCase() === 'POST') {
                window._deepseekStreamFinished = false;
                window._deepseekRawResponse = "";
                xhr.addEventListener('readystatechange', function() {
                    if (xhr.readyState === 4) {
                        // CAPTURE THE RAW DATA BEFORE THE BROWSER MANGLES IT!
                        window._deepseekRawResponse = xhr.responseText;
                        window._deepseekStreamFinished = true;
                    }
                });
            }
            return originalOpen.apply(this, [method, url, ...args]);
        };
        return xhr;
    };
    """
    driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {"source": xhr_interceptor_js})

    print("🌐 Navigating to DeepSeek Sign-In...")
    driver.get("https://chat.deepseek.com/sign_in")
    wait = WebDriverWait(driver, 30)

    try:
        print("🔐 Attempting automated login...")
        email_selector = 'input[placeholder="Phone number / email address"]'
        email_input = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, email_selector)))
        email_input.clear()
        email_input.send_keys(email)
        time.sleep(0.5)

        password_selector = 'input[placeholder="Password"]'
        password_input = driver.find_element(By.CSS_SELECTOR, password_selector)
        password_input.clear()
        password_input.send_keys(password)
        time.sleep(0.5)

        print("🚪 Clicking the Login button...")
        login_button_xpath = "//button[span[text()='Log in']]"
        login_button = wait.until(EC.element_to_be_clickable((By.XPATH, login_button_xpath)))
        login_button.click()

        print("⏳ Waiting for chat interface to load...")
        print("   (⚠️ If a Cloudflare 'Verify you are human' box appears, please click it manually!)")
        wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, 'textarea[placeholder="Message DeepSeek"]')))

        print("✅ Login Successful & Network Wiretap Active!")
        return driver

    except Exception as e:
        print(f"❌ Login failed! Error: {str(e)}")
        raise
