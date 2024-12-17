import os
import uuid
from pyrogram import Client, filters
from pyrogram.types import Message
from pymongo import MongoClient
from pyrogram.errors import FloodWait
import time

# Bot and MongoDB Configuration
API_ID = "YOUR_API_ID"  # Replace with your API ID
API_HASH = "YOUR_API_HASH"  # Replace with your API Hash
BOT_TOKEN = "YOUR_BOT_TOKEN"  # Replace with your Bot Token
CHANNEL_ID = -1001234567890  # Replace with your Telegram Channel ID (negative for private channels)
WELCOME_CHANNEL_ID = "@YourWelcomeChannel"  # Replace with your Telegram Channel for user verification
MONGO_URI = "YOUR_MONGODB_URI"  # Replace with your MongoDB URI

# Admin List (replace with actual Admin IDs)
ADMIN_IDS = [123456789, 987654321]  # Replace with the Telegram User IDs of your admins

# MongoDB Configuration
mongo_client = MongoClient(MONGO_URI)
db = mongo_client['telegram_bot']
files_collection = db['files']
users_collection = db['users']

# Initialize the Bot
app = Client("file_store_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# Function to save file metadata in MongoDB
def save_file_metadata(file_id, file_type, channel_message_id):
    unique_id = str(uuid.uuid4())[:8]  # Short UUID for unique link
    files_collection.insert_one({
        "unique_id": unique_id,
        "file_id": file_id,
        "file_type": file_type,
        "channel_message_id": channel_message_id
    })
    return unique_id

# Function to fetch file metadata from MongoDB
def get_file_metadata(unique_id):
    result = files_collection.find_one({"unique_id": unique_id})
    return result

# Function to check if a user has joined the required channel
async def check_user_subscription(user_id):
    try:
        member = await app.get_chat_member(WELCOME_CHANNEL_ID, user_id)
        return member.status in ["member", "administrator", "creator"]
    except:
        return False

# Start Command: Bot will welcome the user and check channel membership
@app.on_message(filters.command("start"))
async def start(_, message: Message):
    user_id = message.from_user.id

    # Check if the user has joined the required channel
    if not await check_user_subscription(user_id):
        await message.reply("❌ You must join the required channel to use this bot.\nPlease join and try again.")
        return

    # Add user to the MongoDB collection (if not already)
    if not users_collection.find_one({"user_id": user_id}):
        users_collection.insert_one({"user_id": user_id})

    await message.reply("👋 Welcome! Send me any post or document, and I'll store it securely and give you a special link to access it.")

# Only Admins can send Broadcast Messages
@app.on_message(filters.command("broadcast") & filters.user(ADMIN_IDS))  # Only admins can broadcast
async def broadcast(_, message: Message):
    # Check if the user is an admin
    if message.from_user.id not in ADMIN_IDS:
        await message.reply("❌ You don't have the required admin privileges to broadcast messages.")
        return

    broadcast_message = " ".join(message.command[1:])
    for user in users_collection.find():
        try:
            await app.send_message(user["user_id"], broadcast_message)
        except Exception as e:
            print(f"Failed to send message to {user['user_id']}: {str(e)}")
            if isinstance(e, FloodWait):
                time.sleep(e.x)  # Handle flood wait

# Store posts and documents (Only Admins can do this)
@app.on_message(filters.text | filters.document | filters.photo | filters.video)
async def store_content(_, message: Message):
    user_id = message.from_user.id

    # Only allow admins to store files
    if user_id not in ADMIN_IDS:
        await message.reply("❌ You are not authorized to store files. Only admins can use this feature.")
        return

    try:
        # Forward message to the channel
        forwarded_message = await message.forward(CHANNEL_ID)
        unique_id = save_file_metadata(forwarded_message.message_id, message.chat.type, forwarded_message.message_id)

        # Send user the special link to access the file
        await message.reply(f"✅ File stored successfully! Access it anytime using this link:\n`/get_{unique_id}`")

    except Exception as e:
        await message.reply(f"❌ Failed to store the content! Error: {str(e)}")

# Retrieve file using unique link
@app.on_message(filters.command("get_"))
async def retrieve_file(_, message: Message):
    unique_id = message.command[0][4:]

    # Retrieve file metadata from MongoDB
    file_metadata = get_file_metadata(unique_id)

    if file_metadata:
        # Forward the file to the user
        await app.forward_messages(
            chat_id=message.chat.id,
            from_chat_id=CHANNEL_ID,
            message_ids=file_metadata["channel_message_id"]
        )
    else:
        await message.reply("❌ File not found or the link is invalid!")

# Prevent users from forwarding bot's messages to others
@app.on_message(filters.chat(BOT_TOKEN))
async def block_forward(_, message: Message):
    # Delete the message if it's being forwarded
    await message.delete()

# Run the bot
print("Bot is running...")
app.run()
