#!/usr/bin/env python3
# main.py - Orangecarrier monitor (undetected-chromedriver + proxy + cookie save/load)
import os
import time
import re
import pickle
import threading
from datetime import datetime
from pathlib import Path

import requests
import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, StaleElementReferenceException, WebDriverException

import phonenumbers
from phonenumbers import region_code_for_number
import pycountry

import config

# ----------------- state & folders -----------------
Path(config.DOWNLOAD_FOLDER).mkdir(parents=True, exist_ok=True)
COOKIE_PATH = getattr(config, "COOKIES_FILE", "cookies.pkl")

active_calls = {}
pending_recordings = {}

# ----------------- utilities -----------------
def country_to_flag(country_code):
    if not country_code or len(country_code) != 2:
        return "🏳️"
    return "".join(chr(127397 + ord(c)) for c in country_code.upper())

def detect_country(number):
    try:
        clean_number = re.sub(r"\D", "", number)
        if not clean_number:
            return "Unknown", "🏳️"
        parsed = phonenumbers.parse("+" + clean_number, None)
        region = region_code_for_number(parsed)
        if not region:
            return "Unknown", "🏳️"
        country = pycountry.countries.get(alpha_2=region)
        if country:
            return country.name, country_to_flag(region)
    except Exception:
        pass
    return "Unknown", "🏳️"

def mask_number(number):
    digits = re.sub(r"\D", "", number)
    if len(digits) > 6:
        return digits[:4] + "****" + digits[-3:]
    return number

# ----------------- Telegram helpers -----------------
def send_message(text):
    try:
        url = f"https://api.telegram.org/bot{config.BOT_TOKEN}/sendMessage"
        payload = {"chat_id": config.CHAT_ID, "text": text, "parse_mode": "Markdown"}
        res = requests.post(url, json=payload, timeout=10)
        if res.ok:
            return res.json().get("result", {}).get("message_id")
    except Exception as e:
        print(f"[❌] Failed to send message: {e}")
    return None

def edit_message_text(msg_id, new_text):
    try:
        url = f"https://api.telegram.org/bot{config.BOT_TOKEN}/editMessageText"
        payload = {"chat_id": config.CHAT_ID, "message_id": msg_id, "text": new_text, "parse_mode": "Markdown"}
        requests.post(url, json=payload, timeout=10)
    except Exception as e:
        print(f"[❌] edit_message_text failed: {e}")

def delete_message(msg_id):
    try:
        url = f"https://api.telegram.org/bot{config.BOT_TOKEN}/deleteMessage"
        requests.post(url, data={"chat_id": config.CHAT_ID, "message_id": msg_id}, timeout=5)
    except Exception:
        pass

def send_voice_with_caption(voice_path, caption):
    try:
        if os.path.getsize(voice_path) < 1000:  # small file check
            raise ValueError("File too small or empty")
        url = f"https://api.telegram.org/bot{config.BOT_TOKEN}/sendVoice"
        with open(voice_path, "rb") as voice:
            payload = {"chat_id": config.CHAT_ID, "caption": caption, "parse_mode": "HTML"}
            files = {"voice": voice}
            response = requests.post(url, data=payload, files=files, timeout=60)
            time.sleep(2)
            if response.status_code == 200:
                return True
            else:
                print(f"[DEBUG] Telegram response: {response.status_code} - {response.text}")
    except Exception as e:
        print(f"[❌] Failed to send voice: {e}")
    return False

# ----------------- cookie/session -----------------
def save_cookies(driver, path=COOKIE_PATH):
    try:
        cookies = driver.get_cookies()
        with open(path, "wb") as f:
            pickle.dump(cookies, f)
        print(f"[+] Cookies saved to {path} ({len(cookies)} cookies).")
    except Exception as e:
        print("[!] Failed to save cookies:", e)

def load_cookies(driver, base_url=None, path=COOKIE_PATH):
    if not os.path.exists(path):
        print("[i] No cookie file found at", path)
        return False
    try:
        base_url = base_url or config.BASE_URL
        driver.get(base_url)
        time.sleep(1)
        with open(path, "rb") as f:
            cookies = pickle.load(f)
        added = 0
        for c in cookies:
            cookie = {k: c.get(k) for k in ("name", "value", "path", "domain", "secure", "httpOnly") if c.get(k) is not None}
            try:
                driver.add_cookie(cookie)
                added += 1
            except Exception:
                try:
                    # fallback minimal cookie
                    driver.add_cookie({"name": c.get("name"), "value": c.get("value"), "path": "/"})
                    added += 1
                except Exception:
                    pass
        print(f"[+] Loaded {added} cookies from {path}.")
        return True
    except Exception as e:
        print("[!] Failed to load cookies:", e)
        return False

