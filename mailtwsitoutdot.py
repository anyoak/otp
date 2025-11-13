import os
import json
import csv
import logging
import logging.handlers
import asyncio
import gc
import tracemalloc
from concurrent.futures import ThreadPoolExecutor
from aiogram import Bot, Dispatcher, types, BaseMiddleware
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, FSInputFile
from aiogram.filters import Command
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram import F
from aiogram.client.default import DefaultBotProperties
import aiofiles
import async_timeout

# ---------------------------
# CONFIG
# ---------------------------
BOT_TOKEN = "8472314239:AAEuxP4QTgl-gCg4SUl13htj8V7ZE3LB8nc"
CHANNEL_USERNAME = "@mailtwist"
HELP_CONTACT = "@professor_cry"
DATA_DIR = "user_data"
ADMIN_ID = 6577308099

# Enhanced configuration
MAX_WORKERS = 4
MAX_FILE_SIZE = 10 * 1024 * 1024
MEMORY_CLEANUP_INTERVAL = 1800
LOG_ROTATION_SIZE = 50 * 1024 * 1024
LOG_BACKUP_COUNT = 3

os.makedirs(DATA_DIR, exist_ok=True)

# Enhanced logging with rotation
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.handlers.RotatingFileHandler(
            'bot_debug.log', 
            encoding='utf-8',
            maxBytes=LOG_ROTATION_SIZE,
            backupCount=LOG_BACKUP_COUNT
        ),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Start memory tracking
tracemalloc.start()

# Initialize bot with HTML parse mode
bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode='HTML'))
dp = Dispatcher()

# Thread pool for CPU-intensive tasks
thread_pool = ThreadPoolExecutor(max_workers=MAX_WORKERS)

# ---------------------------
# ASYNC FILE OPERATIONS
# ---------------------------
async def async_write_json(filepath, data):
    """Async JSON file write"""
    try:
        async with aiofiles.open(filepath, 'w', encoding='utf-8') as f:
            await f.write(json.dumps(data, indent=2, ensure_ascii=False))
        return True
    except Exception as e:
        logger.error(f"Async JSON write error for {filepath}: {e}")
        return False

async def async_read_json(filepath):
    """Async JSON file read"""
    try:
        if not os.path.exists(filepath):
            return None
        async with aiofiles.open(filepath, 'r', encoding='utf-8') as f:
            content = await f.read()
            return json.loads(content)
    except Exception as e:
        logger.error(f"Async JSON read error for {filepath}: {e}")
        return None

