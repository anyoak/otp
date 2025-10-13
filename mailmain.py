import os
import json
import csv
import logging
import asyncio
from aiogram import Bot, Dispatcher, types, BaseMiddleware
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, InputFile
from aiogram.filters import Command
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram import F
from aiogram.client.default import DefaultBotProperties

# ---------------------------
# CONFIG
# ---------------------------
BOT_TOKEN = "8472314239:AAEuxP4QTgl-gCg4SUl13htj8V7ZE3LB8nc"  # Replace with your actual token
CHANNEL_USERNAME = "@mailtwist"
HELP_CONTACT = "@professor_cry"
DATA_DIR = "user_data"
os.makedirs(DATA_DIR, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Initialize bot with HTML parse mode
bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode='HTML'))
dp = Dispatcher()

# ---------------------------
# AUTO-RECOVERY MIDDLEWARE
# ---------------------------
class ErrorHandlerMiddleware(BaseMiddleware):
    async def __call__(self, handler, event, data):
        try:
            return await handler(event, data)
        except Exception as e:
            logger.error(f"Error in handler: {e}", exc_info=True)
            try:
                if hasattr(event, 'message') and event.message:
                    await event.message.answer("⚠️ Something went wrong. Please try again or contact support.")
            except:
                pass
            return

dp.update.outer_middleware(ErrorHandlerMiddleware())

# ---------------------------
# HELPERS
# ---------------------------
def generate_variations(email):
    """Generate email variations by changing case of local part"""
    try:
        if "@" not in email:
            return []
            
        local, domain = email.split("@")
        if not local or not domain:
            return []
            
        variations = set()
        # Generate variations by changing case
        for i in range(1, min(2 ** len(local), 1000)):  # Limit to 1000 variations
            chars = [c.upper() if (i >> j) & 1 else c.lower() for j, c in enumerate(local)]
            variations.add("".join(chars) + "@" + domain)
        return list(variations)
    except Exception as e:
        logger.error(f"Error generating variations for {email}: {e}")
        return []

def user_file(user_id):
    """Get user's JSON data file path"""
    return os.path.join(DATA_DIR, f"{user_id}.json")

def user_csv_file(user_id):
    """Get user's CSV file path"""
    return os.path.join(DATA_DIR, f"{user_id}_variations.csv")

async def check_channel_join(user_id):
    """Check if user has joined the channel"""
    try:
        member = await bot.get_chat_member(chat_id=CHANNEL_USERNAME, user_id=user_id)
        return member.status not in ["left", "kicked"]
    except Exception as e:
        logger.warning(f"Channel check failed for user {user_id}: {e}")
        return False

async def save_emails(user_id, emails):
    """Save email variations for user"""
    try:
        all_variations = []
        valid_emails = [email.strip() for email in emails if "@" in email and "." in email.split("@")[1]]
        
        if not valid_emails:
            return []
            
        for email in valid_emails:
            variations = generate_variations(email)
            all_variations.extend(variations)
        
        # Remove duplicates
        all_variations = list(set(all_variations))
        
        # Save to JSON
        user_data = {
            "user_id": user_id,
            "emails": all_variations,
            "index": 0,
            "original_emails": valid_emails,
            "total_count": len(all_variations),
            "created_at": str(asyncio.get_event_loop().time())
        }
        
        with open(user_file(user_id), "w") as f:
            json.dump(user_data, f, indent=2)
        
        # Save to CSV
        with open(user_csv_file(user_id), "w", newline="", encoding="utf-8") as csvfile:
            writer = csv.writer(csvfile)
            writer.writerow(["Email Variations"])
            for email in all_variations:
                writer.writerow([email])
        
        logger.info(f"Saved {len(all_variations)} variations for user {user_id}")
        return all_variations
        
    except Exception as e:
        logger.error(f"Error saving emails for user {user_id}: {e}")
        return []

def progress_bar(index, total):
    """Generate progress bar"""
    if total == 0:
        return "⬜⬜⬜⬜⬜⬜⬜⬜⬜⬜", 0
        
    percent = min(100, int((index / total) * 100))
    blocks = int((percent / 10))
    bar = "🟩" * blocks + "⬜" * (10 - blocks)
    return bar, percent

