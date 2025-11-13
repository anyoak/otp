import os
import json
import csv
import logging
import asyncio
import phonenumbers
import pycountry
import itertools
import gc
import tracemalloc
from phonenumbers import carrier, geocoder, timezone
from aiogram import Bot, Dispatcher, types, BaseMiddleware
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, FSInputFile
from aiogram.filters import Command
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram import F
from aiogram.client.default import DefaultBotProperties

# ---------------------------
# CONFIG
# ---------------------------
BOT_TOKEN = "8472314239:AAHy-ghEb0ZW5rYLlpp24laUkAZO9nwhdGI"
CHANNEL_USERNAME = "@mailtwist"
HELP_CONTACT = "@professor_cry"
DATA_DIR = "user_data"
ADMIN_ID = 6577308099  # Admin user ID for broadcast
os.makedirs(DATA_DIR, exist_ok=True)

# Enhanced logging configuration
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('bot_debug.log', encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Start memory tracking
tracemalloc.start()

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
# MEMORY MANAGEMENT
# ---------------------------
async def periodic_cleanup():
    """Periodic memory cleanup"""
    while True:
        await asyncio.sleep(3600)  # 1 hour
        gc.collect()
        logger.info("Memory cleanup completed")

# ---------------------------
# COUNTRY FLAG FUNCTION
# ---------------------------
def get_country_flag(country_code):
    """Get country flag emoji from country code"""
    try:
        if not country_code:
            return "🏳️"
        
        # Convert country code to flag emoji
        offset = 127397  # Unicode offset for regional indicator symbols
        
        if len(country_code) == 2:
            flag_emoji = ''.join(chr(ord(char) + offset) for char in country_code.upper())
            return flag_emoji
        else:
            return "🏳️"
    except:
        return "🏳️"

def parse_phone_number(phone_str):
    """Parse phone number and detect country info without modifying the number"""
    try:
        # Keep the original number exactly as provided
        original_number = phone_str.strip()
        
        if not original_number:
            return None, None, None, None, None, None
        
        # Try to parse the number as-is
        try:
            parsed = phonenumbers.parse(original_number, None)
            if phonenumbers.is_valid_number(parsed):
                # Get country code
                country_code = phonenumbers.region_code_for_number(parsed)
                country_name = geocoder.description_for_number(parsed, "en")
                carrier_name = carrier.name_for_number(parsed, "en")
                time_zones = timezone.time_zones_for_number(parsed)
                
                # Get country flag
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
# HELPERS - ENHANCED CASE VARIATIONS WITHOUT DOTS
# ---------------------------
def generate_variations(email):
    """Generate email variations with enhanced case patterns only (no dots)"""
    try:
        if "@" not in email:
            return []
            
        local, domain = email.split("@")
        if not local or not domain:
            return []
            
        variations = set()
        
        # Remove any existing dots from local part for processing
        clean_local = local.replace('.', '')
        
        if not clean_local:
            return []
        
        # Enhanced case variation patterns
        case_patterns = set()
        n = len(clean_local)
        
        # Pattern 1: All possible case combinations (2^n)
        for i in range(2 ** n):
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
        
        # Pattern 2: Single uppercase at each position
        for i in range(n):
            if clean_local[i].isalpha():
                variant = list(clean_local.lower())
                variant[i] = clean_local[i].upper()
                case_patterns.add("".join(variant))
        
        # Pattern 3: Every other character uppercase (starting from 0 and 1)
        for start in [0, 1]:
            variant = []
            for i, char in enumerate(clean_local):
                if char.isalpha():
                    if (i + start) % 2 == 0:
                        variant.append(char.upper())
                    else:
                        variant.append(char.lower())
                else:
                    variant.append(char)
            case_patterns.add("".join(variant))
        
        # Pattern 4: First half uppercase, second half lowercase and vice versa
        if n > 1:
            # First half upper
            variant = []
            mid = n // 2
            for i, char in enumerate(clean_local):
                if char.isalpha():
                    if i < mid:
                        variant.append(char.upper())
                    else:
                        variant.append(char.lower())
                else:
                    variant.append(char)
            case_patterns.add("".join(variant))
            
            # Second half upper
            variant = []
            for i, char in enumerate(clean_local):
                if char.isalpha():
                    if i >= mid:
                        variant.append(char.upper())
                    else:
                        variant.append(char.lower())
                else:
                    variant.append(char)
            case_patterns.add("".join(variant))
        
        # Pattern 5: Groups of 2, 3, 4 characters alternating case
        for group_size in [2, 3, 4]:
            if n >= group_size:
                # Upper then lower
                variant = []
                for i, char in enumerate(clean_local):
                    if char.isalpha():
                        if (i // group_size) % 2 == 0:
                            variant.append(char.upper())
                        else:
                            variant.append(char.lower())
                    else:
                        variant.append(char)
                case_patterns.add("".join(variant))
                
                # Lower then upper
                variant = []
                for i, char in enumerate(clean_local):
                    if char.isalpha():
                        if (i // group_size) % 2 == 0:
                            variant.append(char.lower())
                        else:
                            variant.append(char.upper())
                    else:
                        variant.append(char)
                case_patterns.add("".join(variant))
        
        # Pattern 6: Random uppercase patterns (every 1, 2, 3, 4 characters)
        for step in range(1, min(5, n)):
            variant = []
            for i, char in enumerate(clean_local):
                if char.isalpha():
                    if i % step == 0:
                        variant.append(char.upper())
                    else:
                        variant.append(char.lower())
                else:
                    variant.append(char)
            case_patterns.add("".join(variant))
        
        # Pattern 7: CamelCase style
        for word_length in [2, 3, 4]:
            variant = []
            for i, char in enumerate(clean_local):
                if char.isalpha():
                    if i % word_length == 0:
                        variant.append(char.upper())
                    else:
                        variant.append(char.lower())
                else:
                    variant.append(char)
            case_patterns.add("".join(variant))
        
        # Generate variations for each case pattern (NO DOTS)
        for case_variant in case_patterns:
            # Add without dots - this is the only variation now
            variations.add(case_variant + "@" + domain)
        
        # Remove the original email
        original_email = f"{local}@{domain}"
        if original_email in variations:
            variations.remove(original_email)
            
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

def user_numbers_file(user_id):
    """Get user's numbers data file path"""
    return os.path.join(DATA_DIR, f"{user_id}_numbers.json")

def user_numbers_csv_file(user_id):
    """Get user's numbers CSV file path"""
    return os.path.join(DATA_DIR, f"{user_id}_numbers.csv")

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
        valid_emails = []
        
        # Validate emails
        for email in emails:
            email = email.strip()
            if "@" in email and "." in email.split("@")[1]:
                valid_emails.append(email)
        
        if not valid_emails:
            return []
            
        # Generate variations for each valid email
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
        
        json_path = user_file(user_id)
        with open(json_path, "w", encoding='utf-8') as f:
            json.dump(user_data, f, indent=2)
        
        # Save to CSV
        csv_path = user_csv_file(user_id)
        with open(csv_path, "w", newline="", encoding="utf-8") as csvfile:
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
            with open(path, "r", encoding='utf-8') as f:
                return json.load(f)
    except Exception as e:
        logger.error(f"Error reading user data for {user_id}: {e}")
    return None

def get_numbers_data(user_id):
    """Get numbers data safely"""
    try:
        path = user_numbers_file(user_id)
        if os.path.exists(path):
            with open(path, "r", encoding='utf-8') as f:
                return json.load(f)
    except Exception as e:
        logger.error(f"Error reading numbers data for {user_id}: {e}")
    return None

def save_user_data(user_id, data):
    """Save user data safely"""
    try:
        path = user_file(user_id)
        with open(path, "w", encoding='utf-8') as f:
            json.dump(data, f, indent=2)
        return True
    except Exception as e:
        logger.error(f"Error saving user data for {user_id}: {e}")
        return False

def save_numbers_data(user_id, data):
    """Save numbers data safely"""
    try:
        path = user_numbers_file(user_id)
        with open(path, "w", encoding='utf-8') as f:
            json.dump(data, f, indent=2)
        return True
    except Exception as e:
        logger.error(f"Error saving numbers data for {user_id}: {e}")
        return False

async def detect_file_type(user_id, document):
    """Detect if file contains phone numbers or names"""
    try:
        temp_file = os.path.join(DATA_DIR, f"temp_detect_{user_id}_{document.file_name}")
        await bot.download(document, destination=temp_file)
        
        with open(temp_file, 'r', encoding='utf-8', errors='ignore') as f:
            lines = [line.strip() for line in f if line.strip()]
            
        # Clean up
        if os.path.exists(temp_file):
            os.remove(temp_file)
            
        # If most lines don't contain @ but contain text, it's likely names/phones
        email_count = sum(1 for line in lines if "@" in line and "." in line.split("@")[1])
        if email_count < len(lines) * 0.5:  # Less than 50% emails
            return True
            
    except Exception as e:
        logger.error(f"Error detecting file type: {e}")
    
    return False

async def process_numbers_file(user_id, document, message):
    """Process file for phone numbers and names"""
    processing_msg = await message.answer("🔄 <b>Processing file for phone numbers and names...</b>")
    
    try:
        file_name = document.file_name or ""
        temp_file = os.path.join(DATA_DIR, f"temp_{user_id}_{file_name}")
        await bot.download(document, destination=temp_file)
        
        items = []
        valid_phones = 0
        invalid_entries = 0
        
        with open(temp_file, 'r', encoding='utf-8', errors='ignore') as f:
            if file_name.lower().endswith('.csv'):
                reader = csv.reader(f)
                for row in reader:
                    if row:
                        line = row[0].strip()
                        if line:
                            original_number, country_code, country_name, carrier_name, time_zones, flag = parse_phone_number(line)
                            
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
            else:
                # TXT file
                for line in f:
                    line = line.strip()
                    if line:
                        original_number, country_code, country_name, carrier_name, time_zones, flag = parse_phone_number(line)
                        
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
        
        # Clean up temp file
        if os.path.exists(temp_file):
            os.remove(temp_file)
        
        if not items:
            await processing_msg.edit_text("❌ No valid phone numbers or names found in the file!")
            return
        
        # Save numbers data
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
        
        save_numbers_data(user_id, numbers_data)
        
        # Save to CSV
        csv_path = user_numbers_csv_file(user_id)
        with open(csv_path, "w", newline="", encoding="utf-8") as csvfile:
            writer = csv.writer(csvfile)
            writer.writerow(["Type", "Original Number", "Country Code", "Country Name", "Flag", "Carrier", "Timezone"])
            for item in items:
                if item["type"] == "phone":
                    writer.writerow([
                        item["type"], 
                        item["original"], 
                        item.get("country_code", "Unknown"),
                        item.get("country_name", "Unknown"),
                        item.get("flag", "🏳️"),
                        item.get("carrier", "Unknown"),
                        item.get("timezone", "Unknown")
                    ])
                else:
                    writer.writerow([item["type"], item["original"], "N/A", "N/A", "N/A", "N/A", "N/A"])
        
        response_text = (
            f"✅ <b>Numbers Data Processed Successfully!</b>\n\n"
            f"📊 <b>Enhanced Summary:</b>\n"
            f"• 📞 Valid Phone Numbers: {valid_phones}\n"
            f"• 👤 Valid Names: {len(items) - valid_phones}\n"
            f"• 📋 Total Valid Entries: {len(items)}\n"
            f"• ❌ Invalid Entries: {invalid_entries}\n\n"
            f"💡 Use /getnumbers to retrieve entries one by one."
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
        
        # Read emails from file
        emails = []
        with open(temp_file, 'r', encoding='utf-8', errors='ignore') as f:
            if file_name.lower().endswith('.csv'):
                reader = csv.reader(f)
                for row in reader:
                    if row and "@" in row[0]:
                        emails.append(row[0].strip())
            else:
                for line in f:
                    line = line.strip()
                    if "@" in line and "." in line.split("@")[1]:
                        emails.append(line)
        
        # Clean up temp file
        if os.path.exists(temp_file):
            os.remove(temp_file)
        
        if not emails:
            await processing_msg.edit_text("❌ No valid email addresses found in the file!")
            return
        
        # Process emails
        variations = await save_emails(user_id, emails)
        
        if variations:
            response_text = (
                f"✅ <b>File Processing Complete!</b>\n\n"
                f"📁 <b>File:</b> {file_name}\n"
                f"📧 <b>Emails Found:</b> {len(emails)}\n"
                f"🔢 <b>Total Variations:</b> {len(variations)}\n"
                f"💡 <b>Algorithm:</b> Enhanced case patterns\n\n"
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
        "🔹 <b>Enhanced case patterns</b> - Multiple case variation algorithms\n"
        "🔹 <b>Smart phone detection</b> - Auto country & flag detection\n"
        "🔹 <b>Batch processing</b> - Upload TXT/CSV files\n"  
        "🔹 <b>Professional tracking</b> with progress bars\n\n"
        "💡 <b>Quick Commands:</b>\n"
        "• /get - Get next email variation\n"
        "• /summary - View email progress overview\n"
        "• /download - Download email variations as CSV\n"
        "• /number - Process phone numbers & names\n"
        "• /getnumbers - Get next phone/name entry\n"
        "• /summarynumbers - View numbers progress\n"
        "• /downloadnumbers - Download numbers CSV\n"
        "• /remove - Delete your data\n"
        "• /help - Guide & support\n\n"
        f"📬 <b>Support:</b> {HELP_CONTACT}"
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
        "📝 <b>MailTwist Premium 3.0 - Complete Guide</b> 📝\n\n"
        "🔸 <b>Email Features:</b>\n"
        "• Send email or upload file → /get to retrieve variations\n"
        "• Enhanced case patterns\n"
        "• Progress tracking with /summary\n"
        "• Download with /download\n\n"
        "🔸 <b>Number Features:</b>\n"
        "• Use /number to upload phone numbers or names\n"
        "• Auto country detection with flag emojis\n"
        "• Enhanced information: carrier, timezone, country\n"
        "• Use /getnumbers to retrieve entries\n"
        "• Enhanced progress tracking with /summarynumbers\n\n"
        "🛠 <b>Commands:</b>\n"
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
        f"📬 <b>Support Contact:</b> {HELP_CONTACT}"
    )
    await message.answer(help_text)

# ---------------------------
# BROADCAST FEATURE (ADMIN ONLY)
# ---------------------------
@dp.message(Command("broadcast"))
async def broadcast_handler(message: types.Message):
    """Handle broadcast command (admin only)"""
    user_id = message.from_user.id
    
    if user_id != ADMIN_ID:
        await message.answer("❌ This command is for admin only.")
        return
    
    # Extract broadcast message
    broadcast_text = message.text.replace('/broadcast', '').strip()
    if not broadcast_text:
        await message.answer("❌ Please provide a message to broadcast.\nExample: /broadcast Hello everyone!")
        return
    
    # Get all user files
    user_files = [f for f in os.listdir(DATA_DIR) if f.endswith('.json') and not f.endswith('_numbers.json')]
    
    if not user_files:
        await message.answer("❌ No users found in database.")
        return
    
    sent_count = 0
    failed_count = 0
    
    processing_msg = await message.answer(f"📢 Starting broadcast to {len(user_files)} users...")
    
    for user_file in user_files:
        try:
            user_id = int(user_file.replace('.json', ''))
            await bot.send_message(user_id, f"📢 <b>Announcement:</b>\n\n{broadcast_text}")
            sent_count += 1
            
            # Small delay to avoid rate limiting
            await asyncio.sleep(0.1)
            
        except Exception as e:
            logger.warning(f"Failed to send broadcast to {user_file}: {e}")
            failed_count += 1
    
    await processing_msg.edit_text(
        f"✅ <b>Broadcast Completed!</b>\n\n"
        f"📤 Sent: {sent_count} users\n"
        f"❌ Failed: {failed_count} users\n"
        f"📊 Total: {len(user_files)} users"
    )

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
        # Show processing message
        processing_msg = await message.answer("🔄 <b>Generating email variations...</b>")
        
        # Single email
        variations = await save_emails(user_id, [text])
        
        if variations:
            response_text = (
                f"✅ <b>Email Variations Generated!</b>\n\n"
                f"📧 <b>Original Email:</b> <code>{text}</code>\n"
                f"🔢 <b>Total Variations:</b> {len(variations)}\n"
                f"💡 <b>Algorithm:</b> Enhanced case patterns\n\n"
                f"Use the buttons below to manage your variations:"
            )
            
            kb = InlineKeyboardBuilder()
            kb.button(text="🚀 Get First Variation", callback_data="get_first")
            kb.button(text="📥 Download CSV", callback_data="download_csv")
            kb.button(text="📊 View Summary", callback_data="show_summary")
            kb.adjust(1)
            
            await processing_msg.edit_text(response_text, reply_markup=kb.as_markup())
        else:
            await processing_msg.edit_text("❌ Could not generate variations. Please check the email format.")
    
    else:
        # Multiple emails in text (one per line)
        emails = [line.strip() for line in text.split('\n') if line.strip() and "@" in line and "." in line.split("@")[1]]
        
        if emails:
            processing_msg = await message.answer("🔄 <b>Processing multiple emails...</b>")
            variations = await save_emails(user_id, emails)
            
            if variations:
                response_text = (
                    f"✅ <b>Batch Email Processing Complete!</b>\n\n"
                    f"📧 <b>Original Emails:</b> {len(emails)}\n"
                    f"🔢 <b>Total Variations:</b> {len(variations)}\n"
                    f"💡 <b>Algorithm:</b> Enhanced case patterns\n\n"
                    f"Use the buttons below to manage your variations:"
                )
                
                kb = InlineKeyboardBuilder()
                kb.button(text="🚀 Get First Variation", callback_data="get_first")
                kb.button(text="📥 Download CSV", callback_data="download_csv")
                kb.button(text="📊 View Summary", callback_data="show_summary")
                kb.adjust(1)
                
                await processing_msg.edit_text(response_text, reply_markup=kb.as_markup())
            else:
                await processing_msg.edit_text("❌ Could not generate variations from the provided emails.")
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
    """Handle document uploads for both emails and numbers"""
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
        # Check if user recently used /number command by looking at their data
        numbers_data = get_numbers_data(user_id)
        
        # If user has active numbers session or file contains phone numbers/names, process as numbers
        if numbers_data or await detect_file_type(user_id, document):
            await process_numbers_file(user_id, document, message)
        else:
            # Otherwise process as emails
            await process_email_file(user_id, document, message)
            
    except Exception as e:
        logger.error(f"Error processing file for user {user_id}: {e}")
        await message.answer("❌ Error processing file. Please try again or contact support.")

# ---------------------------
# NUMBER COMMAND HANDLERS
# ---------------------------
@dp.message(Command("number"))
async def number_handler(message: types.Message):
    """Handle /number command for phone numbers and names"""
    user_id = message.from_user.id
    
    if not await check_channel_join(user_id):
        return await message.answer(f"⚠️ Please join {CHANNEL_USERNAME} first to use this bot!")
    
    # Check if user sent text or we need to wait for file
    if message.text and message.text.strip() != "/number":
        # User sent text with command
        text = message.text.replace('/number', '').strip()
        await process_numbers_text(user_id, text, message)
    else:
        # User just sent /number, wait for file or text
        await message.answer(
            "📞 <b>Phone Number & Name Processor</b>\n\n"
            "Send me a file (TXT/CSV) or text containing:\n"
            "• Phone numbers (any format)\n"
            "• Names\n"
            "• One entry per line\n\n"
            "I will:\n"
            "• Auto-detect country and show flag\n"
            "• Detect carrier and timezone\n"
            "• Store names as provided\n\n"
            "Then use /getnumbers to retrieve entries one by one."
        )

async def process_numbers_text(user_id, text, message):
    """Process text containing phone numbers and names"""
    processing_msg = await message.answer("🔄 <b>Processing phone numbers and names...</b>")
    
    lines = [line.strip() for line in text.split('\n') if line.strip()]
    items = []
    
    valid_phones = 0
    invalid_entries = 0
    
    for line in lines:
        # Try to parse as phone number first
        original_number, country_code, country_name, carrier_name, time_zones, flag = parse_phone_number(line)
        
        if country_code and country_name:
            phone_info = {
                "type": "phone",
                "original": original_number,
                "country_code": country_code,
                "country_name": country_name,
                "flag": flag
            }
            
            # Add carrier info if available
            if carrier_name:
                phone_info["carrier"] = carrier_name
            
            # Add timezone info if available
            if time_zones:
                phone_info["timezone"] = time_zones[0] if time_zones else "Unknown"
            
            items.append(phone_info)
            valid_phones += 1
        else:
            # Check if it's a valid name (not just numbers, at least 2 chars)
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
    
    # Save numbers data
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
    
    save_numbers_data(user_id, numbers_data)
    
    # Save to CSV
    csv_path = user_numbers_csv_file(user_id)
    with open(csv_path, "w", newline="", encoding="utf-8") as csvfile:
        writer = csv.writer(csvfile)
        writer.writerow(["Type", "Original Number", "Country Code", "Country Name", "Flag", "Carrier", "Timezone"])
        for item in items:
            if item["type"] == "phone":
                writer.writerow([
                    item["type"], 
                    item["original"], 
                    item.get("country_code", "Unknown"),
                    item.get("country_name", "Unknown"),
                    item.get("flag", "🏳️"),
                    item.get("carrier", "Unknown"),
                    item.get("timezone", "Unknown")
                ])
            else:
                writer.writerow([item["type"], item["original"], "N/A", "N/A", "N/A", "N/A", "N/A"])
    
    response_text = (
        f"✅ <b>Numbers Data Processed Successfully!</b>\n\n"
        f"📊 <b>Enhanced Summary:</b>\n"
        f"• 📞 Valid Phone Numbers: {valid_phones}\n"
        f"• 👤 Valid Names: {len(items) - valid_phones}\n"
        f"• 📋 Total Valid Entries: {len(items)}\n"
        f"• ❌ Invalid Entries: {invalid_entries}\n\n"
        f"💡 Country detection with flags completed\n"
        f"🌍 Carrier and timezone info detected\n\n"
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
    
    numbers_data = get_numbers_data(user_id)
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
    """Send next numbers entry"""
    numbers_data = get_numbers_data(user_id)
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
    
    # Get next item
    next_item = items[current_index]
    
    # Update index
    numbers_data["index"] = current_index + 1
    save_numbers_data(user_id, numbers_data)
    
    # Generate progress
    bar, percent = progress_bar(current_index + 1, total)
    
    if next_item["type"] == "phone":
        response_text = (
            f"📞 <b>Phone Number #{current_index + 1}</b>\n\n"
            f"<b>Number:</b> <code>{next_item['original']}</code>\n"
            f"<b>Country:</b> {next_item.get('flag', '🏳️')} {next_item.get('country_name', 'Unknown')}\n"
            f"<b>Country Code:</b> {next_item.get('country_code', 'Unknown')}\n"
            f"<b>Carrier:</b> {next_item.get('carrier', 'Unknown')}\n"
            f"<b>Timezone:</b> {next_item.get('timezone', 'Unknown')}\n\n"
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

@dp.message(Command("summarynumbers"))
async def summarynumbers_handler(message: types.Message):
    """Handle /summarynumbers command"""
    user_id = message.from_user.id
    await send_numbers_summary(user_id, message)

async def send_numbers_summary(user_id, message=None, callback=None):
    """Send numbers summary - ENHANCED VERSION"""
    numbers_data = get_numbers_data(user_id)
    
    if not numbers_data or not numbers_data.get("items"):
        text = "📞 <b>No numbers data found!</b>\n\nUse /number to process phone numbers or names."
        if callback:
            await callback.message.edit_text(text)
        else:
            await message.answer(text)
        return
    
    items = numbers_data["items"]
    current_index = numbers_data["index"]
    total = len(items)
    
    phone_count = numbers_data.get('valid_phones', 0)
    name_count = numbers_data.get('names_count', 0)
    invalid_count = numbers_data.get('invalid_entries', 0)
    
    bar, percent = progress_bar(current_index, total)
    
    # Enhanced summary with more details
    summary_text = (
        "📞 <b>Enhanced Numbers Data Summary</b>\n\n"
        f"📊 <b>Total Entries:</b> {total}\n"
        f"📞 <b>Valid Phone Numbers:</b> {phone_count}\n"
        f"👤 <b>Valid Names:</b> {name_count}\n"
        f"❌ <b>Invalid Entries:</b> {invalid_count}\n"
        f"✅ <b>Processed:</b> {current_index}\n"
        f"⏳ <b>Remaining:</b> {total - current_index}\n"
        f"📈 <b>Progress:</b> {percent}%\n"
        f"{bar}\n\n"
    )
    
    # Add completion status
    if current_index >= total:
        summary_text += "🎉 <b>All entries completed!</b>\n✅ Ready for download"
    elif current_index == 0:
        summary_text += "🚀 <b>Ready to start!</b> Use /getnumbers to begin."
    else:
        remaining_time = "Calculating..."
        if current_index > 0:
            # Estimate remaining time (very rough estimate)
            estimated_seconds = (total - current_index) * 2  # 2 seconds per entry
            if estimated_seconds < 60:
                remaining_time = f"{estimated_seconds} seconds"
            else:
                remaining_time = f"{estimated_seconds // 60} minutes"
        
        summary_text += f"🔄 <b>Processing in progress...</b>\n⏰ <b>Est. time remaining:</b> {remaining_time}"
    
    kb = InlineKeyboardBuilder()
    if current_index < total:
        kb.button(text="▶️ Continue Processing", callback_data="next_number")
    kb.button(text="💾 Download CSV", callback_data="download_numbers_csv")
    if current_index > 0 and current_index < total:
        kb.button(text="🔄 Restart from Beginning", callback_data="restart_numbers")
    kb.adjust(1)
    
    if callback:
        await callback.message.edit_text(summary_text, reply_markup=kb.as_markup())
        await callback.answer()
    else:
        await message.answer(summary_text, reply_markup=kb.as_markup())

@dp.message(Command("downloadnumbers"))
async def downloadnumbers_handler(message: types.Message):
    """Handle /downloadnumbers command"""
    user_id = message.from_user.id
    await send_numbers_csv_file(user_id, message)

async def send_numbers_csv_file(user_id, message=None, callback=None):
    """Send numbers CSV file"""
    try:
        csv_path = user_numbers_csv_file(user_id)
        
        if not os.path.exists(csv_path):
            # Try to generate CSV from JSON data
            numbers_data = get_numbers_data(user_id)
            if numbers_data and numbers_data.get("items"):
                items = numbers_data["items"]
                with open(csv_path, "w", newline="", encoding="utf-8") as csvfile:
                    writer = csv.writer(csvfile)
                    writer.writerow(["Type", "Original Number", "Country Code", "Country Name", "Flag", "Carrier", "Timezone"])
                    for item in items:
                        if item["type"] == "phone":
                            writer.writerow([
                                item["type"], 
                                item["original"], 
                                item.get("country_code", "Unknown"),
                                item.get("country_name", "Unknown"),
                                item.get("flag", "🏳️"),
                                item.get("carrier", "Unknown"),
                                item.get("timezone", "Unknown")
                            ])
                        else:
                            writer.writerow([item["type"], item["original"], "N/A", "N/A", "N/A", "N/A", "N/A"])
            else:
                text = "❌ No numbers data found! Use /number first."
                if callback:
                    await callback.message.edit_text(text)
                else:
                    await message.answer(text)
                return
        
        file_size = os.path.getsize(csv_path)
        if file_size == 0:
            text = "❌ Numbers CSV file is empty. Please process data again with /number."
            if callback:
                await callback.message.edit_text(text)
            else:
                await message.answer(text)
            return
        
        numbers_data = get_numbers_data(user_id)
        total_entries = len(numbers_data.get("items", [])) if numbers_data else 0
        phone_count = numbers_data.get('valid_phones', 0) if numbers_data else 0
        name_count = numbers_data.get('names_count', 0) if numbers_data else 0
        
        file_to_send = FSInputFile(csv_path, filename=f"numbers_data_{user_id}.csv")
        
        caption = (
            f"📁 <b>Numbers Data Export</b>\n\n"
            f"📊 <b>Total Entries:</b> {total_entries}\n"
            f"📞 <b>Phone Numbers:</b> {phone_count}\n"
            f"👤 <b>Names:</b> {name_count}\n"
            f"💾 <b>File format:</b> CSV\n"
            f"👤 <b>User ID:</b> {user_id}\n\n"
            f"📋 <b>Includes:</b> Country, Flag, Carrier, Timezone info"
        )
        
        if callback:
            await callback.message.answer_document(file_to_send, caption=caption)
            await callback.answer("✅ Numbers CSV file downloaded successfully!")
        else:
            await message.answer_document(file_to_send, caption=caption)
            
    except Exception as e:
        logger.error(f"Error downloading numbers CSV for user {user_id}: {e}")
        error_text = "❌ Error downloading numbers file. Please try processing data again with /number."
        if callback:
            await callback.message.edit_text(error_text)
        else:
            await message.answer(error_text)

# ---------------------------
# ENHANCED REMOVE COMMAND WITH OPTIONS
# ---------------------------
@dp.message(Command("remove"))
async def remove_handler(message: types.Message):
    """Handle /remove command - show options for data removal"""
    user_id = message.from_user.id
    
    # Check what data exists
    email_json_exists = os.path.exists(user_file(user_id))
    email_csv_exists = os.path.exists(user_csv_file(user_id))
    numbers_json_exists = os.path.exists(user_numbers_file(user_id))
    numbers_csv_exists = os.path.exists(user_numbers_csv_file(user_id))
    
    # Count existing data types
    existing_types = []
    if email_json_exists or email_csv_exists:
        existing_types.append("email")
    if numbers_json_exists or numbers_csv_exists:
        existing_types.append("numbers")
    
    if not existing_types:
        await message.answer(
            "ℹ️ <b>No data found to remove!</b>\n\n"
            "Your storage is already clean. Send data to get started!"
        )
        return
    
    # Build removal options
    remove_text = "🗑️ <b>Data Removal Options</b>\n\n"
    remove_text += "Choose which data you want to remove:\n\n"
    
    kb = InlineKeyboardBuilder()
    
    if "email" in existing_types:
        remove_text += "• 📧 <b>Email Data</b> - Email variations and CSV files\n"
        kb.button(text="📧 Remove Email Data", callback_data="remove_email")
    
    if "numbers" in existing_types:
        remove_text += "• 📞 <b>Numbers Data</b> - Phone numbers, names and CSV files\n"
        kb.button(text="📞 Remove Numbers Data", callback_data="remove_numbers")
    
    if len(existing_types) > 1:
        remove_text += "• 🗑️ <b>All Data</b> - Remove everything\n"
        kb.button(text="🗑️ Remove All Data", callback_data="remove_all")
    
    kb.button(text="❌ Cancel", callback_data="cancel_remove")
    
    if len(existing_types) == 1:
        kb.adjust(1)
    else:
        kb.adjust(2, 1)
    
    await message.answer(remove_text, reply_markup=kb.as_markup())

async def remove_email_data(user_id, callback=None):
    """Remove only email data"""
    json_path = user_file(user_id)
    csv_path = user_csv_file(user_id)
    
    files_removed = []
    
    if os.path.exists(json_path):
        os.remove(json_path)
        files_removed.append("Email JSON data")
    
    if os.path.exists(csv_path):
        os.remove(csv_path)
        files_removed.append("Email CSV file")
    
    if files_removed:
        removed_text = ", ".join(files_removed)
        response_text = (
            f"🗑️ <b>Email Data Cleanup Complete!</b>\n\n"
            f"✅ Removed: {removed_text}\n\n"
            f"📧 Your email variations have been deleted.\n"
            f"📞 Your numbers data (if any) remains safe."
        )
    else:
        response_text = "❌ No email data found to remove."
    
    if callback:
        await callback.message.edit_text(response_text)
        await callback.answer()
    else:
        return response_text

async def remove_numbers_data(user_id, callback=None):
    """Remove only numbers data"""
    numbers_json_path = user_numbers_file(user_id)
    numbers_csv_path = user_numbers_csv_file(user_id)
    
    files_removed = []
    
    if os.path.exists(numbers_json_path):
        os.remove(numbers_json_path)
        files_removed.append("Numbers JSON data")
    
    if os.path.exists(numbers_csv_path):
        os.remove(numbers_csv_path)
        files_removed.append("Numbers CSV file")
    
    if files_removed:
        removed_text = ", ".join(files_removed)
        response_text = (
            f"🗑️ <b>Numbers Data Cleanup Complete!</b>\n\n"
            f"✅ Removed: {removed_text}\n\n"
            f"📞 Your phone numbers and names have been deleted.\n"
            f"📧 Your email variations (if any) remain safe."
        )
    else:
        response_text = "❌ No numbers data found to remove."
    
    if callback:
        await callback.message.edit_text(response_text)
        await callback.answer()
    else:
        return response_text

async def remove_all_data(user_id, callback=None):
    """Remove all user data"""
    # Remove email data files
    json_path = user_file(user_id)
    csv_path = user_csv_file(user_id)
    
    # Remove numbers data files
    numbers_json_path = user_numbers_file(user_id)
    numbers_csv_path = user_numbers_csv_file(user_id)
    
    files_removed = []
    
    if os.path.exists(json_path):
        os.remove(json_path)
        files_removed.append("Email JSON data")
    
    if os.path.exists(csv_path):
        os.remove(csv_path)
        files_removed.append("Email CSV file")
    
    if os.path.exists(numbers_json_path):
        os.remove(numbers_json_path)
        files_removed.append("Numbers JSON data")
    
    if os.path.exists(numbers_csv_path):
        os.remove(numbers_csv_path)
        files_removed.append("Numbers CSV file")
    
    if files_removed:
        removed_text = ", ".join(files_removed)
        response_text = (
            f"🗑️ <b>Complete Data Cleanup!</b>\n\n"
            f"✅ Removed: {removed_text}\n\n"
            f"🔓 All your data has been cleared. You can start fresh!"
        )
    else:
        response_text = "ℹ️ No data found to remove."
    
    if callback:
        await callback.message.edit_text(response_text)
        await callback.answer()
    else:
        return response_text

# ---------------------------
# REMOVE CALLBACK HANDLERS
# ---------------------------
@dp.callback_query(F.data == "remove_email")
async def remove_email_callback(callback: types.CallbackQuery):
    """Handle remove email data callback"""
    user_id = callback.from_user.id
    await remove_email_data(user_id, callback)

@dp.callback_query(F.data == "remove_numbers")
async def remove_numbers_callback(callback: types.CallbackQuery):
    """Handle remove numbers data callback"""
    user_id = callback.from_user.id
    await remove_numbers_data(user_id, callback)

@dp.callback_query(F.data == "remove_all")
async def remove_all_callback(callback: types.CallbackQuery):
    """Handle remove all data callback"""
    user_id = callback.from_user.id
    await remove_all_data(user_id, callback)

@dp.callback_query(F.data == "cancel_remove")
async def cancel_remove_callback(callback: types.CallbackQuery):
    """Handle cancel removal callback"""
    await callback.message.edit_text(
        "✅ <b>Removal cancelled!</b>\n\n"
        "Your data remains safe and unchanged."
    )
    await callback.answer()

# ---------------------------
# EXISTING EMAIL COMMAND HANDLERS
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
    """Send next email variation (shared function for both messages and callbacks)"""
    user_data = get_user_data(user_id)
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
    kb.button(text="▶️ Next Variation", callback_data="next_email")
    kb.button(text="📊 Summary", callback_data="show_summary")
    kb.button(text="📥 Download CSV", callback_data="download_csv")
    kb.adjust(1)
    
    if callback:
        await callback.message.edit_text(response_text, reply_markup=kb.as_markup())
        await callback.answer()
    else:
        await message.answer(response_text, reply_markup=kb.as_markup())

@dp.message(Command("summary"))
async def summary_handler(message: types.Message):
    """Handle /summary command"""
    user_id = message.from_user.id
    await send_summary(user_id, message)

async def send_summary(user_id, message=None, callback=None):
    """Send summary (shared function for both messages and callbacks)"""
    user_data = get_user_data(user_id)
    
    if not user_data or not user_data.get("emails"):
        text = "📊 <b>No active session found!</b>\n\nSend an email or upload a file to get started."
        if callback:
            await callback.message.edit_text(text)
        else:
            await message.answer(text)
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
        kb.button(text="▶️ Continue", callback_data="next_email")
    kb.button(text="💾 Download CSV", callback_data="download_csv")
    kb.adjust(1)
    
    if callback:
        await callback.message.edit_text(summary_text, reply_markup=kb.as_markup())
        await callback.answer()
    else:
        await message.answer(summary_text, reply_markup=kb.as_markup())

@dp.message(Command("download"))
async def download_handler(message: types.Message):
    """Handle /download command"""
    user_id = message.from_user.id
    await send_csv_file(user_id, message)

async def send_csv_file(user_id, message=None, callback=None):
    """Send CSV file (shared function for both messages and callbacks)"""
    try:
        csv_path = user_csv_file(user_id)
        
        # Check if CSV file exists
        if not os.path.exists(csv_path):
            # Try to generate CSV from JSON data
            user_data = get_user_data(user_id)
            if user_data and user_data.get("emails"):
                # Regenerate CSV file
                emails = user_data["emails"]
                with open(csv_path, "w", newline="", encoding="utf-8") as csvfile:
                    writer = csv.writer(csvfile)
                    writer.writerow(["Email Variations"])
                    for email in emails:
                        writer.writerow([email])
            else:
                text = (
                    "❌ <b>No CSV file found!</b>\n\n"
                    "Please generate email variations first by:\n"
                    "• Sending an email address\n"
                    "• Uploading a TXT/CSV file\n"
                )
                if callback:
                    await callback.message.edit_text(text)
                else:
                    await message.answer(text)
                return
        
        # Verify file size
        file_size = os.path.getsize(csv_path)
        if file_size == 0:
            text = "❌ CSV file is empty. Please generate variations again."
            if callback:
                await callback.message.edit_text(text)
            else:
                await message.answer(text)
            return
        
        user_data = get_user_data(user_id)
        total_variations = len(user_data.get("emails", [])) if user_data else 0
        
        file_to_send = FSInputFile(csv_path, filename=f"email_variations_{user_id}.csv")
        
        caption = (
            f"📁 <b>Email Variations Export</b>\n\n"
            f"🔢 <b>Total Variations:</b> {total_variations}\n"
            f"💾 <b>File format:</b> CSV\n"
            f"👤 <b>User ID:</b> {user_id}"
        )
        
        if callback:
            await callback.message.answer_document(file_to_send, caption=caption)
            await callback.answer("✅ CSV file downloaded successfully!")
        else:
            await message.answer_document(file_to_send, caption=caption)
            
    except Exception as e:
        logger.error(f"Error downloading CSV for user {user_id}: {e}", exc_info=True)
        error_text = "❌ Error downloading file. Please try generating variations again."
        if callback:
            await callback.message.edit_text(error_text)
        else:
            await message.answer(error_text)

# ---------------------------
# CALLBACK HANDLERS - UPDATED WITH NEW COMMANDS
# ---------------------------
@dp.callback_query(F.data == "next_email")
async def next_email_callback(callback: types.CallbackQuery):
    """Handle next email callback"""
    user_id = callback.from_user.id
    await send_next_variation(user_id, callback=callback)

@dp.callback_query(F.data == "get_first")
async def get_first_callback(callback: types.CallbackQuery):
    """Handle get first variation callback"""
    user_id = callback.from_user.id
    await send_next_variation(user_id, callback=callback)

@dp.callback_query(F.data == "download_csv")
async def download_csv_callback(callback: types.CallbackQuery):
    """Handle download CSV callback"""
    user_id = callback.from_user.id
    await send_csv_file(user_id, callback=callback)

@dp.callback_query(F.data == "show_summary")
async def show_summary_callback(callback: types.CallbackQuery):
    """Handle show summary callback"""
    user_id = callback.from_user.id
    await send_summary(user_id, callback=callback)

@dp.callback_query(F.data == "next_number")
async def next_number_callback(callback: types.CallbackQuery):
    """Handle next numbers callback"""
    user_id = callback.from_user.id
    await send_next_number(user_id, callback=callback)

@dp.callback_query(F.data == "get_first_number")
async def get_first_number_callback(callback: types.CallbackQuery):
    """Handle get first numbers callback"""
    user_id = callback.from_user.id
    await send_next_number(user_id, callback=callback)

@dp.callback_query(F.data == "download_numbers_csv")
async def download_numbers_csv_callback(callback: types.CallbackQuery):
    """Handle download numbers CSV callback"""
    user_id = callback.from_user.id
    await send_numbers_csv_file(user_id, callback=callback)

@dp.callback_query(F.data == "show_numbers_summary")
async def show_numbers_summary_callback(callback: types.CallbackQuery):
    """Handle show numbers summary callback"""
    user_id = callback.from_user.id
    await send_numbers_summary(user_id, callback=callback)

@dp.callback_query(F.data == "restart_numbers")
async def restart_numbers_callback(callback: types.CallbackQuery):
    """Handle restart numbers callback"""
    user_id = callback.from_user.id
    numbers_data = get_numbers_data(user_id)
    if numbers_data:
        numbers_data["index"] = 0
        save_numbers_data(user_id, numbers_data)
        await callback.answer("🔄 Restarted from beginning!")
        await send_next_number(user_id, callback=callback)
    else:
        await callback.answer("❌ No numbers data found!")

# ---------------------------
# ERROR HANDLER
# ---------------------------
@dp.errors()
async def error_handler(event, exception):
    """Global error handler"""
    logger.error(f"Update {event} caused error: {exception}", exc_info=True)
    return True

# ---------------------------
# BOT STARTUP WITH AUTO-RECOVERY
# ---------------------------
async def main():
    """Main function to start the bot"""
    logger.info("Starting MailTwist Premium Bot 3.0...")
    
    try:
        # Test bot token
        bot_info = await bot.get_me()
        logger.info(f"Bot started successfully: @{bot_info.username}")
        
        # Start cleanup task
        asyncio.create_task(periodic_cleanup())
        
        # Start polling
        await dp.start_polling(bot)
        
    except Exception as e:
        logger.error(f"Failed to start bot: {e}")
        raise

async def run_bot():
    """Run bot with auto-recovery"""
    restart_attempts = 0
    max_restart_attempts = 10
    
    while restart_attempts < max_restart_attempts:
        try:
            logger.info(f"Starting bot (attempt {restart_attempts + 1})...")
            await main()
            
        except KeyboardInterrupt:
            logger.info("Bot stopped by user")
            break
            
        except Exception as e:
            restart_attempts += 1
            wait_time = min(300, restart_attempts * 30)  # Max 5 minutes
            
            logger.error(f"Bot crashed (attempt {restart_attempts}): {e}")
            logger.info(f"Restarting in {wait_time} seconds...")
            
            await asyncio.sleep(wait_time)
            
    if restart_attempts >= max_restart_attempts:
        logger.error("Max restart attempts reached. Bot stopped permanently.")

if __name__ == "__main__":
    # Use the enhanced runner
    asyncio.run(run_bot())
