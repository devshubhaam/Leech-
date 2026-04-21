"""
Middleware: block all users except the configured OWNER_ID.
"""

import logging
from functools import wraps

from telegram import Update
from telegram.ext import ContextTypes

from config import Config

logger = logging.getLogger(__name__)


def owner_only_middleware(handler):
    """Decorator that silently ignores requests from non-owner users."""

    @wraps(handler)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
        user = update.effective_user
        if user is None or user.id != Config.OWNER_ID:
            if user:
                logger.warning(
                    "Blocked unauthorized user: %s (id=%s)", user.username, user.id
                )
            return  # Silently ignore
        return await handler(update, context)

    return wrapper
