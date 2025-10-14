import time
import re
import requests
import os
import threading
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
from pydub import AudioSegment
import config

class AccountManager:
    def __init__(self, account_id, login_url, call_url):
        self.account_id = account_id
        self.login_url = login_url
        self.call_url = call_url
        self.driver = None
        self.active_calls = {}
        self.pending_recordings = {}
        self.is_logged_in = False
        
        # Account-specific download folder
        self.download_folder = os.path.join(config.DOWNLOAD_FOLDER, f"account_{account_id}")
        os.makedirs(self.download_folder, exist_ok=True)
        
        print(f"[👤] Account {self.account_id} initialized")

    def country_to_flag(self, country_code):
        if not country_code or len(country_code) != 2:
            return "🏳️"
        return "".join(chr(127397 + ord(c)) for c in country_code.upper())

    def detect_country(self, number):
        try:
            clean_number = re.sub(r"\D", "", number)
            if clean_number:
                parsed = phonenumbers.parse("+" + clean_number, None)
                region = region_code_for_number(parsed)
                country = pycountry.countries.get(alpha_2=region)
                if country:
                    return country.name, self.country_to_flag(region)
        except:
            pass
        return "Unknown", "🏳️"

    def mask_number(self, number):
        digits = re.sub(r"\D", "", number)
        if len(digits) > 6:
            return digits[:4] + "****" + digits[-3:]
        return number

    def send_message(self, text):
        try:
            url = f"https://api.telegram.org/bot{config.BOT_TOKEN}/sendMessage"
            payload = {"chat_id": config.CHAT_ID, "text": text, "parse_mode": "Markdown"}
            res = requests.post(url, json=payload, timeout=10)
            if res.ok:
                return res.json().get("result", {}).get("message_id")
        except Exception as e:
            print(f"[❌] Account {self.account_id}: Failed to send message: {e}")
            return None

    def delete_message(self, msg_id):
        try:
            url = f"https://api.telegram.org/bot{config.BOT_TOKEN}/deleteMessage"
            requests.post(url, data={"chat_id": config.CHAT_ID, "message_id": msg_id}, timeout=5)
        except:
            pass

    def send_voice_with_caption(self, voice_path, caption):
        try:
            url = f"https://api.telegram.org/bot{config.BOT_TOKEN}/sendVoice"
            with open(voice_path, "rb") as voice:
                payload = {"chat_id": config.CHAT_ID, "caption": caption, "parse_mode": "HTML"}
                files = {"voice": voice}
                response = requests.post(url, data=payload, files=files, timeout=60)
                if response.status_code == 200:
                    return True
                else:
                    print(f"[❌] Account {self.account_id}: Send voice failed with status {response.status_code}: {response.text}")
                    return False
        except Exception as e:
            print(f"[❌] Account {self.account_id}: Failed to send voice: {e}")
            return False

    def get_authenticated_session(self):
        session = requests.Session()
        selenium_cookies = self.driver.get_cookies()
        
        # Clear previous session cookies
        session.cookies.clear()
        
        for cookie in selenium_cookies:
            session.cookies.set(cookie['name'], cookie['value'])
        
        # Add unique session identifier
        session.headers.update({
            'User-Agent': f'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (Account-{self.account_id})',
            'Referer': self.call_url,
            'Accept': 'audio/mpeg, audio/*',
            'Cache-Control': 'no-cache'
        })
        return session

    def construct_recording_url(self, did_number, call_uuid):
        return f"https://www.orangecarrier.com/live/calls/sound?did={did_number}&uuid={call_uuid}"

    def simulate_play_button(self, did_number, call_uuid):
        try:
            script = f'window.Play("{did_number}", "{call_uuid}"); return "Play executed";'
            result = self.driver.execute_script(script)
            print(f"[▶️] Account {self.account_id}: Play button simulated: {did_number} - Result: {result}")
            return True
        except Exception as e:
            print(f"[❌] Account {self.account_id}: Play simulation failed: {e}")
            return False

    def download_recording(self, did_number, call_uuid, file_path):
        try:
            if not self.simulate_play_button(did_number, call_uuid):
                return False
            time.sleep(3)

            recording_url = self.construct_recording_url(did_number, call_uuid)  
            session = self.get_authenticated_session()
            
            headers = {
                'User-Agent': f'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (Account-{self.account_id})',
                'Referer': self.call_url,
                'Accept': 'audio/mpeg, audio/*, */*',
                'Accept-Encoding': 'identity',
                'Range': 'bytes=0-',
                'Cache-Control': 'no-cache',
                'Pragma': 'no-cache'
            }
            
            # Add retry mechanism with longer delay
            for attempt in range(5):
                try:
                    print(f"[📥] Account {self.account_id}: Download attempt {attempt+1} for {recording_url}")
                    response = session.get(recording_url, headers=headers, timeout=60, stream=True)
                    
                    print(f"[HTTP] Account {self.account_id}: Status {response.status_code}, Content-Type: {response.headers.get('Content-Type')}")
                    
                    if response.status_code == 200:
                        with open(file_path, "wb") as f:
                            total_bytes = 0
                            for chunk in response.iter_content(chunk_size=8192):
                                if chunk:
                                    f.write(chunk)
                                    total_bytes += len(chunk)
                        
                        if total_bytes > 2000:  # Increased minimum size threshold
                            print(f"[✅] Account {self.account_id}: Recording downloaded - {total_bytes} bytes")
                            return True
                        else:
                            print(f"[⚠️] Account {self.account_id}: File too small - {total_bytes} bytes")
                            os.remove(file_path)
                    else:
                        print(f"[❌] Account {self.account_id}: HTTP {response.status_code} - {response.text[:100]}")
                        
                    time.sleep(5)  # Delay between retries
                    
                except Exception as e:
                    print(f"[❌] Account {self.account_id}: Download attempt {attempt+1} failed: {e}")
                    time.sleep(5)
                    
            return False
            
        except Exception as e:
            print(f"[❌] Account {self.account_id}: Download failed: {e}")
            if os.path.exists(file_path):
                os.remove(file_path)
            return False

    def wait_for_manual_login(self):
        """Wait for manual login with 300 seconds timeout"""
        print(f"[🔐] Account {self.account_id}: Login page: {self.login_url}")
        print(f"[➡️] Account {self.account_id}: Please login manually within 300 seconds...")
        print(f"[⏰] Account {self.account_id}: Timer started: 300 seconds")

        try:  
            # Wait for URL change indicating successful login
            WebDriverWait(self.driver, 300).until(  
                lambda d: "orangecarrier.com" in d.current_url and "login" not in d.current_url and "signin" not in d.current_url
            )  
            self.is_logged_in = True
            print(f"[✅] Account {self.account_id}: Manual login successful!")  
            return True  
        except TimeoutException:  
            print(f"[❌] Account {self.account_id}: Manual login timeout after 300 seconds")  
            return False

    def extract_calls(self):
        try:  
            calls_table = WebDriverWait(self.driver, 10).until(  
                EC.presence_of_element_located((By.ID, "LiveCalls"))  
            )  
              
            rows = calls_table.find_elements(By.TAG_NAME, "tr")  
            current_call_ids = set()  
              
            for row in rows:  
                try:  
                    row_id = row.get_attribute('id')  
                    if not row_id:  
                        continue  
                          
                    cells = row.find_elements(By.TAG_NAME, "td")  
                    if len(cells) < 5:  
                        continue  
                      
                    did_element = cells[1]  
                    did_text = did_element.text.strip()  
                    did_number = re.sub(r"\D", "", did_text)  
                      
                    if not did_number:  
                        continue  
                      
                    current_call_ids.add(row_id)  
                      
                    if row_id not in self.active_calls:  
                        print(f"[📞] Account {self.account_id}: New call: {did_number}")  
                          
                        country_name, flag = self.detect_country(did_number)  
                        masked = self.mask_number(did_number)  
                          
                        alert_text = f"📞 [{self.account_id}] New call from {flag} {masked}. Waiting for it to end."  
                          
                        msg_id = self.send_message(alert_text)  
                        self.active_calls[row_id] = {  
                            "msg_id": msg_id,  
                            "flag": flag,  
                            "country": country_name,  
                            "masked": masked,  
                            "did_number": did_number,  
                            "detected_at": datetime.now(),  
                            "last_seen": datetime.now()  
                        }  
                    else:  
                        self.active_calls[row_id]["last_seen"] = datetime.now()  
                          
                except StaleElementReferenceException:  
                    continue  
                except Exception as e:  
                    print(f"[❌] Account {self.account_id}: Row error: {e}")  
                    continue  
              
            current_time = datetime.now()  
            completed_calls = []  
              
            for call_id, call_info in list(self.active_calls.items()):  
                if (call_id not in current_call_ids) or ((current_time - call_info["last_seen"]).total_seconds() > 15):
                    if call_id not in self.pending_recordings:  
                        print(f"[✅] Account {self.account_id}: Call completed: {call_info['did_number']}")  
                        completed_calls.append(call_id)  
              
            for call_id in completed_calls:  
                call_info = self.active_calls[call_id]  
                  
                self.pending_recordings[call_id] = {  
                    **call_info,  
                    "completed_at": datetime.now(),  
                    "checks": 0,  
                    "last_check": datetime.now()  
                }  
                  
                wait_text = f"{call_info['flag']} {call_info['masked']} — [{self.account_id}] Processing recording..."  
                  
                if call_info["msg_id"]:  
                    self.delete_message(call_info["msg_id"])  
                  
                new_msg_id = self.send_message(wait_text)  
                if new_msg_id:  
                    self.pending_recordings[call_id]["msg_id"] = new_msg_id  
                  
                del self.active_calls[call_id]  
                      
        except TimeoutException:  
            print(f"[⏱️] Account {self.account_id}: No active calls table")  
        except Exception as e:  
            print(f"[❌] Account {self.account_id}: Extract error: {e}")

    def process_pending_recordings(self):
        current_time = datetime.now()  
        processed_calls = []  
        
        for call_id, call_info in list(self.pending_recordings.items()):  
            try:  
                time_since_check = (current_time - call_info["last_check"]).total_seconds()  
                if time_since_check < config.RECORDING_RETRY_DELAY:  
                    continue  
                  
                call_info["checks"] += 1  
                call_info["last_check"] = current_time  
                  
                print(f"[🔍] Account {self.account_id}: Check #{call_info['checks']} for: {call_info['did_number']}")  
                  
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")  
                mp3_path = os.path.join(self.download_folder, f"call_{call_info['did_number']}_{timestamp}.mp3")  
                  
                if self.download_recording(call_info['did_number'], call_id, mp3_path):  
                    self.process_recording_file(call_info, mp3_path)  
                    processed_calls.append(call_id)  
                else:  
                    print(f"[❌] Account {self.account_id}: Recording not available: {call_info['did_number']}")  
                  
                time_since_complete = (current_time - call_info["completed_at"]).total_seconds()  
                if time_since_complete > config.MAX_RECORDING_WAIT:  
                    print(f"[⏰] Account {self.account_id}: Timeout: {call_info['did_number']}")  
                      
                    timeout_text = f"❌ [{self.account_id}] Recording timeout for {call_info['flag']} {call_info['masked']}"  
                      
                    if call_info.get("msg_id"):  
                        self.delete_message(call_info["msg_id"])  
                      
                    self.send_message(timeout_text)  
                    processed_calls.append(call_id)  
                      
            except Exception as e:  
                print(f"[❌] Account {self.account_id}: Processing error: {e}")  
        
        for call_id in processed_calls:  
            if call_id in self.pending_recordings:  
                del self.pending_recordings[call_id]

    def process_recording_file(self, call_info, mp3_path):
        try:
            ogg_path = mp3_path.replace('.mp3', '.ogg')
            audio = AudioSegment.from_mp3(mp3_path)
            audio.export(ogg_path, format='ogg', codec='opus')
            print(f"[🔄] Account {self.account_id}: Converted MP3 to OGG: {ogg_path}")

            if call_info.get("msg_id"):
                self.delete_message(call_info["msg_id"])

            call_time = call_info['detected_at'].strftime('%Y-%m-%d %I:%M:%S %p')  
              
            caption = (  
                "🔥 NEW CALL RECEIVED ✨\n\n"  
                f"⏰ Time: {call_time}\n"  
                f"🏪 Account: {self.account_id}\n"  
                f"{call_info['flag']} Country: {call_info['country']}\n"  
                f"🚀 Number: {call_info['masked']}\n\n"  
                f"🌟 Configure by @professor_cry"  
            )  
              
            if self.send_voice_with_caption(ogg_path, caption):  
                print(f"[✅] Account {self.account_id}: Recording sent: {call_info['did_number']}")  
                # Clean up files after successful send
                try:
                    os.remove(mp3_path)
                    os.remove(ogg_path)
                except:
                    pass
            else:  
                self.send_message(caption)  
                # Keep the files for debugging if send fails
                print(f"[⚠️] Account {self.account_id}: Kept files for debug: {mp3_path} and {ogg_path}")
                  
        except Exception as e:  
            print(f"[❌] Account {self.account_id}: File processing error: {e}")  
            error_text = f"❌ [{self.account_id}] Processing error for {call_info['flag']} {call_info['masked']}"  
            self.send_message(error_text)
            # Clean up if conversion fails
            if os.path.exists(mp3_path):
                os.remove(mp3_path)

    def initialize_driver(self):
        chrome_options = Options()
        
        # VNC compatible settings
        chrome_options.add_argument("--disable-gpu")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("--disable-software-rasterizer")
        chrome_options.add_argument("--disable-extensions")
        chrome_options.add_argument("--disable-background-timer-throttling")
        chrome_options.add_argument("--disable-backgrounding-occluded-windows")
        chrome_options.add_argument("--disable-renderer-backgrounding")
        chrome_options.add_argument("--no-first-run")
        chrome_options.add_argument("--disable-default-apps")
        chrome_options.add_argument("--disable-features=TranslateUI")
        chrome_options.add_argument("--disable-ipc-flooding-protection")
        
        # Display settings for VNC
        chrome_options.add_argument("--window-size=1280,720")
        chrome_options.add_argument("--start-maximized")
        chrome_options.add_argument("--force-device-scale-factor=1")
        
        # Account specific profile
        chrome_options.add_argument(f"--user-data-dir=/tmp/chrome_account_{self.account_id}")
        
        # Add for audio issues
        chrome_options.add_argument("--use-fake-ui-for-media-stream")
        chrome_options.add_argument("--use-fake-device-for-media-stream")
        
        # Optional: Headless mode to save resources (comment out if manual login requires visible browser)
        # chrome_options.add_argument("--headless=new")
        
        return webdriver.Chrome(options=chrome_options)

    def start_manual_login_process(self):
        """Start the manual login process for this account"""
        self.driver = None
        try:
            self.driver = self.initialize_driver()
            
            # Navigate to login page
            print(f"[🌐] Account {self.account_id}: Opening browser for manual login...")
            self.driver.get(self.login_url)
            
            # Wait for manual login
            login_success = self.wait_for_manual_login()
            
            if login_success:
                # Navigate to calls page after successful login
                print(f"[✅] Account {self.account_id}: Login successful, navigating to calls page...")
                self.driver.get(self.call_url)
                
                # Wait for calls page to load
                try:
                    WebDriverWait(self.driver, 30).until(
                        EC.presence_of_element_located((By.ID, "LiveCalls"))
                    )
                    print(f"[✅] Account {self.account_id}: Active Calls page loaded")
                except:
                    print(f"[⚠️] Account {self.account_id}: Calls page load timeout, but continuing...")
                
                print(f"[🎯] Account {self.account_id}: Monitoring started...")
                return True
            else:
                print(f"[❌] Account {self.account_id}: Login failed or timeout")
                return False
                
        except Exception as e:
            print(f"[💥] Account {self.account_id}: Error during login process: {e}")
            return False

    def start_monitoring(self):
        """Start monitoring calls after successful login"""
        if not self.is_logged_in:
            print(f"[❌] Account {self.account_id}: Cannot start monitoring - not logged in")
            return

        error_count = 0
        last_recording_check = datetime.now()
        
        while error_count < config.MAX_ERRORS:
            try:
                self.extract_calls()
                
                current_time = datetime.now()
                if (current_time - last_recording_check).total_seconds() >= 10:
                    self.process_pending_recordings()
                    last_recording_check = current_time
                
                error_count = 0
                time.sleep(config.CHECK_INTERVAL)
                
            except KeyboardInterrupt:
                print(f"\n[🛑] Account {self.account_id}: Stopped by user")
                break
            except Exception as e:
                error_count += 1
                print(f"[❌] Account {self.account_id}: Main loop error ({error_count}/{config.MAX_ERRORS}): {e}")
                time.sleep(10)  # Increased delay on error


