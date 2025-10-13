import os
import json
import csv
import logging
import asyncio
from aiogram import Bot, Dispatcher, types
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils import executor

# ---------------------------
# CONFIG
# ---------------------------
BOT_TOKEN = "8472314239:AAEuxP4QTgl-gCg4SUl13htj8V7ZE3LB8nc"
CHANNEL_USERNAME = "@mailtwist"
HELP_CONTACT = "@professor_cry"
DATA_DIR = "user_data"
os.makedirs(DATA_DIR, exist_ok=True)

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(bot)
logging.basicConfig(level=logging.INFO)

# ---------------------------
# Helper Functions
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
        member = await bot.get_chat_member(CHANNEL_USERNAME, user_id)
        return member.status not in ["left", "kicked"]
    except:
        return False

async def save_emails(user_id, emails):
    all_variations = []
    for email in emails:
        all_variations.extend(generate_variations(email))
    # Save JSON
    with open(user_file(user_id), "w") as f:
        json.dump({"emails": all_variations, "index": 0}, f)
    # Save CSV
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
# START & HELP
# ---------------------------
@dp.message_handler(commands=["start"])
async def start(message: types.Message):
    if not await check_channel_join(message.from_user.id):
        return await message.answer(f"⚠️ You must join {CHANNEL_USERNAME} to use MailTwist.")
    await message.answer(
        "🎉 **Welcome to MailTwist Premium 2.0**!\n\n"
        "Send a single email or upload a TXT/CSV file containing multiple emails.\n\n"
        "Commands:\n"
        "/get — Fetch next email variation\n"
        "/summary — View batch summary\n"
        "/download — Download all variations\n"
        "/remove — Delete saved email lists\n"
        "/help — Usage instructions"
    )

@dp.message_handler(commands=["help"])
async def help_command(message: types.Message):
    await message.answer(
        "💡 **MailTwist Premium Guide**:\n"
        "1️⃣ Send an email or upload a TXT/CSV file.\n"
        "2️⃣ /get to fetch next email variation with live progress.\n"
        "3️⃣ /summary to view batch progress.\n"
        "4️⃣ /download to get all variations as CSV.\n"
        "5️⃣ /remove to delete saved email lists.\n"
        "❓ Questions? Contact: @professor_cry"
    )

# ---------------------------
# Handle Single Email
# ---------------------------
@dp.message_handler(lambda m: "@" in m.text and "." in m.text)
async def handle_single_email(message: types.Message):
    if not await check_channel_join(message.from_user.id):
        return await message.answer(f"⚠️ Join {CHANNEL_USERNAME} first!")

    email = message.text.strip()
    variations = await save_emails(message.from_user.id, [email])
    await message.answer(f"✅ Generated {len(variations)} variations for your email.")
    await message.answer_document(open(user_csv_file(message.from_user.id), "rb"))

# ---------------------------
# Handle Batch File
# ---------------------------
@dp.message_handler(content_types=[types.ContentType.DOCUMENT])
async def handle_file_upload(message: types.Message):
    if not await check_channel_join(message.from_user.id):
        return await message.answer(f"⚠️ Join {CHANNEL_USERNAME} first!")

    file = message.document
    if not file.file_name.endswith((".txt", ".csv")):
        return await message.answer("⚠️ Only TXT or CSV files supported.")

    temp_path = os.path.join(DATA_DIR, f"temp_{message.from_user.id}.txt")
    await file.download(destination_file=temp_path)
    with open(temp_path, "r") as f:
        emails = [line.strip() for line in f if "@" in line]
    variations = await save_emails(message.from_user.id, emails)
    os.remove(temp_path)

    await message.answer(f"✅ Batch processed {len(emails)} emails, generating {len(variations)} variations total.")
    await message.answer_document(open(user_csv_file(message.from_user.id), "rb"))

# ---------------------------
# Fancy /get Command
# ---------------------------
@dp.message_handler(commands=["get"])
async def get_next(message: types.Message):
    try:
        path = user_file(message.from_user.id)
        if not os.path.exists(path):
            return await message.answer("⚠️ No email list found. Send email(s) first.")

        data = json.load(open(path))
        total = len(data["emails"])
        if data["index"] >= total:
            return await message.answer("🎉 All emails in this batch finished!")

        # Typing animation
        typing_msg = await message.answer("💌 Fetching next email...")
        for _ in range(3):
            await bot.edit_message_text("💌 Fetching next email.", message.chat.id, typing_msg.message_id)
            await asyncio.sleep(0.5)
            await bot.edit_message_text("💌 Fetching next email..", message.chat.id, typing_msg.message_id)
            await asyncio.sleep(0.5)
            await bot.edit_message_text("💌 Fetching next email...", message.chat.id, typing_msg.message_id)
            await asyncio.sleep(0.5)

        current_email = data["emails"][data["index"]]
        data["index"] += 1
        json.dump(data, open(path, "w"))

        bar, percent = progress_bar(data["index"], total)
        kb = InlineKeyboardMarkup().add(InlineKeyboardButton("Next Email ▶️", callback_data="next_email"))
        await bot.edit_message_text(
            f"📧 **Email:** {current_email}\n"
            f"📊 **Progress:** {bar} {percent}% ({data['index']}/{total} remaining {total - data['index']})",
            message.chat.id, typing_msg.message_id, reply_markup=kb
        )

    except Exception as e:
        logging.error(f"Error in /get: {e}")
        await message.answer("⚠️ Something went wrong. Try again.")

@dp.callback_query_handler(lambda c: c.data == "next_email")
async def next_email(call: types.CallbackQuery):
    await get_next(types.Message(chat=call.message.chat, from_user=call.from_user, text="/get"))

# ---------------------------
# /summary Command
# ---------------------------
@dp.message_handler(commands=["summary"])
async def batch_summary(message: types.Message):
    path = user_file(message.from_user.id)
    if not os.path.exists(path):
        return await message.answer("⚠️ No email list found.")

    data = json.load(open(path))
    total = len(data["emails"])
    sent = data["index"]
    remaining = total - sent

    await message.answer(
        f"📌 **Batch Summary Card**\n"
        f"🟢 Total emails: {total}\n"
        f"✅ Sent: {sent}\n"
        f"⏳ Remaining: {remaining}\n"
        f"💡 Download all variations: /download"
    )

# ---------------------------
# /download Command
# ---------------------------
@dp.message_handler(commands=["download"])
async def download_variations(message: types.Message):
    csv_path = user_csv_file(message.from_user.id)
    if os.path.exists(csv_path):
        await message.answer_document(open(csv_path, "rb"))
    else:
        await message.answer("⚠️ No variations found. Send email(s) first.")

# ---------------------------
# /remove Command
# ---------------------------
@dp.message_handler(commands=["remove"])
async def remove_files(message: types.Message):
    files = [f for f in os.listdir(DATA_DIR) if f.endswith(".json")]
    if not files:
        return await message.answer("⚠️ No saved lists found.")
    kb = InlineKeyboardMarkup()
    for f in files:
        kb.add(InlineKeyboardButton(f"🗑 Remove {f}", callback_data=f"remove_{f}"))
    await message.answer("Select a file to remove:", reply_markup=kb)

@dp.callback_query_handler(lambda c: c.data.startswith("remove_"))
async def remove_file(call: types.CallbackQuery):
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
    executor.start_polling(dp, skip_updates=True)
