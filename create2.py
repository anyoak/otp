import asyncio
import calendar
import random
from datetime import datetime
from telethon import TelegramClient
from telethon.tl.functions.channels import CreateChannelRequest
from telethon.tl.types import InputPeerChannel

# ------------------------------
# CONFIG - Replace with your info
# ------------------------------
api_id = 20505183  # Your Account API I'D
api_hash = '935939ffdecb9d95d67278af3bdbc971' # Your Account Hash I'D
phone_number = '+8801714636409'  			# Your Acc Phone Number

# Number of groups to create
number_of_groups = 50

# Message sending settings
messages_per_group = 10
interval_between_messages = 2  # seconds
interval_between_groups = 10   # seconds

# ------------------------------
# MESSAGE LIST (20 random messages)
# ------------------------------
messages = [
    "Welcome to the new group! 🎉",
    "Let's make this month productive 💪",
    "Stay active and positive, team!",
    "Good vibes only 🌈",
    "Share your ideas freely 💭",
    "Together we grow stronger 🌱",
    "Never stop learning 📚",
    "Make today count 🔥",
    "Focus on progress, not perfection 🚀",
    "Keep moving forward ➡️",
    "Respect and teamwork matter most 🤝",
    "Every small step counts 💡",
    "Let's hit our goals this week 🏆",
    "Don't give up, your time is coming ⏰",
    "Motivation is the key to success 🔑",
    "Consistency beats talent 🧠",
    "Stay humble, work hard 💼",
    "Celebrate every win 🎯",
    "Together, everything is possible 🌍",
    "New beginnings start here 💫"
]

# ------------------------------

client = TelegramClient('session_name', api_id, api_hash)

async def send_random_messages(chat_peer):
    """Send 10 random messages to the given chat"""
    for _ in range(messages_per_group):
        msg = random.choice(messages)
        try:
            await client.send_message(chat_peer, msg)
            print(f"Sent message: {msg}")
        except Exception as e:
            print(f"Error sending message: {e}")
        await asyncio.sleep(interval_between_messages)

async def main():
    await client.start(phone=phone_number)

    now = datetime.now()
    month_name = calendar.month_name[now.month]
    year = now.year

    for i in range(number_of_groups):
        # Group name format: "October 2025 #1"
        group_name = f"{month_name} {year} #{i+1}"
        try:
            # Create private megagroup
            result = await client(CreateChannelRequest(
                title=group_name,
                about='Auto created private group',
                megagroup=True
            ))

            chat = result.chats[0]
            chat_peer = InputPeerChannel(chat.id, chat.access_hash)
            print(f"\n✅ Created private group: {group_name} (ID: {chat.id})")

            # Send 10 random messages
            await send_random_messages(chat_peer)

            await asyncio.sleep(interval_between_groups)

        except Exception as e:
            print(f"❌ Error creating group {group_name}: {e}")
            await asyncio.sleep(interval_between_groups)

    print("\n🎯 Finished creating all groups and sending messages!")
    await client.disconnect()

if __name__ == '__main__':
    asyncio.run(main())
