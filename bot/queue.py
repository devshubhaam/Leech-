"""
Simple async task queue — sequential processing so Render free tier
doesn't OOM from parallel downloads.
"""

import asyncio
import logging
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Callable, Coroutine, Dict, Optional

logger = logging.getLogger(__name__)


class TaskStatus(Enum):
    QUEUED = "queued"
    RUNNING = "running"
    DONE = "done"
    CANCELLED = "cancelled"
    FAILED = "failed"


@dataclass
class Task:
    task_id: str
    url: str
    status: TaskStatus = TaskStatus.QUEUED
    cancel_event: asyncio.Event = field(default_factory=asyncio.Event)
    asyncio_task: Optional[asyncio.Task] = None


class LeechQueue:
    """Single-owner sequential task queue."""

    def __init__(self, max_size: int = 10):
        self._queue: asyncio.Queue = asyncio.Queue(maxsize=max_size)
        self._tasks: Dict[str, Task] = {}
        self._worker_task: Optional[asyncio.Task] = None

    def start(self):
        self._worker_task = asyncio.create_task(self._worker())

    async def _worker(self):
        while True:
            task, coro_fn = await self._queue.get()
            task.status = TaskStatus.RUNNING
            logger.info("Queue: starting task %s — %s", task.task_id, task.url)
            try:
                await coro_fn(task)
                task.status = TaskStatus.DONE
            except asyncio.CancelledError:
                task.status = TaskStatus.CANCELLED
                logger.info("Task %s cancelled", task.task_id)
            except Exception as exc:
                task.status = TaskStatus.FAILED
                logger.exception("Task %s failed: %s", task.task_id, exc)
            finally:
                self._queue.task_done()

    async def enqueue(
        self,
        url: str,
        coro_fn: Callable[[Task], Coroutine],
    ) -> Task:
        task_id = str(uuid.uuid4())[:8]
        task = Task(task_id=task_id, url=url)
        self._tasks[task_id] = task
        await self._queue.put((task, coro_fn))
        return task

    def cancel_current(self) -> bool:
        """Cancel the currently running task if any."""
        for task in self._tasks.values():
            if task.status == TaskStatus.RUNNING:
                task.cancel_event.set()
                if task.asyncio_task and not task.asyncio_task.done():
                    task.asyncio_task.cancel()
                return True
        return False

    def queue_size(self) -> int:
        return self._queue.qsize()

    def running_task(self) -> Optional[Task]:
        for t in self._tasks.values():
            if t.status == TaskStatus.RUNNING:
                return t
        return None


# Global queue instance
leech_queue = LeechQueue()
