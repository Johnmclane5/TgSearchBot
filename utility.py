
import re
import aiohttp
import asyncio
import base64
import uuid
import time
import os
import logging
from datetime import datetime, timezone, timedelta
from pyrogram.errors import FloodWait, UserNotParticipant, UserIsBlocked, InputUserDeactivated, PeerIdInvalid, UserIsBot
from pyrogram import enums
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, User
from db import (
    allowed_channels_col,
    users_col,
    tokens_col,
    auth_users_col,
    files_col
)
from config import *
from mutagen.mp3 import MP3
from mutagen.flac import FLAC
from mutagen.mp4 import MP4
from mutagen.id3 import ID3, APIC
from mutagen import File as MutagenFile

# =========================
# Constants & Globals
# =========================

TOKEN_VALIDITY_SECONDS = 24 * 60 * 60  # 24 hours
AUTO_DELETE_SECONDS = 3 * 60

# Simple in-memory cache: {(q, channel_id): (timestamp, results)}
search_api_cache = {}
CACHE_TTL = 300  # 5 minutes

logger = logging.getLogger(__name__)

# =========================
# Channel & User Utilities
# =========================

async def get_allowed_channels():
    return [
        doc["channel_id"]
        for doc in allowed_channels_col.find({}, {"_id": 0, "channel_id": 1})
    ]

def add_user(user_id):
    """
    Add a user to users_col only if not already present.
    Stores user_id, joined_date (UTC), and blocked status.
    Returns the user document with an extra key '_new' (True if newly added).
    """
    user_doc = users_col.find_one({"user_id": user_id})
    
    if not user_doc:
        user_doc = {
            "user_id": user_id,
            "joined": datetime.now(timezone.utc),
            "blocked": False
        }

        users_col.insert_one(user_doc)

        user_doc["_new"] = True
    else:
        user_doc["_new"] = False
    
    return user_doc


def authorize_user(user_id):
    """Authorize a user for 24 hours."""
    expiry = datetime.now(timezone.utc) + timedelta(seconds=TOKEN_VALIDITY_SECONDS)
    auth_users_col.update_one(
        {"user_id": user_id},
        {"$set": {"expiry": expiry}},
        upsert=True
    )

def is_user_authorized(user_id):
    """Check if a user is authorized."""
    doc = auth_users_col.find_one({"user_id": user_id})
    if not doc:
        return False
    expiry = doc["expiry"]
    if isinstance(expiry, str):
        try:
            expiry = datetime.fromisoformat(expiry)
        except Exception:
            return False
    if isinstance(expiry, datetime) and expiry.tzinfo is None:
        expiry = expiry.replace(tzinfo=timezone.utc)
    if expiry < datetime.now(timezone.utc):
        return False
    return True

async def get_user_link(user: User) -> str:
    try:
        user_id = user.id if hasattr(user, 'id') else None
        first_name = user.first_name if hasattr(user, 'first_name') else "Unknown"
    except Exception as e:
        logger.info(f"{e}")
        user_id = None
        first_name = "Unknown"
    
    if user_id:
        return f'<a href=tg://user?id={user_id}>{first_name}</a>'
    else:
        return first_name
    
# =========================
# Token Utilities
# =========================

def generate_token(user_id):
    """Generate a new access token for a user."""
    token_id = str(uuid.uuid4())
    expiry = datetime.now(timezone.utc) + timedelta(seconds=TOKEN_VALIDITY_SECONDS)
    tokens_col.insert_one({
        "token_id": token_id,
        "user_id": user_id,
        "expiry": expiry,
        "created_at": datetime.now(timezone.utc)
    })
    return token_id

def is_token_valid(token_id, user_id):
    """Check if a token is valid for a user."""
    token = tokens_col.find_one({"token_id": token_id, "user_id": user_id})
    if not token:
        return False
    expiry = token["expiry"]
    if expiry.tzinfo is None:
        expiry = expiry.replace(tzinfo=timezone.utc)
    if expiry < datetime.now(timezone.utc):
        tokens_col.delete_one({"_id": token["_id"]})
        return False
    return True

def get_token_link(token_id, bot_username):
    """Generate a Telegram deep link for a token."""
    return f"https://telegram.dog/{bot_username}?start=token_{token_id}"

async def is_user_subscribed(client, user_id):
    """Check if a user is subscribed to backup channel."""
    if not BACKUP_CHANNEL:
        return True  # No backup channel configured, consider all subscribed
    try:
        member = await client.get_chat_member(BACKUP_CHANNEL, user_id)
    except UserNotParticipant:
        pass
    except Exception as e:
        logger.exception(e)
    else:
        if not member.status == 'kicked':
            return True
        
    return False
