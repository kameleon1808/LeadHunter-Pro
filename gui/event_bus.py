"""
EventBus — thread-safe message queue between background workers and the GUI.

Workers post events via EventBus.post().
The GUI drains the queue via EventBus.drain() from a root.after() callback.
"""

import asyncio
import queue
from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class TaskStartedEvent:
    task_type: str       # "scrape" | "enrich" | "export" | "pipeline"
    campaign_id: int


@dataclass
class TaskProgressEvent:
    campaign_id: int
    message: str
    level: str = "info"  # "info" | "warning" | "error"


@dataclass
class TaskDoneEvent:
    campaign_id: int
    task_type: str
    success: bool
    result: Any = None
    error: str = ""


@dataclass
class CaptchaEvent:
    campaign_id: int
    # Background coroutine awaits this event; GUI sets it when user clicks "Solved"
    asyncio_event: asyncio.Event = field(default_factory=asyncio.Event)


class EventBus:
    """Singleton-style queue — one instance shared across the whole app."""

    def __init__(self):
        self._q: queue.Queue = queue.Queue()

    def post(self, event) -> None:
        """Post an event from any thread."""
        self._q.put_nowait(event)

    def drain(self) -> list:
        """Drain all pending events. Call from the Tkinter main thread."""
        events = []
        while True:
            try:
                events.append(self._q.get_nowait())
            except queue.Empty:
                break
        return events
