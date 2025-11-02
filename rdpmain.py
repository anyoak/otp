import time
import re
import requests
import os
import sys
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

try:
    import config
except ImportError:
    print("❌ config.py file not found! Please create config.py first.")
    sys.exit(1)

# Global variables
active_calls = {}
pending_recordings = {}

# Create download folder
os.makedirs(config.DOWNLOAD_FOLDER, exist_ok=True)

def setup_directories():
    """Ensure all necessary directories exist"""
    directories = [
        config.DOWNLOAD_FOLDER,
        "logs",
        "screenshots"
    ]
    for directory in directories:
        os.makedirs(directory, exist_ok=True)

def setup_logging():
    """Setup basic logging for Windows"""
    import logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler('logs/monitor.log', encoding='utf-8'),
            logging.StreamHandler()
        ]
    )
    return logging.getLogger(__name__)

logger = setup_logging()

def country_to_flag(country_code):
    """Convert country code to flag emoji"""
    if not country_code or len(country_code) != 2:
        return "🏳️"
    return "".join(chr(127397 + ord(c)) for c in country_code.upper())

def detect_country(number):
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
        logger.error(f"Country detection error: {e}")
    return "Unknown", "🏳️"

def mask_number(number):
    """Mask phone number for privacy"""
    digits = re.sub(r"\D", "", number)
    if len(digits) > 6:
        return digits[:4] + "****" + digits[-3:]
    return number

def send_message(text):
    """Send message to Telegram"""
    try:
        url = f"https://api.telegram.org/bot{config.BOT_TOKEN}/sendMessage"
        payload = {"chat_id": config.CHAT_ID, "text": text, "parse_mode": "Markdown"}
        res = requests.post(url, json=payload, timeout=10)
        if res.ok:
            return res.json().get("result", {}).get("message_id")
    except Exception as e:
        logger.error(f"Failed to send message: {e}")
    return None

def delete_message(msg_id):
    """Delete Telegram message"""
    try:
        url = f"https://api.telegram.org/bot{config.BOT_TOKEN}/deleteMessage"
        requests.post(url, data={"chat_id": config.CHAT_ID, "message_id": msg_id}, timeout=5)
    except Exception as e:
        logger.error(f"Failed to delete message: {e}")

def send_voice_with_caption(voice_path, caption):
    """Send voice recording to Telegram"""
    try:
        if not os.path.exists(voice_path) or os.path.getsize(voice_path) < 1000:
            logger.error("File too small or empty")
            return False
            
        url = f"https://api.telegram.org/bot{config.BOT_TOKEN}/sendVoice"
        with open(voice_path, "rb") as voice:
            payload = {"chat_id": config.CHAT_ID, "caption": caption, "parse_mode": "HTML"}
            files = {"voice": voice}
            response = requests.post(url, data=payload, files=files, timeout=60)
            time.sleep(2)
            if response.status_code == 200:
                return True
            else:
                logger.error(f"Telegram response: {response.status_code} - {response.text}")
    except Exception as e:
        logger.error(f"Failed to send voice: {e}")
    return False

def get_authenticated_session(driver):
    """Get authenticated session from Selenium cookies"""
    session = requests.Session()
    selenium_cookies = driver.get_cookies()
    for cookie in selenium_cookies:
        session.cookies.set(cookie['name'], cookie['value'])
    return session

def construct_recording_url(did_number, call_uuid):
    """Construct recording URL"""
    return f"https://www.orangecarrier.com/live/calls/sound?did={did_number}&uuid={call_uuid}"

def simulate_play_button(driver, did_number, call_uuid):
    """Simulate play button click using JavaScript"""
    try:
        script = f'window.Play("{did_number}", "{call_uuid}"); return "Play executed";'
        result = driver.execute_script(script)
        logger.info(f"Play button simulated: {did_number} - {result}")
        return True
    except Exception as e:
        logger.error(f"Play simulation failed: {e}")
        return False