def get_authenticated_session(driver):
    session = requests.Session()
    try:
        for cookie in driver.get_cookies():
            session.cookies.set(cookie['name'], cookie['value'], domain=cookie.get('domain'), path=cookie.get('path', '/'))
    except Exception as e:
        print("[!] get_authenticated_session error:", e)
    return session

# ----------------- recording helpers -----------------
def construct_recording_url(did_number, call_uuid):
    return f"{config.CALL_URL.rstrip('/')}/sound?did={did_number}&uuid={call_uuid}"

def simulate_play_button(driver, did_number, call_uuid):
    try:
        script = f'if (window.Play) {{ window.Play("{did_number}", "{call_uuid}"); "played"; }} else {{ "no_play"; }}'
        res = driver.execute_script(script)
        if res == "played":
            print(f"[▶️] Play invoked via JS: {did_number}")
            return True
    except Exception as e:
        print(f"[❌] Play JS exec failed: {e}")

    # fallback: click element with onclick that includes Play/did/uuid
    try:
        elems = driver.find_elements(By.XPATH, f"//*[contains(@onclick, 'Play') and (contains(@onclick, '{call_uuid}') or contains(@onclick, '{did_number}'))]")
        for el in elems:
            try:
                el.click()
                print(f"[▶️] Play clicked element fallback: {did_number}")
                return True
            except Exception:
                continue
    except Exception:
        pass

    print("[⚠️] Play not simulated")
    return False

def download_recording(driver, did_number, call_uuid, file_path):
    try:
        simulate_play_button(driver, did_number, call_uuid)
        time.sleep(3)  # wait for server to prepare

        recording_url = construct_recording_url(did_number, call_uuid)
        session = get_authenticated_session(driver)
        headers = {
            'User-Agent': getattr(config, "USER_AGENT", "Mozilla/5.0"),
            'Referer': config.CALL_URL,
            'Accept': 'audio/mpeg, audio/*'
        }

        for attempt in range(5):
            try:
                print(f"[DEBUG] Attempt {attempt+1} -> {recording_url}")
                with session.get(recording_url, headers=headers, timeout=30, stream=True) as response:
                    status = response.status_code
                    length = int(response.headers.get('Content-Length', 0) or 0)
                    print(f"[DEBUG] Status: {status}, Content-Length: {length}")
                    if status == 200 and length > 1000:
                        tmp_path = file_path + ".part"
                        with open(tmp_path, "wb") as f:
                            for chunk in response.iter_content(chunk_size=8192):
                                if chunk:
                                    f.write(chunk)
                        os.replace(tmp_path, file_path)
                        print(f"[✅] Recording downloaded: {file_path} ({os.path.getsize(file_path)} bytes)")
                        return True
            except requests.RequestException as e:
                print(f"[❌] download attempt error: {e}")
            time.sleep(4 + attempt)
        return False
    except Exception as e:
        print(f"[❌] Download failed: {e}")
        if os.path.exists(file_path):
            os.remove(file_path)
        return False

# ----------------- animation thread -----------------
def animate_message_dots(msg_id, base_text, stop_event):
    try:
        dots = 0
        direction = 1
        while not stop_event.is_set():
            suffix = "." * dots
            new_text = f"{base_text} {suffix}" if suffix else base_text
            try:
                edit_message_text(msg_id, new_text)
            except Exception:
                pass
            time.sleep(0.5)
            if dots >= 3:
                direction = -1
            elif dots <= 0:
                direction = 1
            dots += direction
    except Exception as e:
        print(f"[❌] Animation thread error: {e}")

