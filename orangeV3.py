import time
import re
import requests
import os
from datetime import datetime
import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, StaleElementReferenceException
import phonenumbers
from phonenumbers import region_code_for_number
import pycountry
import config

# Fix for distutils issue in Python 3.12+
import setuptools
import sys
sys.modules['distutils'] = setuptools

# ==================== Globals ====================
active_calls = {}
pending_recordings = {}
os.makedirs(config.DOWNLOAD_FOLDER, exist_ok=True)

# ==================== Utility ====================
def country_to_flag(country_code):
    if not country_code or len(country_code) != 2:
        return "🏳️"
    return "".join(chr(127397 + ord(c)) for c in country_code.upper())

def detect_country(number):
    try:
        digits = re.sub(r"\D", "", number)
        if digits:
            parsed = phonenumbers.parse("+" + digits, None)
            region = region_code_for_number(parsed)
            country = pycountry.countries.get(alpha_2=region)
            if country:
                return country.name, country_to_flag(region)
    except:
        pass
    return "Unknown", "🏳️"

def mask_number(number):
    digits = re.sub(r"\D", "", number)
    if len(digits) > 6:
        return digits[:4] + "****" + digits[-3:]
    return number

def send_message(text):
    try:
        url = f"https://api.telegram.org/bot{config.BOT_TOKEN}/sendMessage"
        payload = {"chat_id": config.CHAT_ID, "text": text, "parse_mode": "HTML"}
        res = requests.post(url, json=payload, timeout=10)
        if res.ok:
            return res.json().get("result", {}).get("message_id")
    except Exception as e:
        print(f"[❌] Failed to send message: {e}")
    return None

def delete_message(msg_id):
    try:
        url = f"https://api.telegram.org/bot{config.BOT_TOKEN}/deleteMessage"
        requests.post(url, json={"chat_id": config.CHAT_ID, "message_id": msg_id}, timeout=5)
    except:
        pass

def send_voice_with_caption(voice_path, caption):
    try:
        if os.path.getsize(voice_path) < 1000:
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

def get_authenticated_session(driver):
    session = requests.Session()
    for cookie in driver.get_cookies():
        session.cookies.set(cookie['name'], cookie['value'])
    return session

# ==================== Recording ====================
def construct_recording_url(did_number, call_uuid):
    return f"https://www.orangecarrier.com/live/calls/sound?did={did_number}&uuid={call_uuid}"

def simulate_play_button(driver, did_number, call_uuid):
    try:
        script = f'window.Play("{did_number}", "{call_uuid}"); return "Play executed";'
        driver.execute_script(script)
        print(f"[▶️] Play button simulated: {did_number}")
        return True
    except Exception as e:
        print(f"[❌] Play simulation failed: {e}")
        return False

def download_recording(driver, did_number, call_uuid, file_path):
    try:
        simulate_play_button(driver, did_number, call_uuid)
        time.sleep(5)
        recording_url = construct_recording_url(did_number, call_uuid)
        session = get_authenticated_session(driver)
        headers = {
            'User-Agent': 'Mozilla/5.0',
            'Referer': config.CALL_URL,
            'Accept': 'audio/mpeg, audio/*'
        }

        for attempt in range(3):
            response = session.get(recording_url, headers=headers, timeout=30, stream=True)
            print(f"[DEBUG] Attempt {attempt+1} - Response: {response.status_code}")
            if response.status_code == 200 and int(response.headers.get('Content-Length', 0)) > 1000:
                with open(file_path, "wb") as f:
                    for chunk in response.iter_content(8192):
                        f.write(chunk)
                print(f"[✅] Recording downloaded: {file_path}")
                return True
            time.sleep(5)
        return False
    except Exception as e:
        print(f"[❌] Download failed: {e}")
        if os.path.exists(file_path):
            os.remove(file_path)
        return False

