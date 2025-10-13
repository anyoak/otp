import os
import json
import logging
import asyncio
from io import BytesIO
from aiogram import Bot, Dispatcher, types, BaseMiddleware
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, InputFile
from aiogram.filters import Command
from aiogram import F
from aiogram.client.default import DefaultBotProperties

# ---------------------------
# CONFIG
# ---------------------------
BOT_TOKEN = "8472314239:AAEuxP4QTgl-gCg4SUl13htj8V7ZE3LB8nc"
CHANNEL_USERNAME = "@mailtwist"
HELP_CONTACT = "@professor_cry"
DATA_DIR = "user_data"
os.makedirs(DATA_DIR, exist_ok=True)

logging.basicConfig(level=logging.INFO)

# Initialize bot with parse_mode
bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode='HTML'))
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

# Register middleware
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
    await message.answer(start_text)

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
    await message.answer(help_text)

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
# Missing Handlers (Added for completeness)
# ---------------------------
@dp.message(Command("get"))
async def get_handler(message: types.Message):
    path = user_file(message.from_user.id)
    if not os.path.exists(path):
        return await message.answer("⚠️ No email list found. Please send an email first.")
    
    with open(path, "r") as f:
        data = json.load(f)
    
    if data["index"] >= len(data["emails"]):
        await message.answer("🎉 You've reached the end of your email variations!")
        return
    
    email = data["emails"][data["index"]]
    data["index"] += 1
    
    with open(path, "w") as f:
        json.dump(data, f)
    
    bar, percent = progress_bar(data["index"], len(data["emails"]))
    
    response_text = (
        f"📧 Email Variation #{data['index']}:\n"
        f"<code>{email}</code>\n\n"
        f"📊 Progress: {data['index']}/{len(data['emails'])}\n"
        f"{bar} {percent}%"
    )
    await message.answer(response_text)

@dp.message(Command("summary"))
async def summary_handler(message: types.Message):
    path = user_file(message.from_user.id)
    if not os.path.exists(path):
        return await message.answer("⚠️ No email list found.")
    
    with open(path, "r") as f:
        data = json.load(f)
    
    bar, percent = progress_bar(data["index"], len(data["emails"]))
    
    summary_text = (
        f"📊 <b>Batch Progress Summary</b>\n"
        f"📧 Main Email: <code>{data['main_email']}</code>\n"
        f"🔢 Total Variations: {len(data['emails'])}\n"
        f"📍 Current Position: {data['index']}\n"
        f"📈 Progress: {percent}%\n"
        f"{bar}\n"
        f"🔄 Remaining: {len(data['emails']) - data['index']}"
    )
    await message.answer(summary_text)

@dp.message(Command("remove"))
async def remove_handler(message: types.Message):
    path = user_file(message.from_user.id)
    if os.path.exists(path):
        with open(path, "r") as f:
            data = json.load(f)
        txt_path = user_txt_file(message.from_user.id, data['main_email'])
        if os.path.exists(txt_path):
            os.remove(txt_path)
        os.remove(path)
        await message.answer("✅ Your email list has been removed successfully.")
    else:
        await message.answer("⚠️ No list found to remove.")

# Handle email input and file uploads
@dp.message(F.text & ~F.text.startswith('/'))
async def email_input_handler(message: types.Message):
    email = message.text.strip()
    if "@" not in email or "." not in email.split("@")[1]:
        await message.answer("⚠️ Please enter a valid email address.")
        return
    
    variations = await save_emails(message.from_user.id, [email])
    await message.answer(f"✅ Generated {len(variations)} variations for: <code>{email}</code>\nUse /get to start retrieving them.")

@dp.message(F.document)
async def file_upload_handler(message: types.Message):
    if not message.document:
        return
    
    file_name = message.document.file_name or ""
    if not (file_name.endswith('.txt') or file_name.endswith('.csv')):
        await message.answer("⚠️ Please upload a .txt or .csv file.")
        return
    
    try:
        file = await bot.download(message.document)
        content = file.read().decode('utf-8')
        emails = [line.strip() for line in content.splitlines() if "@" in line and line.strip()]
        
        if not emails:
            await message.answer("⚠️ No valid emails found in the file.")
            return
        
        variations = await save_emails(message.from_user.id, emails)
        await message.answer(f"✅ Processed {len(emails)} emails and generated {len(variations)} total variations.\nUse /get to start retrieving them.")
        
    except Exception as e:
        logging.error(f"File processing error: {e}")
        await message.answer("⚠️ Error processing file. Please try again.")

# ---------------------------
# Run Bot
# ---------------------------
if __name__ == "__main__":
    try:
        import uvloop
        asyncio.set_event_loop_policy(uvloop.EventLoopPolicy())
    except ImportError:
        logging.warning("uvloop not available, using default event loop")
    
    logging.info("Bot starting...")
    dp.run_polling(bot, skip_updates=True)
