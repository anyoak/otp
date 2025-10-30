import time
import re
import requests
import os
from datetime import datetime
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, StaleElementReferenceException
import phonenumbers
from phonenumbers import region_code_for_number
import pycountry
import config

# ======================== TOR / Proxy Setup ========================
TOR_PROXY = "socks5h://127.0.0.1:9050"  # Tor default SOCKS5 proxy

def requests_get(url, **kwargs):
    proxies = {"http": TOR_PROXY, "https": TOR_PROXY}
    return requests.get(url, proxies=proxies, **kwargs)

def requests_post(url, **kwargs):
    proxies = {"http": TOR_PROXY, "https": TOR_PROXY}
    return requests.post(url, proxies=proxies, **kwargs)

# ======================== Global Variables ========================
active_calls = {}
pending_recordings = {}

os.makedirs(config.DOWNLOAD_FOLDER, exist_ok=True)

# ======================== Helper Functions ========================
def country_to_flag(country_code):
    if not country_code or len(country_code) != 2:
        return "🏳️"
    return "".join(chr(127397 + ord(c)) for c in country_code.upper())

def detect_country(number):
    try:
        clean_number = re.sub(r"\D", "", number)
        if clean_number:
            parsed = phonenumbers.parse("+" + clean_number, None)
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
        payload = {"chat_id": config.CHAT_ID, "text": text, "parse_mode": "Markdown"}
        res = requests_post(url, json=payload, timeout=10)
        if res.ok:
            return res.json().get("result", {}).get("message_id")
    except Exception as e:
        print(f"[❌] Failed to send message: {e}")
    return None

def delete_message(msg_id):
    try:
        url = f"https://api.telegram.org/bot{config.BOT_TOKEN}/deleteMessage"
        requests_post(url, data={"chat_id": config.CHAT_ID, "message_id": msg_id}, timeout=5)
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
            response = requests_post(url, data=payload, files=files, timeout=60)
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
    selenium_cookies = driver.get_cookies()
    for cookie in selenium_cookies:
        session.cookies.set(cookie['name'], cookie['value'])
    session.proxies = {"http": TOR_PROXY, "https": TOR_PROXY}  # Tor proxy for requests
    return session

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
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Referer': config.CALL_URL,
            'Accept': 'audio/mpeg, audio/*'
        }
        for attempt in range(3):
            response = session.get(recording_url, headers=headers, timeout=30, stream=True)
            print(f"[DEBUG] Attempt {attempt+1} - Status: {response.status_code}, Length: {response.headers.get('Content-Length', '0')}")
            if response.status_code == 200 and int(response.headers.get('Content-Length', 0)) > 1000:
                with open(file_path, "wb") as f:
                    for chunk in response.iter_content(chunk_size=8192):
                        if chunk:
                            f.write(chunk)
                print(f"[✅] Recording downloaded: {os.path.getsize(file_path)} bytes")
                return True
            time.sleep(5)
        return False
    except Exception as e:
        print(f"[❌] Download failed: {e}")
        if os.path.exists(file_path):
            os.remove(file_path)
        return False

# ======================== Call Extraction ========================
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
                did_element = cells[1]
                did_text = did_element.text.strip()
                did_number = re.sub(r"\D", "", did_text)
                if not did_number: continue
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
        current_time = datetime.now()
        completed_calls = []
        for call_id, call_info in list(active_calls.items()):
            if (call_id not in current_call_ids) or ((current_time - call_info["last_seen"]).total_seconds() > 15):
                if call_id not in pending_recordings:
                    print(f"[✅] Call completed: {call_info['did_number']}")
                    completed_calls.append(call_id)
        for call_id in completed_calls:
            call_info = active_calls[call_id]
            pending_recordings[call_id] = {**call_info, "completed_at": datetime.now(), "checks": 0, "last_check": datetime.now()}
            wait_text = f"{call_info['flag']} {call_info['masked']} — The call record for this number is currently being processed."
            if call_info["msg_id"]:
                delete_message(call_info["msg_id"])
            new_msg_id = send_message(wait_text)
            if new_msg_id:
                pending_recordings[call_id]["msg_id"] = new_msg_id
            del active_calls[call_id]
    except TimeoutException:
        print("[⏱️] No active calls table")
    except Exception as e:
        print(f"[❌] Extract error: {e}")

