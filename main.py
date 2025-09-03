import time
import re
import hashlib
from datetime import datetime, timedelta
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.common.exceptions import WebDriverException, NoSuchElementException
import phonenumbers
from phonenumbers import geocoder

import config
from storage import seen_before
from telegram_client import send_message_html, esc

# -----------------------
# 194 country flags
# -----------------------
COUNTRY_FLAGS = {
    "Afghanistan": "🇦🇫","Albania": "🇦🇱","Algeria": "🇩🇿","Andorra": "🇦🇩","Angola": "🇦🇴",
    "Antigua and Barbuda": "🇦🇬","Argentina": "🇦🇷","Armenia": "🇦🇲","Australia": "🇦🇺","Austria": "🇦🇹",
    "Azerbaijan": "🇦🇿","Bahamas": "🇧🇸","Bahrain": "🇧🇭","Bangladesh": "🇧🇩","Barbados": "🇧🇧",
    "Belarus": "🇧🇾","Belgium": "🇧🇪","Belize": "🇧🇿","Benin": "🇧🇯","Bhutan": "🇧🇹",
    "Bolivia": "🇧🇴","Bosnia and Herzegovina": "🇧🇦","Botswana": "🇧🇼","Brazil": "🇧🇷","Brunei": "🇧🇳",
    "Bulgaria": "🇧🇬","Burkina Faso": "🇧🇫","Burundi": "🇧🇮","Cabo Verde": "🇨🇻","Cambodia": "🇰🇭",
    "Cameroon": "🇨🇲","Canada": "🇨🇦","Central African Republic": "🇨🇫","Chad": "🇹🇩","Chile": "🇨🇱",
    "China": "🇨🇳","Colombia": "🇨🇴","Comoros": "🇰🇲","Congo (Congo-Brazzaville)": "🇨🇬",
    "Costa Rica": "🇨🇷","Croatia": "🇭🇷","Cuba": "🇨🇺","Cyprus": "🇨🇾","Czechia": "🇨🇿",
    "Democratic Republic of the Congo": "🇨🇩","Denmark": "🇩🇰","Djibouti": "🇩🇯","Dominica": "🇩🇲",
    "Dominican Republic": "🇩🇴","Ecuador": "🇪🇨","Egypt": "🇪🇬","El Salvador": "🇸🇻","Equatorial Guinea": "🇬🇶",
    "Eritrea": "🇪🇷","Estonia": "🇪🇪","Eswatini": "🇸🇿","Ethiopia": "🇪🇹","Fiji": "🇫🇯",
    "Finland": "🇫🇮","France": "🇫🇷","Gabon": "🇬🇦","Gambia": "🇬🇲","Georgia": "🇬🇪",
    "Germany": "🇩🇪","Ghana": "🇬🇭","Greece": "🇬🇷","Grenada": "🇬🇩","Guatemala": "🇬🇹",
    "Guinea": "🇬🇳","Guinea-Bissau": "🇬🇼","Guyana": "🇬🇾","Haiti": "🇭🇹","Honduras": "🇭🇳",
    "Hungary": "🇭🇺","Iceland": "🇮🇸","India": "🇮🇳","Indonesia": "🇮🇩","Iran": "🇮🇷",
    "Iraq": "🇮🇶","Ireland": "🇮🇪","Israel": "🇮🇱","Italy": "🇮🇹","Jamaica": "🇯🇲",
    "Japan": "🇯🇵","Jordan": "🇯🇴","Kazakhstan": "🇰🇿","Kenya": "🇰🇪","Kiribati": "🇰🇮",
    "Kuwait": "🇰🇼","Kyrgyzstan": "🇰🇬","Laos": "🇱🇦","Latvia": "🇱🇻","Lebanon": "🇱🇧",
    "Lesotho": "🇱🇸","Liberia": "🇱🇷","Libya": "🇱🇾","Liechtenstein": "🇱🇮","Lithuania": "🇱🇹",
    "Luxembourg": "🇱🇺","Madagascar": "🇲🇬","Malawi": "🇲🇼","Malaysia": "🇲🇾","Maldives": "🇲🇻",
    "Mali": "🇲🇱","Malta": "🇲🇹","Marshall Islands": "🇲🇭","Mauritania": "🇲🇷","Mauritius": "🇲🇺",
    "Mexico": "🇲🇽","Micronesia": "🇫🇲","Moldova": "🇲🇩","Monaco": "🇲🇨","Mongolia": "🇲🇳",
    "Montenegro": "🇲🇪","Morocco": "🇲🇦","Mozambique": "🇲🇿","Myanmar": "🇲🇲","Namibia": "🇳🇦",
    "Nauru": "🇳🇷","Nepal": "🇳🇵","Netherlands": "🇳🇱","New Zealand": "🇳🇿","Nicaragua": "🇳🇮",
    "Niger": "🇳🇪","Nigeria": "🇳🇬","North Korea": "🇰🇵","North Macedonia": "🇲🇰","Norway": "🇳🇴",
    "Oman": "🇴🇲","Pakistan": "🇵🇰","Palau": "🇵🇼","Palestine": "🇵🇸","Panama": "🇵🇦",
    "Papua New Guinea": "🇵🇬","Paraguay": "🇵🇾","Peru": "🇵🇪","Philippines": "🇵🇭","Poland": "🇵🇱",
    "Portugal": "🇵🇹","Qatar": "🇶🇦","Romania": "🇷🇴","Russia": "🇷🇺","Rwanda": "🇷🇼",
    "Saint Kitts and Nevis": "🇰🇳","Saint Lucia": "🇱🇨","Saint Vincent and the Grenadines": "🇻🇨",
    "Samoa": "🇼🇸","San Marino": "🇸🇲","Sao Tome and Principe": "🇸🇹","Saudi Arabia": "🇸🇦",
    "Senegal": "🇸🇳","Serbia": "🇷🇸","Seychelles": "🇸🇨","Sierra Leone": "🇸🇱","Singapore": "🇸🇬",
    "Slovakia": "🇸🇰","Slovenia": "🇸🇮","Solomon Islands": "🇸🇧","Somalia": "🇸🇴","South Africa": "🇿🇦",
    "South Korea": "🇰🇷","South Sudan": "🇸🇸","Spain": "🇪🇸","Sri Lanka": "🇱🇰","Sudan": "🇸🇩",
    "Suriname": "🇸🇷","Sweden": "🇸🇪","Switzerland": "🇨🇭","Syria": "🇸🇾","Taiwan": "🇹🇼",
    "Tajikistan": "🇹🇯","Tanzania": "🇹🇿","Thailand": "🇹🇭","Timor-Leste": "🇹🇱","Togo": "🇹🇬",
    "Tonga": "🇹🇴","Trinidad and Tobago": "🇹🇹","Tunisia": "🇹🇳","Turkey": "🇹🇷","Turkmenistan": "🇹🇲",
    "Tuvalu": "🇹🇻","Uganda": "🇺🇬","Ukraine": "🇺🇦","United Arab Emirates": "🇦🇪","United Kingdom": "🇬🇧",
    "United States": "🇺🇸","Uruguay": "🇺🇾","Uzbekistan": "🇺🇿","Vanuatu": "🇻🇺","Vatican City": "🇻🇦",
    "Venezuela": "🇻🇪","Vietnam": "🇻🇳","Yemen": "🇾🇪","Zambia": "🇿🇲","Zimbabwe": "🇿🇼"
}