def download_recording(driver, did_number, call_uuid, file_path):
    """Download recording file"""
    try:
        # First simulate the play button
        if not simulate_play_button(driver, did_number, call_uuid):
            return False
            
        time.sleep(8)  # Increased wait time for Windows
        
        recording_url = construct_recording_url(did_number, call_uuid)
        session = get_authenticated_session(driver)
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36',
            'Referer': config.CALL_URL,
            'Accept': 'audio/mpeg, audio/*',
            'Accept-Language': 'en-US,en;q=0.9',
            'Connection': 'keep-alive'
        }
        
        for attempt in range(3):
            try:
                logger.info(f"Download attempt {attempt+1} for {did_number}")
                response = session.get(recording_url, headers=headers, timeout=30, stream=True)
                
                if response.status_code == 200:
                    content_length = int(response.headers.get('Content-Length', 0))
                    logger.info(f"Response status: {response.status_code}, Size: {content_length} bytes")
                    
                    if content_length > 1000:
                        with open(file_path, "wb") as f:
                            for chunk in response.iter_content(chunk_size=8192):
                                if chunk:
                                    f.write(chunk)
                        
                        file_size = os.path.getsize(file_path)
                        logger.info(f"Recording downloaded: {file_size} bytes")
                        
                        if file_size > 1000:
                            return True
                        else:
                            logger.warning("Downloaded file too small")
                    else:
                        logger.warning("Content too small")
                else:
                    logger.warning(f"HTTP {response.status_code}")
                    
            except Exception as e:
                logger.error(f"Download attempt {attempt+1} failed: {e}")
            
            time.sleep(5)
            
        return False
        
    except Exception as e:
        logger.error(f"Download failed: {e}")
        if os.path.exists(file_path):
            try:
                os.remove(file_path)
            except:
                pass
        return False

def take_screenshot(driver, name):
    """Take screenshot for debugging"""
    try:
        screenshot_path = f"screenshots/{name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
        driver.save_screenshot(screenshot_path)
        logger.info(f"Screenshot saved: {screenshot_path}")
    except Exception as e:
        logger.error(f"Screenshot failed: {e}")

def extract_calls(driver):
    """Extract call information from the page"""
    global active_calls, pending_recordings
    
    try:
        # Wait for calls table
        calls_table = WebDriverWait(driver, 15).until(
            EC.presence_of_element_located((By.ID, "LiveCalls"))
        )
        
        rows = calls_table.find_elements(By.TAG_NAME, "tr")
        current_call_ids = set()
        
        for row in rows:
            try:
                row_id = row.get_attribute('id')
                if not row_id or 'call_' not in row_id:
                    continue
                    
                cells = row.find_elements(By.TAG_NAME, "td")
                if len(cells) < 5:
                    continue
                
                # Extract phone number from second cell
                did_element = cells[1]
                did_text = did_element.text.strip()
                did_number = re.sub(r"\D", "", did_text)
                
                if not did_number:
                    continue
                
                current_call_ids.add(row_id)
                
                if row_id not in active_calls:
                    logger.info(f"New call detected: {did_number}")
                    
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
                    
                    # Take screenshot of new call
                    take_screenshot(driver, f"new_call_{did_number}")
                    
                else:
                    active_calls[row_id]["last_seen"] = datetime.now()
                    
            except StaleElementReferenceException:
                continue
            except Exception as e:
                logger.error(f"Row processing error: {e}")
                continue
        
        # Check for completed calls
        current_time = datetime.now()
        completed_calls = []
        
        for call_id, call_info in list(active_calls.items()):
            if (call_id not in current_call_ids) or \
               ((current_time - call_info["last_seen"]).total_seconds() > 20):  # Increased timeout
                if call_id not in pending_recordings:
                    logger.info(f"Call completed: {call_info['did_number']}")
                    completed_calls.append(call_id)
        
        # Process completed calls
        for call_id in completed_calls:
            call_info = active_calls[call_id]
            
            pending_recordings[call_id] = {
                **call_info,
                "completed_at": datetime.now(),
                "checks": 0,
                "last_check": datetime.now()
            }
            
            wait_text = f"{call_info['flag']} {call_info['masked']} — The call record for this number is currently being processed."
            
            if call_info["msg_id"]:
                delete_message(call_info["msg_id"])
            
            new_msg_id = send_message(wait_text)
            if new_msg_id:
                pending_recordings[call_id]["msg_id"] = new_msg_id
            
            del active_calls[call_id]
                
    except TimeoutException:
        logger.warning("No active calls table found")
    except Exception as e:
        logger.error(f"Call extraction error: {e}")
        take_screenshot(driver, "extraction_error")

