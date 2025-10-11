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
from openai import OpenAI
import config

# ---------------- Global Variables ---------------- #
active_calls = {}
client = OpenAI(api_key=config.OPENAI_API_KEY)

# Create downloads directory if it doesn't exist
os.makedirs(config.DOWNLOAD_FOLDER, exist_ok=True)

# ---------------- Helper Functions ---------------- #
def country_to_flag(country_code: str) -> str:
    """Convert country code to flag emoji"""
    if not country_code or len(country_code) != 2:
        return "🏳️"
    return "".join(chr(127397 + ord(c)) for c in country_code.upper())

def detect_country(number: str):
    """Detect country from phone number"""
    try:
        clean_number = re.sub(r"\D", "", number)
        if clean_number:
            parsed = phonenumbers.parse("+" + clean_number, None)
            region = region_code_for_number(parsed)
            country = pycountry.countries.get(alpha_2=region)
            if country:
                return country.name, country_to_flag(region)
    except Exception as e:
        print(f"[🌍] Country detection failed for {number}: {e}")
    return "Unknown", "🏳️"

def mask_number(number: str) -> str:
    """Mask phone number for privacy"""
    digits = re.sub(r"\D", "", number)
    if len(digits) > 6:
        return digits[:4] + "****" + digits[-3:]
    return number

def extract_otp(text: str) -> str:
    """Extract OTP codes from text"""
    patterns = [
        r'\b\d{4,6}\b',
        r'code[\s:]*(\d{4,6})',
        r'password[\s:]*(\d{4,6})',
        r'verification[\s:]*(\d{4,6})',
        r'otp[\s:]*(\d{4,6})',
        r'pin[\s:]*(\d{4,6})'
    ]
    
    for pattern in patterns:
        matches = re.findall(pattern, text, re.IGNORECASE)
        if matches:
            return matches[0]
    return "N/A"

def send_message(text: str):
    """Send message to Telegram"""
    try:
        url = f"https://api.telegram.org/bot{config.BOT_TOKEN}/sendMessage"
        payload = {"chat_id": config.CHAT_ID, "text": text, "parse_mode": "Markdown"}
        res = requests.post(url, json=payload, timeout=10)
        if res.ok:
            return res.json().get("result", {}).get("message_id")
    except Exception as e:
        print(f"[❌] Failed to send message: {e}")
    return None

def delete_message(msg_id):
    """Delete Telegram message"""
    try:
        url = f"https://api.telegram.org/bot{config.BOT_TOKEN}/deleteMessage"
        requests.post(url, data={"chat_id": config.CHAT_ID, "message_id": msg_id}, timeout=5)
    except Exception as e:
        print(f"[❌] Failed to delete message: {e}")

def send_voice_with_caption(voice_path, caption):
    """Send voice recording with caption to Telegram"""
    try:
        url = f"https://api.telegram.org/bot{config.BOT_TOKEN}/sendVoice"
        with open(voice_path, "rb") as voice:
            payload = {"chat_id": config.CHAT_ID, "caption": caption, "parse_mode": "Markdown"}
            files = {"voice": voice}
            response = requests.post(url, data=payload, files=files, timeout=60)
            if response.status_code == 200:
                print(f"[✅] Voice message sent successfully")
            else:
                print(f"[❌] Failed to send voice: {response.status_code}")
    except Exception as e:
        print(f"[❌] Failed to send voice: {e}")

def transcribe_voice(file_path):
    """Transcribe voice recording using OpenAI"""
    try:
        with open(file_path, "rb") as audio:
            result = client.audio.transcriptions.create(
                model="whisper-1",
                file=audio,
                response_format="text",
                language="en"
            )
        return result.strip()
    except Exception as e:
        print(f"[❌] Transcription failed: {e}")
        return ""

def get_authenticated_session(driver):
    """Create requests session with Selenium cookies"""
    session = requests.Session()
    selenium_cookies = driver.get_cookies()
    
    for cookie in selenium_cookies:
        session.cookies.set(cookie['name'], cookie['value'])
    
    return session