def get_user_data(user_id):
    """Get user data safely"""
    try:
        path = user_file(user_id)
        if os.path.exists(path):
            with open(path, "r") as f:
                return json.load(f)
    except Exception as e:
        logger.error(f"Error reading user data for {user_id}: {e}")
    return None

def save_user_data(user_id, data):
    """Save user data safely"""
    try:
        path = user_file(user_id)
        with open(path, "w") as f:
            json.dump(data, f, indent=2)
        return True
    except Exception as e:
        logger.error(f"Error saving user data for {user_id}: {e}")
        return False

# ---------------------------
# COMMAND HANDLERS
# ---------------------------
@dp.message(Command("start"))
async def start_handler(message: types.Message):
    """Handle /start command"""
    user_id = message.from_user.id
    username = message.from_user.username or message.from_user.first_name
    
    if not await check_channel_join(user_id):
        kb = InlineKeyboardBuilder()
        kb.add(InlineKeyboardButton(
            text="👀 Join Channel & Get Access",
            url=f"https://t.me/{CHANNEL_USERNAME.strip('@')}"
        ))
        kb.add(InlineKeyboardButton(
            text="✅ I've Joined",
            callback_data="check_join"
        ))
        return await message.answer(
            "⚠️ Please join our channel first to unlock MailTwist Premium features!",
            reply_markup=kb.as_markup()
        )

    welcome_text = (
        "✨ <b>Welcome to MailTwist Premium 2.0</b> ✨\n\n"
        "🚀 <b>Advanced Email Variation Generator</b>\n\n"
        "🔹 <b>Unlimited email variations</b> with smart case switching\n"
        "🔹 <b>Batch processing</b> - Upload TXT/CSV files\n"  
        "🔹 <b>Professional tracking</b> with progress bars\n"
        "🔹 <b>Secure & Private</b> - Your data stays with you\n\n"
        "💡 <b>Quick Commands:</b>\n"
        "• /get - Get next email variation\n"
        "• /summary - View progress overview\n"
        "• /download - Download all variations as CSV\n"
        "• /remove - Delete your data\n"
        "• /help - Guide & support\n\n"
        f"📬 <b>Support:</b> {HELP_CONTACT}\n"
        f"👤 <b>User ID:</b> <code>{user_id}</code>"
    )
    await message.answer(welcome_text)

@dp.callback_query(F.data == "check_join")
async def check_join_callback(callback: types.CallbackQuery):
    """Handle join check callback"""
    if await check_channel_join(callback.from_user.id):
        await callback.message.edit_text(
            "✅ Great! You've joined the channel. Use /start to begin."
        )
    else:
        await callback.answer("❌ Please join the channel first!", show_alert=True)

@dp.message(Command("help"))
async def help_handler(message: types.Message):
    """Handle /help command"""
    help_text = (
        "📝 <b>MailTwist Premium 2.0 - Complete Guide</b> 📝\n\n"
        "🔸 <b>Step 1:</b> Send a single email address or upload a TXT/CSV file\n"
        "🔸 <b>Step 2:</b> Use /get to retrieve variations one by one\n"
        "🔸 <b>Step 3:</b> Check progress with /summary\n"
        "🔸 <b>Step 4:</b> Download all variations with /download\n\n"
        "💎 <b>Features:</b>\n"
        "• Smart case variation generation\n"
        "• Batch file processing\n"
        "• Progress tracking\n"
        "• Secure data storage\n\n"
        "🛠 <b>Commands:</b>\n"
        "/start - Start the bot\n"
        "/get - Get next email variation\n" 
        "/summary - View progress\n"
        "/download - Download CSV\n"
        "/remove - Delete your data\n"
        "/help - This guide\n\n"
        f"📬 <b>Support Contact:</b> {HELP_CONTACT}\n"
        "🚀 <b>Enjoy premium email variation generation!</b>"
    )
    await message.answer(help_text)

