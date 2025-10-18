
import logging
from datetime import datetime
import asyncio
from pyrogram import filters, enums
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from pyrogram.errors import ChatAdminRequired, UserAlreadyParticipant

from config import LOG_CHANNEL_ID, BOT_USERNAME, BACKUP_CHANNEL, MY_DOMAIN
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
)
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
                f"Send me any file to get a shareable link.\n\n"
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


@bot.on_message(filters.private & (filters.document | filters.video | filters.audio | filters.photo))
async def private_file_handler(client, message):
    try:
        # 1. Copy the file to the log channel
        copied_message = await message.copy(chat_id=LOG_CHANNEL_ID)

        # 2. Generate links
        file_link = bot.encode_file_link(copied_message.chat.id, copied_message.id)
        download_url = f"{MY_DOMAIN}/download/{file_link}"
        mx_player_url = f"{MY_DOMAIN}/play/mx/{file_link}"
        mx_player_pro_url = f"{MY_DOMAIN}/play/mxpro/{file_link}"

        buttons = [
            [
                InlineKeyboardButton("📥 DL", url=download_url),
                InlineKeyboardButton("▶️ MX", url=mx_player_url),
                InlineKeyboardButton("▶️ Pro", url=mx_player_pro_url)
            ]
        ]
        reply_markup = InlineKeyboardMarkup(buttons)

        # 3. Reply to the user
        await message.reply_text(
            text=f"✅ File processed successfully!",
            reply_markup=reply_markup,
            quote=True
        )

        # 4. Delete the original message
        await message.delete()

    except Exception as e:
        logger.error(f"Error in private_file_handler: {e}")
        await message.reply_text("An error occurred while processing the file.")
