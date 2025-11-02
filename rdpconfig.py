# config.py

# Telegram Bot Configuration
BOT_TOKEN = "YOUR_BOT_TOKEN_HERE"  # আপনার বট টোকেন
CHAT_ID = "YOUR_CHAT_ID_HERE"     # আপনার চ্যাট আইডি

# Website URLs
LOGIN_URL = "https://www.orangecarrier.com/live/login"
CALL_URL = "https://www.orangecarrier.com/live/calls"
BASE_URL = "https://www.orangecarrier.com/live"

# File paths
DOWNLOAD_FOLDER = "recordings"

# Timing configurations
CHECK_INTERVAL = 5  # seconds
RECORDING_RETRY_DELAY = 10  # seconds
MAX_RECORDING_WAIT = 300  # seconds (5 minutes)
MAX_ERRORS = 10