def process_pending_recordings(driver):
    """Process pending recordings"""
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
            
            logger.info(f"Check #{call_info['checks']} for recording: {call_info['did_number']}")
            
            # Max checks limit
            if call_info["checks"] > 15:  # Increased max checks
                logger.warning(f"Max checks exceeded for: {call_info['did_number']}")
                timeout_text = f"❌ Max checks exceeded for {call_info['flag']} {call_info['masked']}"
                if call_info.get("msg_id"):
                    delete_message(call_info["msg_id"])
                send_message(timeout_text)
                processed_calls.append(call_id)
                continue
            
            # Download recording
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            file_path = os.path.join(config.DOWNLOAD_FOLDER, f"call_{call_info['did_number']}_{timestamp}.mp3")
            
            if download_recording(driver, call_info['did_number'], call_id, file_path):
                process_recording_file(call_info, file_path)
                processed_calls.append(call_id)
            else:
                logger.warning(f"Recording not available yet: {call_info['did_number']}")
            
            # Check if recording wait timeout exceeded
            time_since_complete = (current_time - call_info["completed_at"]).total_seconds()
            if time_since_complete > config.MAX_RECORDING_WAIT:
                logger.warning(f"Recording timeout for: {call_info['did_number']}")
                timeout_text = f"❌ Recording timeout for {call_info['flag']} {call_info['masked']}"
                
                if call_info.get("msg_id"):
                    delete_message(call_info["msg_id"])
                
                send_message(timeout_text)
                processed_calls.append(call_id)
                
        except Exception as e:
            logger.error(f"Recording processing error: {e}")
    
    # Clean up processed calls
    for call_id in processed_calls:
        if call_id in pending_recordings:
            del pending_recordings[call_id]

def process_recording_file(call_info, file_path):
    """Process and send recording file"""
    try:
        # Delete wait message
        if call_info.get("msg_id"):
            delete_message(call_info["msg_id"])
        
        # Format call time
        call_time = call_info['detected_at'].strftime('%Y-%m-%d %I:%M:%S %p')
        
        # Create caption
        caption = (
            "🔥 NEW CALL RECEIVED ✨\n\n"
            f"⏰ Time: {call_time}\n"
            f"{call_info['flag']} Country: {call_info['country']}\n"
            f"🚀 Number: {call_info['masked']}\n\n"
            f"🌟 Configure by @professor_cry"
        )
        
        # Send recording
        if send_voice_with_caption(file_path, caption):
            logger.info(f"Recording sent successfully: {call_info['did_number']}")
            
            # Clean up local file after sending
            try:
                os.remove(file_path)
                logger.info("Local file cleaned up")
            except Exception as e:
                logger.warning(f"File cleanup failed: {e}")
        else:
            # Fallback with error message
            error_caption = caption + "\n\n⚠️ Voice file failed to upload. Check server connection."
            send_message(error_caption)
            logger.error("Voice file sending failed")
            
    except Exception as e:
        logger.error(f"File processing error: {e}")
        error_text = f"❌ Processing error for {call_info['flag']} {call_info['masked']}"
        send_message(error_text)

def wait_for_login(driver):
    """Wait for user to login manually"""
    logger.info(f"Login page: {config.LOGIN_URL}")
    logger.info("Please login manually in the browser window...")
    
    try:
        # Wait for URL to change from login page (max 10 minutes)
        WebDriverWait(driver, 600).until(
            lambda d: d.current_url.startswith(config.BASE_URL) and not d.current_url.startswith(config.LOGIN_URL)
        )
        logger.info("Login successful! Redirecting to calls page...")
        return True
    except TimeoutException:
        logger.error("Login timeout - user did not login within 10 minutes")
        return False

def initialize_driver():
    """Initialize Chrome driver for Windows"""
    chrome_options = Options()
    
    # Windows RDP optimized settings
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--disable-notifications")
    chrome_options.add_argument("--disable-extensions")
    chrome_options.add_argument("--disable-blink-features=AutomationControlled")
    chrome_options.add_experimental_option("excludeSwitches", ["enable-automation", "enable-logging"])
    chrome_options.add_experimental_option('useAutomationExtension', False)
    
    # User agent and window settings
    chrome_options.add_argument("--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36")
    chrome_options.add_argument("--window-size=1200,800")
    chrome_options.add_argument("--log-level=3")  # Reduce logging noise
    
    # Auto-download ChromeDriver
    try:
        from webdriver_manager.chrome import ChromeDriverManager
        from selenium.webdriver.chrome.service import Service
        
        service = Service(ChromeDriverManager().install())
        driver = webdriver.Chrome(service=service, options=chrome_options)
        
    except ImportError:
        # Fallback to system ChromeDriver
        logger.warning("webdriver-manager not available, using system ChromeDriver")
        driver = webdriver.Chrome(options=chrome_options)
    
    # Additional anti-detection
    driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
    
    return driver

