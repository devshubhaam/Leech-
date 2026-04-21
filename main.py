"""
Telegram Leech Bot - Personal Single-User Bot
Main entry point
"""

import asyncio
import logging
import os
import signal
import sys

from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes,
)

from bot.handlers import (
    start_handler,
    help_handler,
    leech_handler,
    cancel_handler,
    message_handler,
)
from bot.middleware import owner_only_middleware
from config import Config
from utils.cleanup import cleanup_temp_dir

# ─── Logging ────────────────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger(__name__)

# Silence noisy libraries
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)
logging.getLogger("telegram").setLevel(logging.WARNING)


# ─── Application Setup ───────────────────────────────────────────────────────


def build_application() -> Application:
    """Build and configure the Telegram application."""
    app = (
        Application.builder()
        .token(Config.BOT_TOKEN)
        .connect_timeout(30)
        .read_timeout(30)
        .write_timeout(30)
        .pool_timeout(30)
        .build()
    )

    # Register handlers — all guarded by owner-only middleware
    app.add_handler(CommandHandler("start", owner_only_middleware(start_handler)))
    app.add_handler(CommandHandler("help", owner_only_middleware(help_handler)))
    app.add_handler(CommandHandler("leech", owner_only_middleware(leech_handler)))
    app.add_handler(CommandHandler("cancel", owner_only_middleware(cancel_handler)))

    # Catch raw messages (URLs sent without a command)
    app.add_handler(
        MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            owner_only_middleware(message_handler),
        )
    )

    # Document uploads (e.g. .torrent files)
    app.add_handler(
        MessageHandler(
            filters.Document.ALL,
            owner_only_middleware(message_handler),
        )
    )

    return app


# ─── Graceful Shutdown ───────────────────────────────────────────────────────


def shutdown(signum, frame):
    logger.info("Shutdown signal received. Cleaning up …")
    cleanup_temp_dir()
    sys.exit(0)


signal.signal(signal.SIGTERM, shutdown)
signal.signal(signal.SIGINT, shutdown)


# ─── Main ────────────────────────────────────────────────────────────────────


async def main():
    Config.validate()
    cleanup_temp_dir()  # Start fresh

    app = build_application()

    logger.info("Starting Leech Bot (polling mode) …")
    logger.info("Owner ID : %s", Config.OWNER_ID)

    # Drop pending updates on start so old messages are ignored after a restart
    await app.initialize()
    await app.bot.delete_webhook(drop_pending_updates=True)
    await app.start()
    await app.updater.start_polling(
        drop_pending_updates=True,
        allowed_updates=Update.ALL_TYPES,
    )

    logger.info("Bot is running. Press Ctrl-C to stop.")

    # Keep alive
    stop_event = asyncio.Event()
    loop = asyncio.get_running_loop()
    loop.add_signal_handler(signal.SIGTERM, stop_event.set)
    loop.add_signal_handler(signal.SIGINT, stop_event.set)
    await stop_event.wait()

    logger.info("Stopping …")
    await app.updater.stop()
    await app.stop()
    await app.shutdown()
    cleanup_temp_dir()


if __name__ == "__main__":
    asyncio.run(main())
