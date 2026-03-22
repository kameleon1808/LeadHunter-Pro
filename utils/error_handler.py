"""
ErrorHandler — global error categorisation, reporting and graceful shutdown.

Usage:
    handler = ErrorHandler()
    handler.register_shutdown_handler(callback=save_state)

    try:
        ...
    except Exception as exc:
        handler.handle(exc, context="scraping", url="https://example.com")

    report = handler.generate_report()
    handler.print_summary()
"""

import json
import logging
import signal
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


class ErrorCategory(Enum):
    NETWORK  = "NETWORK"    # HTTP errors, timeouts, connection failures
    PARSING  = "PARSING"    # HTML / JSON decode errors
    AI_API   = "AI_API"     # Claude CLI / Anthropic API failures
    DATABASE = "DATABASE"   # SQLAlchemy / SQLite errors
    UNKNOWN  = "UNKNOWN"    # Anything else


@dataclass
class ErrorRecord:
    category:  ErrorCategory
    error_type: str
    message:   str
    context:   str
    url:       Optional[str]
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class ErrorHandler:
    """Centralised error handler for the LeadHunter Pro pipeline."""

    def __init__(self) -> None:
        self._errors: List[ErrorRecord] = []
        self._shutdown_callback: Optional[Callable] = None

    # ── Classification ────────────────────────────────────────────────────

    def categorize(self, error: Exception) -> ErrorCategory:
        """Map an exception to an ErrorCategory."""
        name = type(error).__name__
        msg  = str(error).lower()

        # Network
        if isinstance(error, (ConnectionError, TimeoutError, OSError,
                               ConnectionResetError, BrokenPipeError)):
            return ErrorCategory.NETWORK
        if "timeout" in msg or "connection" in msg or "network" in msg:
            return ErrorCategory.NETWORK

        # aiohttp
        try:
            import aiohttp
            if isinstance(error, (aiohttp.ClientError,)):
                return ErrorCategory.NETWORK
        except ImportError:
            pass

        # Parsing
        if isinstance(error, (json.JSONDecodeError, ValueError, UnicodeDecodeError)):
            return ErrorCategory.PARSING
        if "json" in msg or "parse" in msg or "decode" in msg:
            return ErrorCategory.PARSING

        # AI / Claude
        if "claude" in msg or "anthropic" in msg or "subprocess" in name.lower():
            return ErrorCategory.AI_API
        if "filenotfounderror" in name.lower() and "claude" in msg:
            return ErrorCategory.AI_API

        # Database
        try:
            import sqlalchemy.exc as sa_exc
            if isinstance(error, sa_exc.SQLAlchemyError):
                return ErrorCategory.DATABASE
        except ImportError:
            pass
        if "sqlalchemy" in name.lower() or "sqlite" in msg or "database" in msg:
            return ErrorCategory.DATABASE

        return ErrorCategory.UNKNOWN

    # ── Recording ─────────────────────────────────────────────────────────

    def handle(
        self,
        error: Exception,
        context: str = "",
        url: Optional[str] = None,
    ) -> None:
        """Record an error and log it at WARNING level."""
        category = self.categorize(error)
        record   = ErrorRecord(
            category   = category,
            error_type = type(error).__name__,
            message    = str(error)[:500],
            context    = context,
            url        = url,
        )
        self._errors.append(record)
        logger.warning(
            "[%s] %s in '%s'%s: %s",
            category.value,
            type(error).__name__,
            context,
            f" ({url})" if url else "",
            str(error)[:200],
        )

    # ── Reporting ─────────────────────────────────────────────────────────

    def generate_report(self) -> Dict:
        """Return a structured error report dict."""
        by_category: Dict[str, List[dict]] = {}
        for rec in self._errors:
            cat = rec.category.value
            by_category.setdefault(cat, []).append({
                "type":      rec.error_type,
                "message":   rec.message,
                "context":   rec.context,
                "url":       rec.url,
                "timestamp": rec.timestamp,
            })

        return {
            "total_errors": len(self._errors),
            "by_category": {
                cat: {"count": len(errs), "errors": errs}
                for cat, errs in by_category.items()
            },
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }

    def print_summary(self) -> None:
        """Print a concise error summary to stdout."""
        if not self._errors:
            print("No errors recorded.")
            return

        report = self.generate_report()
        print(f"\nError Summary ({report['total_errors']} total):")
        for cat, data in report["by_category"].items():
            print(f"  {cat:<12} {data['count']} error(s)")

    @property
    def total_errors(self) -> int:
        return len(self._errors)

    @property
    def errors_by_category(self) -> Dict[str, int]:
        counts: Dict[str, int] = {}
        for rec in self._errors:
            key = rec.category.value
            counts[key] = counts.get(key, 0) + 1
        return counts

    # ── Graceful shutdown ─────────────────────────────────────────────────

    def register_shutdown_handler(self, callback: Optional[Callable] = None) -> None:
        """
        Register a SIGINT / SIGTERM handler.

        *callback* is called before exit — use it to save state, close
        database connections, etc.
        """
        self._shutdown_callback = callback
        signal.signal(signal.SIGINT,  self._signal_handler)
        try:
            signal.signal(signal.SIGTERM, self._signal_handler)
        except (OSError, ValueError):
            # SIGTERM not available on Windows in some environments
            pass

    def _signal_handler(self, signum: int, frame) -> None:
        logger.info("Shutdown signal %d received — saving state…", signum)
        print("\n\nShutdown requested. Saving state…")
        if self._shutdown_callback:
            try:
                self._shutdown_callback()
            except Exception as exc:  # noqa: BLE001
                logger.error("Shutdown callback failed: %s", exc)
        print("State saved. Exiting.")
        sys.exit(0)
