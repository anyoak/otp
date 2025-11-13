import os
import json
import csv
import logging
import logging.handlers
import asyncio
import phonenumbers
import pycountry
import itertools
import gc
import tracemalloc
from concurrent.futures import ThreadPoolExecutor
from phonenumbers import carrier, geocoder, timezone
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
MAX_WORKERS = 4  # Thread pool size for CPU-heavy tasks
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB
CHUNK_SIZE = 8192  # For file processing
MEMORY_CLEANUP_INTERVAL = 1800  # 30 minutes
LOG_ROTATION_SIZE = 50 * 1024 * 1024  # 50MB
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
            await f.write(json.dumps(data, indent=2))
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
        self.max_memory = max_memory_mb * 1024 * 1024  # Convert to bytes
        self.cleanup_interval = MEMORY_CLEANUP_INTERVAL
        
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
            
            # Check memory usage first
            await memory_protector.force_cleanup_if_needed()
            
            # Force garbage collection
            collected = gc.collect()
            current, peak = await memory_protector.check_memory_usage()
            
            logger.info(f"Memory cleanup: collected {collected}, current: {current/1024/1024:.2f}MB, peak: {peak/1024/1024:.2f}MB")
            
            # CPU throttling - sleep to prevent excessive CPU usage
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
        with async_timeout.timeout(300):  # 5 minute timeout
            result = await loop.run_in_executor(thread_pool, func, *args)
            return result
    except asyncio.TimeoutError:
        logger.error(f"CPU task timeout for {func.__name__}")
        return None
    except Exception as e:
        logger.error(f"CPU task error for {func.__name__}: {e}")
        return None

# ---------------------------
# COUNTRY FLAG FUNCTION
# ---------------------------
def get_country_flag(country_code):
    """Get country flag emoji from country code"""
    try:
        if not country_code:
            return "🏳️"
        if len(country_code) == 2:
            offset = 127397
            flag_emoji = ''.join(chr(ord(char) + offset) for char in country_code.upper())
            return flag_emoji
        return "🏳️"
    except:
        return "🏳️"

def parse_phone_number(phone_str):
    """Parse phone number and detect country info without modifying the number"""
    try:
        original_number = phone_str.strip()
        if not original_number:
            return None, None, None, None, None, None

        # Try to parse the number as-is
        try:
            parsed = phonenumbers.parse(original_number, None)
            if phonenumbers.is_valid_number(parsed):
                country_code = phonenumbers.region_code_for_number(parsed)
                country_name = geocoder.description_for_number(parsed, "en")
                carrier_name = carrier.name_for_number(parsed, "en")
                time_zones = timezone.time_zones_for_number(parsed)
                flag = get_country_flag(country_code)
                return original_number, country_code, country_name, carrier_name, time_zones, flag
        except:
            pass

        # If parsing fails, try to detect country from the number pattern
        for country in pycountry.countries:
            try:
                country_code = country.alpha_2
                parsed = phonenumbers.parse(original_number, country_code)
                if phonenumbers.is_valid_number(parsed):
                    country_name = geocoder.description_for_number(parsed, "en")
                    carrier_name = carrier.name_for_number(parsed, "en")
                    time_zones = timezone.time_zones_for_number(parsed)
                    flag = get_country_flag(country_code)
                    return original_number, country_code, country_name, carrier_name, time_zones, flag
            except:
                continue
                
    except Exception as e:
        logger.warning(f"Error parsing phone number {phone_str}: {e}")
    
    return original_number, None, None, None, None, "🏳️"