# ----------------- core extraction & processing -----------------
def extract_calls(driver):
    global active_calls, pending_recordings
    try:
        calls_table = WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.ID, "LiveCalls")))
        rows = calls_table.find_elements(By.TAG_NAME, "tr")
        current_call_ids = set()

        for row in rows:
            try:
                row_id = row.get_attribute('id')
                if not row_id:
                    continue
                cells = row.find_elements(By.TAG_NAME, "td")
                if len(cells) < 2:
                    continue
                did_element = cells[1]
                did_text = did_element.text.strip()
                did_number = re.sub(r"\D", "", did_text)
                if not did_number:
                    continue
                current_call_ids.add(row_id)
                if row_id not in active_calls:
                    print(f"[📞] New call: {did_number}")
                    country_name, flag = detect_country(did_number)
                    masked = mask_number(did_number)
                    alert_text = f"📞 New call detected from {flag} {masked}. Waiting for it to end."
                    msg_id = send_message(alert_text)
                    active_calls[row_id] = {
                        "msg_id": msg_id,
                        "flag": flag,
                        "country": country_name,
                        "masked": masked,
                        "did_number": did_number,
                        "detected_at": datetime.now(),
                        "last_seen": datetime.now()
                    }
                else:
                    active_calls[row_id]["last_seen"] = datetime.now()
            except StaleElementReferenceException:
                continue
            except Exception as e:
                print(f"[❌] Row error: {e}")
                continue

        # detect finished
        current_time = datetime.now()
        completed_calls = []
        for call_id, call_info in list(active_calls.items()):
            if (call_id not in current_call_ids) or ((current_time - call_info["last_seen"]).total_seconds() > 15):
                if call_id not in pending_recordings:
                    print(f"[✅] Call completed: {call_info['did_number']}")
                    completed_calls.append(call_id)

        for call_id in completed_calls:
            call_info = active_calls[call_id]
            pending_recordings[call_id] = {
                **call_info,
                "completed_at": datetime.now(),
                "checks": 0,
                "last_check": datetime.now(),
                "anim_stop": threading.Event(),
                "anim_thread": None
            }
            wait_text = f"{call_info['flag']} {call_info['masked']} — The call record for this number is currently being processed."
            if call_info["msg_id"]:
                delete_message(call_info["msg_id"])
            new_msg_id = send_message(wait_text)
            if new_msg_id:
                pending_recordings[call_id]["msg_id"] = new_msg_id
                t = threading.Thread(target=animate_message_dots, args=(new_msg_id, wait_text, pending_recordings[call_id]["anim_stop"]), daemon=True)
                pending_recordings[call_id]["anim_thread"] = t
                t.start()
            del active_calls[call_id]

    except TimeoutException:
        print("[⏱️] No active calls table")
    except Exception as e:
        print(f"[❌] Extract error: {e}")

def process_pending_recordings(driver):
    global pending_recordings
    current_time = datetime.now()
    processed_calls = []

    for call_id, call_info in list(pending_recordings.items()):
        try:
            time_since_check = (current_time - call_info["last_check"]).total_seconds()
            if time_since_check < getattr(config, "RECORDING_RETRY_DELAY", 15):
                continue

            call_info["checks"] += 1
            call_info["last_check"] = current_time
            print(f"[🔍] Check #{call_info['checks']} for: {call_info['did_number']}")

            if call_info["checks"] > 10:
                print("[⏰] Max checks exceeded for recording")
                timeout_text = f"❌ Max checks exceeded for {call_info['flag']} {call_info['masked']}"
                if call_info.get("anim_stop"):
                    call_info["anim_stop"].set()
                if call_info.get("msg_id"):
                    try:
                        delete_message(call_info["msg_id"])
                    except:
                        pass
                send_message(timeout_text)
                processed_calls.append(call_id)
                continue

            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            path = os.path.join(config.DOWNLOAD_FOLDER, f"call_{call_info['did_number']}_{timestamp}.mp3")

            if download_recording(driver, call_info['did_number'], call_id, path):
                if call_info.get("anim_stop"):
                    call_info["anim_stop"].set()
                process_recording_file(call_info, path)
                processed_calls.append(call_id)
            else:
                print(f"[❌] Recording not available yet: {call_info['did_number']}")

            time_since_complete = (current_time - call_info["completed_at"]).total_seconds()
            if time_since_complete > getattr(config, "MAX_RECORDING_WAIT", 600):
                print(f"[⏰] Timeout: {call_info['did_number']}")
                timeout_text = f"❌ Recording timeout for {call_info['flag']} {call_info['masked']}"
                if call_info.get("anim_stop"):
                    call_info["anim_stop"].set()
                if call_info.get("msg_id"):
                    try:
                        delete_message(call_info["msg_id"])
                    except:
                        pass
                send_message(timeout_text)
                processed_calls.append(call_id)

        except Exception as e:
            print(f"[❌] Processing error: {e}")

    for call_id in processed_calls:
        if call_id in pending_recordings:
            try:
                if pending_recordings[call_id].get("anim_stop"):
                    pending_recordings[call_id]["anim_stop"].set()
            except:
                pass
            del pending_recordings[call_id]

def process_recording_file(call_info, file_path):
    try:
        if call_info.get("msg_id"):
            try:
                delete_message(call_info["msg_id"])
            except:
                pass
        call_time = call_info['detected_at'].strftime('%Y-%m-%d %I:%M:%S %p')
        caption = (
            "🔥 NEW CALL RECEIVED ✨\n\n"
            f"⏰ Time: {call_time}\n"
            f"{call_info['flag']} Country: {call_info['country']}\n"
            f"🚀 Number: {call_info['masked']}\n\n"
            f"🌟 Configure by professor_cry"
        )
        if send_voice_with_caption(file_path, caption):
            print(f"[✅] Recording sent: {call_info['did_number']}")
        else:
            send_message(caption + "\n⚠️ Voice file failed to upload.")
    except Exception as e:
        print(f"[❌] File processing error: {e}")
        error_text = f"❌ Processing error for {call_info['flag']} {call_info['masked']}"
        send_message(error_text)

