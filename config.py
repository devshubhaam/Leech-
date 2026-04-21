"""
Configuration — loads all settings from environment variables.
Never hard-code secrets here.
"""

import os
import sys


class Config:
    # ── Required ──────────────────────────────────────────────────────────────
    BOT_TOKEN: str = os.environ.get("BOT_TOKEN", "")
    OWNER_ID: int = int(os.environ.get("OWNER_ID", "0"))

    # ── Paths ─────────────────────────────────────────────────────────────────
    # /tmp is ephemeral but always present on Render free (ramdisk-backed)
    DOWNLOAD_DIR: str = os.environ.get("DOWNLOAD_DIR", "/tmp/leech_downloads")

    # ── Limits ────────────────────────────────────────────────────────────────
    # Telegram Bot API hard limit for sendDocument / sendVideo = 50 MB
    # (With local bot server it can be 2 GB, but we use the public API)
    MAX_UPLOAD_SIZE: int = 50 * 1024 * 1024  # 50 MB

    # Split threshold — files bigger than this get split
    SPLIT_SIZE: int = 49 * 1024 * 1024  # 49 MB per part

    # Max total download size — protect free-tier disk (~512 MB on Render)
    MAX_DOWNLOAD_SIZE: int = int(
        os.environ.get("MAX_DOWNLOAD_SIZE", str(400 * 1024 * 1024))
    )  # 400 MB default

    # ── yt-dlp ────────────────────────────────────────────────────────────────
    # Maximum video quality height (720 keeps files manageable on free tier)
    YTDLP_MAX_HEIGHT: int = int(os.environ.get("YTDLP_MAX_HEIGHT", "720"))

    # ── Progress update throttle ──────────────────────────────────────────────
    PROGRESS_UPDATE_INTERVAL: int = 5  # seconds between progress edits

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
            errors.append("OWNER_ID is not set (must be your numeric Telegram user ID)")
        if errors:
            for e in errors:
                print(f"[CONFIG ERROR] {e}", file=sys.stderr)
            sys.exit(1)

        import os as _os
        _os.makedirs(cls.DOWNLOAD_DIR, exist_ok=True)
