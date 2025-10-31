import os
import json
import csv
import logging
import asyncio
import phonenumbers
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
BOT_TOKEN = "8472314239:AAEuxP4QTgl-gCg4SUl13htj8V7ZE3LB8nc"
CHANNEL_USERNAME = "@mailtwist"
HELP_CONTACT = "@professor_cry"
DATA_DIR = "user_data"
ADMIN_ID = 6577308099  # Admin user ID for broadcast
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
# HELPERS - ENHANCED VARIATION GENERATION
# ---------------------------
def generate_variations(email):
    """Generate email variations with enhanced algorithm for more variations"""
    try:
        if "@" not in email:
            return []
            
        local, domain = email.split("@")
        if not local or not domain:
            return []
            
        variations = set()
        
        # Enhanced variation generation with multiple strategies
        strategies = [
            # Strategy 1: Case variations (increased limit)
            lambda loc: [loc],  # Original
            
            # Strategy 2: Character substitutions
            lambda loc: [loc.replace('a', '4').replace('e', '3').replace('i', '1').replace('o', '0')],
            lambda loc: [loc.replace('s', '5').replace('t', '7')],
            
            # Strategy 3: Add numbers
            lambda loc: [f"{loc}{i}" for i in range(10)],
            lambda loc: [f"{loc}{i:02d}" for i in range(10, 100)],
            
            # Strategy 4: Add common suffixes
            lambda loc: [f"{loc}1", f"{loc}2", f"{loc}123", f"{loc}2024", f"{loc}2025"],
            
            # Strategy 5: Insert dots and underscores
            lambda loc: [f"{loc[:i]}.{loc[i:]}" for i in range(1, min(len(loc), 5))],
            lambda loc: [f"{loc[:i]}_{loc[i:]}" for i in range(1, min(len(loc), 5))],
        ]
        
        # Apply all strategies
        for strategy in strategies:
            try:
                new_variants = strategy(local)
                for variant in new_variants:
                    if len(variant) <= 64:  # Email length limit
                        variation = f"{variant}@{domain}"
                        variations.add(variation.lower())
            except Exception as e:
                logger.warning(f"Strategy failed: {e}")
                continue
        
        # Case variations with increased limit
        local_lower = local.lower()
        max_case_variations = min(2 ** len(local_lower), 1024)  # Increased to 1024
        
        for i in range(min(max_case_variations, 1024)):
            chars = []
            for j, c in enumerate(local_lower):
                if (i >> j) & 1 and c.isalpha():
                    chars.append(c.upper())
                else:
                    chars.append(c)
            variation = "".join(chars) + "@" + domain
            variations.add(variation)
        
        # Remove the original email if it was added by strategies
        original_email = f"{local}@{domain}"
        if original_email in variations:
            variations.remove(original_email)
            
        return list(variations)[:2048]  # Maximum 2048 variations per email
        
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