# =========================
# Link & URL Utilities
# =========================

def generate_telegram_link(bot_username, channel_id, message_id):
    """Generate a base64-encoded Telegram deep link for a file."""
    raw = f"{channel_id}_{message_id}".encode()
    b64 = base64.urlsafe_b64encode(raw).decode().rstrip("=")
    return f"https://telegram.dog/{bot_username}?start=file_{b64}" 

def generate_c_link(channel_id, message_id):
    # channel_id must be like -1001234567890
    return f"https://t.me/c/{str(channel_id)[4:]}/{message_id}"

def extract_channel_and_msg_id(link):
    # Only support t.me/c/(-?\d+)/(\d+)
    match = re.search(r"t\.me/c/(-?\d+)/(\d+)", link)
    if match:
        channel_id = int("-100" + match.group(1)) if not match.group(1).startswith("-100") else int(match.group(1))
        msg_id = int(match.group(2))
        return channel_id, msg_id
    raise ValueError("Invalid Telegram message link format. Only /c/ links are supported.")

async def shorten_url(url):
    """
    Shorten a URL using the configured shortener service.
    Returns the original URL if shortening fails.
    """
    try:
        api_url = f"https://{SHORTERNER_URL}/api"
        params = {
            "api": URLSHORTX_API_TOKEN,
            "url": url,
            "format": "text"
        }

        async with aiohttp.ClientSession() as session:
            async with session.get(api_url, params=params) as response:
                if response.status == 200:
                    return (await response.text()).strip()
                else:
                    logger.error(
                        f"URL shortening failed. Status code: {response.status}, Response: {await response.text()}"
                    )
                    return url
    except Exception as e:
        logger.error(f"URL shortening failed: {e}")
        return url
    
# =========================
# File Utilities
# =========================
def upsert_file_info(file_info):
    """Insert or update file info, avoiding duplicates."""
    files_col.update_one(
        {"channel_id": file_info["channel_id"], "message_id": file_info["message_id"]},
        {"$set": file_info},
        upsert=True
    )


def extract_file_info(message, channel_id=None):
    """Extract file info from a Pyrogram message."""
    caption_name = message.caption.strip() if message.caption else None
    file_info = {
        "channel_id": channel_id if channel_id is not None else message.chat.id,
        "message_id": message.id,
        "file_name": None,
        "file_size": None,
        "file_format": None,
    }
    if message.document:
        file_info["file_name"] = caption_name or message.document.file_name
        file_info["file_size"] = message.document.file_size
        file_info["file_format"] = message.document.mime_type
    elif message.video:
        file_info["file_name"] = caption_name or (message.video.file_name or "video.mp4")
        file_info["file_size"] = message.video.file_size
        file_info["file_format"] = message.video.mime_type
    elif message.audio:
        file_info["file_name"] = caption_name or (message.audio.file_name or "audio.mp3")
        file_info["file_size"] = message.audio.file_size
        file_info["file_format"] = message.audio.mime_type
    elif message.photo:
        file_info["file_name"] = caption_name or "photo.jpg"
        file_info["file_size"] = getattr(message.photo, "file_size", None)
        file_info["file_format"] = "image/jpeg"
    if file_info["file_name"]:
        file_info["file_name"] = remove_extension(re.sub(r"[',]", "", file_info["file_name"].replace("&", "and")))
    return file_info

def human_readable_size(size):
    for unit in ['B','KB','MB','GB','TB']:
        if size < 1024:
            return f"{size:.2f} {unit}"
        size /= 1024
    return f"{size:.2f} PB"

def remove_extension(caption):
    try:
        # Remove the extension and everything after it
        cleaned_caption = re.sub(r'\.(mkv|mp4|webm).*$', '', caption, flags=re.IGNORECASE)
        return cleaned_caption
    except Exception as e:
        logger.error(e)
        return None
    
def remove_unwanted(caption):
    try:
        # Match and keep everything up to and including the extension
        match = re.match(r'^(.*?\.(mkv|mp4|webm))', caption, flags=re.IGNORECASE)
        if match:
            return match.group(1)
        return caption  # Return original if no match
    except Exception as e:
        logger.error(e)
        return None

# =========================
# Async/Bot Utilities
# =========================
async def safe_api_call(coro):
    """Utility wrapper to add delay before every bot API call."""
    try:
        return await coro
    except (UserIsBlocked, InputUserDeactivated, PeerIdInvalid, UserIsBot) as e:
        raise e
    except FloodWait as e:
        await asyncio.sleep(e.value * 1.2)
    except Exception as e:
        logger.error(f"An error occurred during an API call: {e}")
        return None

