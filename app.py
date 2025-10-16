
import asyncio
import base64
import re
from collections import defaultdict

from pyrogram import Client, enums

from cache import user_file_count

class Bot(Client):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.user_file_count = user_file_count
        self.copy_lock = asyncio.Lock()
        self.SEARCH_PAGE_SIZE = 10
        self.MAX_FILES_PER_SESSION = 10
        self.PAGE_SIZE = 10

    def sanitize_query(self, query):
        """Sanitizes and normalizes a search query for consistent matching of 'and' and '&'."""
        query = query.strip().lower()
        query = re.sub(r"\s*&\s*", " and ", query)
        query = re.sub(r"[:',]", "", query)
        query = re.sub(r"[.\s_\-\(\)\[\]!]+", " ", query).strip()
        return query

    def remove_surrogates(self, text):
        return ''.join(c for c in text if not (0xD800 <= ord(c) <= 0xDFFF))

    def encode_file_link(self, channel_id, message_id):
        raw = f"{channel_id}_{message_id}".encode()
        return base64.urlsafe_b64encode(raw).decode().rstrip("=")

from config import API_ID, API_HASH, BOT_TOKEN

bot = Bot(
    "bot",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN,
    parse_mode=enums.ParseMode.HTML
)
