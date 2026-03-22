"""
RetryManager — exponential backoff with smart error classification.

Usage (async):
    rm = RetryManager(max_retries=3, base_delay=2.0)
    result = await rm.exponential_backoff(my_async_func, arg1, url="https://...")

Usage (sync wrapped):
    result = await rm.exponential_backoff(sync_func, arg1)
"""

import asyncio
import inspect
import logging
from typing import Any, Callable, Optional

logger = logging.getLogger(__name__)

# Exceptions that are worth retrying (transient / recoverable)
_RETRYABLE_BASE = (
    ConnectionError,
    TimeoutError,
    OSError,
    ConnectionResetError,
    BrokenPipeError,
    ConnectionRefusedError,
)

# HTTP status codes worth retrying
_RETRYABLE_HTTP_CODES = {429, 500, 502, 503, 504}


class RetryManager:
    """Provides exponential backoff retry logic for flaky I/O operations."""

    def __init__(self, max_retries: int = 3, base_delay: float = 2.0) -> None:
        self.max_retries = max_retries
        self.base_delay = base_delay

    async def exponential_backoff(
        self,
        func: Callable,
        *args: Any,
        max_retries: Optional[int] = None,
        base_delay: Optional[float] = None,
        url: str = "",
        **kwargs: Any,
    ) -> Any:
        """
        Call *func* with retry on transient errors.

        Delay sequence: base_delay, base_delay*2, base_delay*4, …

        Parameters
        ----------
        func        : async or sync callable
        *args       : positional arguments forwarded to func
        max_retries : override instance default
        base_delay  : override instance default (seconds)
        url         : included in log messages for context
        **kwargs    : keyword arguments forwarded to func
        """
        retries   = max_retries if max_retries is not None else self.max_retries
        delay     = base_delay  if base_delay  is not None else self.base_delay
        is_async  = inspect.iscoroutinefunction(func)
        last_exc: Optional[Exception] = None

        for attempt in range(1, retries + 1):
            try:
                if is_async:
                    return await func(*args, **kwargs)
                return func(*args, **kwargs)

            except Exception as exc:  # noqa: BLE001
                last_exc = exc
                if not self.should_retry(exc) or attempt == retries:
                    raise
                self.log_retry_attempt(url, attempt, exc)
                await asyncio.sleep(delay * (2 ** (attempt - 1)))

        raise last_exc  # type: ignore[misc]

    def should_retry(self, error: Exception) -> bool:
        """
        Return True if *error* is a transient failure worth retrying.

        Retryable:   network errors, timeouts, certain HTTP status codes
        Not retried: JSON errors, authentication, not-found (permanent)
        """
        if isinstance(error, _RETRYABLE_BASE):
            return True

        # aiohttp-specific (optional dependency)
        try:
            import aiohttp
            if isinstance(error, (aiohttp.ClientConnectionError, aiohttp.ServerTimeoutError)):
                return True
            if isinstance(error, aiohttp.ClientResponseError):
                return error.status in _RETRYABLE_HTTP_CODES
        except ImportError:
            pass

        # subprocess / asyncio process errors
        if isinstance(error, (asyncio.TimeoutError, asyncio.CancelledError)):
            return True

        return False

    @staticmethod
    def log_retry_attempt(url: str, attempt: int, error: Exception) -> None:
        """Log a retry attempt with context."""
        location = f" [{url}]" if url else ""
        logger.warning(
            "Retry attempt %d%s — %s: %s",
            attempt,
            location,
            type(error).__name__,
            str(error)[:120],
        )