# -----------------------
# Helper functions
# -----------------------
def mask_number(number: str):
    digits = re.sub(r'\D', '', number)
    if len(digits) >= 7:
        return digits[:2] + '***' + digits[-2:]
    return number

def detect_service(service_text: str, message_text: str):
    s = service_text.lower()
    m = message_text.lower()
    if "telegram" in s or "telegram" in m:
        return "Telegram"
    elif "whatsapp" in s or "whatsapp" in m:
        return "WhatsApp"
    else:
        return service_text or "Unknown"

def get_country_from_number(raw_number: str):
    try:
        if not raw_number.startswith('+'):
            raw_number = "+" + raw_number
        num = phonenumbers.parse(raw_number, None)
        name = geocoder.description_for_number(num, "en") or "Unknown"
        flag = COUNTRY_FLAGS.get(name, "🏳️")
        return name, flag
    except Exception:
        return "Unknown", "🏳️"

def extract_otp(message: str):
    match = re.search(r"(?<!\d)(\d{4,8})(?!\d)", message)
    return match.group(1) if match else None

def create_html_card(timestamp: datetime, service: str, number: str, country_flag: str,
                     country_name: str, otp: str | None, full_msg: str):
    local_time = timestamp + timedelta(hours=config.TZ_OFFSET_HOURS)
    t_str = local_time.strftime('%Y-%m-%d %H:%M:%S')
    otp_html = f"<code>{esc(otp)}</code>" if otp else "<i>Not detected</i>"
    masked_number = mask_number(number)
    return (
        f"<b>🔐 OTP Captured</b>\n"
        f"<u>Time</u>: {esc(t_str)}\n"
        f"<u>Service</u>: {esc(service)}\n"
        f"<u>Number</u>: {esc(masked_number)}  {esc(country_flag)} {esc(country_name)}\n"
        f"<u>Code</u>: {otp_html}\n\n"
        f"<b>Message</b>:\n<tg-spoiler>{esc(full_msg)}</tg-spoiler>\n\n"
        f"<i>— bot by @your_handle • anti-dup✓ • headless✓ • docker✓</i>"
    )

