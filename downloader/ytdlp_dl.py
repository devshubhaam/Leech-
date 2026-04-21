"""
yt-dlp downloader for YouTube, Vimeo, and 1000+ supported sites.
"""

import asyncio
import logging
import os
from typing import Callable, Coroutine, List

import yt_dlp

from config import Config

logger = logging.getLogger(__name__)


class YtDlpProgressHook:
    """Bridges yt-dlp's synchronous progress hook to our async callback."""

    def __init__(self, loop: asyncio.AbstractEventLoop, progress_cb, cancel_event):
        self.loop = loop
        self.progress_cb = progress_cb
        self.cancel_event = cancel_event
        self._last_call = 0.0

    def __call__(self, d: dict):
        if self.cancel_event.is_set():
            raise yt_dlp.utils.DownloadCancelled()

        status = d.get("status")
        if status == "downloading":
            downloaded = d.get("downloaded_bytes", 0)
            total = d.get("total_bytes") or d.get("total_bytes_estimate", 0)
            speed = d.get("speed") or 0

            import time
            now = time.monotonic()
            if now - self._last_call < 3:
                return
            self._last_call = now

            asyncio.run_coroutine_threadsafe(
                self.progress_cb(downloaded, total, speed),
                self.loop,
            )


async def download_ytdlp(
    url: str,
    dest_dir: str,
    progress_cb: Callable[[int, int, float], Coroutine],
    cancel_event: asyncio.Event,
) -> List[str]:
    """Download url with yt-dlp. Returns list of downloaded file paths."""

    loop = asyncio.get_event_loop()
    hook = YtDlpProgressHook(loop, progress_cb, cancel_event)

    # Format: best video+audio up to YTDLP_MAX_HEIGHT, prefer mp4
    height = Config.YTDLP_MAX_HEIGHT
    ydl_opts = {
        "outtmpl": os.path.join(dest_dir, "%(title).60s.%(ext)s"),
        "format": (
            f"bestvideo[height<={height}][ext=mp4]+bestaudio[ext=m4a]"
            f"/bestvideo[height<={height}]+bestaudio"
            f"/best[height<={height}]"
            f"/best"
        ),
        "merge_output_format": "mp4",
        "progress_hooks": [hook],
        "quiet": True,
        "no_warnings": False,
        "noplaylist": True,          # Single video unless playlist URL
        "writethumbnail": False,
        "writesubtitles": False,
        "writeautomaticsub": False,
        "concurrent_fragment_downloads": 4,
        "retries": 5,
        "fragment_retries": 5,
        "http_headers": {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            )
        },
    }

    files_before = set(os.listdir(dest_dir))

    def _download():
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])

    try:
        # Run blocking yt-dlp in thread pool
        await asyncio.get_event_loop().run_in_executor(None, _download)
    except yt_dlp.utils.DownloadCancelled:
        raise asyncio.CancelledError()
    except yt_dlp.utils.DownloadError as e:
        logger.error("yt-dlp download error: %s", e)
        return []
    except Exception as e:
        logger.exception("yt-dlp unexpected error: %s", e)
        return []

    # Collect new files
    files_after = set(os.listdir(dest_dir))
    new_files = files_after - files_before
    result = []
    for fn in new_files:
        fp = os.path.join(dest_dir, fn)
        if os.path.isfile(fp):
            result.append(fp)

    return result
