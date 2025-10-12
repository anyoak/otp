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
from selenium.webdriver.common.action_chains import ActionChains
import phonenumbers
from phonenumbers import region_code_for_number
import pycountry
import config

# ---------------- Global Variables ---------------- #
active_calls = {}
processed_recordings = set()

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
                return True
            else:
                print(f"[❌] Failed to send voice: {response.status_code}")
                return False
    except Exception as e:
        print(f"[❌] Failed to send voice: {e}")
        return False

def get_authenticated_session(driver):
    """Create requests session with Selenium cookies"""
    session = requests.Session()
    selenium_cookies = driver.get_cookies()
    
    for cookie in selenium_cookies:
        session.cookies.set(cookie['name'], cookie['value'])
    
    return session

def click_play_button(driver, row):
    """Click the Play button for a specific call row"""
    try:
        # Find the Play button in the row (last cell)
        cells = row.find_elements(By.TAG_NAME, "td")
        if len(cells) >= 6:  # Check if there's a button cell
            play_button = cells[5].find_element(By.TAG_NAME, "button")
            if "Play" in play_button.text:
                # Scroll to the button
                driver.execute_script("arguments[0].scrollIntoView(true);", play_button)
                time.sleep(1)
                
                # Click using JavaScript to avoid interception
                driver.execute_script("arguments[0].click();", play_button)
                print("[▶️] Play button clicked")
                return True
    except Exception as e:
        print(f"[❌] Failed to click play button: {e}")
    return False

def download_recording_from_play(driver, call_id, did_number):
    """Download recording after clicking Play button"""
    try:
        # Wait for audio element to appear after clicking play
        print("[🎵] Waiting for audio player to load...")
        time.sleep(3)
        
        # Look for audio elements in the page
        audio_elements = driver.find_elements(By.TAG_NAME, "audio")
        audio_sources = driver.find_elements(By.CSS_SELECTOR, "audio source")
        
        recording_url = None
        
        # Check audio elements for src attribute
        for audio in audio_elements:
            src = audio.get_attribute("src")
            if src and "live/calls/sound" in src:
                recording_url = src
                break
        
        # Check source elements
        if not recording_url:
            for source in audio_sources:
                src = source.get_attribute("src")
                if src and "live/calls/sound" in src:
                    recording_url = src
                    break
        
        # If no audio element found, construct URL manually
        if not recording_url:
            recording_url = f"https://www.orangecarrier.com/live/calls/sound?did={did_number}&uuid={call_id}"
            print(f"[🔗] Using constructed URL: {recording_url}")
        else:
            print(f"[🔗] Found audio URL: {recording_url}")
        
        # Download the recording
        if recording_url:
            session = get_authenticated_session(driver)
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                'Referer': config.CALL_URL,
                'Accept': 'audio/mpeg, audio/*'
            }
            
            response = session.get(recording_url, headers=headers, timeout=60)
            
            if response.status_code == 200 and len(response.content) > 1000:
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                file_path = os.path.join(config.DOWNLOAD_FOLDER, f"call_{did_number}_{timestamp}.mp3")
                
                with open(file_path, "wb") as f:
                    f.write(response.content)
                
                print(f"[✅] Recording downloaded: {file_path} ({len(response.content)} bytes)")
                return file_path
            else:
                print(f"[❌] Download failed: HTTP {response.status_code}, Size: {len(response.content)}")
        
    except Exception as e:
        print(f"[❌] Error downloading from play: {e}")
    
    return None