async def delete_after_delay(client, channel_id, message_id, delay=AUTO_DELETE_SECONDS):
    await asyncio.sleep(delay)
    try:
        await safe_api_call(client.delete_messages(channel_id, message_id))
    except Exception as e:
        logger.error(f"Failed to auto delete message: {e}")

async def auto_delete_message(user_message, bot_message):
    try:        
        await asyncio.sleep(AUTO_DELETE_SECONDS)
        await safe_api_call(user_message.delete())
        await safe_api_call(bot_message.delete())
    except Exception as e:
        pass


# =========================
# Queue System for File Processing
# =========================

file_queue = asyncio.Queue()

async def handle_duplicate_file(bot, file_info):
    """Checks for duplicate files and logs if found."""
    existing = files_col.find_one({
        "channel_id": file_info["channel_id"],
        "file_name": file_info["file_name"]
    })
    if existing:
        telegram_link = generate_c_link(file_info["channel_id"], file_info["message_id"])
        await safe_api_call(
            bot.send_message(
                LOG_CHANNEL_ID,
                f"⚠️ Duplicate File.\nLink: {telegram_link}",
                parse_mode=enums.ParseMode.HTML
            )
        )
        return True
    return False

async def process_audio_file(bot, message):
    """Processes audio files: downloads, gets thumbnail, sends info, and cleans up."""
    try:
        audio_path = await bot.download_media(message)
        thumb_path = await get_audio_thumbnail(audio_path)
        if thumb_path:
            file_info_text = f"🎧 <b>Title:</b> {message.audio.title}\n🧑‍🎤 <b>Artist:</b> {message.audio.performer}"
            await bot.send_photo(UPDATE_CHANNEL_ID2, photo=thumb_path, caption=file_info_text)
            os.remove(thumb_path)
        os.remove(audio_path)
    except Exception as e:
        logger.error(f"Error processing audio file: {e}")


async def file_queue_worker(bot):
    while True:
        item = await file_queue.get()
        file_info, _, message, duplicate = item
        try:
            if duplicate and await handle_duplicate_file(bot, file_info):
                continue

            upsert_file_info(file_info)

            if duplicate:
                if message.audio:
                    await process_audio_file(bot, message)

        except Exception as e:
            logger.error(f"❌ Error saving file: {e}")
        finally:
            file_queue.task_done()

# =========================
# Unified File Queueing
# =========================

async def queue_file_for_processing(message, channel_id=None, reply_func=None, duplicate=True):
    try:            
        file_info = extract_file_info(message, channel_id=channel_id)
        if file_info["file_name"]:
            await file_queue.put((file_info, reply_func, message, duplicate))
    except Exception as e:
        if reply_func:
            await safe_api_call(reply_func(f"❌ Error queuing file: {e}"))

def delete_expired_auth_users():
    """
    Delete expired auth users from auth_users_col using 'expiry' field.
    """
    now = datetime.now(timezone.utc)
    result = auth_users_col.delete_many({"expiry": {"$lt": now}})
    logger.info(f"Deleted {result.deleted_count} expired auth users.")

def delete_expired_tokens():
    """
    Delete expired tokens from tokens_col using 'expiry' field.
    """
    now = datetime.now(timezone.utc)
    result = tokens_col.delete_many({"expiry": {"$lt": now}})
    logger.info(f"Deleted {result.deleted_count} expired tokens.")

async def periodic_expiry_cleanup(interval_seconds=3600 * 4):
    """
    Periodically delete expired auth users and tokens.
    """
    while True:
        delete_expired_auth_users()
        delete_expired_tokens()
        await asyncio.sleep(interval_seconds)


async def get_audio_thumbnail(audio_path, output_dir="downloads"):
    audio = MutagenFile(audio_path)
    thumbnail_path = os.path.join(output_dir, "audio_thumbnail.jpg")

    if isinstance(audio, MP3):
        if audio.tags and isinstance(audio.tags, ID3):
            for tag in audio.tags.values():
                if isinstance(tag, APIC):
                    with open(thumbnail_path, "wb") as img_file:
                        img_file.write(tag.data)
                    return thumbnail_path
    elif isinstance(audio, FLAC):
        if audio.pictures:
            with open(thumbnail_path, "wb") as img_file:
                img_file.write(audio.pictures[0].data)
            return thumbnail_path
    elif isinstance(audio, MP4):
        if audio.tags and 'covr' in audio.tags:
            cover = audio.tags['covr'][0]
            with open(thumbnail_path, "wb") as img_file:
                img_file.write(cover)
            return thumbnail_path
    
    return None