def parse_phone_number(phone_str):
    """Parse phone number and return formatted number with country info"""
    try:
        # Clean the phone number
        phone_str = ''.join(filter(str.isdigit, phone_str))
        
        if not phone_str:
            return None, None
            
        # Try to parse with international format
        if not phone_str.startswith('+'):
            # Try different country codes
            for country_code in ['1', '44', '91', '86', '81', '49', '33', '7', '61']:
                try:
                    parsed = phonenumbers.parse(f"+{country_code}{phone_str}", None)
                    if phonenumbers.is_valid_number(parsed):
                        formatted = phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.E164)
                        country = geocoder.description_for_number(parsed, "en")
                        carrier_name = carrier.name_for_number(parsed, "en")
                        time_zones = timezone.time_zones_for_number(parsed)
                        return formatted, country, carrier_name, time_zones
                except:
                    continue
            
            # If no country code works, try without
            try:
                parsed = phonenumbers.parse(phone_str, None)
                if phonenumbers.is_valid_number(parsed):
                    formatted = phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.E164)
                    country = geocoder.description_for_number(parsed, "en")
                    carrier_name = carrier.name_for_number(parsed, "en")
                    time_zones = timezone.time_zones_for_number(parsed)
                    return formatted, country, carrier_name, time_zones
            except:
                pass
        else:
            # Already has country code
            parsed = phonenumbers.parse(phone_str, None)
            if phonenumbers.is_valid_number(parsed):
                formatted = phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.E164)
                country = geocoder.description_for_number(parsed, "en")
                carrier_name = carrier.name_for_number(parsed, "en")
                time_zones = timezone.time_zones_for_number(parsed)
                return formatted, country, carrier_name, time_zones
                
    except Exception as e:
        logger.warning(f"Error parsing phone number {phone_str}: {e}")
    
    return None, None, None, None

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
        "🚀 <b>Advanced Email Variation Generator</b>\n\n"
        "🔹 <b>Enhanced email variations</b> with multiple strategies\n"
        "🔹 <b>Batch processing</b> - Upload TXT/CSV files\n"  
        "🔹 <b>Phone number & name processing</b> with /number\n"
        "🔹 <b>Professional tracking</b> with progress bars\n"
        "🔹 <b>Secure & Private</b> - Your data stays with you\n\n"
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
        "• Enhanced variation generation with multiple strategies\n"
        "• Progress tracking with /summary\n"
        "• Download with /download\n\n"
        "🔸 <b>Number Features:</b>\n"
        "• Use /number to upload phone numbers or names\n"
        "• Phone numbers auto-formatted with country detection\n"
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
        "/remove - Delete all your data\n"
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
        processing_msg = await message.answer("🔄 <b>Generating enhanced email variations...</b>")
        
        # Single email
        variations = await save_emails(user_id, [text])
        
        if variations:
            response_text = (
                f"✅ <b>Enhanced Email Variations Generated!</b>\n\n"
                f"📧 <b>Original Email:</b> <code>{text}</code>\n"
                f"🔢 <b>Total Variations:</b> {len(variations)}\n"
                f"💡 <b>Algorithm:</b> Multiple strategies applied\n\n"
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
            processing_msg = await message.answer("🔄 <b>Processing multiple emails with enhanced algorithm...</b>")
            variations = await save_emails(user_id, emails)
            
            if variations:
                response_text = (
                    f"✅ <b>Batch Email Processing Complete!</b>\n\n"
                    f"📧 <b>Original Emails:</b> {len(emails)}\n"
                    f"🔢 <b>Total Variations:</b> {len(variations)}\n"
                    f"💡 <b>Algorithm:</b> Enhanced variation generation\n\n"
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
        # Show processing message
        processing_msg = await message.answer("🔄 <b>Processing your file...</b>")
        
        # Download file
        temp_file = os.path.join(DATA_DIR, f"temp_{user_id}_{file_name}")
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
                f"💡 <b>Algorithm:</b> Enhanced variation generation\n\n"
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
        logger.error(f"Error processing file for user {user_id}: {e}")
        await message.answer("❌ Error processing file. Please try again or contact support.")

# ---------------------------
# NUMBER COMMAND HANDLERS (UPDATED FROM OTHERS)
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
            "• Auto-format phone numbers with + country code\n"
            "• Detect country, carrier, and timezone\n"
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
        formatted_phone, country, carrier_name, time_zones = parse_phone_number(line)
        
        if formatted_phone and country:
            phone_info = {
                "type": "phone",
                "original": line,
                "value": formatted_phone,
                "country": country
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
        writer.writerow(["Type", "Original", "Formatted Value", "Country", "Carrier", "Timezone"])
        for item in items:
            if item["type"] == "phone":
                writer.writerow([
                    item["type"], 
                    item["original"], 
                    item["value"], 
                    item.get("country", "Unknown"),
                    item.get("carrier", "Unknown"),
                    item.get("timezone", "Unknown")
                ])
            else:
                writer.writerow([item["type"], item["original"], item["value"], "N/A", "N/A", "N/A"])
    
    response_text = (
        f"✅ <b>Numbers Data Processed Successfully!</b>\n\n"
        f"📊 <b>Enhanced Summary:</b>\n"
        f"• 📞 Valid Phone Numbers: {valid_phones}\n"
        f"• 👤 Valid Names: {len(items) - valid_phones}\n"
        f"• 📋 Total Valid Entries: {len(items)}\n"
        f"• ❌ Invalid Entries: {invalid_entries}\n\n"
        f"💡 Phone numbers have been formatted with + country code\n"
        f"🌍 Country, carrier, and timezone info detected\n\n"
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
            f"<b>Original:</b> <code>{next_item['original']}</code>\n"
            f"<b>Formatted:</b> <code>{next_item['value']}</code>\n"
            f"<b>Country:</b> {next_item.get('country', 'Unknown')}\n"
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
                    writer.writerow(["Type", "Original", "Formatted Value", "Country", "Carrier", "Timezone"])
                    for item in items:
                        if item["type"] == "phone":
                            writer.writerow([
                                item["type"], 
                                item["original"], 
                                item["value"], 
                                item.get("country", "Unknown"),
                                item.get("carrier", "Unknown"),
                                item.get("timezone", "Unknown")
                            ])
                        else:
                            writer.writerow([item["type"], item["original"], item["value"], "N/A", "N/A", "N/A"])
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
            f"📋 <b>Includes:</b> Country, Carrier, Timezone info"
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

@dp.message(Command("remove"))
async def remove_handler(message: types.Message):
    """Handle /remove command - delete all user data"""
    user_id = message.from_user.id
    
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
        await message.answer(
            f"🗑️ <b>Complete Data Cleanup!</b>\n\n"
            f"✅ Removed: {removed_text}\n\n"
            f"🔓 All your data has been cleared. You can start fresh!"
        )
    else:
        await message.answer(
            "ℹ️ <b>No data found to remove!</b>\n\n"
            "Your storage is already clean. Send data to get started!"
        )

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
# BOT STARTUP
# ---------------------------
async def main():
    """Main function to start the bot"""
    logger.info("Starting MailTwist Premium Bot 3.0...")
    
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