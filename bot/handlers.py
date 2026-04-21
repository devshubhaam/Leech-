"""
Telegram handlers for all commands and messages.
"""

import asyncio
import logging
import os
import re
import time
from pathlib import Path
from typing import Optional

from telegram import Update, Message
from telegram.constants import ParseMode
from telegram.error import TelegramError
from telegram.ext import ContextTypes

from bot.queue import leech_queue, TaskStatus
from config import Config
from downloader.dispatcher import detect_and_download
from utils.cleanup import delete_file, cleanup_dir
from utils.filetools import split_file, human_size
from utils.progress import ProgressTracker

logger = logging.getLogger(__name__)

URL_RE = re.compile(r"(https?://[^\s]+|magnet:\?[^\s]+)", re.IGNORECASE)


def extract_url(text: str) -> Optional[str]:
    m = URL_RE.search(text)
    return m.group(0) if m else None


async def safe_edit(message: Message, text: str):
    try:
        await message.edit_text(text, parse_mode=ParseMode.HTML)
    except TelegramError as e:
        if "not modified" not in str(e).lower():
            logger.debug("safe_edit error: %s", e)


async def upload_file(
    file_path: str,
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    status_msg: Message,
    as_document: bool = True,
):
    """Upload file to Telegram — manual progress polling (no progress callback)."""
    size = os.path.getsize(file_path)
    filename = os.path.basename(file_path)
    chat_id = update.effective_chat.id

    await safe_edit(
        status_msg,
        f"📤 <b>Uploading:</b> <code>{filename}</code>\n"
        f"📦 Size: <b>{human_size(size)}</b>\n"
        f"⏳ Please wait…",
    )

    ext = Path(file_path).suffix.lower()

    try:
        with open(file_path, "rb") as f:
            if not as_document and ext in (".mp4", ".mkv", ".mov", ".webm"):
                await context.bot.send_video(
                    chat_id=chat_id,
                    video=f,
                    filename=filename,
                    write_timeout=300,
                    connect_timeout=60,
                    read_timeout=300,
                    supports_streaming=True,
                )
            else:
                await context.bot.send_document(
                    chat_id=chat_id,
                    document=f,
                    filename=filename,
                    write_timeout=300,
                    connect_timeout=60,
                    read_timeout=300,
                )
    except TelegramError as e:
        raise RuntimeError(f"Telegram upload failed: {e}") from e


async def do_leech(
    url: str,
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    task,
    as_document: bool = True,
):
    chat_id = update.effective_chat.id
    status_msg = await context.bot.send_message(
        chat_id=chat_id,
        text=f"🔍 <b>Detecting link type…</b>\n<code>{url[:80]}</code>",
        parse_mode=ParseMode.HTML,
    )

    download_dir = os.path.join(Config.DOWNLOAD_DIR, task.task_id)
    os.makedirs(download_dir, exist_ok=True)

    downloaded_files = []

    try:
        tracker = ProgressTracker(total=0, label="Downloading")
        last_edit = 0.0

        async def dl_progress(current: int, total: int, speed: float = 0):
            nonlocal last_edit
            now = time.monotonic()
            if now - last_edit < 4:
                return
            last_edit = now
            if total > 0:
                tracker.total = total
            text = tracker.render(current, now, speed=speed)
            await safe_edit(status_msg, text)

        downloaded_files = await detect_and_download(
            url=url,
            dest_dir=download_dir,
            progress_cb=dl_progress,
            cancel_event=task.cancel_event,
        )

        if not downloaded_files:
            await safe_edit(status_msg, "❌ <b>Download failed</b> — no files received.")
            return

        for file_path in downloaded_files:
            if task.cancel_event.is_set():
                await safe_edit(status_msg, "🚫 <b>Cancelled.</b>")
                return

            size = os.path.getsize(file_path)

            if size > Config.MAX_UPLOAD_SIZE:
                await safe_edit(
                    status_msg,
                    f"✂️ File is <b>{human_size(size)}</b> — splitting into ≤49 MB parts…",
                )
                parts = await split_file(file_path, Config.SPLIT_SIZE)
                for part in parts:
                    await upload_file(part, update, context, status_msg, as_document)
                    delete_file(part)
            else:
                await upload_file(file_path, update, context, status_msg, as_document)

            delete_file(file_path)

        await safe_edit(status_msg, "✅ <b>Leech complete!</b>")

    except asyncio.CancelledError:
        await safe_edit(status_msg, "🚫 <b>Task cancelled.</b>")
    except Exception as exc:
        logger.exception("do_leech error for %s", url)
        await safe_edit(
            status_msg,
            f"❌ <b>Error:</b> <code>{str(exc)[:300]}</code>",
        )
    finally:
        cleanup_dir(download_dir)


async def start_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    leech_queue.start()
    await update.message.reply_text(
        "👋 <b>Leech Bot Online</b>\n\n"
        "Send me any supported link or use /leech &lt;url&gt;\n"
        "Use /help for details.",
        parse_mode=ParseMode.HTML,
    )


async def help_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "<b>📖 Leech Bot Help</b>\n\n"
        "<b>Commands:</b>\n"
        "• /leech &lt;url&gt; — Download and upload\n"
        "• /cancel — Cancel current task\n"
        "• /help — This message\n\n"
        "<b>Supported links:</b>\n"
        "• Direct file links (.mp4, .mkv, .zip, .rar …)\n"
        "• MEGA links (mega.nz/file)\n"
        "• Magnet links\n"
        "• YouTube / yt-dlp supported sites\n\n"
        f"• Max upload: 50 MB per file (auto-split)\n"
        f"• Max download: {human_size(Config.MAX_DOWNLOAD_SIZE)}\n",
        parse_mode=ParseMode.HTML,
    )


async def cancel_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    cancelled = leech_queue.cancel_current()
    if cancelled:
        await update.message.reply_text("🚫 Cancellation requested.")
    else:
        await update.message.reply_text("Nothing is currently running.")


async def leech_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = context.args
    if not args:
        await update.message.reply_text(
            "Usage: /leech &lt;url&gt;", parse_mode=ParseMode.HTML
        )
        return
    url = args[0].strip()
    await _enqueue_leech(url, update, context)


async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    if msg.document:
        await msg.reply_text("Send a URL to leech a file.")
        return
    text = msg.text or ""
    url = extract_url(text)
    if url:
        await _enqueue_leech(url, update, context)


async def _enqueue_leech(url: str, update: Update, context: ContextTypes.DEFAULT_TYPE):
    if leech_queue.queue_size() >= Config.MAX_QUEUE_SIZE:
        await update.message.reply_text("⚠️ Queue is full. Try again later.")
        return

    qsize = leech_queue.queue_size()
    pos_msg = f" (position: {qsize})" if qsize > 0 else ""
    await update.message.reply_text(
        f"✅ Added to queue{pos_msg}.\n<code>{url[:100]}</code>",
        parse_mode=ParseMode.HTML,
    )

    async def run(task):
        await do_leech(url, update, context, task)

    await leech_queue.enqueue(url, run)
