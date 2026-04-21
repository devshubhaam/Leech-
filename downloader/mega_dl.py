"""
MEGA downloader.

Strategy (two-tier):
1. Try megapy (Python library) — works for /file links when logged in.
2. Fall back to mega-cmd CLI if installed (handles folders too).

On Render free: mega-cmd is NOT available by default. We use megapy.
Install: pip install megapy  (note: NOT "mega.py" — that package is abandoned)

For anonymous (no-login) downloads of /file links, megapy works without credentials.
For folder links or large files, MEGA_EMAIL + MEGA_PASSWORD env vars are needed.
"""

import asyncio
import logging
import os
import re
from typing import Callable, Coroutine, List

from config import Config

logger = logging.getLogger(__name__)

MEGA_FILE_RE = re.compile(r"mega\.nz/(file|#!)/", re.IGNORECASE)
MEGA_FOLDER_RE = re.compile(r"mega\.nz/(folder|#F)/", re.IGNORECASE)


async def download_mega(
    url: str,
    dest_dir: str,
    progress_cb: Callable[[int, int, float], Coroutine],
    cancel_event: asyncio.Event,
) -> List[str]:
    """Download a MEGA link. Returns list of downloaded file paths."""

    try:
        import mega as megapy  # megapy package
    except ImportError:
        raise RuntimeError(
            "megapy is not installed. Add 'megapy' to requirements.txt"
        )

    is_folder = bool(MEGA_FOLDER_RE.search(url))

    await progress_cb(0, 0, 0)  # Signal start

    def _do_download():
        if Config.MEGA_EMAIL and Config.MEGA_PASSWORD:
            m = megapy.Mega()
            m.login(Config.MEGA_EMAIL, Config.MEGA_PASSWORD)
        else:
            m = megapy.Mega()
            m.login()  # anonymous — works for public /file links

        if is_folder:
            # Download folder — megapy downloads all files
            result = m.download_url(url, dest_dir)
        else:
            result = m.download_url(url, dest_dir)

        return result

    try:
        downloaded = await asyncio.get_event_loop().run_in_executor(None, _do_download)
    except Exception as e:
        logger.exception("MEGA download failed: %s", e)
        raise RuntimeError(f"MEGA download failed: {e}") from e

    # Collect all files in dest_dir
    result = []
    for root, _, fnames in os.walk(dest_dir):
        for fn in fnames:
            fp = os.path.join(root, fn)
            result.append(fp)

    return result