# ======================== Pending Recordings ========================
def process_pending_recordings(driver):
    global pending_recordings
    current_time = datetime.now()
    processed_calls = []
    for call_id, call_info in list(pending_recordings.items()):
        try:
            time_since_check = (current_time - call_info["last_check"]).total_seconds()
            if time_since_check < config.RECORDING_RETRY_DELAY:
                continue
            call_info["checks"] += 1
            call_info["last_check"] = current_time
            print(f"[🔍] Check #{call_info['checks']} for: {call_info['did_number']}")
            if call_info["checks"] > 10:
                print("[⏰] Max checks exceeded")
                timeout_text = f"❌ Max checks exceeded for {call_info['flag']} {call_info['masked']}"
                if call_info.get("msg_id"):
                    delete_message(call_info["msg_id"])
                send_message(timeout_text)
                processed_calls.append(call_id)
                continue
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            file_path = os.path.join(config.DOWNLOAD_FOLDER, f"call_{call_info['did_number']}_{timestamp}.mp3")
            if download_recording(driver, call_info['did_number'], call_id, file_path):
                process_recording_file(call_info, file_path)
                processed_calls.append(call_id)
            else:
                print(f"[❌] Recording not available: {call_info['did_number']}")
            time_since_complete = (current_time - call_info["completed_at"]).total_seconds()
            if time_since_complete > config.MAX_RECORDING_WAIT:
                print(f"[⏰] Timeout: {call_info['did_number']}")
                timeout_text = f"❌ Recording timeout for {call_info['flag']} {call_info['masked']}"
                if call_info.get("msg_id"):
                    delete_message(call_info["msg_id"])
                send_message(timeout_text)
                processed_calls.append(call_id)
        except Exception as e:
            print(f"[❌] Processing error: {e}")
    for call_id in processed_calls:
        if call_id in pending_recordings:
            del pending_recordings[call_id]

def process_recording_file(call_info, file_path):
    try:
        if call_info.get("msg_id"):
            delete_message(call_info["msg_id"])
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
        print(f"[❌] File processing error: {e}")
        send_message(f"❌ Processing error for {call_info['flag']} {call_info['masked']}")

def wait_for_login(driver):
    print(f"🔐 Login page: {config.LOGIN_URL}")
    print("➡️ Please login in browser...")
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
    chrome_options = Options()
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--disable-notifications")
    chrome_options.add_argument("--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36")
    chrome_options.add_experimental_option("excludeSwitches", ["enable-logging"])
    chrome_options.add_argument("--window-size=1200,800")
    chrome_options.add_argument("--proxy-server=socks5://127.0.0.1:9050")  # TOR Proxy
    return webdriver.Chrome(options=chrome_options)

# ======================== Main Loop ========================
def main():
    driver = None
    try:
        driver = initialize_driver()
        driver.get(config.LOGIN_URL)
        
        # Login
        if not wait_for_login(driver):
            return
        
        # Go to Calls page
        driver.get(config.CALL_URL)
        WebDriverWait(driver, 15).until(EC.presence_of_element_located((By.ID, "LiveCalls")))
        print("✅ Active Calls page loaded!")
        print("[*] Monitoring started...")

        error_count = 0
        last_recording_check = datetime.now()
        last_refresh = datetime.now()  # Track last page refresh
        
        while error_count < config.MAX_ERRORS:
            try:
                # Refresh page every 30 minutes to maintain session
                if (datetime.now() - last_refresh).total_seconds() > 1800:
                    driver.refresh()
                    WebDriverWait(driver, 15).until(EC.presence_of_element_located((By.ID, "LiveCalls")))
                    last_refresh = datetime.now()
                    print("[🔄] Page refreshed to maintain session")
                
                # Check if session expired
                if config.LOGIN_URL in driver.current_url:
                    print("[⚠️] Session expired, re-logging in")
                    if not wait_for_login(driver):
                        break
                    driver.get(config.CALL_URL)
                
                # Extract active calls
                extract_calls(driver)
                
                # Process pending recordings every 10 seconds
                current_time = datetime.now()
                if (current_time - last_recording_check).total_seconds() >= 10:
                    process_pending_recordings(driver)
                    last_recording_check = current_time
                
                # Reset error count if everything is fine
                error_count = 0
                time.sleep(config.CHECK_INTERVAL)
                
            except KeyboardInterrupt:
                print("\n[🛑] Stopped by user")
                break
            except Exception as e:
                error_count += 1
                print(f"[❌] Main loop error ({error_count}/{config.MAX_ERRORS}): {e}")
                time.sleep(5)
                
    except Exception as e:
        print(f"[💥] Fatal error: {e}")
    finally:
        if driver:
            driver.quit()
        print("[*] Monitoring stopped")

if __name__ == "__main__":
    main()
