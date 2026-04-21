"""
Progress bar / status text generator.
"""

import time
from typing import Optional


def human_size(b: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if b < 1024:
            return f"{b:.1f} {unit}"
        b /= 1024
    return f"{b:.1f} TB"


def human_speed(bps: float) -> str:
    return human_size(int(bps)) + "/s"


def eta_str(seconds: float) -> str:
    if seconds <= 0 or seconds > 86400:
        return "∞"
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    if h:
        return f"{h}h {m}m"
    if m:
        return f"{m}m {s}s"
    return f"{s}s"


def progress_bar(pct: float, width: int = 12) -> str:
    filled = int(width * pct / 100)
    bar = "█" * filled + "░" * (width - filled)
    return f"[{bar}]"


class ProgressTracker:
    """Stateful tracker that computes speed from samples."""

    def __init__(self, total: int, label: str = "Progress"):
        self.total = total
        self.label = label
        self._start = time.monotonic()
        self._last_current = 0

    def render(self, current: int, now: float, speed: float = 0) -> str:
        elapsed = (now - self._start) or 0.001
        if speed == 0 and current > 0:
            speed = current / elapsed

        pct = (current / self.total * 100) if self.total > 0 else 0
        bar = progress_bar(pct) if self.total > 0 else "⏳"
        eta = eta_str((self.total - current) / speed) if speed > 0 and self.total > current else "—"

        lines = [
            f"{'⬇️' if 'Down' in self.label else '📤'} <b>{self.label}</b>",
            f"{bar} <b>{pct:.1f}%</b>",
            f"📦 {human_size(current)} / {human_size(self.total) if self.total else '?'}",
            f"⚡ {human_speed(speed)}   ⏱ ETA: {eta}",
        ]
        return "\n".join(lines)
