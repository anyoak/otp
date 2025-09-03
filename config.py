import os

# ==== Telegram ====
BOT_TOKEN = os.getenv('BOT_TOKEN', 'your_bot_token_here')
CHAT_ID = os.getenv('CHAT_ID', 'your_chat_id_here')

# ==== Target site ====
LOGIN_URL = os.getenv('LOGIN_URL', 'http://94.23.120.156/ints/login')
SMS_URL = os.getenv('SMS_URL', 'http://94.23.120.156/ints/client/SMSCDRStats')

# Login credentials
SITE_USERNAME = os.getenv('SITE_USERNAME', 'your_username_here')
SITE_PASSWORD = os.getenv('SITE_PASSWORD', 'your_password_here')

# CSS selectors for the login form
USERNAME_SELECTOR = os.getenv('USERNAME_SELECTOR', 'input[name="username"]')
PASSWORD_SELECTOR = os.getenv('PASSWORD_SELECTOR', 'input[name="password"]')
CAPTCHA_SELECTOR = os.getenv('CAPTCHA_SELECTOR', 'input[name="answer"]')
SUBMIT_SELECTOR = os.getenv('SUBMIT_SELECTOR', 'button.login100-form-btn')

# Scrape interval (seconds)
SCRAPE_INTERVAL = int(os.getenv('SCRAPE_INTERVAL', '6'))

# Timezone offset (hours) for Dhaka (+6)
TZ_OFFSET_HOURS = int(os.getenv('TZ_OFFSET_HOURS', '6'))
