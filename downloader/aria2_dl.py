"""
aria2c-based downloader for direct/CDN links.
aria2 handles HTTP/HTTPS/FTP with multi-connection acceleration.
"""

import asyncio
import logging
import os
import re
import shutil
from typing import Callable, Coroutine, List, Optional

from config import Config

logger = logging.getLogger(__name__)

ARIA2C = shutil.which("aria2c") or "aria2c"

# Parse aria2c progress line:  [#abc123 10MiB/100MiB(10%) CN:4 DL:2.5MiB ETA:40s]
PROGRESS_RE = re.compile(
    r"\[#\w+\s+([\d.]+\w+)/([\d.]+\w+)\((\d+)%\)"
    r".*?DL:([\d.]+\w+)"
    r".*?ETA:(\w+)"
    r"\]",
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


async def download_aria2(
    url: str,
    dest_dir: str,
    progress_cb: Callable[[int, int, float], Coroutine],
    cancel_event: asyncio.Event,
) -> List[str]:
    """Download url into dest_dir using aria2c. Returns list of downloaded files."""

    if not shutil.which("aria2c"):
        logger.warning("aria2c not found in PATH — skipping")
        return []

    cmd = [
        ARIA2C,
        "--dir", dest_dir,
        "--max-connection-per-server=4",
        "--split=4",
        "--min-split-size=5M",
        "--file-allocation=none",       # faster on ephemeral storage
        "--max-file-not-found=3",
        "--max-tries=5",
        "--retry-wait=3",
        "--console-log-level=notice",
        "--summary-interval=2",         # progress lines every 2s
        "--human-readable=true",
        f"--max-overall-download-limit={Config.MAX_DOWNLOAD_SIZE}",
        "--allow-overwrite=true",
        "--auto-file-renaming=false",
        url,
    ]

    logger.info("aria2c command: %s", " ".join(cmd[:6]) + " …")

    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
    except FileNotFoundError:
        logger.error("aria2c binary not found")
        return []

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

    # Watch cancel event
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
        logger.error("aria2c failed (rc=%s):\n%s", proc.returncode, "\n".join(output_lines[-20:]))
        return []

    # Collect downloaded files
    files = []
    for fname in os.listdir(dest_dir):
        fpath = os.path.join(dest_dir, fname)
        if os.path.isfile(fpath) and not fname.endswith(".aria2"):
            files.append(fpath)

    return files