async def async_write_csv(filepath, rows):
    """Async CSV file write"""
    try:
        async with aiofiles.open(filepath, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            for row in rows:
                await f.write(','.join(f'"{cell}"' for cell in row) + '\n')
        return True
    except Exception as e:
        logger.error(f"Async CSV write error for {filepath}: {e}")
        return False

# ---------------------------
# AUTO-RECOVERY MIDDLEWARE
# ---------------------------
class ErrorHandlerMiddleware(BaseMiddleware):
    async def __call__(self, handler, event, data):
        try:
            return await handler(event, data)
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.error(f"Error in handler: {e}", exc_info=True)
            try:
                if hasattr(event, 'message') and event.message:
                    await event.message.answer("⚠️ Something went wrong. Please try again or contact support.")
            except:
                pass
            return True

dp.update.outer_middleware(ErrorHandlerMiddleware())

# ---------------------------
# MEMORY & PERFORMANCE MANAGEMENT
# ---------------------------
class MemoryProtection:
    def __init__(self, max_memory_mb=512):
        self.max_memory = max_memory_mb * 1024 * 1024
        
    async def check_memory_usage(self):
        """Check current memory usage"""
        current, peak = tracemalloc.get_traced_memory()
        return current, peak
        
    async def force_cleanup_if_needed(self):
        """Force cleanup if memory usage is high"""
        current, peak = await self.check_memory_usage()
        if current > self.max_memory:
            logger.warning(f"High memory usage detected: {current/1024/1024:.2f}MB, forcing cleanup")
            gc.collect()
            return True
        return False

memory_protector = MemoryProtection()

async def periodic_cleanup():
    """Periodic memory cleanup with CPU throttling"""
    while True:
        try:
            await asyncio.sleep(MEMORY_CLEANUP_INTERVAL)
            await memory_protector.force_cleanup_if_needed()
            collected = gc.collect()
            current, peak = await memory_protector.check_memory_usage()
            logger.info(f"Memory cleanup: collected {collected}, current: {current/1024/1024:.2f}MB")
            await asyncio.sleep(1)
        except Exception as e:
            logger.error(f"Error in periodic cleanup: {e}")

# ---------------------------
# ASYNC TASK EXECUTOR
# ---------------------------
async def run_cpu_task(func, *args):
    """Run CPU-intensive tasks in thread pool"""
    try:
        loop = asyncio.get_event_loop()
        with async_timeout.timeout(300):
            result = await loop.run_in_executor(thread_pool, func, *args)
            return result
    except asyncio.TimeoutError:
        logger.error(f"CPU task timeout for {func.__name__}")
        return None
    except Exception as e:
        logger.error(f"CPU task error for {func.__name__}: {e}")
        return None

# ---------------------------
# SIMPLE PHONE NUMBER FORMATTING (NO COUNTRY DETECTION)
# ---------------------------
def format_phone_number(phone_str):
    """Simply add + to phone number and clean it"""
    try:
        original_number = phone_str.strip()
        if not original_number:
            return None
            
        # Remove any existing + and spaces
        clean_number = original_number.replace('+', '').replace(' ', '').replace('-', '').replace('(', '').replace(')', '')
        
        # Check if it's a valid phone number (at least 5 digits)
        if clean_number.isdigit() and len(clean_number) >= 5:
            return "+" + clean_number
        else:
            return None
            
    except Exception as e:
        logger.warning(f"Error formatting phone number {phone_str}: {e}")
        return None

# ---------------------------
# EMAIL VARIATION GENERATOR - FIXED VERSION
# ---------------------------
def generate_variations(email):
    """Generate email variations with enhanced case patterns only (no dots)"""
    try:
        if "@" not in email:
            return []
            
        local, domain = email.split("@")
        if not local or not domain:
            return []
            
        # Remove dots from local part for processing
        clean_local = local.replace('.', '')
        if not clean_local:
            return []
            
        variations = set()
        
        # Always include the original email without dots as base variation
        base_variation = clean_local + "@" + domain
        variations.add(base_variation)
        
        n = len(clean_local)
        if n == 0:
            return list(variations)
        
        # Generate basic case variations (most useful patterns)
        patterns_to_generate = []
        
        # 1. All lowercase and uppercase
        patterns_to_generate.append(clean_local.lower())
        patterns_to_generate.append(clean_local.upper())
        
        # 2. First letter uppercase, rest lowercase
        if n > 0:
            patterns_to_generate.append(clean_local[0].upper() + clean_local[1:].lower())
        
        # 3. CamelCase style for longer strings
        if n > 2:
            patterns_to_generate.append(clean_local[:2].upper() + clean_local[2:].lower())
        
        # 4. Every other character uppercase
        variant1 = []
        variant2 = []
        for i, char in enumerate(clean_local):
            if char.isalpha():
                if i % 2 == 0:
                    variant1.append(char.upper())
                    variant2.append(char.lower())
                else:
                    variant1.append(char.lower())
                    variant2.append(char.upper())
            else:
                variant1.append(char)
                variant2.append(char)
        patterns_to_generate.append("".join(variant1))
        patterns_to_generate.append("".join(variant2))
        
        # 5. Last letter uppercase
        if n > 0:
            patterns_to_generate.append(clean_local[:-1].lower() + clean_local[-1].upper())
        
        # Remove duplicates and empty patterns
        unique_patterns = set(p for p in patterns_to_generate if p and len(p) == n)
        
        # Generate variations
        for pattern in unique_patterns:
            variations.add(pattern + "@" + domain)
        
        # Remove the original email WITH dots if it exists
        original_email = f"{local}@{domain}"
        if original_email in variations:
            variations.remove(original_email)
            
        return list(variations)
        
    except Exception as e:
        logger.error(f"Error generating variations for {email}: {e}")
        # Return at least the base variation without dots
        try:
            local, domain = email.split("@")
            clean_local = local.replace('.', '')
            if clean_local and domain:
                return [clean_local + "@" + domain]
        except:
            pass
        return []

# ---------------------------
# FILE PATHS
# ---------------------------
def user_file(user_id):
    return os.path.join(DATA_DIR, f"{user_id}.json")

def user_csv_file(user_id):
    return os.path.join(DATA_DIR, f"{user_id}_variations.csv")

def user_numbers_file(user_id):
    return os.path.join(DATA_DIR, f"{user_id}_numbers.json")

def user_numbers_csv_file(user_id):
    return os.path.join(DATA_DIR, f"{user_id}_numbers.csv")

# ---------------------------
# ASYNC HELPER FUNCTIONS
# ---------------------------
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
        # Enhanced email validation
        valid_emails = []
        for email in emails:
            email = email.strip().lower()
            if "@" in email:
                local, domain = email.split("@")
                if (local and domain and "." in domain and 
                    len(domain.split(".")[-1]) >= 2 and len(local) >= 1):
                    valid_emails.append(email)
                
        if not valid_emails:
            logger.warning(f"No valid emails found for user {user_id}")
            return []
            
        # Generate variations using thread pool
        all_variations = []
        for email in valid_emails:
            variations = await run_cpu_task(generate_variations, email)
            if variations:
                all_variations.extend(variations)
                logger.info(f"Generated {len(variations)} variations for {email}")
            else:
                logger.warning(f"No variations generated for {email}")
                
        # Remove duplicates
        all_variations = list(set(all_variations))
        
        if not all_variations:
            logger.warning(f"Failed to generate any variations for user {user_id}")
            return []
        
        # Save data
        user_data = {
            "user_id": user_id,
            "emails": all_variations,
            "index": 0,
            "original_emails": valid_emails,
            "total_count": len(all_variations),
            "created_at": str(asyncio.get_event_loop().time())
        }
        
        json_path = user_file(user_id)
        await async_write_json(json_path, user_data)
        
        csv_path = user_csv_file(user_id)
        csv_rows = [["Email Variations"]] + [[email] for email in all_variations]
        await async_write_csv(csv_path, csv_rows)
        
        logger.info(f"Saved {len(all_variations)} variations for user {user_id}")
        return all_variations
        
    except Exception as e:
        logger.error(f"Error saving emails for user {user_id}: {e}")
        return []

async def get_user_data(user_id):
    return await async_read_json(user_file(user_id))

async def get_numbers_data(user_id):
    return await async_read_json(user_numbers_file(user_id))

async def save_user_data(user_id, data):
    return await async_write_json(user_file(user_id), data)

async def save_numbers_data(user_id, data):
    return await async_write_json(user_numbers_file(user_id), data)

def progress_bar(index, total):
    """Generate progress bar"""
    if total == 0:
        return "░░░░░░░░░░", 0
    percent = min(100, int((index / total) * 100))
    blocks = int((percent / 10))
    bar = "█" * blocks + "░" * (10 - blocks)
    return bar, percent

# ---------------------------
# FILE PROCESSING
# ---------------------------
async def detect_file_type(user_id, document):
    """Detect if file contains phone numbers or names"""
    try:
        temp_file = os.path.join(DATA_DIR, f"temp_detect_{user_id}_{document.file_name}")
        await bot.download(document, destination=temp_file)
        
        email_count = 0
        total_lines = 0
        
        async with aiofiles.open(temp_file, 'r', encoding='utf-8', errors='ignore') as f:
            async for line in f:
                total_lines += 1
                if "@" in line and "." in line.split("@")[1]:
                    email_count += 1
                if total_lines > 1000:
                    break
                    
        if os.path.exists(temp_file):
            os.remove(temp_file)
            
        return email_count < total_lines * 0.5
        
    except Exception as e:
        logger.error(f"Error detecting file type: {e}")
        return False

async def process_numbers_file(user_id, document, message):
    """Process file for phone numbers - SIMPLIFIED VERSION"""
    processing_msg = await message.answer("🔄 <b>Processing file for phone numbers...</b>")
    
    try:
        file_name = document.file_name or ""
        temp_file = os.path.join(DATA_DIR, f"temp_{user_id}_{file_name}")
        await bot.download(document, destination=temp_file)
        
        items = []
        valid_phones = 0
        invalid_entries = 0
        
        async with aiofiles.open(temp_file, 'r', encoding='utf-8', errors='ignore') as f:
            async for line in f:
                line = line.strip()
                if line:
                    # Simple phone number formatting - just add +
                    formatted_number = await run_cpu_task(format_phone_number, line)
                    
                    if formatted_number:
                        phone_info = {
                            "type": "phone",
                            "original": line,
                            "formatted": formatted_number
                        }
                        items.append(phone_info)
                        valid_phones += 1
                    else:
                        # Check if it's a valid name
                        if len(line) >= 2 and not line.replace(' ', '').isdigit():
                            items.append({
                                "type": "name",
                                "value": line,
                                "original": line
                            })
                        else:
                            invalid_entries += 1
                                
                if len(items) % 1000 == 0:
                    await asyncio.sleep(0.1)
                    
        if os.path.exists(temp_file):
            os.remove(temp_file)
            
        if not items:
            await processing_msg.edit_text("❌ No valid phone numbers or names found in the file!")
            return
            
        numbers_data = {
            "user_id": user_id,
            "items": items,
            "index": 0,
            "total_count": len(items),
            "valid_phones": valid_phones,
            "names_count": len(items) - valid_phones,
            "invalid_entries": invalid_entries,
            "created_at": str(asyncio.get_event_loop().time())
        }
        
        await save_numbers_data(user_id, numbers_data)
        
        # Save to CSV
        csv_path = user_numbers_csv_file(user_id)
        csv_rows = [["Type", "Original", "Formatted"]]
        for item in items:
            if item["type"] == "phone":
                csv_rows.append([item["type"], item["original"], item["formatted"]])
            else:
                csv_rows.append([item["type"], item["original"], "N/A"])
                
        await async_write_csv(csv_path, csv_rows)
        
        response_text = (
            f"✅ <b>Phone Numbers Processed Successfully!</b>\n\n"
            f"📊 <b>Summary:</b>\n"
            f"• 📞 Valid Phone Numbers: {valid_phones}\n"
            f"• 👤 Valid Names: {len(items) - valid_phones}\n"
            f"• 📋 Total Entries: {len(items)}\n"
            f"• ❌ Invalid Entries: {invalid_entries}\n\n"
            f"🔧 Use /getnumbers to retrieve entries one by one."
        )
        
        kb = InlineKeyboardBuilder()
        kb.button(text="🚀 Get First Entry", callback_data="get_first_number")
        kb.button(text="📥 Download Numbers CSV", callback_data="download_numbers_csv")
        kb.button(text="📊 Numbers Summary", callback_data="show_numbers_summary")
        kb.adjust(1)
        
        await processing_msg.edit_text(response_text, reply_markup=kb.as_markup())
        
    except Exception as e:
        logger.error(f"Error processing numbers file for user {user_id}: {e}")
        await processing_msg.edit_text("❌ Error processing file for numbers. Please try again.")

async def process_email_file(user_id, document, message):
    """Process file for emails"""
    processing_msg = await message.answer("🔄 <b>Processing your file for emails...</b>")
    
    try:
        file_name = document.file_name or ""
        temp_file = os.path.join(DATA_DIR, f"temp_{user_id}_{file_name}")
        await bot.download(document, destination=temp_file)
        
        emails = []
        async with aiofiles.open(temp_file, 'r', encoding='utf-8', errors='ignore') as f:
            async for line in f:
                line = line.strip()
                if "@" in line and "." in line.split("@")[1]:
                    emails.append(line)
                    
                if len(emails) % 1000 == 0:
                    await asyncio.sleep(0.1)
                    
        if os.path.exists(temp_file):
            os.remove(temp_file)
            
        if not emails:
            await processing_msg.edit_text("❌ No valid email addresses found in the file!")
            return
            
        variations = await save_emails(user_id, emails)
        
        if variations:
            response_text = (
                f"✅ <b>File Processing Complete!</b>\n\n"
                f"📁 <b>File:</b> {file_name}\n"
                f"📧 <b>Emails Found:</b> {len(emails)}\n"
                f"🔄 <b>Total Variations:</b> {len(variations)}\n"
                f"🔧 <b>Algorithm:</b> Enhanced case patterns\n\n"
                f"Use the buttons below to manage your variations:"
            )
            
            kb = InlineKeyboardBuilder()
            kb.button(text="🚀 Get First Variation", callback_data="get_first")
            kb.button(text="📥 Download CSV", callback_data="download_csv")
            kb.button(text="📊 View Summary", callback_data="show_summary")
            kb.adjust(1)
            
            await processing_msg.edit_text(response_text, reply_markup=kb.as_markup())
        else:
            await processing_msg.edit_text("❌ Could not generate variations from the file content.")
            
    except Exception as e:
        logger.error(f"Error processing email file for user {user_id}: {e}")
        await message.answer("❌ Error processing file. Please try again or contact support.")

# ---------------------------
# COMMAND HANDLERS
# ---------------------------
@dp.message(Command("start"))
async def start_handler(message: types.Message):
    """Handle /start command"""
    user_id = message.from_user.id
    
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
        "✨ <b>Welcome to MailTwist Premium 3.0</b> ✨\n\n"
        "🚀 <b>Enhanced Email Variation Generator</b>\n\n"
        "📚 <b>Enhanced case patterns</b> - Multiple case variation algorithms\n"
        "📚 <b>Simple phone formatting</b> - Just add + to numbers\n"
        "📚 <b>Batch processing</b> - Upload TXT/CSV files\n"
        "📚 <b>Professional tracking</b> with progress bars\n\n"
        "🔧 <b>Quick Commands:</b>\n"
        "• /get - Get next email variation\n"
        "• /summary - View email progress overview\n"
        "• /download - Download email variations as CSV\n"
        "• /number - Process phone numbers & names\n"
        "• /getnumbers - Get next phone/name entry\n"
        "• /summarynumbers - View numbers progress\n"
        "• /downloadnumbers - Download numbers CSV\n"
        "• /remove - Delete your data\n"
        "• /help - Guide & support\n\n"
        f"📞 <b>Support:</b> {HELP_CONTACT}"
    )
    await message.answer(welcome_text)

