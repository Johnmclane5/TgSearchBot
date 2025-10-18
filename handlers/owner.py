
import os
import sys
import logging
from bson import ObjectId
from pyrogram.errors import UserIsBlocked, InputUserDeactivated, ListenerTimeout, PeerIdInvalid, UserIsBot

from pyrogram import filters, enums
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton

from config import OWNER_ID, LOG_CHANNEL_ID, UPDATE_CHANNEL_ID
from db import files_col, allowed_channels_col, auth_users_col, users_col, db
from utility import (
    extract_channel_and_msg_id,
    get_allowed_channels,
    queue_file_for_processing,
    invalidate_search_cache,
    auto_delete_message,
    safe_api_call,
    remove_unwanted,
    human_readable_size,
)
from app import bot

logger = logging.getLogger(__name__)

@bot.on_message(filters.private & (filters.document | filters.video | filters.audio) & filters.user(OWNER_ID))
async def del_file_handler(client, message):
    try:
        reply = None
        channel_id = message.forward_from_chat.id if message.forward_from_chat else None
        msg_id = message.forward_from_message_id if message.forward_from_message_id else None
        if channel_id and msg_id:
            file_doc = files_col.find_one({"channel_id": channel_id, "message_id": msg_id})
            if not file_doc:
                reply = await message.reply_text("No file found with that name in the database.")
                return
            result = files_col.delete_one({"channel_id": channel_id, "message_id": msg_id})
            if result.deleted_count > 0:
                reply = await message.reply_text(f"Database record deleted. File name: {file_doc['file_name']}")
        else:
            reply = await message.reply_text("Please forward a file from a channel to delete its record.")
        if reply:
            bot.loop.create_task(auto_delete_message(message, reply))
    except Exception as e:
        logger.error(f"Error in del_file_handler: {e}")
        await message.reply_text(f"An error occurred: {e}")



@bot.on_message(filters.command('restart') & filters.private & filters.user(OWNER_ID))
async def restart(client, message):
    await message.delete()
    os.system("python3 update.py")
    os.execl(sys.executable, sys.executable, "bot.py")


@bot.on_message(filters.command("broadcast") & filters.chat(LOG_CHANNEL_ID))
async def broadcast_handler(client, message: Message):
    if message.reply_to_message:
        users = users_col.find({}, {"_id": 0, "user_id": 1})
        total = 0
        failed = 0
        removed = 0

        for user in users:
             try:
                msg = message.reply_to_message
                if msg.forward_from_chat:
                     await safe_api_call(msg.copy(chat_id=user["user_id"],
                                                  caption=f"{msg.caption.html}\n\n✅ <b>Now Available!</b>",
                                                  reply_markup=msg.reply_markup
                                        ))
                else:
                    await safe_api_call(msg.copy(user["user_id"]))
                total += 1
             except (UserIsBlocked, InputUserDeactivated, PeerIdInvalid, UserIsBot):
                users_col.delete_one({"user_id": user["user_id"]})
                removed += 1
             except Exception as e:
                failed += 1
                logger.error(f"Error broadcasting to {user['user_id']}: {e}")
        await message.reply_text(f"✅ Broadcasted to {total} users.\n❌ Failed: {failed}\n🗑️ Removed: {removed}")

@bot.on_message(filters.command("log") & filters.private & filters.user(OWNER_ID))
async def send_log_file(client, message: Message):
    log_file = "bot_log.txt"
    try:
        if not os.path.exists(log_file):
            await safe_api_call(message.reply_text("Log file not found."))
            return
        reply = await safe_api_call(client.send_document(message.chat.id, log_file, caption="Here is the log file."))
        bot.loop.create_task(auto_delete_message(message, reply))
    except Exception as e:
        logger.error(f"Failed to send log file: {e}")

