"""
Dispatcher: auto-detect URL type and route to the correct downloader.
"""

import asyncio
import logging
import re
from typing import Callable, Coroutine, List

logger = logging.getLogger(__name__)

# ─── Regex patterns ──────────────────────────────────────────────────────────

MEGA_RE = re.compile(r"https?://(www\.)?mega\.nz/(file|folder|#)", re.IGNORECASE)
MAGNET_RE = re.compile(r"^magnet:\?", re.IGNORECASE)
DIRECT_EXT_RE = re.compile(
    r"\.(mp4|mkv|avi|mov|webm|flv|m4v|ts|"
    r"zip|rar|7z|tar|gz|bz2|xz|"
    r"pdf|epub|mobi|"
    r"mp3|flac|aac|wav|ogg|"
    r"iso|img|exe|apk|"
    r"jpg|jpeg|png|gif|webp)"
    r"(\?.*)?$",
    re.IGNORECASE,
)

# Sites yt-dlp handles best (non-exhaustive — yt-dlp supports 1000+)
YTDLP_DOMAIN_RE = re.compile(
    r"(youtube\.com|youtu\.be|vimeo\.com|dailymotion\.com|"
    r"twitch\.tv|twitter\.com|x\.com|instagram\.com|"
    r"facebook\.com|fb\.watch|tiktok\.com|reddit\.com|"
    r"streamable\.com|mixcloud\.com|soundcloud\.com|"
    r"bilibili\.com|niconico\.jp|nicovideo\.jp|"
    r"crunchyroll\.com|funimation\.com)",
    re.IGNORECASE,
)


def classify_url(url: str) -> str:
    """Return one of: 'mega', 'magnet', 'direct', 'ytdlp', 'aria2'."""
    if MAGNET_RE.match(url):
        return "magnet"
    if MEGA_RE.search(url):
        return "mega"
    if YTDLP_DOMAIN_RE.search(url):
        return "ytdlp"
    if DIRECT_EXT_RE.search(url):
        return "direct"
    # Unknown — try aria2 first (handles most CDN/direct links), then ytdlp fallback
    return "aria2"


async def detect_and_download(
    url: str,
    dest_dir: str,
    progress_cb: Callable[[int, int, float], Coroutine],
    cancel_event: asyncio.Event,
) -> List[str]:
    """
    Detect URL type and download using the appropriate backend.
    Returns list of local file paths.
    """
    url_type = classify_url(url)
    logger.info("URL classified as: %s — %s", url_type, url[:80])

    if url_type == "mega":
        from downloader.mega_dl import download_mega
        return await download_mega(url, dest_dir, progress_cb, cancel_event)

    elif url_type == "magnet":
        from downloader.torrent_dl import download_torrent
        return await download_torrent(url, dest_dir, progress_cb, cancel_event)

    elif url_type == "ytdlp":
        from downloader.ytdlp_dl import download_ytdlp
        return await download_ytdlp(url, dest_dir, progress_cb, cancel_event)

    elif url_type == "direct":
        from downloader.aria2_dl import download_aria2
        files = await download_aria2(url, dest_dir, progress_cb, cancel_event)
        if not files:
            # Fallback to aiohttp streaming downloader
            from downloader.http_dl import download_http
            files = await download_http(url, dest_dir, progress_cb, cancel_event)
        return files

    else:  # aria2 / unknown
        from downloader.aria2_dl import download_aria2
        files = await download_aria2(url, dest_dir, progress_cb, cancel_event)
        if not files:
            # Fallback to yt-dlp (it handles many more sites than we listed)
            from downloader.ytdlp_dl import download_ytdlp
            files = await download_ytdlp(url, dest_dir, progress_cb, cancel_event)
        return files
