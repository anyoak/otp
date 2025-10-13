import os
import json
import csv
import logging
import asyncio
from aiogram import Bot, Dispatcher, types
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.filters import Command
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram import F

# ---------------------------
# CONFIG
# ---------------------------
BOT_TOKEN = "8472314239:AAEuxP4QTgl-gCg4SUl13htj8V7ZE3LB8nc"
CHANNEL_USERNAME = "@mailtwist"
HELP_CONTACT = "@professor_cry"
DATA_DIR = "user_data"
os.makedirs(DATA_DIR, exist_ok=True)

logging.basicConfig(level=logging.INFO)

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# ---------------------------
# Helpers
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

def user_csv_file(user_id):
    return os.path.join(DATA_DIR, f"{user_id}_variations.csv")

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
    with open(user_file(user_id), "w") as f:
        json.dump({"emails": all_variations, "index": 0}, f)
    with open(user_csv_file(user_id), "w", newline="") as csvfile:
        writer = csv.writer(csvfile)
        for e in all_variations:
            writer.writerow([e])
    return all_variations

def progress_bar(index, total):
    percent = int((index / total) * 100)
    blocks = int((percent / 10))
    bar = "🟩"*blocks + "⬜"*(10-blocks)
    return bar, percent

# ---------------------------
# Commands (Premium Look)
# ---------------------------
@dp.message(Command("start"))
async def start_handler(message: types.Message):
    if not await check_channel_join(message.from_user.id):
        kb = InlineKeyboardBuilder()
        kb.add(InlineKeyboardButton(
            text="👀 Check & Get Access",
            url=f"https://t.me/{CHANNEL_USERNAME.strip('@')}"
        ))
        return await message.answer(
            "⚠️ Please join @mailtwist first to unlock MailTwist Premium features.",
            reply_markup=kb.as_markup()
        )

    start_text = (
        "✨ <b>Welcome to MailTwist Premium 2.0</b> ✨\n\n"
        "🔹 <b>Generate unlimited email variations</b> with a single click.\n"
        "🔹 Supports <b>TXT/CSV batch uploads</b>.\n"
        "🔹 Professional progress tracking & CSV download.\n\n"
        "💡 Quick Commands:\n"
        "• /get - Next email variation\n"
        "• /summary - Batch progress\n"
        "• /download - Download CSV\n"
        "• /remove - Delete your lists\n"
        "• /help - Guide & Support\n\n"
        f"❓ Need help? Contact {HELP_CONTACT}"
    )
    await message.answer(start_text, parse_mode="HTML")

@dp.message(Command("help"))
async def help_handler(message: types.Message):
    help_text = (
        "📝 <b>MailTwist Premium 2.0 Guide</b> 📝\n\n"
        "1️⃣ Send a single email or upload TXT/CSV file.\n"
        "2️⃣ /get - fetch next email variation (touch-to-copy!)\n"
        "3️⃣ /summary - batch progress overview\n"
        "4️⃣ /download - get all variations as CSV\n"
        "5️⃣ /remove - delete your lists\n\n"
        f"📬 Support & Questions: {HELP_CONTACT}\n"
        "💎 Enjoy the Premium Experience!"
    )
    await message.answer(help_text, parse_mode="HTML")

# ---------------------------
# Email / File Handlers
# ---------------------------
@dp.message(lambda m: "@" in m.text and "." in m.text)
async def single_email_handler(message: types.Message):
    if not await check_channel_join(message.from_user.id):
        return await message.answer(f"⚠️ Join {CHANNEL_USERNAME} first!")

    email = message.text.strip()
    variations = await save_emails(message.from_user.id, [email])
    await message.answer(f"✅ Generated {len(variations)} variations.")
    await message.answer_document(open(user_csv_file(message.from_user.id), "rb"))

@dp.message(lambda m: m.document)
async def file_upload_handler(message: types.Message):
    if not await check_channel_join(message.from_user.id):
        return await message.answer(f"⚠️ Join {CHANNEL_USERNAME} first!")

    file = await message.document.get_file()
    ext = os.path.splitext(message.document.file_name)[1]
    if ext not in [".txt", ".csv"]:
        return await message.answer("⚠️ Only TXT/CSV files supported.")

    temp_path = os.path.join(DATA_DIR, f"temp_{message.from_user.id}.txt")
    await message.document.download(destination_file=temp_path)
    with open(temp_path, "r") as f:
        emails = [line.strip() for line in f if "@" in line]
    variations = await save_emails(message.from_user.id, emails)
    os.remove(temp_path)

    await message.answer(f"✅ Batch processed {len(emails)} emails, {len(variations)} variations total.")
    await message.answer_document(open(user_csv_file(message.from_user.id), "rb"))

