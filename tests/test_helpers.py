
import unittest
import sys
import os
from unittest.mock import patch, MagicMock

# Set dummy environment variables for testing
os.environ['API_ID'] = '12345'
os.environ['API_HASH'] = 'test_hash'
os.environ['BOT_TOKEN'] = 'test_token'
os.environ['OWNER_ID'] = '123456789'
os.environ['BOT_USERNAME'] = 'test_bot'
os.environ['UPDATE_CHANNEL_ID'] = '0'
os.environ['UPDATE_CHANNEL_ID2'] = '0'
os.environ['TMDB_CHANNEL_ID'] = '0'
os.environ['LOG_CHANNEL_ID'] = '0'
os.environ['BACKUP_CHANNEL'] = ''
os.environ['MY_DOMAIN'] = 'test.com'
os.environ['MONGO_URI'] = 'mongodb://localhost:27017/'
os.environ['TMDB_API_KEY'] = 'test_key'
os.environ['URLSHORTX_API_TOKEN'] = 'test_token'
os.environ['SHORTERNER_URL'] = 'test.url'

# Add the project root to the sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# Mock the db module before importing the bot
with patch('db.files_col', MagicMock()) as mock_files_col:
    mock_files_col.list_indexes.return_value = [{'name': 'file_name_text'}]
    from app import Bot
    from query_helper import generate_query_id, store_query, get_query_by_id

class TestHelpers(unittest.TestCase):

    def setUp(self):
        self.bot = Bot("test_bot", api_id=12345, api_hash="test_hash")

    def test_sanitize_query(self):
        self.assertEqual(self.bot.sanitize_query("  test  query  "), "test query")
        self.assertEqual(self.bot.sanitize_query("test & query"), "test and query")
        self.assertEqual(self.bot.sanitize_query("test:query"), "testquery")
        self.assertEqual(self.bot.sanitize_query("test'query"), "testquery")
        self.assertEqual(self.bot.sanitize_query("test,query"), "testquery")
        self.assertEqual(self.bot.sanitize_query("test.query"), "test query")
        self.assertEqual(self.bot.sanitize_query("test_query"), "test query")
        self.assertEqual(self.bot.sanitize_query("test-query"), "test query")
        self.assertEqual(self.bot.sanitize_query("test(query)"), "test query")
        self.assertEqual(self.bot.sanitize_query("test[query]"), "test query")
        self.assertEqual(self.bot.sanitize_query("test!query"), "test query")

    def test_generate_query_id(self):
        self.assertEqual(len(generate_query_id()), 8)
        self.assertIsInstance(generate_query_id(), str)

    def test_store_and_get_query(self):
        query = "test query"
        query_id = store_query(query)
        self.assertEqual(get_query_by_id(query_id), query)

if __name__ == '__main__':
    unittest.main()