# ---------------- Call Detection Functions ---------------- #
def extract_calls(driver):
    """Extract and process active calls from the website"""
    global active_calls
    
    try:
        # Wait for the active calls table
        calls_table = WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.ID, "LiveCalls"))
        )
        
        # Get all rows from the table
        rows = calls_table.find_elements(By.TAG_NAME, "tr")
        current_call_ids = set()
        
        for row in rows:
            try:
                # Get row ID (UUID) and cells
                row_id = row.get_attribute('id')
                if not row_id:
                    continue
                    
                cells = row.find_elements(By.TAG_NAME, "td")
                if len(cells) < 5:  # Should have at least 5 cells
                    continue
                
                # Extract DID from second cell (index 1)
                did_element = cells[1]
                did_text = did_element.text.strip()
                did_number = re.sub(r"\D", "", did_text)
                
                if not did_number:
                    continue
                
                current_call_ids.add(row_id)
                
                # Check if this is a new call
                if row_id not in active_calls:
                    print(f"[📞] New call detected: {did_number} (UUID: {row_id})")
                    
                    country_name, flag = detect_country(did_number)
                    masked = mask_number(did_number)
                    
                    alert_text = (
                        f"📞 **New Call Alert!**\n"
                        f"🔗 **Location:** {country_name} {flag}\n"
                        f"✨ **DID Number:** `{masked}`\n"
                        f"📋 **Original:** `{did_text}`\n\n"
                        f"☎️ **Your call is currently being recorded...**\n"
                        f"⏳ Please wait — the recording will be sent once ready."
                    )
                    
                    msg_id = send_message(alert_text)
                    active_calls[row_id] = {
                        "msg_id": msg_id,
                        "flag": flag,
                        "country": country_name,
                        "masked": masked,
                        "did_number": did_number,
                        "original_text": did_text,
                        "detected_at": datetime.now(),
                        "status": "active",
                        "last_seen": datetime.now()
                    }
                else:
                    # Update last seen time for existing call
                    active_calls[row_id]["last_seen"] = datetime.now()
                    
            except StaleElementReferenceException:
                print("[⚠️] Stale element, skipping row")
                continue
            except Exception as e:
                print(f"[❌] Error processing row: {e}")
                continue
        
        # Check for completed calls (rows that disappeared or haven't been seen for a while)
        current_time = datetime.now()
        completed_calls = []
        
        for call_id, call_info in list(active_calls.items()):
            # If call ID not in current rows OR last seen more than 30 seconds ago
            if (call_id not in current_call_ids) or \
               ((current_time - call_info["last_seen"]).total_seconds() > 30):
                print(f"[✅] Call completed: {call_info['did_number']}")
                completed_calls.append(call_id)
        
        # Process completed calls
        for call_id in completed_calls:
            process_completed_call(driver, call_id)
                
    except TimeoutException:
        print("[⏱️] Active calls table not found, waiting...")
    except Exception as e:
        print(f"[❌] Extract calls failed: {e}")

