
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
    build_search_pipeline,
    human_readable_size,
    is_user_authorized,
    generate_token,
    shorten_url,
    get_token_link,
    delete_after_delay,
    safe_api_call,
)
from query_helper import get_query_by_id
from app import bot

logger = logging.getLogger(__name__)

@bot.on_callback_query(filters.regex(r"^search_channel:(.+):(-?\d+):(\d+):(\d+)$"))
async def channel_search_callback_handler(client, callback_query: CallbackQuery):
    try:
        query_id = callback_query.matches[0].group(1)
        channel_id = int(callback_query.matches[0].group(2))
        page = int(callback_query.matches[0].group(3))
        mode = int(callback_query.matches[0].group(4))
        user_link = await get_user_link(callback_query.from_user)
        user_id = callback_query.from_user.id

        skip = (page - 1) * bot.SEARCH_PAGE_SIZE
        query = get_query_by_id(query_id)
        if not query:
            await callback_query.answer("Your query has expired. Please send a new one.", show_alert=True)
            return

        query = bot.sanitize_query(unquote_plus(query))
        pipeline = build_search_pipeline(query, [channel_id], skip, bot.SEARCH_PAGE_SIZE)

        result = list(files_col.aggregate(pipeline))
        files = result[0]["results"] if result and result[0]["results"] else []
        total_files = result[0]["totalCount"][0]["total"] if result and result[0]["totalCount"] else 0

        channel_info = allowed_channels_col.find_one({'channel_id': channel_id})
        channel_name = channel_info.get('channel_name', str(channel_id)) if channel_info else str(channel_id)

        if not files:
            google_search_url = f"https://www.google.com/search?q={query.replace(' ', '+')}"
            text = (f"🚫 Not Available in {channel_name}\n\n"
                    f"Spelling check 👉 <b><a href=\"{google_search_url}\">Google</a></b>\n\n")
            text = bot.remove_surrogates(text)
            await callback_query.edit_message_text(text, disable_web_page_preview=True)
            await safe_api_call(client.send_message(
                LOG_CHANNEL_ID, text=f"{user_link} | <code>{user_id}</code>\n{channel_name} | <code>{query}</code>"
                ))
            return

        total_pages = (total_files + bot.SEARCH_PAGE_SIZE - 1) // bot.SEARCH_PAGE_SIZE
        text = f"📂 Found: {total_files} file(s)\n🛒 Category: {bot.remove_surrogates(channel_name)}"
        buttons = []
        for f in files:
            file_link = bot.encode_file_link(f["channel_id"], f["message_id"])
            size_str = human_readable_size(f.get('file_size', 0))
            file_name = bot.remove_surrogates(f.get('file_name', ''))
            btn_text = f"{size_str}┃{file_name}"

            if mode == 0:
                btn = InlineKeyboardButton(btn_text, callback_data=f"getfile:{file_link}")
            else:
                btn = InlineKeyboardButton(btn_text, callback_data=f"viewfile:{f['channel_id']}:{f['message_id']}")
            buttons.append([btn])

        page_buttons = []
        if page > 1:
            page_buttons.append(InlineKeyboardButton("⬅️", callback_data=f"search_channel:{query_id}:{channel_id}:{page - 1}:{mode}"))
        page_buttons.append(InlineKeyboardButton(f"📃 {page}/{total_pages}", callback_data="noop"))
        if page < total_pages:
            page_buttons.append(InlineKeyboardButton("➡️", callback_data=f"search_channel:{query_id}:{channel_id}:{page + 1}:{mode}"))

        toggle_mode = 1 - mode
        toggle_icon = "👁️" if mode == 0 else "📲"
        page_buttons.append(InlineKeyboardButton(toggle_icon, callback_data=f"search_channel:{query_id}:{channel_id}:{page}:{toggle_mode}"))

        reply_markup = InlineKeyboardMarkup(buttons + ([page_buttons] if page_buttons else []))

        await safe_api_call(callback_query.edit_message_text(
            text,
            reply_markup=reply_markup,
            parse_mode=enums.ParseMode.HTML,
            disable_web_page_preview=True
        ))
    except MessageNotModified:
        pass
    except Exception as e:
        logger.exception(f"Error in channel_search_callback_handler: {e}")
    finally:
        await callback_query.answer()

@bot.on_callback_query(filters.regex(r"^getfile:(.+)$"))
async def send_file_callback(client, callback_query: CallbackQuery):
    try:
        file_link = callback_query.matches[0].group(1)
        user_id = callback_query.from_user.id

        padding = '=' * (-len(file_link) % 4)
        decoded = base64.urlsafe_b64decode(file_link + padding).decode()
        channel_id, msg_id = map(int, decoded.split("_"))

        if not is_user_authorized(user_id):
            now = datetime.now(timezone.utc)
            token_doc = tokens_col.find_one({"user_id": user_id, "expiry": {"$gt": now}})
            token_id = token_doc["token_id"] if token_doc else generate_token(user_id)
            short_link = await shorten_url(get_token_link(token_id, BOT_USERNAME))
            await safe_api_call(callback_query.edit_message_text(
                text="You are not authorized",
                reply_markup=InlineKeyboardMarkup(
                    [[InlineKeyboardButton("🔓 Unlock", url=short_link)]]
                )
            ))
            return

        if bot.user_file_count.get(user_id, 0) >= bot.MAX_FILES_PER_SESSION:
            await safe_api_call(callback_query.answer("Limit reached. Please take a break.", show_alert=True))
            return

        file_doc = files_col.find_one({"channel_id": channel_id, "message_id": msg_id})
        if not file_doc:
            await callback_query.answer("File not found.", show_alert=True)
            return

        file_name = file_doc.get("file_name", "Unknown File")

        download_url = f"{MY_DOMAIN}/download/{file_link}"
        mx_player_url = f"{MY_DOMAIN}/play/mx/{file_link}"
        mx_player_pro_url = f"{MY_DOMAIN}/play/mxpro/{file_link}"

        buttons = [
            [InlineKeyboardButton("📥 Download", url=download_url)],
            [InlineKeyboardButton("▶️ Play in MX Player", url=mx_player_url)],
            [InlineKeyboardButton("▶️ Play in MX Player Pro", url=mx_player_pro_url)]
        ]
        reply_markup = InlineKeyboardMarkup(buttons)

        copy_msg = await safe_api_call(client.copy_message(
            chat_id=user_id,
            from_chat_id=file_doc["channel_id"],
            message_id=file_doc["message_id"],
            caption=f"🎥 <b>{file_name}</b>",
            reply_markup=reply_markup,
            protect_content=True
        ))

        if copy_msg:
            bot.user_file_count[user_id] = bot.user_file_count.get(user_id, 0) + 1
            await safe_api_call(callback_query.answer(
                "File sent successfully!", show_alert=True
            ))
        else:
            await safe_api_call(callback_query.answer(
                "Failed to send file. Please try again later.", show_alert=True
            ))

    except Exception as e:
        logger.error(f"Error in send_file_callback: {e}")

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
