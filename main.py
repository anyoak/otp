import time, re, hashlib
from datetime import datetime, timedelta
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.service import Service
from selenium.common.exceptions import TimeoutException
import phonenumbers
from phonenumbers import geocoder

import config
from storage import seen_before
from telegram_client import send_message_html, esc

COUNTRY_FLAGS = {
    "Bangladesh": "🇧🇩", "United States": "🇺🇸", "India": "🇮🇳", "Unknown": "🏳️"
    # Add other countries as needed
}

def mask_number(number):
    digits = re.sub(r'\D', '', number)
    return digits[:2] + '***' + digits[-2:] if len(digits) >= 7 else number

def detect_service(service_text, message_text):
    s = service_text.lower(); m = message_text.lower()
    if "telegram" in s or "telegram" in m: return "Telegram"
    elif "whatsapp" in s or "whatsapp" in m: return "WhatsApp"
    else: return service_text or "Unknown"

def get_country_from_number(raw_number):
    try:
        if not raw_number.startswith('+'): raw_number = "+" + raw_number
        num = phonenumbers.parse(raw_number, None)
        name = geocoder.description_for_number(num, "en") or "Unknown"
        return name, COUNTRY_FLAGS.get(name, "🏳️")
    except: return "Unknown", "🏳️"

def extract_otp(message):
    match = re.search(r"(?<!\d)(\d{4,8})(?!\d)", message)
    return match.group(1) if match else None

def create_html_card(ts, service, number, flag, country, otp, msg):
    local_time = ts + timedelta(hours=config.TZ_OFFSET_HOURS)
    otp_html = f"<code>{esc(otp)}</code>" if otp else "<i>Not detected</i>"
    masked_number = mask_number(number)
    return (
        f"<b>🔐 OTP Captured</b>\n"
        f"<u>Time</u>: {esc(local_time.strftime('%Y-%m-%d %H:%M:%S'))}\n"
        f"<u>Service</u>: {esc(service)}\n"
        f"<u>Number</u>: {esc(masked_number)}  {esc(flag)} {esc(country)}\n"
        f"<u>Code</u>: {otp_html}\n\n"
        f"<b>Message</b>:\n<tg-spoiler>{esc(msg)}</tg-spoiler>\n\n"
        f"<i>— bot by @your_handle • anti-dup✓ • headless✓ • docker✓</i>"
    )

def compute_captcha_safe(q):
    match = re.search(r'What is (.+?) = \?', q)
    if not match: return None
    expr = match.group(1)
    parts = re.findall(r'\d+', expr)
    if len(parts)!=2: return None
    a,b=int(parts[0]),int(parts[1])
    if '+' in expr: return a+b
    elif '-' in expr: return a-b
    elif '*' in expr: return a*b
    elif '/' in expr: return a//b
    else: return None

def login(driver):
    try:
        driver.get(config.LOGIN_URL)
        wait = WebDriverWait(driver,25)
        username_field = wait.until(EC.visibility_of_element_located((By.CSS_SELECTOR, config.USERNAME_SELECTOR)))
        username_field.clear(); username_field.send_keys(config.SITE_USERNAME)
        print("[INFO] Username entered")
        password_field = wait.until(EC.visibility_of_element_located((By.CSS_SELECTOR, config.PASSWORD_SELECTOR)))
        password_field.clear(); password_field.send_keys(config.SITE_PASSWORD)
        print("[INFO] Password entered")
        captcha_label = wait.until(EC.visibility_of_element_located(
            (By.XPATH,"//label[contains(text(),'What is')] | //div[contains(text(),'What is')]")
        ))
        q = captcha_label.text.strip()
        print(f"[INFO] CAPTCHA question: {q}")
        ans = compute_captcha_safe(q)
        if ans is None: print("[ERROR] Could not compute CAPTCHA"); return False
        captcha_field = wait.until(EC.visibility_of_element_located((By.CSS_SELECTOR, config.CAPTCHA_SELECTOR)))
        captcha_field.clear(); captcha_field.send_keys(str(ans))
        print(f"[INFO] CAPTCHA answer: {ans}")
        submit_button = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, config.SUBMIT_SELECTOR)))
        driver.execute_script("arguments[0].click();", submit_button)
        try: wait.until(EC.url_changes(config.LOGIN_URL), timeout=20); time.sleep(5)
        except TimeoutException: print("[WARNING] URL did not change")
        if driver.current_url == config.LOGIN_URL: print("[ERROR] Login failed"); return False
        print("[INFO] Login successful"); return True
    except Exception as e: print(f"[ERROR] Login failed: {e}"); return False

def scrape_once(driver):
    try:
        driver.get(config.SMS_URL)
        wait = WebDriverWait(driver,10)
        wait.until(EC.presence_of_element_located((By.TAG_NAME,"table")))
        soup=BeautifulSoup(driver.page_source,'html.parser')
        headers=soup.find_all('th')
        n_idx=s_idx=m_idx=None
        for idx,th in enumerate(headers):
            lbl=(th.get('aria-label') or th.get_text(" ") or "").lower()
            if 'number' in lbl or 'phone' in lbl: n_idx=idx
            elif 'cli' in lbl or 'service' in lbl: s_idx=idx
            elif 'sms' in lbl or 'message' in lbl or 'text' in lbl: m_idx=idx
        if None in (n_idx,s_idx,m_idx): print("[WARNING] Columns not detected"); return
        for row in soup.find_all('tr')[1:]:
            cols=row.find_all('td')
            if len(cols)<=max(n_idx,s_idx,m_idx): continue
            number_raw=cols[n_idx].get_text(strip=True) or "Unknown"
            service_raw=cols[s_idx].get_text(strip=True) or "Unknown"
            msg=cols[m_idx].get_text("\n",strip=True)
            if not msg: continue
            h=hashlib.sha256((number_raw+"|"+msg).encode()).hexdigest()
            if seen_before(h): continue
            otp=extract_otp(msg)
            country,flag=get_country_from_number(number_raw)
            service=detect_service(service_raw,msg)
            ts=datetime.utcnow()
            html_card=create_html_card(ts,service,number_raw,flag,country,otp,msg)
            buttons=[[("Open Panel",config.SMS_URL)]]
            send_message_html(html_card,buttons)
            print("[INFO] OTP sent to Telegram")
    except Exception as e: print(f"[ERROR] Scrape failed: {e}")

if __name__=="__main__":
    opts=Options()
    opts.add_argument("--headless=new"); opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-dev-shm-usage"); opts.add_argument("--disable-gpu")
    opts.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/117.0.0.0 Safari/537.36")
    opts.binary_location='/usr/bin/chromium'
    driver=webdriver.Chrome(service=Service('/usr/bin/chromedriver'), options=opts)
    try:
        if not login(driver): print("[ERROR] Login failed"); exit(1)
        print("[INFO] Scraping SMS page...")
        while True: scrape_once(driver); time.sleep(config.SCRAPE_INTERVAL)
    except KeyboardInterrupt: print("Shutting down...")
    finally: driver.quit()
