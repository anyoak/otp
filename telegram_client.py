import telegram
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
import config

bot = telegram.Bot(token=config.BOT_TOKEN)

def esc(text):
    return telegram.utils.helpers.escape_markdown(text, version=2)

def send_message_html(html_text, buttons=None):
    keyboard = None
    if buttons:
        keyboard = InlineKeyboardMarkup([[InlineKeyboardButton(b[0], url=b[1])] for b in buttons])
    bot.send_message(chat_id=config.CHAT_ID, text=html_text, parse_mode='HTML', reply_markup=keyboard)
