#!/usr/bin/env python3
# main.py - Orangecarrier monitor (Fixed & Stable Firefox version)

import os
import re
import time
import pickle
import threading
import requests
from datetime import datetime
from pathlib import Path

from selenium import webdriver
from selenium.webdriver.firefox.options import Options
from selenium.webdriver.firefox.service import Service as FirefoxService
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, WebDriverException, StaleElementReferenceException

import phonenumbers
import pycountry
import config

# -------------- Globals --------------
Path(config.DOWNLOAD_FOLDER).mkdir(parents=True, exist_ok=True)
COOKIE_PATH = getattr(config, "COOKIES_FILE", "cookies.pkl")
active_calls = {}
pending_recordings = {}

# -------------- Helpers --------------
def country_to_flag(code):
    return "".join(chr(127397 + ord(c)) for c in code.upper()) if code and len(code) == 2 else "🏳️"

def detect_country(number):
    try:
        digits = re.sub(r"\D", "", number)
        if not digits:
            return "Unknown", "🏳️"
        parsed = phonenumbers.parse("+" + digits)
        region = phonenumbers.region_code_for_number(parsed)
        country = pycountry.countries.get(alpha_2=region)
        if not region or not country:
            return "Unknown", "🏳️"
        return country.name, country_to_flag(region)
    except Exception:
        return "Unknown", "🏳️"

def mask_number(num):
    digits = re.sub(r"\D", "", num)
    return digits[:4] + "****" + digits[-3:] if len(digits) > 7 else num

# -------------- Telegram --------------
def send_message(text):
    try:
        res = requests.post(
            f"https://api.telegram.org/bot{config.BOT_TOKEN}/sendMessage",
            json={"chat_id": config.CHAT_ID, "text": text, "parse_mode": "Markdown"},
            timeout=30,
        )
        if res.ok:
            return res.json().get("result", {}).get("message_id")
        else:
            print("[Telegram] send failed:", res.text)
    except Exception as e:
        print("[Telegram] Error:", e)
    return None

def edit_message(msg_id, text):
    try:
        requests.post(
            f"https://api.telegram.org/bot{config.BOT_TOKEN}/editMessageText",
            json={"chat_id": config.CHAT_ID, "message_id": msg_id, "text": text, "parse_mode": "Markdown"},
            timeout=10,
        )
    except:
        pass

def delete_message(msg_id):
    try:
        requests.post(
            f"https://api.telegram.org/bot{config.BOT_TOKEN}/deleteMessage",
            data={"chat_id": config.CHAT_ID, "message_id": msg_id},
            timeout=5,
        )
    except:
        pass

def send_voice(path, caption):
    try:
        if os.path.getsize(path) < 500:
            raise Exception("File too small")
        with open(path, "rb") as v:
            files = {"voice": v}
            data = {"chat_id": config.CHAT_ID, "caption": caption, "parse_mode": "HTML"}
            r = requests.post(f"https://api.telegram.org/bot{config.BOT_TOKEN}/sendVoice", data=data, files=files)
            return r.ok
    except Exception as e:
        print("[Voice Upload Error]", e)
    return False

# -------------- Cookies --------------
def save_cookies(driver):
    try:
        with open(COOKIE_PATH, "wb") as f:
            pickle.dump(driver.get_cookies(), f)
        print(f"[✅] Cookies saved ({COOKIE_PATH})")
    except Exception as e:
        print("[❌] Save cookies failed:", e)

def load_cookies(driver):
    if not os.path.exists(COOKIE_PATH):
        print("[ℹ️] No cookies found.")
        return
    try:
        driver.get(config.BASE_URL)
        time.sleep(1)
        with open(COOKIE_PATH, "rb") as f:
            cookies = pickle.load(f)
        for c in cookies:
            try:
                driver.add_cookie(c)
            except:
                pass
        print(f"[✅] Cookies loaded ({len(cookies)})")
    except Exception as e:
        print("[❌] Load cookies failed:", e)

# -------------- Recording --------------
def construct_recording_url(did, uuid):
    return f"{config.CALL_URL.rstrip('/')}/sound?did={did}&uuid={uuid}"

def download_recording(driver, did, uuid, out):
    try:
        url = construct_recording_url(did, uuid)
        session = requests.Session()
        for c in driver.get_cookies():
            session.cookies.set(c["name"], c["value"])
        headers = {"User-Agent": config.USER_AGENT}
        for i in range(3):
            r = session.get(url, headers=headers, stream=True, timeout=20)
            if r.status_code == 200 and int(r.headers.get("Content-Length", 0)) > 1000:
                with open(out, "wb") as f:
                    for chunk in r.iter_content(8192):
                        f.write(chunk)
                print(f"[✅] Recording saved: {out}")
                return True
            time.sleep(3)
        return False
    except Exception as e:
        print("[❌] Download failed:", e)
        return False