# ---------------------------
# EMAIL & FILE HANDLERS
# ---------------------------
@dp.message(F.text & ~F.text.startswith('/'))
async def text_message_handler(message: types.Message):
    """Handle text messages (emails)"""
    user_id = message.from_user.id
    
    if not await check_channel_join(user_id):
        return await message.answer(f"⚠️ Please join {CHANNEL_USERNAME} first to use this bot!")
    
    text = message.text.strip()
    
    # Check if it looks like an email
    if "@" in text and "." in text.split("@")[1]:
        # Single email
        variations = await save_emails(user_id, [text])
        
        if variations:
            response_text = (
                f"✅ <b>Email Variations Generated Successfully!</b>\n\n"
                f"📧 <b>Original Email:</b> <code>{text}</code>\n"
                f"🔢 <b>Total Variations:</b> {len(variations)}\n\n"
                f"💡 Use /get to start retrieving variations\n"
                f"📊 Use /summary to check progress\n"
                f"💾 Use /download to get all variations as CSV"
            )
            
            kb = InlineKeyboardBuilder()
            kb.add(InlineKeyboardButton(text="🚀 Get First Variation", callback_data="get_first"))
            kb.add(InlineKeyboardButton(text="📥 Download CSV", callback_data="download_csv"))
            
            await message.answer(response_text, reply_markup=kb.as_markup())
        else:
            await message.answer("❌ Could not generate variations. Please check the email format.")
    
    else:
        # Multiple emails in text (one per line)
        emails = [line.strip() for line in text.split('\n') if line.strip() and "@" in line and "." in line.split("@")[1]]
        
        if emails:
            variations = await save_emails(user_id, emails)
            
            if variations:
                response_text = (
                    f"✅ <b>Batch Email Processing Complete!</b>\n\n"
                    f"📧 <b>Original Emails:</b> {len(emails)}\n"
                    f"🔢 <b>Total Variations:</b> {len(variations)}\n\n"
                    f"💡 Use /get to start retrieving variations\n"
                    f"📊 Use /summary to check progress\n"
                    f"💾 Use /download to get all variations as CSV"
                )
                
                kb = InlineKeyboardBuilder()
                kb.add(InlineKeyboardButton(text="🚀 Get First Variation", callback_data="get_first"))
                kb.add(InlineKeyboardButton(text="📥 Download CSV", callback_data="download_csv"))
                
                await message.answer(response_text, reply_markup=kb.as_markup())
            else:
                await message.answer("❌ Could not generate variations from the provided emails.")
        else:
            await message.answer(
                "📧 <b>Please send a valid email address or upload a file</b>\n\n"
                "You can:\n"
                "• Send a single email address\n"
                "• Send multiple emails (one per line)\n"
                "• Upload a TXT/CSV file with emails\n\n"
                "Example: <code>example@gmail.com</code>"
            )

@dp.message(F.document)
async def document_handler(message: types.Message):
    """Handle document uploads (TXT/CSV files)"""
    user_id = message.from_user.id
    
    if not await check_channel_join(user_id):
        return await message.answer(f"⚠️ Please join {CHANNEL_USERNAME} first to use this bot!")
    
    document = message.document
    file_name = document.file_name or ""
    file_size = document.file_size or 0
    
    # Check file type and size
    if not file_name.lower().endswith(('.txt', '.csv')):
        await message.answer("❌ Please upload only TXT or CSV files!")
        return
        
    if file_size > 10 * 1024 * 1024:  # 10MB limit
        await message.answer("❌ File too large! Maximum size is 10MB.")
        return
    
    try:
        # Download file
        temp_file = f"temp_{user_id}_{file_name}"
        await bot.download(document, destination=temp_file)
        
        # Read emails from file
        emails = []
        with open(temp_file, 'r', encoding='utf-8', errors='ignore') as f:
            if file_name.lower().endswith('.csv'):
                # CSV file - read first column
                reader = csv.reader(f)
                for row in reader:
                    if row and "@" in row[0]:
                        emails.append(row[0].strip())
            else:
                # TXT file - read line by line
                for line in f:
                    if "@" in line:
                        emails.append(line.strip())
        
        # Clean up temp file
        os.remove(temp_file)
        
        if not emails:
            await message.answer("❌ No valid email addresses found in the file!")
            return
        
        # Process emails
        variations = await save_emails(user_id, emails)
        
        if variations:
            response_text = (
                f"✅ <b>File Processing Complete!</b>\n\n"
                f"📁 <b>File:</b> {file_name}\n"
                f"📧 <b>Emails Found:</b> {len(emails)}\n"
                f"🔢 <b>Total Variations:</b> {len(variations)}\n\n"
                f"💡 Use /get to start retrieving variations\n"
                f"📊 Use /summary to check progress\n"
                f"💾 Use /download to get all variations as CSV"
            )
            
            kb = InlineKeyboardBuilder()
            kb.add(InlineKeyboardButton(text="🚀 Get First Variation", callback_data="get_first"))
            kb.add(InlineKeyboardButton(text="📥 Download CSV", callback_data="download_csv"))
            
            await message.answer(response_text, reply_markup=kb.as_markup())
        else:
            await message.answer("❌ Could not generate variations from the file content.")
            
    except Exception as e:
        logger.error(f"Error processing file for user {user_id}: {e}")
        await message.answer("❌ Error processing file. Please try again or contact support.")

