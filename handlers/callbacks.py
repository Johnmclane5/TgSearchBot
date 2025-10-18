
import base64
import logging
from urllib.parse import unquote_plus
from datetime import datetime, timezone

from pyrogram import filters, enums
from pyrogram.types import CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from pyrogram.errors import MessageNotModified

from config import LOG_CHANNEL_ID, BOT_USERNAME, MY_DOMAIN
from db import files_col, allowed_channels_col, tokens_col
from utility import (
    get_user_link,
    human_readable_size,
    is_user_authorized,
    generate_token,
    shorten_url,
    get_token_link,
    safe_api_call,
)
from app import bot

logger = logging.getLogger(__name__)



@bot.on_callback_query(filters.regex(r"^viewfile:(-?\d+):(\d+)$"))
async def view_file_callback_handler(client, callback_query: CallbackQuery):
    try:
        channel_id = int(callback_query.matches[0].group(1))
        message_id = int(callback_query.matches[0].group(2))

        file_doc = files_col.find_one({"channel_id": channel_id, "message_id": message_id})
        if not file_doc:
            await callback_query.answer("❌ File not found!", show_alert=True)
            return

        file_name = file_doc.get("file_name", "Unknown file")
        await callback_query.answer(file_name, show_alert=True)
    except Exception as e:
        logger.error(f"Error in view_file_callback_handler: {e}")
        await callback_query.answer("An error occurred.", show_alert=True)

@bot.on_callback_query(filters.regex(r"^noop$"))
async def noop_callback_handler(client, callback_query: CallbackQuery):
    await callback_query.answer()
