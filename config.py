"""
Configuration — loads all settings from environment variables.
"""

import os
import sys


class Config:
    # ── Required ──────────────────────────────────────────────────────────────
    BOT_TOKEN: str = os.environ.get("BOT_TOKEN", "")
    OWNER_ID: int = int(os.environ.get("OWNER_ID", "0"))

    # ── Webhook (NEW) ─────────────────────────────────────────────────────────
    # Your Render Web Service URL e.g. https://your-app-name.onrender.com
    WEBHOOK_URL: str = os.environ.get("WEBHOOK_URL", "")
    PORT: int = int(os.environ.get("PORT", "8443"))

    # ── Paths ─────────────────────────────────────────────────────────────────
    DOWNLOAD_DIR: str = os.environ.get("DOWNLOAD_DIR", "/tmp/leech_downloads")

    # ── Limits ────────────────────────────────────────────────────────────────
    MAX_UPLOAD_SIZE: int = 50 * 1024 * 1024         # 50 MB (Telegram limit)
    SPLIT_SIZE: int = 49 * 1024 * 1024              # 49 MB per split part
    MAX_DOWNLOAD_SIZE: int = int(
        os.environ.get("MAX_DOWNLOAD_SIZE", str(400 * 1024 * 1024))
    )

    # ── yt-dlp ────────────────────────────────────────────────────────────────
    YTDLP_MAX_HEIGHT: int = int(os.environ.get("YTDLP_MAX_HEIGHT", "720"))

    # ── Progress ──────────────────────────────────────────────────────────────
    PROGRESS_UPDATE_INTERVAL: int = 5

    # ── Queue ─────────────────────────────────────────────────────────────────
    MAX_QUEUE_SIZE: int = 10

    # ── MEGA ──────────────────────────────────────────────────────────────────
    MEGA_EMAIL: str = os.environ.get("MEGA_EMAIL", "")
    MEGA_PASSWORD: str = os.environ.get("MEGA_PASSWORD", "")

    @classmethod
    def validate(cls):
        errors = []
        if not cls.BOT_TOKEN:
            errors.append("BOT_TOKEN is not set")
        if cls.OWNER_ID == 0:
            errors.append("OWNER_ID is not set")
        if not cls.WEBHOOK_URL:
            errors.append("WEBHOOK_URL is not set (e.g. https://your-app.onrender.com)")
        if errors:
            for e in errors:
                print(f"[CONFIG ERROR] {e}", file=sys.stderr)
            sys.exit(1)

        import os as _os
        _os.makedirs(cls.DOWNLOAD_DIR, exist_ok=True)
