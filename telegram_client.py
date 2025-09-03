from telegram import Bot, InlineKeyboardButton, InlineKeyboardMarkup
import config
import html

def esc(text: str) -> str:
    """Escape HTML special characters for Telegram."""
    return html.escape(str(text))

def send_message_html(message: str, buttons: list = None):
    """Send a message to Telegram with HTML formatting."""
    try:
        bot = Bot(token=config.TELEGRAM_BOT_TOKEN)
        keyboard = None
        if buttons:
            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton(text=text, url=url) for text, url in row]
                for row in buttons
            ])
        bot.send_message(
            chat_id=config.TELEGRAM_CHAT_ID,
            text=message,
            parse_mode='HTML',
            reply_markup=keyboard,
            disable_web_page_preview=True
        )
    except Exception as e:
        print(f"[ERROR] Failed to send Telegram message: {e}")
