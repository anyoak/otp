#!/usr/bin/env python3
# main.py - Orangecarrier monitor (Firefox, no selenium-wire)
# Features:
# - Firefox browser (real) open
# - Proxy support via Firefox prefs (basic; auth popup may be manual)
# - Cookie save/load (cookies.pkl)
# - Call detection -> pending -> download recording (requests session from cookies)
# - Telegram messaging (send/edit/delete/sendVoice)
# - Animation dots for pending messages

import os
import re
import time
import json
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
from selenium.common.exceptions import TimeoutException, StaleElementReferenceException, WebDriverException

import phonenumbers
from phonenumbers import region_code_for_number
import pycountry

import config

# ---------- globals ----------
Path(config.DOWNLOAD_FOLDER).mkdir(parents=True, exist_ok=True)
COOKIE_PATH = getattr(config, "COOKIES_FILE", "cookies.pkl")

active_calls = {}          # call_id -> info
pending_recordings = {}    # call_id -> info

# ---------- utilities ----------
def country_to_flag(country_code):
    if not country_code or len(country_code) != 2:
        return "🏳️"
    return "".join(chr(127397 + ord(c)) for c in country_code.upper())

def detect_country(number):
    try:
        clean = re.sub(r"\D", "", number)
        if not clean:
            return "Unknown", "🏳️"
        parsed = phonenumbers.parse("+" + clean, None)
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

# ---------- Telegram helpers ----------
def send_message(text):
    try:
        url = f"https://api.telegram.org/bot{config.BOT_TOKEN}/sendMessage"
        payload = {"chat_id": config.CHAT_ID, "text": text, "parse_mode": "Markdown"}
        res = requests.post(url, json=payload, timeout=getattr(config, "REQUEST_TIMEOUT", 30))
        if res.ok:
            return res.json().get("result", {}).get("message_id")
        else:
            print(f"[Telegram send_message] HTTP {res.status_code} - {res.text}")
    except Exception as e:
        print(f"[❌] Failed to send message: {e}")
    return None

def edit_message_text(msg_id, new_text):
    try:
        url = f"https://api.telegram.org/bot{config.BOT_TOKEN}/editMessageText"
        payload = {"chat_id": config.CHAT_ID, "message_id": msg_id, "text": new_text, "parse_mode": "Markdown"}
        requests.post(url, json=payload, timeout=getattr(config, "REQUEST_TIMEOUT", 30))
    except Exception as e:
        # non-fatal
        # print(f"[❌] edit_message_text failed: {e}")
        pass

def delete_message(msg_id):
    try:
        url = f"https://api.telegram.org/bot{config.BOT_TOKEN}/deleteMessage"
        requests.post(url, data={"chat_id": config.CHAT_ID, "message_id": msg_id}, timeout=5)
    except Exception:
        pass

def send_voice_with_caption(voice_path, caption):
    try:
        if os.path.getsize(voice_path) < 1000:
            raise ValueError("File too small or empty")
        url = f"https://api.telegram.org/bot{config.BOT_TOKEN}/sendVoice"
        with open(voice_path, "rb") as voice:
            payload = {"chat_id": config.CHAT_ID, "caption": caption, "parse_mode": "HTML"}
            files = {"voice": voice}
            response = requests.post(url, data=payload, files=files, timeout=getattr(config, "REQUEST_TIMEOUT", 60))
            time.sleep(1.5)
            if response.status_code == 200:
                return True
            else:
                print(f"[Telegram sendVoice] HTTP {response.status_code} - {response.text}")
    except Exception as e:
        print(f"[❌] Failed to send voice: {e}")
    return False

# ---------- cookie/session helpers ----------
def save_cookies(driver, path=COOKIE_PATH):
    try:
        cookies = driver.get_cookies()
        with open(path, "wb") as f:
            pickle.dump(cookies, f)
        print(f"[✅] Cookies saved to {path} ({len(cookies)} cookies).")
    except Exception as e:
        print(f"[❌] Failed to save cookies: {e}")

def load_cookies(driver, base_url=None, path=COOKIE_PATH):
    if not os.path.exists(path):
        print("[i] No cookie file to load.")
        return False
    try:
        base = base_url or config.BASE_URL
        driver.get(base)
        time.sleep(1)
        with open(path, "rb") as f:
            cookies = pickle.load(f)
        added = 0
        for c in cookies:
            cookie = {k: c.get(k) for k in ("name","value","path","domain","secure","httpOnly","expiry") if c.get(k) is not None}
            try:
                driver.add_cookie(cookie)
                added += 1
            except Exception:
                try:
                    driver.add_cookie({"name": c.get("name"), "value": c.get("value"), "path": "/"})
                    added += 1
                except Exception:
                    pass
        print(f"[✅] Loaded {added} cookies from {path}")
        return True
    except Exception as e:
        print(f"[❌] Failed to load cookies: {e}")
        return False

