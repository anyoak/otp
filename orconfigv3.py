# config.py - Orangecarrier monitor configuration
# Edit the values below before running main.py

# ---------------- Telegram Bot Configuration ----------------
BOT_TOKEN = "8522542742:AAHr7nwP7BBTfOLFBLemRhn4bDe5bySoaIc"                # <-- Replace with your Telegram Bot token
CHAT_ID = "-1002631004312"                  # Channel or chat ID where messages are sent

# ---------------- Website / Paths ----------------
LOGIN_URL = "https://www.orangecarrier.com/login"
CALL_URL = "https://www.orangecarrier.com/live/calls"
BASE_URL = "https://www.orangecarrier.com"

# ---------------- Monitoring Settings ----------------
CHECK_INTERVAL = 3                          # seconds between main loop iterations
MAX_ERRORS = 5                              # stop after this many consecutive errors (can restart externally)
DOWNLOAD_FOLDER = "recordings"              # folder to save call recordings

# ---------------- Recording Settings ----------------
RECORDING_RETRY_DELAY = 15                  # seconds to wait between retries for a recording
RECORDING_CHECK_INTERVAL = 10               # seconds between processing pending recordings
MAX_RECORDING_WAIT = 600                    # seconds to wait max for a recording before timing out

# ---------------- Browser / Cookie Settings ----------------
USER_DATA_DIR = "ff_profile"            # Chrome profile folder to persist session (recommended)
COOKIES_FILE = "cookies.pkl"                # path where cookies will be saved/loaded
HEADLESS = False                            # set True only if you know Cloudflare won't block headless
WINDOW_SIZE = "1366,768"

# ---------------- Proxy (Authenticated) ----------------
# Format: "http://username:password@host:port"
# Your provided proxy:
PROXY = "http://anam1gbPL2510-zone-abc-region-BD:F2yrC6zUFL4j@as.75ce620de1d51edc.abcproxy.vip:4950"

# If you prefer NO proxy, set:
# PROXY = None

# ---------------- Networking / UA ----------------
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"

# ---------------- Misc ----------------
# Increase timeouts or tweak limits if you have a slow connection / proxy
REQUEST_TIMEOUT = 30        # seconds for HTTP requests (downloads, Telegram API calls)
