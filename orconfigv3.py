# ===== Orangecarrier Monitor Config =====

# Telegram Bot Configuration
BOT_TOKEN = "8522542742:AAHr7nwP7BBTfOLFBLemRhn4bDe5bySoaIc"       # 🔹 Replace with your Telegram Bot Token
CHAT_ID = "-1002631004312"         # 🔹 Replace with your Channel or User ID

# Website Configuration
LOGIN_URL = "https://www.orangecarrier.com/login"
CALL_URL = "https://www.orangecarrier.com/live/calls"
BASE_URL = "https://www.orangecarrier.com"

# Monitoring Settings
CHECK_INTERVAL = 3                 # 🔹 Check every 3 seconds for new calls
MAX_ERRORS = 5                     # 🔹 Stop or restart after 5 consecutive errors
DOWNLOAD_FOLDER = "recordings"     # 🔹 Folder where recordings will be saved

# Recording Settings
RECORDING_RETRY_DELAY = 15         # 🔹 Retry every 15 seconds if recording not found
MAX_RECORDING_WAIT = 600           # 🔹 Maximum wait time (10 minutes) for a recording

# Optional Settings
PROXY = None                       # Example: "http://user:pass@ip:port"
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"

# ===== End of Config ===== 
