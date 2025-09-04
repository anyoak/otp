import time
import re
import hashlib
from datetime import datetime, timedelta
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.service import Service
from selenium.common.exceptions import WebDriverException, TimeoutException
import phonenumbers
from phonenumbers import geocoder

import config
from storage import seen_before
from telegram_client import send_message_html, esc

# COUNTRY_FLAGS dictionary (194 countries)
COUNTRY_FLAGS = {
    "Afghanistan": "🇦🇫", "Albania": "🇦🇱", "Algeria": "🇩🇿", "Andorra": "🇦🇩", "Angola": "🇦🇴",
    "Antigua and Barbuda": "🇦🇬", "Argentina": "🇦🇷", "Armenia": "🇦🇲", "Australia": "🇦🇺", "Austria": "🇦🇹",
    "Azerbaijan": "🇦🇿", "Bahamas": "🇧🇸", "Bahrain": "🇧🇭", "Bangladesh": "🇧🇩", "Barbados": "🇧🇧",
    "Belarus": "🇧🇾", "Belgium": "🇧🇪", "Belize": "🇧🇿", "Benin": "🇧🇯", "Bhutan": "🇧🇹",
    "Bolivia": "🇧🇴", "Bosnia and Herzegovina": "🇧🇦", "Botswana": "🇧🇼", "Brazil": "🇧🇷", "Brunei": "🇧🇳",
    "Bulgaria": "🇧🇬", "Burkina Faso": "🇧🇫", "Burundi": "🇧🇮", "Cabo Verde": "🇨🇻", "Cambodia": "🇰🇭",
    "Cameroon": "🇨🇲", "Canada": "🇨🇦", "Central African Republic": "🇨🇫", "Chad": "🇹🇩", "Chile": "🇨🇱",
    "China": "🇨🇳", "Colombia": "🇨🇴", "Comoros": "🇰🇲", "Congo (Congo-Brazzaville)": "🇨🇬",
    "Costa Rica": "🇨🇷", "Croatia": "🇭🇷", "Cuba": "🇨🇺", "Cyprus": "🇨🇾", "Czechia": "🇨🇿",
    "Democratic Republic of the Congo": "🇨🇩", "Denmark": "🇩🇰", "Djibouti": "🇩🇯", "Dominica": "🇩🇲",
    "Dominican Republic": "🇩🇴", "Ecuador": "🇪🇨", "Egypt": "🇪🇬", "El Salvador": "🇸🇻", "Equatorial Guinea": "🇬🇶",
    "Eritrea": "🇪🇷", "Estonia": "🇪🇪", "Eswatini": "🇸🇿", "Ethiopia": "🇪🇹", "Fiji": "🇫🇯",
    "Finland": "🇫🇮", "France": "🇫🇷", "Gabon": "🇬🇦", "Gambia": "🇬🇲", "Georgia": "🇬🇪",
    "Germany": "🇩🇪", "Ghana": "🇬🇭", "Greece": "🇬🇷", "Grenada": "🇬🇩", "Guatemala": "🇬🇹",
    "Guinea": "🇬🇳", "Guinea-Bissau": "🇬🇼", "Guyana": "🇬🇾", "Haiti": "🇭🇹", "Honduras": "🇭🇳",
    "Hungary": "🇭🇺", "Iceland": "🇮🇸", "India": "🇮🇳", "Indonesia": "🇮🇩", "Iran": "🇮🇷",
    "Iraq": "🇮🇶", "Ireland": "🇮🇪", "Israel": "🇮🇱", "Italy": "🇮🇹", "Jamaica": "🇯🇲",
    "Japan": "🇯🇵", "Jordan": "🇯🇴", "Kazakhstan": "🇰🇿", "Kenya": "🇰🇪", "Kiribati": "🇰🇮",
    "Kuwait": "🇰🇼", "Kyrgyzstan": "🇰🇬", "Laos": "🇱🇦", "Latvia": "🇱🇻", "Lebanon": "🇱🇧",
    "Lesotho": "🇱🇸", "Liberia": "🇱🇷", "Libya": "🇱🇾", "Liechtenstein": "🇱🇮", "Lithuania": "🇱🇹",
    "Luxembourg": "🇱🇺", "Madagascar": "🇲🇬", "Malawi": "🇲🇼", "Malaysia": "🇲🇾", "Maldives": "🇲🇻",
    "Mali": "🇲🇱", "Malta": "🇲🇹", "Marshall Islands": "🇲🇭", "Mauritania": "🇲🇷", "Mauritius": "🇲🇺",
    "Mexico": "🇲🇽", "Micronesia": "🇫🇲", "Moldova": "🇲🇩", "Monaco": "🇲🇨", "Mongolia": "🇲🇳",
    "Montenegro": "🇲🇪", "Morocco": "🇲🇦", "Mozambique": "🇲🇿", "Myanmar": "🇲🇲", "Namibia": "🇳🇦",
    "Nauru": "🇳🇷", "Nepal": "🇳🇵", "Netherlands": "🇳🇱", "New Zealand": "🇳🇿", "Nicaragua": "🇳🇮",
    "Niger": "🇳🇪", "Nigeria": "🇳🇬", "North Korea": "🇰🇵", "North Macedonia": "🇲🇰", "Norway": "🇳🇴",
    "Oman": "🇴🇲", "Pakistan": "🇵🇰", "Palau": "🇵🇼", "Palestine": "🇵🇸", "Panama": "🇵🇦",
    "Papua New Guinea": "🇵🇬", "Paraguay": "🇵🇾", "Peru": "🇵🇪", "Philippines": "🇵🇭", "Poland": "🇵🇱",
    "Portugal": "🇵🇹", "Qatar": "🇶🇦", "Romania": "🇷🇴", "Russia": "🇷🇺", "Rwanda": "🇷🇼",
    "Saint Kitts and Nevis": "🇰🇳", "Saint Lucia": "🇱🇨", "Saint Vincent and the Grenadines": "🇻🇨",
    "Samoa": "🇼🇸", "San Marino": "🇸🇲", "Sao Tome and Principe": "🇸🇹", "Saudi Arabia": "🇸🇦",
    "Senegal": "🇸🇳", "Serbia": "🇷🇸", "Seychelles": "🇸🇨", "Sierra Leone": "🇸🇱", "Singapore": "🇸🇬",
    "Slovakia": "🇸🇰", "Slovenia": "🇸🇮", "Solomon Islands": "🇸🇧", "Somalia": "🇸🇴", "South Africa": "🇿🇦",
    "South Korea": "🇰🇷", "South Sudan": "🇸🇸", "Spain": "🇪🇸", "Sri Lanka": "🇱🇰", "Sudan": "🇸🇩",
    "Suriname": "🇸🇷", "Sweden": "🇸🇪", "Switzerland": "🇨🇭", "Syria": "🇸🇾", "Taiwan": "🇹🇼",
    "Tajikistan": "🇹🇯", "Tanzania": "🇹🇿", "Thailand": "🇹🇭", "Timor-Leste": "🇹🇱", "Togo": "🇹🇬",
    "Tonga": "🇹🇴", "Trinidad and Tobago": "🇹🇹", "Tunisia": "🇹🇳", "Turkey": "🇹🇷", "Turkmenistan": "🇹🇲",
    "Tuvalu": "🇹🇻", "Uganda": "🇺🇬", "Ukraine": "🇺🇦", "United Arab Emirates": "🇦🇪", "United Kingdom": "🇬🇧",
    "United States": "🇺🇸", "Uruguay": "🇺🇾", "Uzbekistan": "🇺🇿", "Vanuatu": "🇻🇺", "Vatican City": "🇻🇦",
    "Venezuela": "🇻🇪", "Vietnam": "🇻🇳", "Yemen": "🇾🇪", "Zambia": "🇿🇲", "Zimbabwe": "🇿🇼"
}