# ==================== Core Logic ====================
def extract_calls(driver):
    global active_calls, pending_recordings
    try:
        calls_table = WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.ID, "LiveCalls"))
        )
        rows = calls_table.find_elements(By.TAG_NAME, "tr")
        current_call_ids = set()
        for row in rows:
            try:
                row_id = row.get_attribute('id')
                if not row_id: continue
                cells = row.find_elements(By.TAG_NAME, "td")
                if len(cells) < 5: continue
                did_number = re.sub(r"\D", "", cells[1].text.strip())
                if not did_number: continue
                current_call_ids.add(row_id)

                if row_id not in active_calls:
                    country_name, flag = detect_country(did_number)
                    masked = mask_number(did_number)
                    msg_id = send_message(f"📞 New call from {flag} {masked}")
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

        # Completed calls
        current_time = datetime.now()
        completed_calls = [cid for cid, info in active_calls.items()
                           if cid not in current_call_ids or (current_time - info["last_seen"]).total_seconds() > 15]

        for call_id in completed_calls:
            call_info = active_calls.pop(call_id)
            pending_recordings[call_id] = {**call_info, "completed_at": datetime.now(), "checks": 0, "last_check": datetime.now()}
            if call_info["msg_id"]:
                delete_message(call_info["msg_id"])
            send_message(f"{call_info['flag']} {call_info['masked']} — Recording processing...")

    except TimeoutException:
        print("[⏱️] No active calls table found")
    except Exception as e:
        print(f"[❌] Extract error: {e}")

def process_pending_recordings(driver):
    global pending_recordings
    current_time = datetime.now()
    to_remove = []
    for call_id, info in list(pending_recordings.items()):
        if (current_time - info["last_check"]).total_seconds() < config.RECORDING_RETRY_DELAY:
            continue
        info["checks"] += 1
        info["last_check"] = current_time
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        file_path = os.path.join(config.DOWNLOAD_FOLDER, f"call_{info['did_number']}_{timestamp}.mp3")
        if download_recording(driver, info['did_number'], call_id, file_path):
            process_recording_file(info, file_path)
            to_remove.append(call_id)
        elif info["checks"] > 10:
            send_message(f"❌ Recording not available for {info['flag']} {info['masked']}")
            to_remove.append(call_id)
    for cid in to_remove:
        pending_recordings.pop(cid, None)

def process_recording_file(call_info, file_path):
    try:
        if call_info.get("msg_id"):
            delete_message(call_info["msg_id"])
        call_time = call_info['detected_at'].strftime('%Y-%m-%d %I:%M:%S %p')
        caption = (f"🔥 NEW CALL RECORDING 🔥\n\n"
                   f"⏰ Time: {call_time}\n"
                   f"{call_info['flag']} Country: {call_info['country']}\n"
                   f"📞 Number: {call_info['masked']}\n\n"
                   f"⚙️ Managed by professor_cry")
        if not send_voice_with_caption(file_path, caption):
            send_message(f"{caption}\n⚠️ Voice upload failed.")
    except Exception as e:
        print(f"[❌] File processing error: {e}")

# ==================== Browser ====================
def wait_for_login(driver):
    print(f"🔐 Open login page: {config.LOGIN_URL}")
    print("➡️ Please log in manually in the Chrome window...")
    try:
        WebDriverWait(driver, 600).until(
            lambda d: d.current_url.startswith(config.BASE_URL) and not d.current_url.startswith(config.LOGIN_URL)
        )
        print("✅ Login successful!")
        return True
    except TimeoutException:
        print("[❌] Login timeout")
        return False

def initialize_driver():
    options = uc.ChromeOptions()
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-gpu")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-notifications")
    return uc.Chrome(options=options)

# ==================== Main ====================
def main():
    driver = None
    try:
        driver = initialize_driver()
        driver.get(config.LOGIN_URL)
        if not wait_for_login(driver):
            return
        driver.get(config.CALL_URL)
        WebDriverWait(driver, 15).until(EC.presence_of_element_located((By.ID, "LiveCalls")))
        print("✅ Active Calls page loaded!")
        print("[*] Monitoring started...")

        last_check = datetime.now()
        while True:
            extract_calls(driver)
            if (datetime.now() - last_check).total_seconds() >= 10:
                process_pending_recordings(driver)
                last_check = datetime.now()
            time.sleep(config.CHECK_INTERVAL)

    except Exception as e:
        print(f"[💥] Fatal error: {e}")
    finally:
        if driver:
            driver.quit()
        print("[*] Monitoring stopped")

if __name__ == "__main__":
    main()
