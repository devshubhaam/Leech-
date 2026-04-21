"""
Pure aiohttp streaming downloader — fallback when aria2 is unavailable
or for URLs that aria2 struggles with (auth headers, redirects, etc.).
"""

import asyncio
import logging
import os
import time
from typing import Callable, Coroutine, List
from urllib.parse import urlparse

import aiohttp

from config import Config

logger = logging.getLogger(__name__)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )
}

CHUNK_SIZE = 512 * 1024  # 512 KB chunks


async def download_http(
    url: str,
    dest_dir: str,
    progress_cb: Callable[[int, int, float], Coroutine],
    cancel_event: asyncio.Event,
) -> List[str]:
    """Stream URL to dest_dir. Returns list of saved file paths."""

    parsed = urlparse(url)
    filename = os.path.basename(parsed.path.rstrip("/")) or "downloaded_file"
    dest_path = os.path.join(dest_dir, filename)

    timeout = aiohttp.ClientTimeout(
        total=None,        # No overall timeout (large files)
        connect=30,
        sock_connect=30,
        sock_read=60,
    )

    try:
        async with aiohttp.ClientSession(headers=HEADERS, timeout=timeout) as session:
            async with session.get(url, allow_redirects=True) as resp:
                if resp.status >= 400:
                    logger.error("HTTP %s for %s", resp.status, url)
                    return []

                total = int(resp.headers.get("Content-Length", 0))

                # Filename from Content-Disposition header if available
                cd = resp.headers.get("Content-Disposition", "")
                if "filename=" in cd:
                    fn = cd.split("filename=")[-1].strip().strip('"').strip("'")
                    if fn:
                        filename = fn
                        dest_path = os.path.join(dest_dir, filename)

                if total > Config.MAX_DOWNLOAD_SIZE:
                    raise RuntimeError(
                        f"File too large: {total / 1e6:.0f} MB "
                        f"(limit {Config.MAX_DOWNLOAD_SIZE / 1e6:.0f} MB)"
                    )

                downloaded = 0
                last_update = 0.0
                speed_start = time.monotonic()

                with open(dest_path, "wb") as f:
                    async for chunk in resp.content.iter_chunked(CHUNK_SIZE):
                        if cancel_event.is_set():
                            raise asyncio.CancelledError()
                        f.write(chunk)
                        downloaded += len(chunk)

                        now = time.monotonic()
                        if now - last_update >= 3:
                            elapsed = now - speed_start or 0.001
                            speed = downloaded / elapsed
                            try:
                                await progress_cb(downloaded, total, speed)
                            except Exception:
                                pass
                            last_update = now

    except asyncio.CancelledError:
        raise
    except aiohttp.ClientError as e:
        logger.error("aiohttp download error: %s", e)
        return []
    except Exception as e:
        logger.exception("Unexpected download error: %s", e)
        return []

    if os.path.exists(dest_path) and os.path.getsize(dest_path) > 0:
        return [dest_path]
    return []
