"""
Telegram handlers for all commands and messages.
"""

import asyncio
import logging
import os
import re
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

# ─── Helpers ────────────────────────────────────────────────────────────────

URL_RE = re.compile(
    r"(https?://[^\s]+|magnet:\?[^\s]+)",
    re.IGNORECASE,
)


def extract_url(text: str) -> Optional[str]:
    m = URL_RE.search(text)
    return m.group(0) if m else None


async def safe_edit(message: Message, text: str):
    """Edit message, ignore 'not modified' errors."""
    try:
        await message.edit_text(text, parse_mode=ParseMode.HTML)
    except TelegramError as e:
        if "not modified" not in str(e).lower():
            logger.debug("safe_edit error: %s", e)


# ─── Upload helper ───────────────────────────────────────────────────────────


async def upload_file(
    file_path: str,
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    status_msg: Message,
    as_document: bool = True,
):
    """Upload a single file to Telegram with progress tracking."""
    size = os.path.getsize(file_path)
    filename = os.path.basename(file_path)
    chat_id = update.effective_chat.id

    await safe_edit(
        status_msg,
        f"📤 <b>Uploading:</b> <code>{filename}</code>\n"
        f"📦 Size: <b>{human_size(size)}</b>",
    )

    tracker = ProgressTracker(total=size, label="Uploading")

    async def progress_cb(current: int, total: int):
        now = asyncio.get_event_loop().time()
        text = tracker.render(current, now)
        await safe_edit(status_msg, text)

    try:
        with open(file_path, "rb") as f:
            if as_document:
                await context.bot.send_document(
                    chat_id=chat_id,
                    document=f,
                    filename=filename,
                    write_timeout=120,
                    connect_timeout=30,
                    read_timeout=120,
                    pool_timeout=30,
                    progress=progress_cb,
                )
            else:
                # Try as video if mp4/mkv
                ext = Path(file_path).suffix.lower()
                if ext in (".mp4", ".mkv", ".mov", ".webm"):
                    await context.bot.send_video(
                        chat_id=chat_id,
                        video=f,
                        filename=filename,
                        write_timeout=120,
                        connect_timeout=30,
                        read_timeout=120,
                        pool_timeout=30,
                        progress=progress_cb,
                        supports_streaming=True,
                    )
                else:
                    await context.bot.send_document(
                        chat_id=chat_id,
                        document=f,
                        filename=filename,
                        write_timeout=120,
                        connect_timeout=30,
                        read_timeout=120,
                        pool_timeout=30,
                        progress=progress_cb,
                    )
    except TelegramError as e:
        raise RuntimeError(f"Telegram upload failed: {e}") from e


# ─── Core leech coroutine ────────────────────────────────────────────────────


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
        # ── Download ─────────────────────────────────────────────────────────
        tracker = ProgressTracker(total=0, label="Downloading")

        async def dl_progress(current: int, total: int, speed: float = 0):
            if total > 0:
                tracker.total = total
            now = asyncio.get_event_loop().time()
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

        # ── Upload each file ──────────────────────────────────────────────────
        for file_path in downloaded_files:
            if task.cancel_event.is_set():
                await safe_edit(status_msg, "🚫 <b>Cancelled.</b>")
                return

            size = os.path.getsize(file_path)

            if size > Config.MAX_UPLOAD_SIZE:
                # Try splitting
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


# ─── Handlers ────────────────────────────────────────────────────────────────


async def start_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 <b>Leech Bot Online</b>\n\n"
        "Send me any supported link or use /leech &lt;url&gt;\n"
        "Use /help for details.",
        parse_mode=ParseMode.HTML,
    )
    leech_queue.start()  # idempotent — safe to call again


async def help_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "<b>📖 Leech Bot Help</b>\n\n"
        "<b>Commands:</b>\n"
        "• /leech &lt;url&gt; — Download and upload a file\n"
        "• /cancel — Cancel the current task\n"
        "• /help — This message\n\n"
        "<b>Or just send a URL directly.</b>\n\n"
        "<b>Supported links:</b>\n"
        "• Direct file links (.mp4, .mkv, .zip, .rar, .7z, .pdf …)\n"
        "• MEGA links (mega.nz/file or mega.nz/folder)\n"
        "• Magnet links\n"
        "• YouTube / yt-dlp supported sites\n\n"
        "<b>Limits:</b>\n"
        f"• Max upload: 50 MB per file (split if larger)\n"
        f"• Max download: {human_size(Config.MAX_DOWNLOAD_SIZE)}\n"
        f"• Video quality: up to {Config.YTDLP_MAX_HEIGHT}p\n",
        parse_mode=ParseMode.HTML,
    )


async def cancel_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    cancelled = leech_queue.cancel_current()
    if cancelled:
        await update.message.reply_text("🚫 Cancellation requested.")
    else:
        await update.message.reply_text("Nothing is currently running.")


async def leech_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /leech <url>"""
    args = context.args
    if not args:
        await update.message.reply_text(
            "Usage: /leech &lt;url&gt;", parse_mode=ParseMode.HTML
        )
        return
    url = args[0].strip()
    await _enqueue_leech(url, update, context)


async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle raw URL messages or .torrent document uploads."""
    msg = update.message

    # Document upload (.torrent)
    if msg.document:
        doc = msg.document
        if doc.file_name and doc.file_name.endswith(".torrent"):
            await msg.reply_text("⬇️ Torrent files via upload are not yet supported. Send a magnet link instead.")
        else:
            await msg.reply_text("📎 Send a URL to leech a file.")
        return

    text = msg.text or ""
    url = extract_url(text)
    if url:
        await _enqueue_leech(url, update, context)
    else:
        # Not a URL — ignore silently or give a hint
        pass


async def _enqueue_leech(url: str, update: Update, context: ContextTypes.DEFAULT_TYPE):
    if leech_queue.queue_size() >= Config.MAX_QUEUE_SIZE:
        await update.message.reply_text("⚠️ Queue is full. Try again later.")
        return

    qsize = leech_queue.queue_size()
    pos_msg = f" (position in queue: {qsize})" if qsize > 0 else ""
    await update.message.reply_text(
        f"✅ Added to queue{pos_msg}.\n<code>{url[:100]}</code>",
        parse_mode=ParseMode.HTML,
    )

    async def run(task):
        await do_leech(url, update, context, task)

    await leech_queue.enqueue(url, run)
