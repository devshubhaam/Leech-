"""
File utility functions: splitting large files, helpers.
"""

import asyncio
import logging
import os
from typing import List

logger = logging.getLogger(__name__)


def human_size(b: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if b < 1024:
            return f"{b:.1f} {unit}"
        b /= 1024
    return f"{b:.1f} TB"


async def split_file(file_path: str, chunk_size: int) -> List[str]:
    """
    Split file_path into ≤chunk_size byte parts.
    Returns list of part file paths.
    Runs in executor so it doesn't block the event loop.
    """

    def _split():
        parts = []
        idx = 1
        with open(file_path, "rb") as src:
            while True:
                data = src.read(chunk_size)
                if not data:
                    break
                part_path = f"{file_path}.part{idx:03d}"
                with open(part_path, "wb") as dst:
                    dst.write(data)
                parts.append(part_path)
                idx += 1
        return parts

    return await asyncio.get_event_loop().run_in_executor(None, _split)
