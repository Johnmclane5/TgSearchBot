
import os
import sys
import logging
from pyrogram.errors import UserIsBlocked, InputUserDeactivated, PeerIdInvalid, UserIsBot

from pyrogram import filters
from pyrogram.types import Message

from config import OWNER_ID, LOG_CHANNEL_ID
from db import auth_users_col, users_col
from utility import (
    auto_delete_message,
    safe_api_call,
)
from app import bot

logger = logging.getLogger(__name__)


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

        text = (
            f"<b>Total authorized users:</b> {total_auth_users}\n"
            f"<b>Total users in db:</b> {total_users}\n"
        )

        reply = await message.reply_text(text)
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