def check_telegram_connection():
    """Check Telegram bot connection"""
    try:
        test_msg = "🤖 Call Monitor Started Successfully!\n\n" \
                  "📍 System: Windows RDP\n" \
                  "⏰ Time: " + datetime.now().strftime("%Y-%m-%d %I:%M:%S %p") + "\n" \
                  "✅ Monitoring calls..."
        
        msg_id = send_message(test_msg)
        if msg_id:
            logger.info("Telegram connection test: SUCCESS")
            return True
        else:
            logger.error("Telegram connection test: FAILED")
            return False
    except Exception as e:
        logger.error(f"Telegram connection error: {e}")
        return False

def main():
    """Main monitoring function"""
    logger.info("Starting Call Monitoring System...")
    
    # Setup directories
    setup_directories()
    
    # Check Telegram connection
    if not check_telegram_connection():
        logger.error("Cannot start without Telegram connection")
        return
    
    driver = None
    try:
        # Initialize driver
        logger.info("Initializing Chrome driver...")
        driver = initialize_driver()
        
        # Navigate to login page
        driver.get(config.LOGIN_URL)
        
        # Wait for manual login
        if not wait_for_login(driver):
            return
        
        # Navigate to calls page
        driver.get(config.CALL_URL)
        WebDriverWait(driver, 20).until(
            EC.presence_of_element_located((By.ID, "LiveCalls"))
        )
        logger.info("Active Calls page loaded successfully!")
        
        # Take initial screenshot
        take_screenshot(driver, "calls_page_loaded")
        
        logger.info("🎯 Monitoring started - Waiting for calls...")
        
        # Monitoring loop
        error_count = 0
        last_recording_check = datetime.now()
        last_refresh = datetime.now()
        last_health_check = datetime.now()
        
        while error_count < config.MAX_ERRORS:
            try:
                current_time = datetime.now()
                
                # Health check every 5 minutes
                if (current_time - last_health_check).total_seconds() > 300:
                    logger.info("System health check: OK")
                    last_health_check = current_time
                
                # Refresh page every 30 minutes to maintain session
                if (current_time - last_refresh).total_seconds() > 1800:
                    logger.info("Refreshing page to maintain session...")
                    driver.refresh()
                    WebDriverWait(driver, 20).until(
                        EC.presence_of_element_located((By.ID, "LiveCalls"))
                    )
                    last_refresh = current_time
                    take_screenshot(driver, "page_refresh")
                
                # Check if still logged in
                if config.LOGIN_URL in driver.current_url:
                    logger.warning("Session expired, redirecting to login...")
                    send_message("🔐 Session expired! Please login again.")
                    if not wait_for_login(driver):
                        break
                    driver.get(config.CALL_URL)
                
                # Extract and process calls
                extract_calls(driver)
                
                # Process pending recordings
                if (current_time - last_recording_check).total_seconds() >= 10:
                    process_pending_recordings(driver)
                    last_recording_check = current_time
                
                error_count = 0  # Reset error count on successful iteration
                time.sleep(config.CHECK_INTERVAL)
                
            except KeyboardInterrupt:
                logger.info("Monitoring stopped by user")
                send_message("🛑 Monitoring stopped by user")
                break
            except Exception as e:
                error_count += 1
                logger.error(f"Main loop error ({error_count}/{config.MAX_ERRORS}): {e}")
                
                # Take screenshot on error
                take_screenshot(driver, f"error_{error_count}")
                
                if error_count >= config.MAX_ERRORS:
                    send_message("💥 Maximum errors reached! Monitoring stopped.")
                    break
                    
                time.sleep(10)  # Longer wait on error
                
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        send_message(f"💥 Fatal error: {e}")
    finally:
        if driver:
            logger.info("Closing browser...")
            driver.quit()
        logger.info("Monitoring stopped")

if __name__ == "__main__":
    print("🚀 Windows RDP Call Monitor Starting...")
    print("=" * 50)
    main()