# ---------------------------
# /get Command
# ---------------------------
@dp.message(Command("get"))
async def get_next_handler(message: types.Message):
    path = user_file(message.from_user.id)
    if not os.path.exists(path):
        return await message.answer("⚠️ No email list found. Send email(s) first.")

    data = json.load(open(path))
    total = len(data["emails"])
    if data["index"] >= total:
        return await message.answer("🎉 All emails finished!")

    msg = await message.answer("💌 Fetching next email...")
    for i in range(3):
        await msg.edit_text("💌 Fetching next email" + "."*(i+1))
        await asyncio.sleep(0.5)

    current_email = data["emails"][data["index"]]
    data["index"] += 1
    json.dump(data, open(path, "w"))

    bar, percent = progress_bar(data["index"], total)
    kb = InlineKeyboardBuilder()
    kb.add(InlineKeyboardButton(text="Next Email ▶️", callback_data="next_email"))

    await msg.edit_text(
        f"📧 <code>{current_email}</code>\n📊 {bar} {percent}% ({data['index']}/{total}) remaining {total - data['index']}",
        reply_markup=kb.as_markup(),
        parse_mode="HTML"
    )

@dp.callback_query(F.data=="next_email")
async def next_email_callback(call: types.CallbackQuery):
    msg = types.Message(chat=call.message.chat, from_user=call.from_user, text="/get")
    await get_next_handler(msg)

# ---------------------------
# /summary Command
# ---------------------------
@dp.message(Command("summary"))
async def summary_handler(message: types.Message):
    path = user_file(message.from_user.id)
    if not os.path.exists(path):
        return await message.answer("⚠️ No email list found.")

    data = json.load(open(path))
    total = len(data["emails"])
    sent = data["index"]
    remaining = total - sent

    summary_text = (
        "📌 <b>MailTwist Batch Summary</b> 📌\n\n"
        f"🟢 <b>Total Emails:</b> {total}\n"
        f"✅ <b>Processed:</b> {sent}\n"
        f"⏳ <b>Remaining:</b> {remaining}\n\n"
        f"💾 Use /download to get full CSV\n"
        f"💎 Keep creating variations like a Pro!"
    )
    await message.answer(summary_text, parse_mode="HTML")

# ---------------------------
# /download Command
# ---------------------------
@dp.message(Command("download"))
async def download_handler(message: types.Message):
    csv_path = user_csv_file(message.from_user.id)
    if os.path.exists(csv_path):
        await message.answer_document(open(csv_path, "rb"))
    else:
        await message.answer("⚠️ No variations found. Send email(s) first.")

# ---------------------------
# /remove Command
# ---------------------------
@dp.message(Command("remove"))
async def remove_handler(message: types.Message):
    files = [f for f in os.listdir(DATA_DIR) if f.endswith(".json")]
    if not files:
        return await message.answer("⚠️ No saved lists.")
    kb = InlineKeyboardBuilder()
    for f in files:
        kb.add(InlineKeyboardButton(text=f"🗑 Remove {f}", callback_data=f"remove_{f}"))
    await message.answer("Select file to remove:", reply_markup=kb.as_markup())

@dp.callback_query(F.data.startswith("remove_"))
async def remove_callback(call: types.CallbackQuery):
    filename = call.data.replace("remove_", "")
    path = os.path.join(DATA_DIR, filename)
    csv_path = user_csv_file(call.from_user.id)
    if os.path.exists(path):
        os.remove(path)
    if os.path.exists(csv_path):
        os.remove(csv_path)
    await call.message.edit_text(f"🗑 File and CSV removed successfully!")

# ---------------------------
# Run Bot
# ---------------------------
if __name__ == "__main__":
    import uvloop
    asyncio.set_event_loop_policy(uvloop.EventLoopPolicy())
    dp.run_polling(bot, skip_updates=True)
