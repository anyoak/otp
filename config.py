import os

# ==== Telegram ====
BOT_TOKEN = os.getenv('BOT_TOKEN', 'your_bot_token_here')  # Fetch from environment, default placeholder
CHAT_ID = os.getenv('CHAT_ID', 'your_chat_id_here')       # Fetch from environment, default placeholder

# ==== Target site ====
LOGIN_URL = os.getenv('LOGIN_URL', 'http://94.23.120.156/ints/login')
SMS_URL = os.getenv('SMS_URL', 'http://94.23.120.156/ints/client/SMSCDRStats')

# Login credentials
SITE_USERNAME = os.getenv('SITE_USERNAME', 'your_username_here')  # Fetch from environment, default placeholder
SITE_PASSWORD = os.getenv('SITE_PASSWORD', 'your_password_here')  # Fetch from environment, default placeholder

# CSS selectors for the login form
USERNAME_SELECTOR = os.getenv('USERNAME_SELECTOR', 'input[type="text"]:nth-of-type(1)')
PASSWORD_SELECTOR = os.getenv('PASSWORD_SELECTOR', 'input[type="password"]')
CAPTCHA_SELECTOR = os.getenv('CAPTCHA_SELECTOR', 'input[type="text"]:nth-of-type(2)')
SUBMIT_SELECTOR = os.getenv('SUBMIT_SELECTOR', 'button')

# Scrape interval (seconds)
SCRAPE_INTERVAL = int(os.getenv('SCRAPE_INTERVAL', '6'))  # Convert to int, default 6 seconds

# Timezone offset (hours) for Dhaka (+6)
TZ_OFFSET_HOURS = int(os.getenv('TZ_OFFSET_HOURS', '6'))  # Convert to int, default 6 hours
