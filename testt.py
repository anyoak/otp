# firefox_test.py
import os
import time
import pickle
from pathlib import Path
from selenium import webdriver
from selenium.webdriver.firefox.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.common.exceptions import TimeoutException
import config  # আপনার config.py ফাইল

PROFILE_DIR = "ff_profile"
COOKIES_FILE = "ff_cookies.pkl"

Path(PROFILE_DIR).mkdir(exist_ok=True)

def build_driver():
    options = Options()
    options.headless = False  # Cloudflare জন্য headless না রাখুন
    options.add_argument("--width=1366")
    options.add_argument("--height=768")
    options.set_preference("dom.webdriver.enabled", False)
    options.set_preference("useAutomationExtension", False)

    # Firefox profile path
    options.profile = os.path.abspath(PROFILE_DIR)

    driver = webdriver.Firefox(options=options)  # geckodriver PATH এ থাকলে executable_path দরকার নেই
    return driver

def load_cookies(driver):
    if not os.path.exists(COOKIES_FILE):
        print("[i] No cookies file found.")
        return
    try:
        driver.get(config.BASE_URL)
        time.sleep(1)
        with open(COOKIES_FILE, "rb") as f:
            cookies = pickle.load(f)
        added = 0
        for c in cookies:
            cookie = {k: c.get(k) for k in ("name","value","path","domain","secure","expiry") if c.get(k) is not None}
            try:
                driver.add_cookie(cookie)
                added += 1
            except Exception:
                pass
        print(f"[+] Loaded {added} cookies.")
    except Exception as e:
        print("[!] load_cookies error:", e)

def save_cookies(driver):
    try:
        cookies = driver.get_cookies()
        with open(COOKIES_FILE, "wb") as f:
            pickle.dump(cookies, f)
        print(f"[+] Saved {len(cookies)} cookies to {COOKIES_FILE}")
    except Exception as e:
        print("[!] save_cookies error:", e)

def wait_for_login(driver, timeout=600):
    print(f"Open page: {config.LOGIN_URL}")
    driver.get(config.LOGIN_URL)
    try:
        WebDriverWait(driver, timeout).until(
            lambda d: d.current_url.startswith(config.BASE_URL) and not d.current_url.startswith(config.LOGIN_URL)
        )
        print("[+] Login successful (URL change detected).")
        return True
    except TimeoutException:
        print("[!] Login wait timed out.")
        return False

def main():
    driver = build_driver()
    try:
        load_cookies(driver)
        driver.get(config.LOGIN_URL)
        print("[i] Browser opened. Solve Cloudflare/login manually if needed.")
        input("Press ENTER after you finish manual login (or after Cloudflare is solved)...")
        save_cookies(driver)
        # Quick verification
        driver.get(config.CALL_URL)
        time.sleep(3)
        print("[i] You can inspect page manually. Current URL:", driver.current_url)
    finally:
        driver.quit()

if __name__ == "__main__":
    main()