class SequentialLoginManager:
    def __init__(self):
        self.accounts = []
        self.login_delay = 60  # Reduced to 60 seconds as requested
        
    def add_account(self, account_id, login_url, call_url):
        account = AccountManager(account_id, login_url, call_url)
        self.accounts.append(account)
        return account
    
    def start_sequential_login(self):
        """Start sequential login process with 60 seconds delay between accounts"""
        print(f"[🎮] Starting sequential login for {len(self.accounts)} accounts...")
        print(f"[⏰] Delay between accounts: {self.login_delay} seconds")
        
        monitoring_threads = []
        
        for i, account in enumerate(self.accounts):
            print(f"\n{'='*50}")
            print(f"[🚀] Starting Account {account.account_id} ({i+1}/{len(self.accounts)})")
            print(f"[⏰] Next account will start in {self.login_delay} seconds after this one")
            print(f"{'='*50}")
            
            # Start login process for current account
            login_success = account.start_manual_login_process()
            
            if login_success:
                # Start monitoring in a separate thread
                monitor_thread = threading.Thread(
                    target=account.start_monitoring, 
                    name=f"Monitor-Account-{account.account_id}"
                )
                monitor_thread.daemon = True
                monitor_thread.start()
                monitoring_threads.append(monitor_thread)
                print(f"[✅] Account {account.account_id}: Monitoring started in background thread")
            else:
                print(f"[❌] Account {account.account_id}: Skipping due to login failure")
            
            # Don't wait after the last account
            if i < len(self.accounts) - 1:
                print(f"[⏳] Waiting {self.login_delay} seconds before starting next account...")
                
                # Countdown timer
                for remaining in range(self.login_delay, 0, -10):
                    if remaining > 0:
                        print(f"[⏰] Next account in {remaining} seconds...")
                    time.sleep(10)
                
                print(f"[🚀] Starting next account...")
        
        print(f"\n[✅] All {len(self.accounts)} accounts login process completed!")
        print(f"[📊] {len(monitoring_threads)} accounts successfully started monitoring")
        
        # Keep main thread alive while monitoring threads run
        try:
            while True:
                time.sleep(10)
                # Check if any monitoring threads are still alive
                alive_threads = [t for t in monitoring_threads if t.is_alive()]
                if not alive_threads:
                    print("[ℹ️] All monitoring threads have stopped")
                    break
                # Optional: Print status
                print(f"[ℹ️] Active monitoring threads: {len(alive_threads)}")
        except KeyboardInterrupt:
            print("\n[🛑] Sequential login manager stopped by user")


if __name__ == "__main__":
    # Create main download folder
    os.makedirs(config.DOWNLOAD_FOLDER, exist_ok=True)
    
    # Initialize sequential login manager
    login_manager = SequentialLoginManager()
    
    # Add 8 accounts (you can modify these as needed)
    for i in range(1, 9):
        login_manager.add_account(
            account_id=i,
            login_url=config.LOGIN_URL,
            call_url=config.CALL_URL
        )
    
    print(f"[🤖] Sequential Login System Initialized")
    print(f"[📋] Total Accounts: {len(login_manager.accounts)}")
    print(f"[⏰] Login Delay: {login_manager.login_delay} seconds between accounts")
    print(f"[🔧] Configured by @professor_cry")
    print(f"\n[⚠️] Important: You have 300 seconds to login for each account")
    print(f"[⚠️] Make sure to complete login within the time limit for each browser window")
    
    try:
        login_manager.start_sequential_login()
    except KeyboardInterrupt:
        print("\n[🛑] Sequential login process stopped by user")
    except Exception as e:
        print(f"[💥] Sequential login error: {e}")