@bot.on_message(filters.command("stats") & filters.private & filters.user(OWNER_ID))
async def stats_command(client, message: Message):
    try:
        total_auth_users = auth_users_col.count_documents({})
        total_users = users_col.count_documents({})

        pipeline = [
            {"$group": {"_id": None, "total": {"$sum": "$file_size"}}}
        ]
        result = list(files_col.aggregate(pipeline))
        total_storage = result[0]["total"] if result else 0

        stats = db.command("dbstats")
        db_storage = stats.get("storageSize", 0)

        channel_pipeline = [
            {"$group": {"_id": "$channel_id", "count": {"$sum": 1}}},
            {"$sort": {"count": -1}}
        ]
        channel_counts = list(files_col.aggregate(channel_pipeline))
        channel_docs = allowed_channels_col.find({}, {"_id": 0, "channel_id": 1, "channel_name": 1})
        channel_names = {c["channel_id"]: c.get("channel_name", "") for c in channel_docs}

        text = (
            f"<b>Total auth users:</b> {total_auth_users} / {total_users}\n"
            f"<b>Files size:</b> {human_readable_size(total_storage)}\n"
            f"<b>Database storage used:</b> {db_storage / (1024 * 1024):.2f} MB\n"
        )

        if not channel_counts:
            text += " <b>No files indexed yet.</b>"
        else:
            for c in channel_counts:
                chan_id = c['_id']
                chan_name = channel_names.get(chan_id, 'Unknown')
                text += f"<b>{chan_name}</b>: {c['count']} files\n"

        reply = await message.reply_text(text, parse_mode=enums.ParseMode.HTML)
        bot.loop.create_task(auto_delete_message(message, reply))
    except Exception as e:
        logger.error(f"Error in stats_command: {e}")

@bot.on_message(filters.command("op") & filters.chat(LOG_CHANNEL_ID))
async def chatop_handler(client, message: Message):
    args = message.text.split(maxsplit=4)
    if len(args) < 3:
        await message.reply_text(
            "Usage:\n/op send <chat_id> [reply_to_message_id] (reply to a message)\n"
            "/op del <chat_id> <message_id> or <start>-<end>"
        )
        return
    try:
        op = args[1].lower()
        chat_id = int(args[2])

        if op == "send":
            if not message.reply_to_message:
                await message.reply_text("❌ Reply to a message to send it.")
                return

            reply_to_msg_id = None
            if len(args) == 4:
                reply_to_msg_id = int(args[3])

            sent = await message.reply_to_message.copy(
                chat_id,
                reply_to_message_id=reply_to_msg_id
            )
            await message.reply_text(f"✅ Sent to {chat_id} (message_id: {sent.id})")

        elif op == "del":
            if len(args) != 4:
                await message.reply_text("Usage: /op del <chat_id> <message_id> or <start>-<end>")
                return

            msg_arg = args[3]
            if '-' in msg_arg:
                start, end = map(int, msg_arg.split('-'))
                if start > end:
                    await message.reply_text("❌ Start ID must be less than or equal to end ID.")
                    return
                await safe_api_call(client.delete_messages(chat_id, list(range(start, end + 1))))
                await message.reply_text(f"✅ Deleted messages in chat {chat_id}")
            else:
                msg_id = int(msg_arg)
                await safe_api_call(client.delete_messages(chat_id, msg_id))
                await message.reply_text(f"✅ Deleted message {msg_id} in chat {chat_id}")
        else:
            await message.reply_text("Invalid operation. Use 'send' or 'del'.")
    except ValueError:
        await message.reply_text("Invalid chat ID or message ID.")
    except Exception as e:
        logger.error(f"Error in chatop_handler: {e}")
        await message.reply_text(f"❌ Failed: {e}")

@bot.on_message(filters.command("block") & filters.private & filters.user(OWNER_ID))
async def block_user_handler(client, message: Message):
    args = message.text.split()
    if len(args) != 2:
        await message.reply_text("Usage: /block <user_id>")
        return
    try:
        user_id = int(args[1])
        users_col.update_one(
            {"user_id": user_id},
            {"$set": {"blocked": True}},
            upsert=True
        )
        await message.reply_text(f"✅ User {user_id} has been blocked.")
    except ValueError:
        await message.reply_text("Invalid user ID.")
    except Exception as e:
        logger.error(f"Error in block_user_handler: {e}")
        await message.reply_text(f"❌ Failed to block user: {e}")

@bot.on_message(filters.command("unblock") & filters.private & filters.user(OWNER_ID))
async def unblock_user_handler(client, message: Message):
    args = message.text.split()
    if len(args) != 2:
        await message.reply_text("Usage: /unblock <user_id>")
        return
    try:
        user_id = int(args[1])
        users_col.update_one(
            {"user_id": user_id},
            {"$set": {"blocked": False}},
            upsert=True
        )
        await message.reply_text(f"✅ User {user_id} has been unblocked.")
    except ValueError:
        await message.reply_text("Invalid user ID.")
    except Exception as e:
        logger.error(f"Error in unblock_user_handler: {e}")
        await message.reply_text(f"❌ Failed to unblock user: {e}")