# ---------------- Call Detection Functions ---------------- #
def extract_calls(driver):
    """Extract and process active calls from the website"""
    global active_calls, processed_recordings
    
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
                        f"📞 **নতুন কল ডিটেক্টেড!**\n"
                        f"🌍 **দেশ:** {country_name} {flag}\n"
                        f"📱 **নম্বর:** `{masked}`\n"
                        f"⏰ **সময়:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
                        f"🎙️ **কল রেকর্ডিং শুরু হয়েছে...**"
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
                        "last_seen": datetime.now(),
                        "play_attempted": False
                    }
                else:
                    # Update last seen time for existing call
                    active_calls[row_id]["last_seen"] = datetime.now()
                    
                    # If call is active and we haven't tried to play it yet, try to get recording
                    if (active_calls[row_id]["status"] == "active" and 
                        not active_calls[row_id]["play_attempted"] and
                        row_id not in processed_recordings):
                        
                        # Wait a bit for the call to establish
                        call_duration = datetime.now() - active_calls[row_id]["detected_at"]
                        if call_duration.total_seconds() > 10:  # Wait at least 10 seconds
                            print(f"[🎵] Attempting to get recording for call: {did_number}")
                            
                            # Try to click Play button and download recording
                            if click_play_button(driver, row):
                                time.sleep(2)  # Wait for player to load
                                file_path = download_recording_from_play(driver, row_id, did_number)
                                
                                if file_path:
                                    # Send recording to Telegram
                                    current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                                    caption = (
                                        f"📞 **কল রেকর্ডিং**\n"
                                        f"🌍 **দেশ:** {active_calls[row_id]['country']} {active_calls[row_id]['flag']}\n"
                                        f"📱 **নম্বর:** `{active_calls[row_id]['masked']}`\n"
                                        f"⏰ **সময়:** {current_time}"
                                    )
                                    
                                    if send_voice_with_caption(file_path, caption):
                                        processed_recordings.add(row_id)
                                        print(f"[✅] Recording sent successfully: {did_number}")
                                
                                active_calls[row_id]["play_attempted"] = True
                    
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
            # If call ID not in current rows OR last seen more than 60 seconds ago
            if (call_id not in current_call_ids) or \
               ((current_time - call_info["last_seen"]).total_seconds() > 60):
                print(f"[✅] Call completed: {call_info['did_number']}")
                completed_calls.append(call_id)
        
        # Process completed calls - try one final download attempt
        for call_id in completed_calls:
            if call_id not in processed_recordings:
                print(f"[🔄] Final attempt to download recording for: {active_calls[call_id]['did_number']}")
                # Try direct download for completed calls
                process_completed_call(driver, call_id)
            else:
                # Already processed, just clean up
                if call_id in active_calls:
                    del active_calls[call_id]
                
    except TimeoutException:
        print("[⏱️] Active calls table not found, waiting...")
    except Exception as e:
        print(f"[❌] Extract calls failed: {e}")

def process_completed_call(driver, call_id):
    """Process a completed call and try to download recording"""
    call_info = active_calls[call_id]
    
    try:
        # Try direct download first
        recording_url = f"https://www.orangecarrier.com/live/calls/sound?did={call_info['did_number']}&uuid={call_id}"
        print(f"[⬇️] Attempting direct download: {recording_url}")
        
        session = get_authenticated_session(driver)
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Referer': config.CALL_URL,
            'Accept': 'audio/mpeg, audio/*'
        }
        
        response = session.get(recording_url, headers=headers, timeout=60)
        
        if response.status_code == 200 and len(response.content) > 1000:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            file_path = os.path.join(config.DOWNLOAD_FOLDER, f"call_{call_info['did_number']}_{timestamp}.mp3")
            
            with open(file_path, "wb") as f:
                f.write(response.content)
            
            print(f"[✅] Direct download successful: {file_path}")
            
            # Send to Telegram
            current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            caption = (
                f"📞 **কল রেকর্ডিং**\n"
                f"🌍 **দেশ:** {call_info['country']} {call_info['flag']}\n"
                f"📱 **নম্বর:** `{call_info['masked']}`\n"
                f"⏰ **সময়:** {current_time}"
            )
            
            if send_voice_with_caption(file_path, caption):
                processed_recordings.add(call_id)
                print(f"[✅] Recording sent via direct download: {call_info['did_number']}")
        
        else:
            print(f"[❌] Direct download failed: HTTP {response.status_code}")
            
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
    
    # Important: Enable automatic downloads and set download directory
    prefs = {
        "download.default_directory": os.path.abspath(config.DOWNLOAD_FOLDER),
        "download.prompt_for_download": False,
        "download.directory_upgrade": True,
        "safebrowsing.enabled": True,
        "profile.default_content_setting_values.automatic_downloads": 1
    }
    chrome_options.add_experimental_option("prefs", prefs)
    
    # For debugging, run in non-headless mode
    # chrome_options.add_argument("--headless")  # Remove this line for debugging
    
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
