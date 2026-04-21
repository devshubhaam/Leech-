"""
Torrent / magnet downloader via aria2c.

NOTE on Render free tier:
- Magnet links require DHT peer discovery which may be slow / unreliable on Render.
- Torrents work best with well-seeded content.
- BitTorrent ports may be blocked by Render's network — this is a known limitation.
- We set a generous timeout and warn the user if it fails.
"""

import asyncio
import logging
import os
import re
import shutil
import time
from typing import Callable, Coroutine, List

from config import Config

logger = logging.getLogger(__name__)

ARIA2C = shutil.which("aria2c") or "aria2c"
PROGRESS_RE = re.compile(
    r"\[#\w+\s+([\d.]+\w+)/([\d.]+\w+)\((\d+)%\).*?DL:([\d.]+\w+)",
    re.IGNORECASE,
)

SIZE_RE = re.compile(r"([\d.]+)(GiB|MiB|KiB|B)", re.IGNORECASE)


def parse_size_bytes(s: str) -> int:
    m = SIZE_RE.match(s.strip())
    if not m:
        return 0
    val = float(m.group(1))
    unit = m.group(2).upper()
    mult = {"B": 1, "KIB": 1024, "MIB": 1024**2, "GIB": 1024**3}
    return int(val * mult.get(unit, 1))


async def download_torrent(
    magnet_or_url: str,
    dest_dir: str,
    progress_cb: Callable[[int, int, float], Coroutine],
    cancel_event: asyncio.Event,
) -> List[str]:
    """Download magnet/torrent via aria2c. Returns list of downloaded files."""

    if not shutil.which("aria2c"):
        raise RuntimeError("aria2c not found — cannot download torrents")

    cmd = [
        ARIA2C,
        "--dir", dest_dir,
        "--bt-save-metadata=true",
        "--seed-time=0",           # Don't seed after download (save bandwidth)
        "--max-overall-upload-limit=1K",
        "--bt-max-peers=50",
        "--enable-dht=true",
        "--dht-listen-port=6881",
        "--listen-port=6881",
        "--file-allocation=none",
        "--console-log-level=notice",
        "--summary-interval=5",
        "--bt-stop-timeout=60",    # Give up if no peers in 60s
        magnet_or_url,
    ]

    logger.info("aria2c torrent: %s …", magnet_or_url[:60])

    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
    except FileNotFoundError:
        raise RuntimeError("aria2c binary not found")

    output_lines = []

    async def read_output():
        assert proc.stdout
        async for raw in proc.stdout:
            line = raw.decode(errors="replace").rstrip()
            output_lines.append(line)
            m = PROGRESS_RE.search(line)
            if m:
                current = parse_size_bytes(m.group(1))
                total = parse_size_bytes(m.group(2))
                speed = parse_size_bytes(m.group(4))
                try:
                    await progress_cb(current, total, speed)
                except Exception:
                    pass

    reader = asyncio.create_task(read_output())

    async def cancel_watcher():
        await cancel_event.wait()
        if proc.returncode is None:
            proc.terminate()

    watcher = asyncio.create_task(cancel_watcher())

    await proc.wait()
    await reader
    watcher.cancel()

    if cancel_event.is_set():
        raise asyncio.CancelledError()

    if proc.returncode != 0:
        last_lines = "\n".join(output_lines[-15:])
        raise RuntimeError(f"aria2c torrent failed (rc={proc.returncode}):\n{last_lines}")

    # Collect downloaded files (skip .aria2 metadata)
    files = []
    for root, _, fnames in os.walk(dest_dir):
        for fn in fnames:
            if not fn.endswith(".aria2") and not fn.endswith(".torrent"):
                files.append(os.path.join(root, fn))

    return files