# -------------- Extract Calls --------------
def extract_calls(driver):
    global active_calls, pending_recordings
    try:
        table = driver.find_element(By.ID, "LiveCalls")
        rows = table.find_elements(By.TAG_NAME, "tr")
        current = set()

        for r in rows:
            rid = r.get_attribute("id")
            if not rid:
                continue
            tds = r.find_elements(By.TAG_NAME, "td")
            if len(tds) < 2:
                continue
            did = re.sub(r"\D", "", tds[1].text)
            if not did:
                continue
            current.add(rid)
            if rid not in active_calls:
                country, flag = detect_country(did)
                masked = mask_number(did)
                msg = send_message(f"📞 New call from {flag} {masked}\nWaiting for completion...")
                active_calls[rid] = {"did": did, "flag": flag, "country": country, "msg": msg, "time": datetime.now()}

        # detect ended calls
        ended = [cid for cid in active_calls if cid not in current]
        for cid in ended:
            info = active_calls.pop(cid)
            pending_recordings[cid] = {**info, "checks": 0, "done": False, "start": datetime.now()}
            print(f"[✅] Call completed: {info['did']}")
    except Exception:
        pass

# -------------- Pending Recordings --------------
def process_pending(driver):
    global pending_recordings
    now = datetime.now()
    for cid, info in list(pending_recordings.items()):
        info["checks"] += 1
        if info["checks"] > 10:
            send_message(f"❌ Recording timeout for {info['flag']} {info['did']}")
            del pending_recordings[cid]
            continue

        out = os.path.join(config.DOWNLOAD_FOLDER, f"{info['did']}_{int(time.time())}.mp3")
        if download_recording(driver, info["did"], cid, out):
            delete_message(info["msg"])
            caption = (
                f"🔥 NEW CALL RECORDING 🔥\n\n"
                f"{info['flag']} {info['country']}\n📞 {info['did']}\n🕒 {info['time'].strftime('%Y-%m-%d %I:%M:%S %p')}"
            )
            send_voice(out, caption)
            del pending_recordings[cid]

# -------------- Firefox Init --------------
def init_driver():
    options = Options()
    options.headless = getattr(config, "HEADLESS", False)
    options.set_preference("dom.webnotifications.enabled", False)
    options.set_preference("media.volume_scale", "0.0")
    options.set_preference("general.useragent.override", config.USER_AGENT)
    profile_dir = getattr(config, "USER_DATA_DIR", "firefox_profile")
    os.makedirs(profile_dir, exist_ok=True)
    options.profile = os.path.abspath(profile_dir)

    # Proxy support
    if getattr(config, "PROXY", None):
        m = re.match(r"^(?:http://)?([^:]+):(\d+)$", config.PROXY)
        if m:
            host, port = m.groups()
            options.set_preference("network.proxy.type", 1)
            options.set_preference("network.proxy.http", host)
            options.set_preference("network.proxy.http_port", int(port))
            options.set_preference("network.proxy.ssl", host)
            options.set_preference("network.proxy.ssl_port", int(port))
            options.set_preference("network.proxy.no_proxies_on", "")

    path = getattr(config, "GECKODRIVER_PATH", "/usr/local/bin/geckodriver")
    driver = webdriver.Firefox(service=FirefoxService(path), options=options)
    driver.set_window_size(1366, 768)
    return driver

# -------------- Main --------------
def main():
    driver = None
    try:
        driver = init_driver()
        load_cookies(driver)
        driver.get(config.LOGIN_URL)
        print("🔐 Please login manually if needed...")
        WebDriverWait(driver, 600).until(lambda d: config.BASE_URL in d.current_url)
        save_cookies(driver)

        driver.get(config.CALL_URL)
        print("[✅] Monitoring started...")
        last_check = time.time()

        while True:
            extract_calls(driver)
            if time.time() - last_check > 15:
                process_pending(driver)
                last_check = time.time()
            time.sleep(getattr(config, "CHECK_INTERVAL", 3))
    except KeyboardInterrupt:
        print("\n[🛑] Stopped by user.")
    except Exception as e:
        print("[💥] Fatal error:", e)
    finally:
        if driver:
            driver.quit()
        print("[*] Monitor stopped.")

if __name__ == "__main__":
    main()
