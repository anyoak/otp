from dotenv import load_dotenv
import os

load_dotenv()  # For local testing; on Render, env vars are set directly

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

SMS_URL = os.getenv("SMS_URL")
LOGIN_URL = os.getenv("LOGIN_URL")

SITE_USERNAME = os.getenv("SITE_USERNAME")
SITE_PASSWORD = os.getenv("SITE_PASSWORD")

USERNAME_SELECTOR = os.getenv("USERNAME_SELECTOR")
PASSWORD_SELECTOR = os.getenv("PASSWORD_SELECTOR")
SUBMIT_SELECTOR = os.getenv("SUBMIT_SELECTOR")

SCRAPE_INTERVAL = int(os.getenv("SCRAPE_INTERVAL", 60))

TZ_OFFSET_HOURS = int(os.getenv("TZ_OFFSET_HOURS", 0))
