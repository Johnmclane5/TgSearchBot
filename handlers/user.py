
import logging
from datetime import datetime
import asyncio
from pyrogram import filters, enums
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from pyrogram.errors import ChatAdminRequired, UserAlreadyParticipant

from config import LOG_CHANNEL_ID, BOT_USERNAME, BACKUP_CHANNEL
from db import users_col, allowed_channels_col
from utility import (
    add_user,
    is_token_valid,
    authorize_user,
    get_user_link,
    safe_api_call,
    is_user_subscribed,
    auto_delete_message,
    get_allowed_channels,
    queue_file_for_processing,
    invalidate_search_cache,
    file_queue,
)
from query_helper import store_query
from app import bot

logger = logging.getLogger(__name__)

@bot.on_message(filters.command("start") & filters.private)
async def start_handler(client, message):
    reply_msg = None
    try:
        user_id = message.from_user.id
        user_link = await get_user_link(message.from_user)
        first_name = message.from_user.first_name or "there"
        username = message.from_user.username or None
        user_doc = add_user(user_id)

        if user_doc["_new"]:
            log_msg = f"👤 New user added:\nID: <code>{user_id}</code>\n"
            if first_name:
                log_msg += f"First Name: <b>{first_name}</b>\n"
            if username:
                log_msg += f"Username: @{username}\n"
            await safe_api_call(
                bot.send_message(LOG_CHANNEL_ID, log_msg, parse_mode=enums.ParseMode.HTML)
            )

        if user_doc.get("blocked", True):
            return

        if len(message.command) == 2 and message.command[1].startswith("token_"):
            if is_token_valid(message.command[1][6:], user_id):
                authorize_user(user_id)
                reply_msg = await safe_api_call(message.reply_text("✅ You are authorized now!"))
                await safe_api_call(bot.send_message(LOG_CHANNEL_ID, f"✅ User <b>{user_link} | <code>{user_id}</code></b> authorized via @{BOT_USERNAME}"))
            else:
                reply_msg = await safe_api_call(message.reply_text("❌ Invalid or expired token. Please get a new one."))
                await safe_api_call(bot.send_message(LOG_CHANNEL_ID, f"❌ User <b>{user_link} | <code>{user_id}</code></b> used invalid or expired token."))
        else:
            user_doc = users_col.find_one({"user_id": user_id})
            joined_date = user_doc.get("joined", "Unknown")
            joined_str = joined_date.strftime("%Y-%m-%d %H:%M") if isinstance(joined_date, datetime) else str(joined_date)

            welcome_text = (
                f"Hey <b>{first_name}</b> 👋\n\n"
                f"Type any keywords to 🔎\n\n"
                f"👤 Joined: {joined_str}"
            )
            reply_msg = await safe_api_call(message.reply_text(
                welcome_text,
                quote=True,
                reply_to_message_id=message.id,
            ))
    except Exception as e:
        logger.error(f"⚠️ An unexpected error occurred in start_handler: {e}")

    if reply_msg:
        bot.loop.create_task(auto_delete_message(message, reply_msg))

@bot.on_message(filters.channel & (filters.document | filters.video | filters.audio | filters.photo))
async def channel_file_handler(client, message):
    try:
        allowed_channels = await get_allowed_channels()
        if message.chat.id not in allowed_channels:
            return

        await queue_file_for_processing(message)
        await file_queue.join()
        invalidate_search_cache()
    except Exception as e:
        logger.error(f"Error in channel_file_handler: {e}")

@bot.on_message(filters.private & filters.text & ~filters.command([
    "start", "stats", "add", "rm", "broadcast", "log", "tmdb",
    "restore", "index", "del", "restart", "op", "block", "unblock", "revoke"]))
async def instant_search_handler(client, message):
    reply = None
    user_id = message.from_user.id
    try:
        query = bot.sanitize_query(message.text)
        if not query:
            return

        query_id = store_query(query)
        user_doc = add_user(user_id)
        if user_doc.get("blocked", True):
            return

        reply = await message.reply_text(text="Please wait ...", quote=True, reply_to_message_id=message.id)
        await asyncio.sleep(3)

        if BACKUP_CHANNEL and not await is_user_subscribed(client, user_id):
            await safe_api_call(reply.edit_text(
                text=(
                    "🚫 You must join our Updates Channel to use the bot.\n\n"
                    "Click the button below to join and then try again."
                ),
                reply_markup=InlineKeyboardMarkup(
                    [[InlineKeyboardButton("🔔 Join Bot Updates", url=f"https://t.me/{BACKUP_CHANNEL}")]]
                )
            ))
            bot.loop.create_task(auto_delete_message(message, reply))
            return

        channels = list(allowed_channels_col.find({}, {"_id": 0, "channel_id": 1, "channel_name": 1}))
        if not channels:
            await safe_api_call(reply.edit_text("No allowed channels available for search."))
            return

        text = "<b>🛒 Choose a Category</b>"
        buttons = []
        for c in channels:
            chan_id = c["channel_id"]
            chan_name = c.get("channel_name", str(chan_id))
            data = f"search_channel:{query_id}:{chan_id}:1:0"
            buttons.append([InlineKeyboardButton(chan_name, callback_data=data)])
        reply_markup = InlineKeyboardMarkup(buttons)
        await safe_api_call(reply.edit_text(text, reply_markup=reply_markup, parse_mode=enums.ParseMode.HTML))
    except Exception as e:
        logger.error(f"Error in instant_search_handler: {e}")
        if reply:
            await reply.edit_text("Invalid search query. Please try again with a different query.")
    if reply:
        bot.loop.create_task(auto_delete_message(message, reply))

@bot.on_message(filters.group & filters.service)
async def delete_service_messages(client, message):
    try:
        await message.delete()
    except Exception as e:
        logger.warning(f"Failed to delete service message in chat {message.chat.id}: {e}")

@bot.on_chat_join_request()
async def approve_join_request_handler(client, join_request):
    try:
        await client.approve_chat_join_request(join_request.chat.id, join_request.from_user.id)
        await safe_api_call(bot.send_message(LOG_CHANNEL_ID, f"✅ Approved join request for {join_request.from_user.mention} in {join_request.chat.title}"))
    except (ChatAdminRequired, UserAlreadyParticipant) as e:
        logger.warning(f"Could not approve join request: {e}")
    except Exception as e:
        logger.error(f"Failed to approve join request: {e}")