def mask_number(number):
    digits = re.sub(r'\D', '', number)
    if len(digits) >= 7:
        return digits[:2] + '***' + digits[-2:]
    return number

def detect_service(service_text, message_text):
    s = service_text.lower()
    m = message_text.lower()
    if "telegram" in s or "telegram" in m:
        return "Telegram"
    elif "whatsapp" in s or "whatsapp" in m:
        return "WhatsApp"
    else:
        return service_text or "Unknown"

def get_country_from_number(raw_number):
    try:
        if not raw_number.startswith('+'):
            raw_number = "+" + raw_number
        num = phonenumbers.parse(raw_number, None)
        name = geocoder.description_for_number(num, "en") or "Unknown"
        flag = COUNTRY_FLAGS.get(name, "🏳️")
        return name, flag
    except Exception:
        return "Unknown", "🏳️"

def extract_otp(message):
    match = re.search(r"(?<!\d)(\d{4,8})(?!\d)", message)
    return match.group(1) if match else None

def create_html_card(timestamp, service, number, country_flag, country_name, otp, full_msg):
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
        f"<i>— PowerBy Incognito • Good Luck</i>"
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
    try:
        driver.get(config.LOGIN_URL)
        wait = WebDriverWait(driver, 25)

        username_field = wait.until(EC.visibility_of_element_located((By.CSS_SELECTOR, config.USERNAME_SELECTOR)))
        username_field.clear()
        username_field.send_keys(config.SITE_USERNAME)
        print("[INFO] Username entered")

        password_field = wait.until(EC.visibility_of_element_located((By.CSS_SELECTOR, config.PASSWORD_SELECTOR)))
        password_field.clear()
        password_field.send_keys(config.SITE_PASSWORD)
        print("[INFO] Password entered")

        captcha_label = wait.until(
            EC.visibility_of_element_located(
                (By.XPATH, "//label[contains(text(), 'What is')] | //div[contains(text(), 'What is')]")
            )
        )
        question_text = captcha_label.text.strip()
        print(f"[INFO] CAPTCHA question: {question_text}")

        match = re.search(r'What is ([0-9\s\+\-\*/]+) = \?', question_text)
        if match:
            math_expr = match.group(1).strip()
            try:
                math_expr_clean = re.sub(r'[^0-9\+\-\*/]', '', math_expr)
                answer = eval(math_expr_clean)
                print(f"[INFO] Computed CAPTCHA answer: {answer}")
                captcha_field = wait.until(EC.visibility_of_element_located((By.CSS_SELECTOR, config.CAPTCHA_SELECTOR)))
                captcha_field.clear()
                captcha_field.send_keys(str(answer))
                print("[INFO] CAPTCHA answer entered")
            except Exception as e:
                print(f"[ERROR] Failed to compute math '{math_expr}': {e}")
                return False
        else:
            print("[ERROR] Could not parse CAPTCHA question")
            return False

        submit_button = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, config.SUBMIT_SELECTOR)))
        driver.execute_script("arguments[0].click();", submit_button)
        print("[INFO] Submit button clicked")

        try:
            wait.until(EC.url_changes(config.LOGIN_URL), timeout=20)
            time.sleep(5)
        except TimeoutException:
            print("[WARNING] URL did not change within 20 seconds, checking page state...")

        if driver.current_url == config.LOGIN_URL:
            print("[ERROR] Login likely failed; URL did not change")
            error_element = driver.find_elements(By.CSS_SELECTOR, ".error-message, .alert-danger, .login-error, .error")
            if error_element:
                print(f"[ERROR] Login failed: {error_element[0].text}")
            else:
                print("[DEBUG] Page source snippet:", driver.page_source[:1000])
            return False

        print("[INFO] Login successful")
        return True

    except WebDriverException as e:
        print(f"[ERROR] Login failed: {str(e)}")
        return False
    except Exception as e:
        print(f"[ERROR] Unexpected error during login: {str(e)}")
        return False

def scrape_once(driver):
    try:
        driver.get(config.SMS_URL)
        wait = WebDriverWait(driver, 10)
        wait.until(EC.presence_of_element_located((By.TAG_NAME, "table")))
        soup = BeautifulSoup(driver.page_source, 'html.parser')
        headers = soup.find_all('th')
        n_idx, s_idx, m_idx = guess_columns(headers)
        if None in (n_idx, s_idx, m_idx):
            print("[WARNING] Could not detect all required columns (number/service/message).")
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
            print("[INFO] OTP sent to Telegram")
    except WebDriverException as e:
        print(f"[ERROR] Scrape failed: {e}")

if __name__ == "__main__":
    options = Options()
    options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/117.0.0.0 Safari/537.36")

    options.binary_location = '/usr/bin/chromium-browser'
    driver = webdriver.Chrome(service=Service('/usr/bin/chromedriver'), options=options)

    try:
        if not login(driver):
            print("[ERROR] Login failed, exiting")
            exit(1)

        print("[INFO] Proceeding to SMS page...")
        while True:
            scrape_once(driver)
            time.sleep(config.SCRAPE_INTERVAL)
    except KeyboardInterrupt:
        print("Shutting down...")
    finally:
        driver.quit()
