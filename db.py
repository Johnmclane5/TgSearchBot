from pymongo import MongoClient
from config import MONGO_URI


# MongoDB setup
mongo = MongoClient(MONGO_URI)
db = mongo["sharing_bot"]
tokens_col = db["tokens"]
auth_users_col = db["auth_users"]
users_col = db["s_users"]
