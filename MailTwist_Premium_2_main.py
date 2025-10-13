
import os
import json
import logging
import asyncio
from io import BytesIO
from aiogram import Bot, Dispatcher, types
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, InputFile
from aiogram.filters import Command
from aiogram import F
from aiogram.dispatcher.middlewares import BaseMiddleware

# ---------------------------
# CONFIG
# ---------------------------
BOT_TOKEN = "YOUR_BOT_TOKEN"
CHANNEL_USERNAME = "@mailtwist"
HELP_CONTACT = "@professor_cry"
DATA_DIR = "user_data"
os.makedirs(DATA_DIR, exist_ok=True)

logging.basicConfig(level=logging.INFO)

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# ---------------------------
# ERROR HANDLING & AUTO-RECOVER
# ---------------------------
class AutoRecoverMiddleware(BaseMiddleware):
    async def __call__(self, handler, event, data):
        for _ in range(3):  # retry up to 3 times
            try:
                return await handler(event, data)
            except Exception as e:
                logging.error(f"Error in handler: {e}")
                await asyncio.sleep(1)
        if hasattr(event, "message"):
            await event.message.answer("⚠️ Something went wrong. Please try again later.")

dp.update.outer_middleware(AutoRecoverMiddleware())

# ---------------------------
# HELPERS
# ---------------------------
def generate_variations(email):
    try:
        local, domain = email.split("@")
        variations = set()
        for i in range(1, 2 ** len(local)):
            chars = [c.upper() if (i >> j) & 1 else c.lower() for j, c in enumerate(local)]
            variations.add("".join(chars) + "@" + domain)
        return list(variations)
    except Exception:
        return []

def user_file(user_id):
    return os.path.join(DATA_DIR, f"{user_id}.json")

def user_txt_file(user_id, main_email):
    safe_email = main_email.replace("@", "_at_")
    return os.path.join(DATA_DIR, f"{safe_email}.txt")

async def check_channel_join(user_id):
    try:
        member = await bot.get_chat_member(chat_id=CHANNEL_USERNAME, user_id=user_id)
        return member.status not in ["left", "kicked"]
    except Exception as e:
        logging.warning(f"Channel check failed: {e}")
        return False

async def save_emails(user_id, emails):
    all_variations = []
    for email in emails:
        all_variations.extend(generate_variations(email))
    json_path = user_file(user_id)
    data = {"emails": all_variations, "index": 0, "main_email": emails[0]}
    with open(json_path, "w") as f:
        json.dump(data, f)
    txt_path = user_txt_file(user_id, emails[0])
    with open(txt_path, "w") as f:
        for e in all_variations:
            f.write(f"{e}\n")
    return all_variations

def progress_bar(index, total):
    percent = int((index / total) * 100)
    blocks = int((percent / 10))
    bar = "🟩"*blocks + "⬜"*(10-blocks)
    return bar, percent

# ---------------------------
# /start
# ---------------------------
@dp.message(Command("start"))
async def start_handler(message: types.Message):
    if not await check_channel_join(message.from_user.id):
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(
                text="👀 Check & Get Access",
                url=f"https://t.me/{CHANNEL_USERNAME.strip('@')}"
            )]
        ])
        return await message.answer(
            "⚠️ Please join @mailtwist first to unlock MailTwist Premium features.",
            reply_markup=kb
        )
    start_text = (
        "✨ <b>Welcome to MailTwist Premium 2.0</b> ✨\n"
        "🔹 Generate unlimited email variations\n"
        "🔹 TXT/CSV batch uploads supported\n"
        "🔹 Professional progress tracking & TXT download\n"
        "\nCommands:\n"
        "• /get - Next email variation\n"
        "• /summary - Batch progress\n"
        "• /download - Download TXT\n"
        "• /remove - Delete your lists\n"
        "• /help - Guide & Support\n"
        f"❓ Need help? Contact {HELP_CONTACT}"
    )
    await message.answer(start_text, parse_mode="HTML")

# ---------------------------
# /help
# ---------------------------
@dp.message(Command("help"))
async def help_handler(message: types.Message):
    help_text = (
        "📝 <b>MailTwist Premium 2.0 Guide</b> 📝\n"
        "1️⃣ Send a single email or upload TXT/CSV file.\n"
        "2️⃣ /get - fetch next email variation\n"
        "3️⃣ /summary - batch progress overview\n"
        "4️⃣ /download - get all variations as TXT\n"
        "5️⃣ /remove - delete your lists\n"
        f"📬 Support: {HELP_CONTACT}"
    )
    await message.answer(help_text, parse_mode="HTML")

# ---------------------------
# /download
# ---------------------------
@dp.message(Command("download"))
async def download_handler(message: types.Message):
    path = user_file(message.from_user.id)
    if not os.path.exists(path):
        return await message.answer("⚠️ No list found.")
    data = json.load(open(path))
    txt_path = user_txt_file(message.from_user.id, data['main_email'])
    if os.path.exists(txt_path):
        with open(txt_path, "rb") as f:
            await message.answer_document(InputFile(f, filename=f"{data['main_email']}.txt"))
    else:
        await message.answer("⚠️ TXT file not found.")

# ---------------------------
# Run Bot
# ---------------------------
if __name__ == "__main__":
    import uvloop
    asyncio.set_event_loop_policy(uvloop.EventLoopPolicy())
    dp.run_polling(bot, skip_updates=True)