# ---------------------------
# COMMAND HANDLERS
# ---------------------------
@dp.message(Command("get"))
async def get_handler(message: types.Message):
    """Handle /get command - get next email variation"""
    user_id = message.from_user.id
    
    if not await check_channel_join(user_id):
        return await message.answer(f"⚠️ Please join {CHANNEL_USERNAME} first!")
    
    user_data = get_user_data(user_id)
    if not user_data or not user_data.get("emails"):
        await message.answer(
            "📧 <b>No email variations found!</b>\n\n"
            "Please send an email address or upload a file first.\n"
            "You can:\n"
            "• Send a single email\n"
            "• Send multiple emails (one per line)\n" 
            "• Upload a TXT/CSV file\n\n"
            "Example: <code>example@gmail.com</code>"
        )
        return
    
    emails = user_data["emails"]
    current_index = user_data["index"]
    total = len(emails)
    
    if current_index >= total:
        await message.answer(
            "🎉 <b>All variations processed!</b>\n\n"
            f"✅ Completed: {total} variations\n"
            f"💾 Use /download to get the complete CSV file\n"
            f"🔄 Use /remove to start over with new emails"
        )
        return
    
    # Get next email
    next_email = emails[current_index]
    
    # Update index
    user_data["index"] = current_index + 1
    save_user_data(user_id, user_data)
    
    # Generate progress
    bar, percent = progress_bar(current_index + 1, total)
    
    response_text = (
        f"📧 <b>Email Variation #{current_index + 1}</b>\n\n"
        f"<code>{next_email}</code>\n\n"
        f"📊 <b>Progress:</b> {current_index + 1}/{total}\n"
        f"{bar} {percent}%\n"
        f"⏳ <b>Remaining:</b> {total - current_index - 1}"
    )
    
    kb = InlineKeyboardBuilder()
    kb.add(InlineKeyboardButton(text="▶️ Next Variation", callback_data="next_email"))
    kb.add(InlineKeyboardButton(text="📊 Summary", callback_data="show_summary"))
    
    await message.answer(response_text, reply_markup=kb.as_markup())

@dp.message(Command("summary"))
async def summary_handler(message: types.Message):
    """Handle /summary command"""
    user_id = message.from_user.id
    user_data = get_user_data(user_id)
    
    if not user_data or not user_data.get("emails"):
        await message.answer(
            "📊 <b>No active session found!</b>\n\n"
            "Send an email or upload a file to get started."
        )
        return
    
    emails = user_data["emails"]
    current_index = user_data["index"]
    total = len(emails)
    bar, percent = progress_bar(current_index, total)
    
    summary_text = (
        "📊 <b>MailTwist Progress Summary</b>\n\n"
        f"🔢 <b>Total Variations:</b> {total}\n"
        f"✅ <b>Processed:</b> {current_index}\n"
        f"⏳ <b>Remaining:</b> {total - current_index}\n"
        f"📈 <b>Progress:</b> {percent}%\n"
        f"{bar}\n\n"
    )
    
    if current_index >= total:
        summary_text += "🎉 <b>All variations completed!</b>"
    elif current_index == 0:
        summary_text += "🚀 <b>Ready to start!</b> Use /get to begin."
    else:
        summary_text += "🔄 <b>Processing in progress...</b>"
    
    kb = InlineKeyboardBuilder()
    if current_index < total:
        kb.add(InlineKeyboardButton(text="▶️ Continue", callback_data="next_email"))
    kb.add(InlineKeyboardButton(text="💾 Download CSV", callback_data="download_csv"))
    
    await message.answer(summary_text, reply_markup=kb.as_markup())

