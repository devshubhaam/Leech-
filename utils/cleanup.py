"""
Cleanup utilities — keep Render free-tier disk usage minimal.
"""

import logging
import os
import shutil

from config import Config

logger = logging.getLogger(__name__)


def delete_file(path: str):
    try:
        if os.path.isfile(path):
            os.remove(path)
            logger.debug("Deleted: %s", path)
    except OSError as e:
        logger.warning("Could not delete %s: %s", path, e)


def cleanup_dir(path: str):
    """Remove a directory and all its contents."""
    try:
        if os.path.isdir(path):
            shutil.rmtree(path, ignore_errors=True)
            logger.debug("Cleaned dir: %s", path)
    except OSError as e:
        logger.warning("Could not clean dir %s: %s", path, e)


def cleanup_temp_dir():
    """Wipe the entire download temp directory (called on startup/shutdown)."""
    d = Config.DOWNLOAD_DIR
    if os.path.isdir(d):
        shutil.rmtree(d, ignore_errors=True)
        logger.info("Wiped temp dir: %s", d)
    os.makedirs(d, exist_ok=True)