@dp.callback_query(F.data == "check_join")
async def check_join_callback(callback: types.CallbackQuery):
    """Handle join check callback"""
    user_id = callback.from_user.id
    if await check_channel_join(user_id):
        await callback.message.edit_text(
            "✅ <b>Access Granted!</b>\n\n"
            "You've successfully joined the channel. Now you can use all MailTwist Premium features!\n\n"
            "Send me an email address or upload a file to get started."
        )
        await callback.answer()
    else:
        await callback.answer("❌ Please join the channel first! Click the 'Join Channel' button.", show_alert=True)

@dp.message(Command("help"))
async def help_handler(message: types.Message):
    """Handle /help command"""
    help_text = (
        "📖 <b>MailTwist Premium 3.0 - Complete Guide</b> 📖\n\n"
        "📚 <b>Email Features:</b>\n"
        "• Send email or upload file → /get to retrieve variations\n"
        "• Enhanced case patterns\n"
        "• Progress tracking with /summary\n"
        "• Download with /download\n\n"
        "📚 <b>Number Features:</b>\n"
        "• Use /number to upload phone numbers or names\n"
        "• Simple + formatting for numbers\n"
        "• Use /getnumbers to retrieve entries\n"
        "• Progress tracking with /summarynumbers\n\n"
        "⚙️ <b>Commands:</b>\n"
        "/start - Start the bot\n"
        "/get - Get next email variation\n"
        "/summary - View email progress\n"
        "/download - Download email CSV\n"
        "/number - Process phone numbers & names\n"
        "/getnumbers - Get next phone/name entry\n"
        "/summarynumbers - View numbers progress\n"
        "/downloadnumbers - Download numbers CSV\n"
        "/remove - Delete your data\n"
        "/help - This guide\n\n"
        f"📞 <b>Support Contact:</b> {HELP_CONTACT}"
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

    if "@" in text and "." in text.split("@")[1]:
        processing_msg = await message.answer("🔄 <b>Generating email variations...</b>")
        variations = await save_emails(user_id, [text])
        
        if variations:
            response_text = (
                f"✅ <b>Email Variations Generated!</b>\n\n"
                f"📧 <b>Original Email:</b> <code>{text}</code>\n"
                f"🔄 <b>Total Variations:</b> {len(variations)}\n"
                f"🔧 <b>Algorithm:</b> Enhanced case patterns\n\n"
                f"Use the buttons below to manage your variations:"
            )
            kb = InlineKeyboardBuilder()
            kb.button(text="🚀 Get First Variation", callback_data="get_first")
            kb.button(text="📥 Download CSV", callback_data="download_csv")
            kb.button(text="📊 View Summary", callback_data="show_summary")
            kb.adjust(1)
            await processing_msg.edit_text(response_text, reply_markup=kb.as_markup())
        else:
            await processing_msg.edit_text(
                f"❌ <b>Could not generate variations for:</b> <code>{text}</code>\n\n"
                f"<b>Try a valid email like:</b>\n"
                f"<code>example@gmail.com</code>"
            )
    else:
        emails = [line.strip() for line in text.split('\n') if line.strip() and "@" in line and "." in line.split("@")[1]]
        if emails:
            processing_msg = await message.answer("🔄 <b>Processing multiple emails...</b>")
            variations = await save_emails(user_id, emails)
            if variations:
                response_text = (
                    f"✅ <b>Batch Email Processing Complete!</b>\n\n"
                    f"📧 <b>Original Emails:</b> {len(emails)}\n"
                    f"🔄 <b>Total Variations:</b> {len(variations)}\n"
                    f"🔧 <b>Algorithm:</b> Enhanced case patterns\n\n"
                    f"Use the buttons below to manage your variations:"
                )
                kb = InlineKeyboardBuilder()
                kb.button(text="🚀 Get First Variation", callback_data="get_first")
                kb.button(text="📥 Download CSV", callback_data="download_csv")
                kb.button(text="📊 View Summary", callback_data="show_summary")
                kb.adjust(1)
                await processing_msg.edit_text(response_text, reply_markup=kb.as_markup())
            else:
                await processing_msg.edit_text(
                    "❌ <b>Could not generate variations from the provided emails.</b>\n\n"
                    "Please check that all emails have valid format."
                )
        else:
            await message.answer(
                "📧 <b>Please send a valid email address or upload a file</b>\n\n"
                "You can:\n"
                "• Send a single email address\n"
                "• Send multiple emails (one per line)\n"
                "• Upload a TXT/CSV file with emails\n\n"
                "<b>Valid examples:</b>\n"
                "<code>example@gmail.com</code>\n"
                "<code>john.doe@yahoo.com</code>"
            )

@dp.message(F.document)
async def document_handler(message: types.Message):
    """Handle document uploads for both emails and numbers"""
    user_id = message.from_user.id
    if not await check_channel_join(user_id):
        return await message.answer(f"⚠️ Please join {CHANNEL_USERNAME} first to use this bot!")

    document = message.document
    file_name = document.file_name or ""
    file_size = document.file_size or 0

    if not file_name.lower().endswith(('.txt', '.csv')):
        await message.answer("❌ Please upload only TXT or CSV files!")
        return

    if file_size > MAX_FILE_SIZE:
        await message.answer("❌ File too large! Maximum size is 10MB.")
        return

    try:
        numbers_data = await get_numbers_data(user_id)
        if numbers_data or await detect_file_type(user_id, document):
            await process_numbers_file(user_id, document, message)
        else:
            await process_email_file(user_id, document, message)
    except Exception as e:
        logger.error(f"Error processing file for user {user_id}: {e}")
        await message.answer("❌ Error processing file. Please try again or contact support.")

# ---------------------------
# SIMPLE NUMBER COMMAND HANDLERS (NO COUNTRY DETECTION)
# ---------------------------
@dp.message(Command("number"))
async def number_handler(message: types.Message):
    """Handle /number command for phone numbers and names"""
    user_id = message.from_user.id
    if not await check_channel_join(user_id):
        return await message.answer(f"⚠️ Please join {CHANNEL_USERNAME} first to use this bot!")

    if message.text and message.text.strip() != "/number":
        text = message.text.replace('/number', '').strip()
        await process_numbers_text(user_id, text, message)
    else:
        await message.answer(
            "📞 <b>Phone Number & Name Processor</b>\n\n"
            "Send me a file (TXT/CSV) or text containing:\n"
            "• Phone numbers (any format)\n"
            "• Names\n"
            "• One entry per line\n\n"
            "I will:\n"
            "• Add + to phone numbers\n"
            "• Store names as provided\n\n"
            "Then use /getnumbers to retrieve entries one by one."
        )

async def process_numbers_text(user_id, text, message):
    """Process text containing phone numbers and names - SIMPLIFIED"""
    processing_msg = await message.answer("🔄 <b>Processing phone numbers and names...</b>")
    lines = [line.strip() for line in text.split('\n') if line.strip()]
    items = []
    valid_phones = 0
    invalid_entries = 0

    for line in lines:
        # Simple phone number formatting - just add +
        formatted_number = await run_cpu_task(format_phone_number, line)
        
        if formatted_number:
            phone_info = {
                "type": "phone",
                "original": line,
                "formatted": formatted_number
            }
            items.append(phone_info)
            valid_phones += 1
        else:
            # Check if it's a valid name
            if len(line) >= 2 and not line.replace(' ', '').isdigit():
                items.append({
                    "type": "name",
                    "value": line,
                    "original": line
                })
            else:
                invalid_entries += 1

    if not items:
        await processing_msg.edit_text("❌ No valid phone numbers or names found in the text!")
        return

    numbers_data = {
        "user_id": user_id,
        "items": items,
        "index": 0,
        "total_count": len(items),
        "valid_phones": valid_phones,
        "names_count": len(items) - valid_phones,
        "invalid_entries": invalid_entries,
        "created_at": str(asyncio.get_event_loop().time())
    }

    await save_numbers_data(user_id, numbers_data)

    # Save to CSV
    csv_path = user_numbers_csv_file(user_id)
    csv_rows = [["Type", "Original", "Formatted"]]
    for item in items:
        if item["type"] == "phone":
            csv_rows.append([item["type"], item["original"], item["formatted"]])
        else:
            csv_rows.append([item["type"], item["original"], "N/A"])

    await async_write_csv(csv_path, csv_rows)

    response_text = (
        f"✅ <b>Numbers Data Processed Successfully!</b>\n\n"
        f"📊 <b>Summary:</b>\n"
        f"• 📞 Valid Phone Numbers: {valid_phones}\n"
        f"• 👤 Valid Names: {len(items) - valid_phones}\n"
        f"• 📋 Total Valid Entries: {len(items)}\n"
        f"• ❌ Invalid Entries: {invalid_entries}\n\n"
        f"Use /getnumbers to retrieve entries one by one."
    )

    kb = InlineKeyboardBuilder()
    kb.button(text="🚀 Get First Entry", callback_data="get_first_number")
    kb.button(text="📥 Download Numbers CSV", callback_data="download_numbers_csv")
    kb.button(text="📊 Numbers Summary", callback_data="show_numbers_summary")
    kb.adjust(1)

    await processing_msg.edit_text(response_text, reply_markup=kb.as_markup())

@dp.message(Command("getnumbers"))
async def getnumbers_handler(message: types.Message):
    """Handle /getnumbers command"""
    user_id = message.from_user.id
    if not await check_channel_join(user_id):
        return await message.answer(f"⚠️ Please join {CHANNEL_USERNAME} first!")

    numbers_data = await get_numbers_data(user_id)
    if not numbers_data or not numbers_data.get("items"):
        await message.answer(
            "📞 <b>No numbers data found!</b>\n\n"
            "Please use /number first to upload phone numbers or names.\n\n"
            "You can:\n"
            "• Send /number followed by text with phone numbers/names\n"
            "• Upload a TXT/CSV file after using /number command\n"
        )
        return

    await send_next_number(user_id, message)

async def send_next_number(user_id, message=None, callback=None):
    """Send next numbers entry - SIMPLIFIED"""
    numbers_data = await get_numbers_data(user_id)
    if not numbers_data:
        if callback:
            await callback.message.edit_text("❌ No numbers data found. Please use /number first.")
        return

    items = numbers_data["items"]
    current_index = numbers_data["index"]
    total = len(items)

    if current_index >= total:
        text = (
            "🎉 <b>All entries processed!</b>\n\n"
            f"✅ Completed: {total} entries\n"
            f"📞 Phones: {numbers_data.get('valid_phones', 0)}\n"
            f"👤 Names: {numbers_data.get('names_count', 0)}\n"
            f"💾 Download your CSV file using the button below\n"
            f"🔄 Use /number to process new data"
        )
        kb = InlineKeyboardBuilder()
        kb.button(text="📥 Download Numbers CSV", callback_data="download_numbers_csv")
        if callback:
            await callback.message.edit_text(text, reply_markup=kb.as_markup())
        else:
            await message.answer(text, reply_markup=kb.as_markup())
        return

    next_item = items[current_index]
    numbers_data["index"] = current_index + 1
    await save_numbers_data(user_id, numbers_data)

    bar, percent = progress_bar(current_index + 1, total)

    if next_item["type"] == "phone":
        response_text = (
            f"📞 <b>Phone Number #{current_index + 1}</b>\n\n"
            f"<b>Original:</b> <code>{next_item['original']}</code>\n"
            f"<b>Formatted:</b> <code>{next_item['formatted']}</code>\n\n"
            f"📊 <b>Progress:</b> {current_index + 1}/{total}\n"
            f"{bar} {percent}%\n"
            f"⏳ <b>Remaining:</b> {total - current_index - 1}"
        )
    else:
        response_text = (
            f"👤 <b>Name #{current_index + 1}</b>\n\n"
            f"<code>{next_item['value']}</code>\n\n"
            f"📊 <b>Progress:</b> {current_index + 1}/{total}\n"
            f"{bar} {percent}%\n"
            f"⏳ <b>Remaining:</b> {total - current_index - 1}"
        )

    kb = InlineKeyboardBuilder()
    kb.button(text="▶️ Next Entry", callback_data="next_number")
    kb.button(text="📊 Numbers Summary", callback_data="show_numbers_summary")
    kb.button(text="📥 Download CSV", callback_data="download_numbers_csv")
    kb.adjust(1)

    if callback:
        await callback.message.edit_text(response_text, reply_markup=kb.as_markup())
        await callback.answer()
    else:
        await message.answer(response_text, reply_markup=kb.as_markup())

# [Keep the rest of the handlers the same - summarynumbers, downloadnumbers, etc.]
# They will work with the simplified data structure

# Continue with the rest of the handlers (summary, download, remove, callbacks)...
# They remain the same as in the previous version

# ---------------------------
# BOT STARTUP
# ---------------------------
async def safe_polling():
    """Safe polling with auto-recovery"""
    restart_attempts = 0
    max_restart_attempts = 10
    
    while restart_attempts < max_restart_attempts:
        try:
            logger.info(f"Starting bot polling (attempt {restart_attempts + 1})...")
            
            # Start cleanup task
            cleanup_task = asyncio.create_task(periodic_cleanup())
            
            # Start polling
            await dp.start_polling(bot)
            
            # If we get here, polling stopped gracefully
            cleanup_task.cancel()
            break
            
        except KeyboardInterrupt:
            logger.info("Bot stopped by user")
            break
        except Exception as e:
            restart_attempts += 1
            wait_time = min(300, restart_attempts * 30)
            
            logger.error(f"Bot crashed (attempt {restart_attempts}): {e}")
            logger.info(f"Restarting in {wait_time} seconds...")
            
            # Force cleanup before restart
            gc.collect()
            await asyncio.sleep(wait_time)
            
    if restart_attempts >= max_restart_attempts:
        logger.error("Max restart attempts reached. Bot stopped permanently.")

async def shutdown():
    """Graceful shutdown"""
    logger.info("Shutting down bot...")
    thread_pool.shutdown(wait=True)
    await bot.session.close()
    gc.collect()
    logger.info("Bot shutdown complete")

async def main():
    """Main async entry point"""
    try:
        bot_info = await bot.get_me()
        logger.info(f"Bot started successfully: @{bot_info.username}")
        await safe_polling()
    except Exception as e:
        logger.error(f"Failed to start bot: {e}")
        raise
    finally:
        await shutdown()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Bot stopped by user")
    except Exception as e:
        logger.error(f"Fatal error: {e}")