def process_completed_call(driver, call_id):
    """Process a completed call and download recording"""
    call_info = active_calls[call_id]
    
    try:
        # Construct recording URL based on website JavaScript
        recording_url = f"https://www.orangecarrier.com/live/calls/sound?did={call_info['did_number']}&uuid={call_id}"
        print(f"[⬇️] Downloading recording from: {recording_url}")
        
        # Get authenticated session
        session = get_authenticated_session(driver)
        
        # Download recording
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Referer': config.CALL_URL,
            'Accept': 'audio/mpeg, audio/*'
        }
        
        response = session.get(recording_url, headers=headers, timeout=60)
        
        if response.status_code == 200 and len(response.content) > 1000:  # Basic validation
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            file_path = os.path.join(config.DOWNLOAD_FOLDER, f"call_{call_info['did_number']}_{timestamp}.mp3")
            
            with open(file_path, "wb") as f:
                f.write(response.content)
            
            print(f"[✅] Recording saved: {file_path} ({len(response.content)} bytes)")
            
            # Transcribe and process
            print("[🎙️] Transcribing recording...")
            text = transcribe_voice(file_path)
            otp_code = extract_otp(text)
            
            # Delete initial alert
            if call_info["msg_id"]:
                delete_message(call_info["msg_id"])
            
            # Send final report
            call_duration = datetime.now() - call_info['detected_at']
            duration_str = f"{call_duration.seconds // 60}:{call_duration.seconds % 60:02d}"
            
            caption = (
                f"🎧 **Call Recording Received!**\n\n"
                f"🌍 **Country:** {call_info['country']} {call_info['flag']}\n"
                f"📞 **DID Number:** `{call_info['masked']}`\n"
                f"🔐 **Detected OTP:** `{otp_code}`\n"
                f"⏰ **Call Duration:** {duration_str}\n\n"
                f"🗣️ **Transcribed Text:**\n"
                f"```{text if text else 'No speech detected'}```"
            )
            
            send_voice_with_caption(file_path, caption)
            print(f"[✅] Call processing completed: {call_info['did_number']}")
            
        else:
            print(f"[❌] Failed to download recording: HTTP {response.status_code}, Size: {len(response.content)}")
            
    except Exception as e:
        print(f"[❌] Failed to process completed call: {e}")
    
    # Clean up
    finally:
        if call_id in active_calls:
            del active_calls[call_id]

def wait_for_login(driver):
    """Wait for user to complete login manually"""
    print(f"🔐 Login page opened: {config.LOGIN_URL}")
    print("➡️ Please login manually in the browser window...")
    print("⏳ Waiting for login to complete...")

    try:
        MAX_LOGIN_WAIT = 600  # 10 minutes
        WebDriverWait(driver, MAX_LOGIN_WAIT).until(
            lambda d: d.current_url.startswith(config.BASE_URL) and not d.current_url.startswith(config.LOGIN_URL)
        )
        print("✅ Login successful!")
        return True
    except TimeoutException:
        print(f"[❌] Login not detected within {MAX_LOGIN_WAIT} seconds")
        return False

def initialize_driver():
    """Initialize and configure Chrome driver"""
    chrome_options = Options()
    
    # Basic options
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--disable-notifications")
    chrome_options.add_argument("--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36")
    chrome_options.add_experimental_option("excludeSwitches", ["enable-logging"])
    
    # Optional: Run in headless mode (uncomment for production)
    # chrome_options.add_argument("--headless")
    
    # Optional: Set window size
    chrome_options.add_argument("--window-size=1200,800")
    
    return webdriver.Chrome(options=chrome_options)

# ---------------- Main Function ---------------- #
def main():
    """Main function to run the call monitoring system"""
    driver = None
    
    try:
        # Initialize driver
        driver = initialize_driver()
        
        # Login process
        driver.get(config.LOGIN_URL)
        
        if not wait_for_login(driver):
            return
        
        # Navigate to calls page
        print("🔄 Navigating to Active Calls page...")
        driver.get(config.CALL_URL)
        
        # Verify we're on the right page
        WebDriverWait(driver, 15).until(
            EC.presence_of_element_located((By.ID, "LiveCalls"))
        )
        print("✅ Active Calls page loaded successfully!")
        print(f"[*] Call Tracker started. Monitoring Active Calls at: {config.CALL_URL}")
        print("[*] Press Ctrl+C to stop monitoring...")

        # Main monitoring loop
        error_count = 0
        
        while error_count < config.MAX_ERRORS:
            try:
                extract_calls(driver)
                error_count = 0  # Reset error count on success
                time.sleep(config.CHECK_INTERVAL)
                
            except KeyboardInterrupt:
                print("\n[🛑] Stopped by user.")
                break
            except Exception as e:
                error_count += 1
                print(f"[❌] Error in main loop ({error_count}/{config.MAX_ERRORS}): {e}")
                time.sleep(5)
                
        if error_count >= config.MAX_ERRORS:
            print("[💥] Too many errors, stopping monitor...")
            
    except Exception as e:
        print(f"[💥] Fatal error: {e}")
    finally:
        if driver:
            driver.quit()
            print("[*] Browser closed.")
        print("[*] Call monitoring stopped.")

if __name__ == "__main__":
    main()