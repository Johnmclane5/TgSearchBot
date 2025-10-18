
import base64
import asyncio
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import StreamingResponse, JSONResponse, RedirectResponse
from fastapi.middleware.cors import CORSMiddleware
from starlette.status import HTTP_404_NOT_FOUND

from app import bot
from config import MY_DOMAIN

api = FastAPI()
api.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

CHUNK_SIZE = 1024 * 1024
CONCURRENCY_LIMIT = 3
semaphore = asyncio.Semaphore(CONCURRENCY_LIMIT)


def get_file_properties(message):
    if message.document:
        return message.document.file_name, message.document.file_size
    elif message.video:
        return message.video.file_name or "video.mp4", message.video.file_size
    elif message.audio:
        return message.audio.file_name or "audio.mp3", message.audio.file_size
    else:
        raise HTTPException(status_code=HTTP_404_NOT_FOUND, detail="Unsupported file type")


@api.get("/")
async def root():
    return JSONResponse({"message": "👋 Hello! Welcome"})


async def get_file_stream(channel_id, message_id, request: Request):
    message = await bot.get_messages(chat_id=channel_id, message_ids=message_id)
    if not message:
        raise HTTPException(status_code=HTTP_404_NOT_FOUND, detail="File not found")

    file_name, file_size = get_file_properties(message)
    range_header = request.headers.get("range")
    start, end = 0, file_size - 1

    if range_header:
        range_value = range_header.strip().split("=")[1]
        start_str, end_str = range_value.split("-")[:2]
        start = int(start_str)
        if end_str:
            end = int(end_str)

    chunk_offset = start // CHUNK_SIZE
    byte_offset_in_chunk = start % CHUNK_SIZE

    async def media_streamer():
        async with semaphore:
            stream = bot.stream_media(message, offset=chunk_offset)
            first_chunk = True
            async for chunk in stream:
                if first_chunk:
                    first_chunk = False
                    yield chunk[byte_offset_in_chunk:]
                else:
                    yield chunk

    return media_streamer, start, end, file_size, file_name


@api.get("/stream/{file_link}")
@api.head("/stream/{file_link}")
async def stream_file(file_link: str, request: Request):
    try:
        padding = '=' * (-len(file_link) % 4)
        decoded = base64.urlsafe_b64decode(file_link + padding).decode()
        channel_id, message_id = map(int, decoded.split("_"))
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid file link")

    media_streamer, start, end, file_size, _ = await get_file_stream(channel_id, message_id, request)
    headers = {
        "Content-Type": "video/mp4",
        "Accept-Ranges": "bytes",
        "Content-Length": str(end - start + 1),
        "Content-Range": f"bytes {start}-{end}/{file_size}",
    }
    return StreamingResponse(media_streamer(), status_code=206 if start > 0 else 200, headers=headers)


@api.get("/download/{file_link}")
async def download_file(file_link: str, request: Request):
    try:
        padding = '=' * (-len(file_link) % 4)
        decoded = base64.urlsafe_b64decode(file_link + padding).decode()
        channel_id, message_id = map(int, decoded.split("_"))
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid file link")

    media_streamer, _, _, file_size, file_name = await get_file_stream(channel_id, message_id, request)
    headers = {
        "Content-Disposition": f"attachment; filename=\"{file_name}\"",
        "Content-Type": "application/octet-stream",
        "Content-Length": str(file_size),
    }
    return StreamingResponse(media_streamer(), headers=headers)


@api.get("/play/{player}/{file_link}")
async def play_in_player(player: str, file_link: str):
    stream_url = f"{MY_DOMAIN}/stream/{file_link}"
    if player == "mx":
        redirect_url = f"intent:{stream_url}#Intent;action=android.intent.action.VIEW;type=video/*;package=com.mxtech.videoplayer.ad;end"
    elif player == "mxpro":
        redirect_url = f"intent:{stream_url}#Intent;action=android.intent.action.VIEW;type=video/*;package=com.mxtech.videoplayer.pro;end"
    else:
        raise HTTPException(status_code=404, detail="Player not supported")
    return RedirectResponse(url=redirect_url, status_code=302)