def get_authenticated_session(driver):
    s = requests.Session()
    try:
        for c in driver.get_cookies():
            s.cookies.set(c['name'], c['value'], domain=c.get('domain'), path=c.get('path', '/'))
    except Exception as e:
        print(f"[!] get_authenticated_session error: {e}")
    return s

# ---------- recording helpers ----------
def construct_recording_url(did_number, call_uuid):
    return f"{config.CALL_URL.rstrip('/')}/sound?did={did_number}&uuid={call_uuid}"

def simulate_play_button(driver, did_number, call_uuid):
    # Try JS Play call first, then fallback to clicking elements
    try:
        script = f'if (window.Play) {{ window.Play("{did_number}", "{call_uuid}"); "played"; }} else {{ "no_play"; }}'
        res = driver.execute_script(script)
        if res == "played":
            print(f"[▶️] Play invoked by JS for {did_number}")
            return True
    except Exception as e:
        # print(f"[!] JS Play exec failed: {e}")
        pass

    try:
        # fallback: search for clickable elements that include the uuid or did_number
        elems = driver.find_elements(By.XPATH, f"//*[contains(@onclick, 'Play') and (contains(@onclick, '{call_uuid}') or contains(@onclick, '{did_number}'))]")
        for el in elems:
            try:
                el.click()
                print(f"[▶️] Click fallback invoked for {did_number}")
                return True
            except Exception:
                continue
    except Exception:
        pass

    return False

def download_recording(driver, did_number, call_uuid, file_path):
    try:
        simulate_play_button(driver, did_number, call_uuid)
        time.sleep(4)  # give server some time to prepare
        recording_url = construct_recording_url(did_number, call_uuid)
        session = get_authenticated_session(driver)
        headers = {
            "User-Agent": getattr(config, "USER_AGENT", "Mozilla/5.0"),
            "Referer": config.CALL_URL,
            "Accept": "audio/mpeg, audio/*"
        }
        for attempt in range(4):
            try:
                print(f"[DEBUG] Download attempt {attempt+1} -> {recording_url}")
                with session.get(recording_url, headers=headers, timeout=getattr(config,"REQUEST_TIMEOUT",30), stream=True) as r:
                    status = r.status_code
                    length = int(r.headers.get("Content-Length", 0) or 0)
                    print(f"[DEBUG] status={status}, length={length}")
                    if status == 200 and length > 1000:
                        tmp = file_path + ".part"
                        with open(tmp, "wb") as f:
                            for chunk in r.iter_content(chunk_size=8192):
                                if chunk:
                                    f.write(chunk)
                        os.replace(tmp, file_path)
                        print(f"[✅] Recording saved: {file_path} ({os.path.getsize(file_path)} bytes)")
                        return True
            except requests.RequestException as e:
                print(f"[!] Download request error: {e}")
            time.sleep(4 + attempt)
        return False
    except Exception as e:
        print(f"[❌] download_recording failure: {e}")
        if os.path.exists(file_path):
            os.remove(file_path)
        return False

# ---------- messaging animation ----------
def animate_message_dots(msg_id, base_text, stop_event):
    try:
        dots = 0
        direction = 1
        while not stop_event.is_set():
            suffix = "." * dots
            new_text = base_text + " " + suffix if suffix else base_text
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