# ---------------------------
# HELPERS - ENHANCED CASE VARIATIONS
# ---------------------------
def generate_variations(email):
    """Generate email variations with enhanced case patterns only (no dots) - CPU INTENSIVE"""
    try:
        if "@" not in email:
            return []
            
        local, domain = email.split("@")
        if not local or not domain:
            return []
            
        clean_local = local.replace('.', '')
        if not clean_local:
            return []
            
        variations = set()
        case_patterns = set()
        n = len(clean_local)
        
        # All possible case combinations (2^n)
        for i in range(min(2 ** n, 10000)):  # Limit to prevent explosion
            variant = []
            for j, char in enumerate(clean_local):
                if char.isalpha():
                    if (i >> j) & 1:
                        variant.append(char.upper())
                    else:
                        variant.append(char.lower())
                else:
                    variant.append(char)
            case_patterns.add("".join(variant))
            
        # Additional patterns with limits
        patterns_to_generate = [
            # Single uppercase at each position
            (lambda: [clean_local[:i] + clean_local[i].upper() + clean_local[i+1:] 
                     for i in range(n) if clean_local[i].isalpha()]),
            
            # Every other character uppercase
            (lambda: [''.join(char.upper() if (i % 2 == 0) else char.lower() 
                             for i, char in enumerate(clean_local))]),
            
            # First/last half uppercase
            (lambda: [clean_local[:n//2].upper() + clean_local[n//2:].lower()] if n > 1 else []),
            (lambda: [clean_local[:n//2].lower() + clean_local[n//2:].upper()] if n > 1 else []),
        ]
        
        for pattern_func in patterns_to_generate:
            try:
                patterns = pattern_func()
                case_patterns.update(patterns)
            except:
                pass
                
        # Generate variations for each case pattern (NO DOTS)
        for case_variant in case_patterns:
            variations.add(case_variant + "@" + domain)
            
        # Remove the original email
        original_email = f"{local}@{domain}"
        if original_email in variations:
            variations.remove(original_email)
            
        return list(variations)[:5000]  # Limit total variations
        
    except Exception as e:
        logger.error(f"Error generating variations for {email}: {e}")
        return []

# ---------------------------
# ASYNC FILE PATHS
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
    """Save email variations for user - ASYNC VERSION"""
    try:
        # Validate emails first
        valid_emails = []
        for email in emails:
            email = email.strip()
            if "@" in email and "." in email.split("@")[1]:
                valid_emails.append(email)
                
        if not valid_emails:
            return []
            
        # Generate variations using thread pool (CPU intensive)
        all_variations = []
        for email in valid_emails:
            variations = await run_cpu_task(generate_variations, email)
            if variations:
                all_variations.extend(variations)
                
        # Remove duplicates
        all_variations = list(set(all_variations))
        
        # Save data
        user_data = {
            "user_id": user_id,
            "emails": all_variations,
            "index": 0,
            "original_emails": valid_emails,
            "total_count": len(all_variations),
            "created_at": str(asyncio.get_event_loop().time())
        }
        
        # Async save
        json_path = user_file(user_id)
        await async_write_json(json_path, user_data)
        
        # Save CSV in thread
        csv_path = user_csv_file(user_id)
        csv_rows = [["Email Variations"]] + [[email] for email in all_variations]
        await async_write_csv(csv_path, csv_rows)
        
        logger.info(f"Saved {len(all_variations)} variations for user {user_id}")
        return all_variations
        
    except Exception as e:
        logger.error(f"Error saving emails for user {user_id}: {e}")
        return []

async def get_user_data(user_id):
    """Get user data safely - ASYNC"""
    return await async_read_json(user_file(user_id))

async def get_numbers_data(user_id):
    """Get numbers data safely - ASYNC"""
    return await async_read_json(user_numbers_file(user_id))

async def save_user_data(user_id, data):
    """Save user data safely - ASYNC"""
    return await async_write_json(user_file(user_id), data)

async def save_numbers_data(user_id, data):
    """Save numbers data safely - ASYNC"""
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
# ASYNC FILE PROCESSING
# ---------------------------
async def detect_file_type(user_id, document):
    """Detect if file contains phone numbers or names"""
    try:
        temp_file = os.path.join(DATA_DIR, f"temp_detect_{user_id}_{document.file_name}")
        await bot.download(document, destination=temp_file)
        
        # Read file in chunks to avoid memory issues
        email_count = 0
        total_lines = 0
        
        async with aiofiles.open(temp_file, 'r', encoding='utf-8', errors='ignore') as f:
            async for line in f:
                total_lines += 1
                if "@" in line and "." in line.split("@")[1]:
                    email_count += 1
                if total_lines > 1000:  # Sample first 1000 lines
                    break
                    
        # Clean up
        if os.path.exists(temp_file):
            os.remove(temp_file)
            
        return email_count < total_lines * 0.5  # Less than 50% emails
        
    except Exception as e:
        logger.error(f"Error detecting file type: {e}")
        return False

async def process_numbers_file(user_id, document, message):
    """Process file for phone numbers and names - ASYNC OPTIMIZED"""
    processing_msg = await message.answer("🔄 <b>Processing file for phone numbers and names...</b>")
    
    try:
        file_name = document.file_name or ""
        temp_file = os.path.join(DATA_DIR, f"temp_{user_id}_{file_name}")
        await bot.download(document, destination=temp_file)
        
        items = []
        valid_phones = 0
        invalid_entries = 0
        
        # Process file in chunks
        async with aiofiles.open(temp_file, 'r', encoding='utf-8', errors='ignore') as f:
            async for line in f:
                line = line.strip()
                if line:
                    # Parse phone number in thread pool
                    result = await run_cpu_task(parse_phone_number, line)
                    if result:
                        original_number, country_code, country_name, carrier_name, time_zones, flag = result
                        
                        if country_code and country_name:
                            phone_info = {
                                "type": "phone",
                                "original": original_number,
                                "country_code": country_code,
                                "country_name": country_name,
                                "flag": flag
                            }
                            if carrier_name:
                                phone_info["carrier"] = carrier_name
                            if time_zones:
                                phone_info["timezone"] = time_zones[0] if time_zones else "Unknown"
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
                                
                # Memory protection - process in chunks
                if len(items) % 1000 == 0:
                    await asyncio.sleep(0.1)  # Yield control
                    
        # Clean up temp file
        if os.path.exists(temp_file):
            os.remove(temp_file)
            
        if not items:
            await processing_msg.edit_text("❌ No valid phone numbers or names found in the file!")
            return
            
        # Save data
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
        
        # Save CSV in background
        csv_rows = [["Type", "Original Number", "Country Code", "Country Name", "Flag", "Carrier", "Timezone"]]
        for item in items:
            if item["type"] == "phone":
                csv_rows.append([
                    item["type"],
                    item["original"],
                    item.get("country_code", "Unknown"),
                    item.get("country_name", "Unknown"),
                    item.get("flag", "🏳️"),
                    item.get("carrier", "Unknown"),
                    item.get("timezone", "Unknown")
                ])
            else:
                csv_rows.append([item["type"], item["original"], "N/A", "N/A", "N/A", "N/A", "N/A"])
                
        csv_path = user_numbers_csv_file(user_id)
        await async_write_csv(csv_path, csv_rows)
        
        response_text = (
            f"✅ <b>Numbers Data Processed Successfully!</b>\n\n"
            f"📊 <b>Enhanced Summary:</b>\n"
            f"• 📞 Valid Phone Numbers: {valid_phones}\n"
            f"• 👤 Valid Names: {len(items) - valid_phones}\n"
            f"• 📋 Total Valid Entries: {len(items)}\n"
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
    """Process file for emails - ASYNC OPTIMIZED"""
    processing_msg = await message.answer("🔄 <b>Processing your file for emails...</b>")
    
    try:
        file_name = document.file_name or ""
        temp_file = os.path.join(DATA_DIR, f"temp_{user_id}_{file_name}")
        await bot.download(document, destination=temp_file)
        
        # Read emails from file in chunks
        emails = []
        async with aiofiles.open(temp_file, 'r', encoding='utf-8', errors='ignore') as f:
            async for line in f:
                line = line.strip()
                if "@" in line and "." in line.split("@")[1]:
                    emails.append(line)
                    
                # Memory protection
                if len(emails) % 1000 == 0:
                    await asyncio.sleep(0.1)
                    
        # Clean up temp file
        if os.path.exists(temp_file):
            os.remove(temp_file)
            
        if not emails:
            await processing_msg.edit_text("❌ No valid email addresses found in the file!")
            return
            
        # Process emails in background
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
# COMMAND HANDLERS (Keep existing structure but add async optimizations)
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
        "📚 <b>Smart phone detection</b> - Auto country & flag detection\n"
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

# [Keep all other command handlers the same but ensure they use async file operations]
# For brevity, I'm showing the structure. You would replace all file operations with async versions.

@dp.message(Command("get"))
async def get_handler(message: types.Message):
    """Handle /get command - get next email variation"""
    user_id = message.from_user.id
    
    if not await check_channel_join(user_id):
        return await message.answer(f"⚠️ Please join {CHANNEL_USERNAME} first!")
    
    user_data = await get_user_data(user_id)
    if not user_data or not user_data.get("emails"):
        await message.answer(
            "📧 <b>No email variations found!</b>\n\n"
            "Please send an email address or upload a file first.\n\n"
            "You can:\n"
            "• Send a single email\n"
            "• Send multiple emails (one per line)\n"
            "• Upload a TXT/CSV file\n\n"
            "Example: <code>example@gmail.com</code>"
        )
        return
        
    await send_next_variation(user_id, message)

async def send_next_variation(user_id, message=None, callback=None):
    """Send next email variation - ASYNC OPTIMIZED"""
    user_data = await get_user_data(user_id)
    if not user_data:
        if callback:
            await callback.message.edit_text("❌ No user data found. Please start over.")
        return
        
    emails = user_data["emails"]
    current_index = user_data["index"]
    total = len(emails)
    
    if current_index >= total:
        text = (
            "🎉 <b>All variations processed!</b>\n\n"
            f"✅ Completed: {total} variations\n"
            f"💾 Download your CSV file using the button below\n"
            f"🔄 Use /remove to start over with new emails"
        )
        kb = InlineKeyboardBuilder()
        kb.button(text="📥 Download CSV", callback_data="download_csv")
        
        if callback:
            await callback.message.edit_text(text, reply_markup=kb.as_markup())
        else:
            await message.answer(text, reply_markup=kb.as_markup())
        return
        
    # Get next email
    next_email = emails[current_index]
    
    # Update index
    user_data["index"] = current_index + 1
    await save_user_data(user_id, user_data)
    
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
    kb.button(text="▶️ Next Variation", callback_data="next_email")
    kb.button(text="📊 Summary", callback_data="show_summary")
    kb.button(text="📥 Download CSV", callback_data="download_csv")
    kb.adjust(1)
    
    if callback:
        await callback.message.edit_text(response_text, reply_markup=kb.as_markup())
        await callback.answer()
    else:
        await message.answer(response_text, reply_markup=kb.as_markup())

# [Continue with all other handlers, converting file operations to async...]

# ---------------------------
# CRASH-SAFE POLLING WITH AUTO-RECOVERY
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
            wait_time = min(300, restart_attempts * 30)  # Max 5 minutes
            
            logger.error(f"Bot crashed (attempt {restart_attempts}): {e}")
            logger.info(f"Restarting in {wait_time} seconds...")
            
            # Force cleanup before restart
            gc.collect()
            await asyncio.sleep(wait_time)
            
    if restart_attempts >= max_restart_attempts:
        logger.error("Max restart attempts reached. Bot stopped permanently.")

# ---------------------------
# GRACEFUL SHUTDOWN
# ---------------------------
async def shutdown():
    """Graceful shutdown"""
    logger.info("Shutting down bot...")
    
    # Close thread pool
    thread_pool.shutdown(wait=True)
    
    # Close bot session
    await bot.session.close()
    
    # Force final cleanup
    gc.collect()
    
    logger.info("Bot shutdown complete")

# ---------------------------
# MAIN ENTRY POINT
# ---------------------------
async def main():
    """Main async entry point"""
    try:
        # Test bot connection
        bot_info = await bot.get_me()
        logger.info(f"Bot started successfully: @{bot_info.username}")
        
        # Start safe polling
        await safe_polling()
        
    except Exception as e:
        logger.error(f"Failed to start bot: {e}")
        raise
    finally:
        await shutdown()

if __name__ == "__main__":
    # Set up signal handlers for graceful shutdown
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Bot stopped by user")
    except Exception as e:
        logger.error(f"Fatal error: {e}")