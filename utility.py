
import asyncio
import base64
import logging
import uuid
from datetime import datetime, timezone, timedelta
from pyrogram.errors import FloodWait, UserNotParticipant, UserIsBlocked, InputUserDeactivated, PeerIdInvalid, UserIsBot
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, User

from db import users_col, tokens_col, auth_users_col
from config import *

# =========================
# Constants & Globals
# =========================

TOKEN_VALIDITY_SECONDS = 24 * 60 * 60  # 24 hours
AUTO_DELETE_SECONDS = 3 * 60

logger = logging.getLogger(__name__)

# =========================
# User Utilities
# =========================

def add_user(user_id):
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
    expiry = datetime.now(timezone.utc) + timedelta(seconds=TOKEN_VALIDITY_SECONDS)
    auth_users_col.update_one(
        {"user_id": user_id},
        {"$set": {"expiry": expiry}},
        upsert=True
    )

def is_user_authorized(user_id):
    doc = auth_users_col.find_one({"user_id": user_id})
    if not doc:
        return False
    expiry = doc["expiry"]
    if isinstance(expiry, datetime) and expiry.tzinfo is None:
        expiry = expiry.replace(tzinfo=timezone.utc)
    return expiry >= datetime.now(timezone.utc)


async def get_user_link(user: User) -> str:
    return f'<a href=tg://user?id={user.id}>{user.first_name}</a>'

# =========================
# Token Utilities
# =========================

def generate_token(user_id):
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
    return f"https://telegram.dog/{bot_username}?start=token_{token_id}"

async def is_user_subscribed(client, user_id):
    if not BACKUP_CHANNEL:
        return True
    try:
        member = await client.get_chat_member(BACKUP_CHANNEL, user_id)
        return not member.status == 'kicked'
    except UserNotParticipant:
        return False
    except Exception as e:
        logger.error(e)
        return False

# =========================
# Link & URL Utilities
# =========================

def encode_file_link(channel_id, message_id):
    return base64.urlsafe_b64encode(f"{channel_id}_{message_id}".encode()).decode().rstrip("=")

# =========================
# Async/Bot Utilities
# =========================

async def safe_api_call(coro):
    try:
        return await coro
    except (UserIsBlocked, InputUserDeactivated, PeerIdInvalid, UserIsBot) as e:
        logger.warning(f"User related error: {e}")
        raise
    except FloodWait as e:
        await asyncio.sleep(e.value * 1.2)
        return await safe_api_call(coro)
    except Exception as e:
        logger.error(f"An error occurred during an API call: {e}")
        return None

async def auto_delete_message(*messages):
    await asyncio.sleep(AUTO_DELETE_SECONDS)
    for message in messages:
        if message:
            try:
                await safe_api_call(message.delete())
            except Exception:
                pass

# =========================
# Queue System for File Processing
# =========================

file_queue = asyncio.Queue()

async def file_queue_worker(bot):
    while True:
        user_message, reply_message = await file_queue.get()
        try:
            log_message = await user_message.forward(LOG_CHANNEL_ID)

            file_link = encode_file_link(log_message.chat.id, log_message.id)

            file_name = getattr(user_message, user_message.media.value).file_name or "N/A"

            download_url = f"{MY_DOMAIN}/download/{file_link}"
            mx_player_url = f"{MY_DOMAIN}/play/mx/{file_link}"
            mx_player_pro_url = f"{MY_DOMAIN}/play/mxpro/{file_link}"

            buttons = [
                [
                    InlineKeyboardButton("📥 Download", url=download_url),
                    InlineKeyboardButton("▶️ MX Player", url=mx_player_url),
                    InlineKeyboardButton("▶️ MX Player Pro", url=mx_player_pro_url)
                ]
            ]
            reply_markup = InlineKeyboardMarkup(buttons)

            await reply_message.edit_text(
                f"🎥 <b>File:</b> <code>{file_name}</code>\n\nYour links are ready!",
                reply_markup=reply_markup
            )
            bot.loop.create_task(auto_delete_message(user_message))
        except Exception as e:
            logger.error(f"Error processing file: {e}")
            await reply_message.edit_text("❌ Failed to process your file. Please try again later.")
        finally:
            file_queue.task_done()


async def queue_file_for_processing(user_message, reply_message):
    await file_queue.put((user_message, reply_message))

# =========================
# Periodic Cleanup
# =========================

def delete_expired_tokens():
    now = datetime.now(timezone.utc)
    tokens_col.delete_many({"expiry": {"$lt": now}})
    auth_users_col.delete_many({"expiry": {"$lt": now}})
    logger.info("Expired tokens and authorized users cleaned up.")

async def periodic_expiry_cleanup(interval_seconds=3600 * 4):
    while True:
        delete_expired_tokens()
        await asyncio.sleep(interval_seconds)