# ----------------- login/watch helpers -----------------
def wait_for_login(driver, timeout=600):
    print(f"🔐 Login page: {config.LOGIN_URL}")
    print("➡️ Please login in browser (solve Cloudflare if required)...")
    try:
        WebDriverWait(driver, timeout).until(
            lambda d: d.current_url.startswith(getattr(config, "BASE_URL", d.current_url)) and not d.current_url.startswith(config.LOGIN_URL)
        )
        print("✅ Login successful!")
        return True
    except TimeoutException:
        print("[❌] Login timeout")
        return False

# ----------------- driver init (undetected + proxy + profile) -----------------
def build_options():
    options = uc.ChromeOptions()
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_argument("--disable-infobars")
    options.add_argument("--disable-notifications")
    options.add_argument("--disable-extensions")
    options.add_argument("--start-maximized")
    options.add_argument(f"--window-size={getattr(config, 'WINDOW_SIZE', '1366,768')}")
    options.add_argument(f"--user-agent={getattr(config, 'USER_AGENT', 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)')}")
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option('useAutomationExtension', False)
    prefs = {"profile.default_content_setting_values.notifications": 2}
    options.add_experimental_option("prefs", prefs)

    if getattr(config, "HEADLESS", False):
        options.add_argument("--headless=new")
    if getattr(config, "PROXY", None):
        # config.PROXY should be like: "http://user:pass@host:port"
        options.add_argument(f"--proxy-server={config.PROXY}")

    return options

def create_driver():
    options = build_options()
    kwargs = {"options": options, "use_subprocess": True}
    if getattr(config, "USER_DATA_DIR", None):
        os.makedirs(config.USER_DATA_DIR, exist_ok=True)
        kwargs["user_data_dir"] = config.USER_DATA_DIR
    driver = uc.Chrome(**kwargs)
    # extra CDP tweaks
    try:
        driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {
            "source": """
                Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
                window.navigator.chrome = { runtime: {} };
                Object.defineProperty(navigator, 'languages', {get: () => ['en-US','en']});
            """
        })
    except Exception:
        pass
    return driver

# ----------------- main flow -----------------
def main():
    driver = None
    try:
        driver = create_driver()

        # try to load cookies
        try:
            load_cookies(driver, getattr(config, "BASE_URL", config.LOGIN_URL))
        except Exception as e:
            print("[!] cookie load error:", e)

        # open login and wait
        driver.get(config.LOGIN_URL)
        if not wait_for_login(driver):
            print("[i] If login timed out, please solve manually in the opened browser and press ENTER")
            input("Press ENTER after manual login...")

        # save cookies after manual login
        try:
            save_cookies(driver)
        except Exception as e:
            print("[!] save_cookies error:", e)

        # go to calls page
        driver.get(config.CALL_URL)
        WebDriverWait(driver, 20).until(EC.presence_of_element_located((By.ID, "LiveCalls")))
        print("✅ Active Calls page loaded! Monitoring started...")

        error_count = 0
        last_recording_check = datetime.now()
        last_refresh = datetime.now()

        while error_count < getattr(config, "MAX_ERRORS", 5):
            try:
                # refresh every 30 minutes to keep session fresh
                if (datetime.now() - last_refresh).total_seconds() > 1800:
                    try:
                        driver.refresh()
                        WebDriverWait(driver, 15).until(EC.presence_of_element_located((By.ID, "LiveCalls")))
                        last_refresh = datetime.now()
                        print("[🔄] Page refreshed to maintain session")
                    except Exception as e:
                        print("[⚠️] Refresh failed:", e)

                # session check
                if config.LOGIN_URL in driver.current_url:
                    print("[⚠️] Session expired, re-login required")
                    if not wait_for_login(driver):
                        break
                    driver.get(config.CALL_URL)

                extract_calls(driver)

                current_time = datetime.now()
                if (current_time - last_recording_check).total_seconds() >= getattr(config, "RECORDING_CHECK_INTERVAL", 10):
                    process_pending_recordings(driver)
                    last_recording_check = current_time

                error_count = 0
                time.sleep(getattr(config, "CHECK_INTERVAL", 3))

            except KeyboardInterrupt:
                print("\n[🛑] Stopped by user")
                break
            except WebDriverException as e:
                error_count += 1
                print(f"[❌] WebDriver error ({error_count}/{getattr(config,'MAX_ERRORS',5)}): {e}")
                time.sleep(5)
            except Exception as e:
                error_count += 1
                print(f"[❌] Main loop error ({error_count}/{getattr(config,'MAX_ERRORS',5)}): {e}")
                time.sleep(5)

    except Exception as e:
        print(f"[💥] Fatal error: {e}")
    finally:
        try:
            if driver:
                driver.quit()
        except:
            pass
        print("[*] Monitoring stopped")

if __name__ == "__main__":
    main()