def guess_columns(headers):
    number_idx = service_idx = message_idx = None
    for idx, th in enumerate(headers):
        label = (th.get('aria-label') or th.get_text(" ") or "").strip().lower()
        if 'number' in label or 'msisdn' in label or 'phone' in label:
            number_idx = idx
        elif 'cli' in label or 'service' in label or 'sender' in label:
            service_idx = idx
        elif 'sms' in label or 'message' in label or 'text' in label:
            message_idx = idx
    return number_idx, service_idx, message_idx

def login(driver):
    """Perform login to the target site."""
    try:
        driver.get(config.LOGIN_URL)
        time.sleep(1)  # Wait for page to load

        # Try each selector in the comma-separated list
        for selector in config.USERNAME_SELECTOR.split(","):
            try:
                driver.find_element(By.CSS_SELECTOR, selector.strip()).send_keys(config.SITE_USERNAME)
                break
            except NoSuchElementException:
                continue
        else:
            print("[ERROR] No valid username selector found")
            return False

        for selector in config.PASSWORD_SELECTOR.split(","):
            try:
                driver.find_element(By.CSS_SELECTOR, selector.strip()).send_keys(config.SITE_PASSWORD)
                break
            except NoSuchElementException:
                continue
        else:
            print("[ERROR] No valid password selector found")
            return False

        for selector in config.SUBMIT_SELECTOR.split(","):
            try:
                driver.find_element(By.CSS_SELECTOR, selector.strip()).click()
                break
            except NoSuchElementException:
                continue
        else:
            print("[ERROR] No valid submit selector found")
            return False

        time.sleep(2)  # Wait for login to complete
        return True
    except WebDriverException as e:
        print(f"[ERROR] Login failed: {e}")
        return False

def scrape_once(driver):
    try:
        driver.get(config.SMS_URL)
        time.sleep(3)  # Increased sleep time for page load
        soup = BeautifulSoup(driver.page_source, 'html.parser')
        headers = soup.find_all('th')
        n_idx, s_idx, m_idx = guess_columns(headers)
        if None in (n_idx, s_idx, m_idx):
            print("[⚠️] Could not detect all required columns (number/service/message).")
            return

        for row in soup.find_all('tr')[1:]:
            cols = row.find_all('td')
            if len(cols) <= max(n_idx, s_idx, m_idx):
                continue
            number_raw = cols[n_idx].get_text(strip=True) or "Unknown"
            service_raw = cols[s_idx].get_text(strip=True) or "Unknown"
            message = cols[m_idx].get_text("\n", strip=True)
            if not message:
                continue

            h = hashlib.sha256((number_raw + "|" + message).encode()).hexdigest()
            if seen_before(h):
                continue

            otp = extract_otp(message)
            country_name, country_flag = get_country_from_number(number_raw)
            service = detect_service(service_raw, message)
            ts = datetime.utcnow()

            html_card = create_html_card(ts, service, number_raw, country_flag, country_name, otp, message)
            buttons = [[("Open Panel", config.SMS_URL)]]
            send_message_html(html_card, buttons)
    except WebDriverException as e:
        print(f"[ERROR] Navigation failed: {e}")

if __name__ == "__main__":
    options = Options()
    options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_argument("--remote-debugging-port=9222")
    driver = webdriver.Chrome(options=options)
    try:
        if config.LOGIN_URL and config.SITE_USERNAME and config.SITE_PASSWORD:
            if not login(driver):
                print("[ERROR] Exiting due to login failure")
                exit(1)
        while True:
            scrape_once(driver)
            time.sleep(config.SCRAPE_INTERVAL)
    except KeyboardInterrupt:
        print("Shutting down...")
    finally:
        driver.quit()
