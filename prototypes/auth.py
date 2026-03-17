import os
import time
from dotenv import load_dotenv
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import undetected_chromedriver as uc

# Load environment variables from the .env file
load_dotenv()

def setup_and_login():
    # Fetch credentials internally
    email = os.getenv("DS_EMAIL")
    password = os.getenv("DS_PASSWORD")

    if not email or not password:
        raise ValueError("❌ Credentials missing! Please set DS_EMAIL and DS_PASSWORD in your .env file.")

    print("🚀 Launching Isolated Stealth Chrome...")

    options = uc.ChromeOptions()

    # 1️⃣ THE MAC PROFILE FIX: Force a completely isolated temporary profile
    profile_path = os.path.join(os.getcwd(), "stealth_profile")
    options.add_argument(f"--user-data-dir={profile_path}")
    options.add_argument("--no-first-run")
    options.add_argument("--no-default-browser-check")

    # Initialize Undetected Chromedriver
    driver = uc.Chrome(options=options, version_main=145)

    # ---------------------------------------------------------
    # 💉 INJECT SMART OMNI-WIRETAP (FETCH + XHR)
    # ---------------------------------------------------------
    omni_interceptor_js = """
    console.log("🟢 [PROBE] Smart Omni-Wiretap injected.");

    // 1. Hook Modern Fetch API (What DeepSeek uses now)
    const originalFetch = window.fetch;
    window.fetch = async function(...args) {
        const url = args[0];
        const options = args[1] || {};
        const method = (options.method || 'GET').toUpperCase();

        if (typeof url === 'string' && method === 'POST' && url.includes('chat')) {
            const response = await originalFetch(...args);

            // 🔥 THE FIX: Check if the response is ACTUALLY the AI text stream!
            const contentType = response.headers.get('content-type') || '';
            if (contentType.includes('event-stream') || contentType.includes('x-ndjson')) {
                console.log("🕸️ [FETCH WIRETAP] Locked onto AI text stream:", url);
                window._deepseekStreamFinished = false;
                window._deepseekRawResponse = "";

                const clone = response.clone();
                const reader = clone.body.getReader();
                const decoder = new TextDecoder("utf-8");

                async function pump() {
                    const { done, value } = await reader.read();
                    if (value) {
                        window._deepseekRawResponse += decoder.decode(value, {stream: true});
                    }
                    if (done) {
                        console.log("🕸️ [FETCH WIRETAP] Stream Finished.");
                        window._deepseekStreamFinished = true;
                        return;
                    }
                    pump();
                }
                pump();
            } else {
                console.log("🕸️ [FETCH WIRETAP] Ignored background request to:", url);
            }
            return response;
        }
        return originalFetch(...args);
    };

    // 2. Hook Legacy XHR (Fallback)
    const originalXHR = window.XMLHttpRequest;
    window.XMLHttpRequest = function() {
        const xhr = new originalXHR();
        const originalOpen = xhr.open;
        xhr.open = function(method, url, ...args) {
            const upperMethod = method.toUpperCase();
            if (typeof url === 'string' && upperMethod === 'POST' && url.includes('chat')) {
                const originalOnReadyStateChange = xhr.onreadystatechange;
                xhr.onreadystatechange = function() {
                    const contentType = xhr.getResponseHeader('Content-Type') || '';
                    if (contentType.includes('event-stream') || contentType.includes('x-ndjson')) {
                        if (xhr.readyState === 2) {
                            console.log("🕸️ [XHR WIRETAP] Locked onto AI text stream:", url);
                            window._deepseekStreamFinished = false;
                            window._deepseekRawResponse = "";
                        }
                        if (xhr.readyState > 2) {
                            window._deepseekRawResponse = xhr.responseText;
                        }
                        if (xhr.readyState === 4) {
                            console.log("🕸️ [XHR WIRETAP] Stream Finished.");
                            window._deepseekStreamFinished = true;
                        }
                    }
                    if (originalOnReadyStateChange) originalOnReadyStateChange.apply(this, arguments);
                };
            }
            return originalOpen.apply(this, [method, url, ...args]);
        };
        return xhr;
    };
    """
    driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {"source": omni_interceptor_js})

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

        print("✅ Login Successful & Omni-Wiretap Ready!")
        return driver

    except Exception as e:
        print(f"❌ Login failed! Error: {str(e)}")
        raise
