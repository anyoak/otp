import asyncio
import calendar
import random
from datetime import datetime
from telethon import TelegramClient
from telethon.tl.functions.channels import CreateChannelRequest, InviteToChannelRequest, EditAdminRequest
from telethon.tl.types import ChatAdminRights, InputPeerChannel

# ------------------------------
# CONFIG - Replace with your info
# ------------------------------
api_id = 20505183  # Your Account API ID
api_hash = '935939ffdecb9d95d67278af3bdbc971'  # Your Account Hash
phone_number = '+8801714636409'  # Your Phone Number

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

async def add_bot_as_admin(chat_peer):
    """Add @SetBotUsername_bot as admin to the given chat"""
    bot_username = '@SetBotUsername_bot'
    try:
        bot_user = await client.get_entity(bot_username)

        # 1️⃣ Invite the bot
        await client(InviteToChannelRequest(
            channel=chat_peer,
            users=[bot_user]
        ))
        await asyncio.sleep(3)

        # 2️⃣ Give admin rights
        admin_rights = ChatAdminRights(
            invite_users=True,
            change_info=True,
            ban_users=True,
            delete_messages=True,
            pin_messages=True,
            add_admins=False,
            manage_call=True,
            other=True,
            post_messages=True,
            edit_messages=True
        )

        await client(EditAdminRequest(
            channel=chat_peer,
            user_id=bot_user,
            admin_rights=admin_rights,
            rank="Manager"
        ))
        print(f"🤖 Added {bot_username} as admin in group.")
    except Exception as e:
        print(f"⚠️ Error adding bot as admin: {e}")

async def send_random_messages(chat_peer):
    """Send random messages to the group"""
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
        group_name = f"{month_name} {year} #{i+1}"
        try:
            result = await client(CreateChannelRequest(
                title=group_name,
                about='Auto created private group',
                megagroup=True
            ))

            chat = result.chats[0]
            chat_peer = InputPeerChannel(chat.id, chat.access_hash)
            print(f"\n✅ Created group: {group_name} (ID: {chat.id})")

            # Add bot as admin
            await add_bot_as_admin(chat_peer)

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