# ---------- extract and process calls (page-specific) ----------
def extract_calls(driver):
    """
    Extract rows from LiveCalls table like previous implementation.
    This function matches previous logic: find table with ID 'LiveCalls',
    then iterate rows and get row.id and DID number text.
    """
    global active_calls, pending_recordings
    try:
        calls_table = WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.ID, "LiveCalls")))
        rows = calls_table.find_elements(By.TAG_NAME, "tr")
        current_call_ids = set()
        for row in rows:
            try:
                row_id = row.get_attribute("id")
                if not row_id:
                    continue
                cells = row.find_elements(By.TAG_NAME, "td")
                if len(cells) < 2:
                    continue
                did_text = cells[1].text.strip()
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
                print(f"[❌] Row parsing error: {e}")
                continue

        # find completed calls
        completed = []
        now = datetime.now()
        for call_id, info in list(active_calls.items()):
            if (call_id not in current_call_ids) or ((now - info["last_seen"]).total_seconds() > 15):
                if call_id not in pending_recordings:
                    print(f"[✅] Call completed: {info['did_number']}")
                    completed.append(call_id)

        for call_id in completed:
            info = active_calls[call_id]
            pending_recordings[call_id] = {
                **info,
                "completed_at": datetime.now(),
                "checks": 0,
                "last_check": datetime.now(),
                "anim_stop": threading.Event(),
                "anim_thread": None
            }
            wait_text = f"{info['flag']} {info['masked']} — The call record for this number is currently being processed."
            if info.get("msg_id"):
                delete_message(info["msg_id"])
            new_msg_id = send_message(wait_text)
            if new_msg_id:
                pending_recordings[call_id]["msg_id"] = new_msg_id
                t = threading.Thread(target=animate_message_dots, args=(new_msg_id, wait_text, pending_recordings[call_id]["anim_stop"]), daemon=True)
                pending_recordings[call_id]["anim_thread"] = t
                t.start()
            del active_calls[call_id]

    except TimeoutException:
        # no table found
        # print("[⏱️] LiveCalls table not present")
        pass
    except Exception as e:
        print(f"[❌] extract_calls error: {e}")

# ---------- process pending recordings ----------
def process_pending_recordings(driver):
    global pending_recordings
    now = datetime.now()
    processed = []
    for call_id, info in list(pending_recordings.items()):
        try:
            since = (now - info["last_check"]).total_seconds()
            if since < getattr(config, "RECORDING_RETRY_DELAY", 15):
                continue
            info["checks"] += 1
            info["last_check"] = now
            print(f"[🔍] Check #{info['checks']} for {info['did_number']}")

            if info["checks"] > 10:
                print("[⏰] Max checks exceeded")
                timeout_text = f"❌ Max checks exceeded for {info['flag']} {info['masked']}"
                if info.get("anim_stop"):
                    info["anim_stop"].set()
                if info.get("msg_id"):
                    try:
                        delete_message(info["msg_id"])
                    except:
                        pass
                send_message(timeout_text)
                processed.append(call_id)
                continue

            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            file_path = os.path.join(config.DOWNLOAD_FOLDER, f"call_{info['did_number']}_{timestamp}.mp3")

            # attempt to download
            if download_recording(driver, info['did_number'], call_id, file_path):
                if info.get("anim_stop"):
                    info["anim_stop"].set()
                process_recording_file(info, file_path)
                processed.append(call_id)
            else:
                print(f"[❌] Recording not ready yet for {info['did_number']}")

            # overall timeout
            if (now - info["completed_at"]).total_seconds() > getattr(config, "MAX_RECORDING_WAIT", 600):
                timeout_text = f"❌ Recording timeout for {info['flag']} {info['masked']}"
                if info.get("anim_stop"):
                    info["anim_stop"].set()
                if info.get("msg_id"):
                    try:
                        delete_message(info["msg_id"])
                    except:
                        pass
                send_message(timeout_text)
                processed.append(call_id)

        except Exception as e:
            print(f"[❌] process_pending_recordings error: {e}")

    for cid in processed:
        try:
            if pending_recordings[cid].get("anim_stop"):
                pending_recordings[cid]["anim_stop"].set()
        except:
            pass
        pending_recordings.pop(cid, None)

# ---------- process & upload ----------
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
            f"🌟 Configure by @professor_cry"
        )
        if send_voice_with_caption(file_path, caption):
            print(f"[✅] Recording sent: {call_info['did_number']}")
        else:
            send_message(caption + "\n⚠️ Voice file failed to upload.")
    except Exception as e:
        print(f"[❌] process_recording_file error: {e}")
        send_message(f"❌ Processing error for {call_info.get('flag','')} {call_info.get('masked','')}")

# ---------- login helper ----------
def wait_for_login(driver, timeout=600):
    print(f"🔐 Open login: {config.LOGIN_URL}")
    print("➡️ Please login manually in the opened browser (solve Cloudflare if required).")
    try:
        WebDriverWait(driver, timeout).until(
            lambda d: d.current_url.startswith(config.BASE_URL) and not d.current_url.startswith(config.LOGIN_URL)
        )
        print("[✅] Login detected by URL change.")
        return True
    except TimeoutException:
        print("[❌] Login timeout.")
        return False

