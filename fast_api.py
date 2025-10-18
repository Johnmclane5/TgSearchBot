import base64
import asyncio
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from app import bot
from config import MY_DOMAIN

api = FastAPI()
api.add_middleware(
    CORSMiddleware,
    allow_origins=[f"{MY_DOMAIN}"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

CHUNK_SIZE = 1024 * 1024
CONCURRENCY_LIMIT = 3
semaphore = asyncio.Semaphore(CONCURRENCY_LIMIT)

@api.get("/")
async def root():
    """Greet users on root route."""
    return JSONResponse({"message": "👋 Hello! Welcome"})

