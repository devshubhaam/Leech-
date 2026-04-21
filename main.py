"""
Telegram Leech Bot - Webhook mode for Render Web Service (Free Tier)
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
)

from bot.handlers import (
    start_handler,
    help_handler,
    leech_handler,
    cancel_handler,
    message_handler,
)
from bot.middleware import owner_only_middleware
from bot.queue import leech_queue
from config import Config
from utils.cleanup import cleanup_temp_dir

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger(__name__)
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)
logging.getLogger("telegram").setLevel(logging.WARNING)


def build_application() -> Application:
    app = (
        Application.builder()
        .token(Config.BOT_TOKEN)
        .connect_timeout(30)
        .read_timeout(30)
        .write_timeout(30)
        .pool_timeout(30)
        .build()
    )

    app.add_handler(CommandHandler("start", owner_only_middleware(start_handler)))
    app.add_handler(CommandHandler("help", owner_only_middleware(help_handler)))
    app.add_handler(CommandHandler("leech", owner_only_middleware(leech_handler)))
    app.add_handler(CommandHandler("cancel", owner_only_middleware(cancel_handler)))
    app.add_handler(
        MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            owner_only_middleware(message_handler),
        )
    )
    app.add_handler(
        MessageHandler(
            filters.Document.ALL,
            owner_only_middleware(message_handler),
        )
    )

    return app


async def main():
    Config.validate()
    cleanup_temp_dir()

    app = build_application()
    leech_queue.start()

    webhook_url = Config.WEBHOOK_URL
    port = Config.PORT

    logger.info("Starting in WEBHOOK mode on port %s", port)
    logger.info("Webhook URL: %s", webhook_url)
    logger.info("Owner ID: %s", Config.OWNER_ID)

    await app.bot.set_webhook(
        url=f"{webhook_url}/webhook",
        drop_pending_updates=True,
        allowed_updates=Update.ALL_TYPES,
    )

    async with app:
        await app.start()
        await app.updater.start_webhook(
            listen="0.0.0.0",
            port=port,
            url_path="webhook",
            webhook_url=f"{webhook_url}/webhook",
        )

        logger.info("Bot is running via webhook.")

        stop_event = asyncio.Event()
        loop = asyncio.get_running_loop()
        loop.add_signal_handler(signal.SIGTERM, stop_event.set)
        loop.add_signal_handler(signal.SIGINT, stop_event.set)
        await stop_event.wait()

        logger.info("Stopping...")
        await app.updater.stop()
        await app.stop()

    cleanup_temp_dir()


if __name__ == "__main__":
    asyncio.run(main())