# ---------- initialize firefox driver ----------
def initialize_driver():
    options = Options()
    options.headless = getattr(config, "HEADLESS", False)
    options.set_preference("general.useragent.override", getattr(config, "USER_AGENT", "Mozilla/5.0"))
    options.set_preference("dom.webnotifications.enabled", False)
    options.set_preference("media.volume_scale", "0.0")
    # Use profile dir so cookies and session persist
    profile_dir = getattr(config, "USER_DATA_DIR", "ff_profile")
    os.makedirs(profile_dir, exist_ok=True)
    options.profile = os.path.abspath(profile_dir)

    # Proxy prefs (basic)
    if getattr(config, "PROXY", None):
        m = re.match(r'^(?:http://)?(?:(.*?):(.*?)@)?([^:]+):(\d+)$', config.PROXY)
        if m:
            user, pwd, host, port = m.groups()
            # set manual proxy hosts/ports
            options.set_preference("network.proxy.type", 1)
            options.set_preference("network.proxy.http", host)
            options.set_preference("network.proxy.http_port", int(port))
            options.set_preference("network.proxy.ssl", host)
            options.set_preference("network.proxy.ssl_port", int(port))
            options.set_preference("network.proxy.no_proxies_on", "")
            # Note: If user/pwd present, Firefox will prompt an auth popup on first request.
            # You must manually enter credentials the first time OR pre-inject an authenticated profile.
        else:
            print("[⚠️] PROXY format not recognized; skipping proxy prefs.")

    # If user set a GECKODRIVER_PATH in config, use it; otherwise assume in PATH
    geckopath = getattr(config, "GECKODRIVER_PATH", None)
    service = FirefoxService(executable_path=geckopath) if geckopath else FirefoxService()

    try:
        driver = webdriver.Firefox(service=service, options=options)
    except Exception as e:
        # helpful message
        print(f"[❌] Failed to start Firefox driver: {e}")
        raise
    driver.set_window_size(*map(int, getattr(config, "WINDOW_SIZE", "1366,768").split(",")))
    return driver

# ---------- main loop ----------
def main():
    driver = None
    try:
        driver = initialize_driver()

        # try load cookies
        try:
            load_cookies(driver, getattr(config, "BASE_URL", config.LOGIN_URL))
        except Exception as e:
            print("[!] cookie load issue:", e)

        # open login
        driver.get(config.LOGIN_URL)
        if not wait_for_login(driver):
            print("[i] If you logged in manually already, press ENTER to continue.")
            input("Press ENTER to continue...")

        # save cookies after login
        try:
            save_cookies(driver)
        except Exception as e:
            print("[!] save cookies failed:", e)

        # go to calls page and start monitoring
        driver.get(config.CALL_URL)
        try:
            WebDriverWait(driver, 20).until(EC.presence_of_element_located((By.ID, "LiveCalls")))
            print("[✅] LiveCalls loaded. Monitoring started.")
        except TimeoutException:
            print("[⚠️] LiveCalls table not found initially — will poll anyway.")

        last_recording_check = datetime.now()
        last_refresh = datetime.now()
        error_count = 0

        while error_count < getattr(config, "MAX_ERRORS", 5):
            try:
                # refresh occasionally to keep session alive
                if (datetime.now() - last_refresh).total_seconds() > 1800:
                    try:
                        driver.refresh()
                        WebDriverWait(driver, 15).until(EC.presence_of_element_located((By.ID, "LiveCalls")))
                        last_refresh = datetime.now()
                        print("[🔄] Page refreshed")
                    except Exception as e:
                        print("[⚠️] Refresh failed:", e)

                # check session
                if config.LOGIN_URL in driver.current_url:
                    print("[⚠️] Session expired — please re-login manually in opened browser.")
                    if not wait_for_login(driver):
                        break
                    driver.get(config.CALL_URL)

                extract_calls(driver)

                # process pending recordings periodically
                if (datetime.now() - last_recording_check).total_seconds() >= getattr(config, "RECORDING_CHECK_INTERVAL", 10):
                    process_pending_recordings(driver)
                    last_recording_check = datetime.now()

                error_count = 0
                time.sleep(getattr(config, "CHECK_INTERVAL", 3))
            except KeyboardInterrupt:
                print("\n[🛑] Stopped by user")
                break
            except WebDriverException as e:
                error_count += 1
                print(f"[❌] WebDriver error ({error_count}): {e}")
                time.sleep(5)
            except Exception as e:
                error_count += 1
                print(f"[❌] Main loop error ({error_count}): {e}")
                time.sleep(5)

    except Exception as e:
        print(f"[💥] Fatal error: {e}")
    finally:
        try:
            if driver:
                driver.quit()
        except:
            pass
        print("[*] Monitor stopped")

if __name__ == "__main__":
    main()