@dp.message(Command("download"))
async def download_handler(message: types.Message):
    """Handle /download command"""
    user_id = message.from_user.id
    csv_path = user_csv_file(user_id)
    
    if not os.path.exists(csv_path):
        await message.answer(
            "❌ <b>No CSV file found!</b>\n\n"
            "Please generate email variations first by:\n"
            "• Sending an email address\n"
            "• Uploading a TXT/CSV file\n"
            "• Using the /get command at least once"
        )
        return
    
    try:
        user_data = get_user_data(user_id)
        total_variations = len(user_data.get("emails", [])) if user_data else 0
        
        await message.answer_document(
            InputFile(csv_path, filename=f"email_variations_{user_id}.csv"),
            caption=f"📁 <b>Email Variations Export</b>\n\n🔢 <b>Total Variations:</b> {total_variations}\n💾 <b>File format:</b> CSV"
        )
    except Exception as e:
        logger.error(f"Error downloading CSV for user {user_id}: {e}")
        await message.answer("❌ Error downloading file. Please try again.")

@dp.message(Command("remove"))
async def remove_handler(message: types.Message):
    """Handle /remove command - delete user data"""
    user_id = message.from_user.id
    
    json_path = user_file(user_id)
    csv_path = user_csv_file(user_id)
    
    files_removed = []
    
    if os.path.exists(json_path):
        os.remove(json_path)
        files_removed.append("JSON data")
    
    if os.path.exists(csv_path):
        os.remove(csv_path)
        files_removed.append("CSV file")
    
    if files_removed:
        removed_text = ", ".join(files_removed)
        await message.answer(
            f"🗑️ <b>Data Cleanup Complete!</b>\n\n"
            f"✅ Removed: {removed_text}\n\n"
            f"🔓 Your storage is now cleared. You can start fresh with new emails!"
        )
    else:
        await message.answer(
            "ℹ️ <b>No data found to remove!</b>\n\n"
            "Your storage is already clean. Send an email to get started!"
        )

# ---------------------------
# CALLBACK HANDLERS
# ---------------------------
@dp.callback_query(F.data == "next_email")
async def next_email_callback(callback: types.CallbackQuery):
    """Handle next email callback"""
    await callback.answer()
    msg = types.Message(
        chat=callback.message.chat,
        from_user=callback.from_user,
        text="/get"
    )
    await get_handler(msg)

@dp.callback_query(F.data == "get_first")
async def get_first_callback(callback: types.CallbackQuery):
    """Handle get first variation callback"""
    await callback.answer()
    msg = types.Message(
        chat=callback.message.chat,
        from_user=callback.from_user, 
        text="/get"
    )
    await get_handler(msg)

@dp.callback_query(F.data == "download_csv")
async def download_csv_callback(callback: types.CallbackQuery):
    """Handle download CSV callback"""
    await callback.answer()
    msg = types.Message(
        chat=callback.message.chat,
        from_user=callback.from_user,
        text="/download"
    )
    await download_handler(msg)

@dp.callback_query(F.data == "show_summary")
async def show_summary_callback(callback: types.CallbackQuery):
    """Handle show summary callback"""
    await callback.answer()
    msg = types.Message(
        chat=callback.message.chat,
        from_user=callback.from_user,
        text="/summary"
    )
    await summary_handler(msg)

# ---------------------------
# ERROR HANDLER
# ---------------------------
@dp.errors()
async def error_handler(update, exception):
    """Global error handler"""
    logger.error(f"Update {update} caused error: {exception}", exc_info=True)
    return True

# ---------------------------
# BOT STARTUP
# ---------------------------
async def main():
    """Main function to start the bot"""
    logger.info("Starting MailTwist Premium Bot...")
    
    # Test bot token
    try:
        bot_info = await bot.get_me()
        logger.info(f"Bot started successfully: @{bot_info.username}")
    except Exception as e:
        logger.error(f"Failed to start bot: {e}")
        return
    
    # Start polling
    await dp.start_polling(bot)

if __name__ == "__main__":
    try:
        # Try to use uvloop for better performance
        import uvloop
        uvloop.install()
        logger.info("Using uvloop for better performance")
    except ImportError:
        logger.info("uvloop not available, using default event loop")
    
    # Start the bot with auto-recovery
    while True:
        try:
            asyncio.run(main())
        except KeyboardInterrupt:
            logger.info("Bot stopped by user")
            break
        except Exception as e:
            logger.error(f"Bot crashed: {e}. Restarting in 5 seconds...")
            asyncio.sleep(5)
