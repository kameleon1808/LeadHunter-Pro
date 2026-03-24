"""
BackgroundTaskRunner — bridges asyncio coroutines with the Tkinter main thread.

Architecture:
  - A single daemon thread runs a permanent asyncio event loop (loop.run_forever()).
  - Coroutines are submitted via asyncio.run_coroutine_threadsafe().
  - Progress / lifecycle events are posted to EventBus and drained by root.after().
  - Cancellation: call cancel(campaign_id) to cancel a running future.

Also defines:
  GUIURLScraper  — URLScraper subclass that posts CaptchaEvent instead of input().
  GUIPipelineRunner — PipelineRunner subclass without signal handlers / CLIDashboard.
"""

import asyncio
import logging
import threading
from concurrent.futures import Future
from typing import Callable, Coroutine, Dict, Optional

import config
from database import DatabaseManager
from export import ExcelExporter
from scrapers import URLScraper

from .event_bus import (
    CaptchaEvent,
    EventBus,
    TaskDoneEvent,
    TaskProgressEvent,
    TaskStartedEvent,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# GUIURLScraper
# ---------------------------------------------------------------------------

class GUIURLScraper(URLScraper):
    """
    URLScraper variant for GUI mode.
    Replaces the blocking input() CAPTCHA wait with an asyncio.Event posted
    to the EventBus so the GUI can show a modal dialog.
    """

    def __init__(self, db_manager, campaign_id: int, event_bus: EventBus) -> None:
        super().__init__(
            db_manager=db_manager,
            campaign_id=campaign_id,
            captcha_callback=self._gui_captcha_wait,
        )
        self._event_bus = event_bus

    async def _gui_captcha_wait(self, campaign_id: int) -> None:
        solve_event = asyncio.Event()
        captcha_ev = CaptchaEvent(campaign_id=campaign_id, asyncio_event=solve_event)
        self._event_bus.post(captcha_ev)
        logger.info("CAPTCHA detected — waiting for GUI user to solve (campaign %d)", campaign_id)
        await solve_event.wait()
        logger.info("CAPTCHA solved signal received (campaign %d)", campaign_id)


# ---------------------------------------------------------------------------
# GUIPipelineRunner
# ---------------------------------------------------------------------------

class GUIPipelineRunner:
    """
    Streamlined pipeline runner for GUI mode.
    Removes CLIDashboard and signal handler registration.
    Posts TaskProgressEvents to the EventBus at each step.
    """

    def __init__(
        self,
        db: DatabaseManager,
        campaign_id: int,
        event_bus: EventBus,
    ) -> None:
        self._db = db
        self._campaign_id = campaign_id
        self._event_bus = event_bus

    def _post(self, msg: str, level: str = "info") -> None:
        self._event_bus.post(
            TaskProgressEvent(campaign_id=self._campaign_id, message=msg, level=level)
        )

    async def run_full_pipeline(
        self,
        search_query: str,
        num_pages: int,
        output_dir: str = "./exports/",
    ) -> str:
        from enrichment import AIExtractor, ClaudeCodeExtractor, EnrichmentPipeline
        from utils import RetryManager

        retry = RetryManager(max_retries=3, base_delay=2.0)

        # ── Step 1: Scrape ──────────────────────────────────────────────
        stats = self._db.get_campaign_stats(self._campaign_id)
        if stats["total_urls"] == 0:
            self._post("Step 1/3 — Scraping URLs from Google…")
            scraper = GUIURLScraper(
                db_manager=self._db,
                campaign_id=self._campaign_id,
                event_bus=self._event_bus,
            )
            try:
                await scraper.start_browser()
                urls = await retry.exponential_backoff(
                    scraper.search_and_collect,
                    search_query,
                    num_pages,
                    url="Google search",
                )
                self._post(f"Step 1/3 — Collected {len(urls)} URLs")
            finally:
                await scraper.close_browser()
        else:
            pending = stats["pending_urls"]
            self._post(
                f"Step 1/3 — Skipped scrape ({stats['total_urls']} URLs exist, {pending} pending)"
            )

        # ── Step 2: Enrich ──────────────────────────────────────────────
        stats = self._db.get_campaign_stats(self._campaign_id)
        if stats["pending_urls"] > 0:
            self._post(f"Step 2/3 — Enriching {stats['pending_urls']} URLs with Claude AI…")
            api_key = config.ANTHROPIC_API_KEY
            extractor = AIExtractor(api_key=api_key) if api_key else ClaudeCodeExtractor()
            pipeline = EnrichmentPipeline(
                db_manager=self._db,
                ai_extractor=extractor,
                campaign_id=self._campaign_id,
            )
            await pipeline.process_campaign(self._campaign_id)
            self._post("Step 2/3 — Enrichment complete")
        else:
            self._post("Step 2/3 — Skipped enrichment (no pending URLs)")

        # ── Step 3: Export ──────────────────────────────────────────────
        self._post("Step 3/3 — Exporting leads to Excel…")
        exporter = ExcelExporter(self._db)
        file_path = exporter.export_campaign(self._campaign_id, output_dir)
        self._post(f"Step 3/3 — Exported: {file_path}")

        return file_path

    async def run_scrape_only(self, search_query: str, num_pages: int) -> int:
        from utils import RetryManager
        retry = RetryManager(max_retries=3, base_delay=2.0)
        self._post(f"Scraping: '{search_query}' ({num_pages} pages)…")
        scraper = GUIURLScraper(
            db_manager=self._db,
            campaign_id=self._campaign_id,
            event_bus=self._event_bus,
        )
        try:
            await scraper.start_browser()
            urls = await retry.exponential_backoff(
                scraper.search_and_collect,
                search_query,
                num_pages,
                url="Google search",
            )
            self._post(f"Scrape complete — {len(urls)} new URLs")
            return len(urls)
        finally:
            await scraper.close_browser()

    async def run_enrich_only(self) -> None:
        from enrichment import AIExtractor, ClaudeCodeExtractor, EnrichmentPipeline
        stats = self._db.get_campaign_stats(self._campaign_id)
        if stats["pending_urls"] == 0:
            self._post("No pending URLs to enrich", level="warning")
            return
        self._post(f"Enriching {stats['pending_urls']} URLs…")
        api_key = config.ANTHROPIC_API_KEY
        extractor = AIExtractor(api_key=api_key) if api_key else ClaudeCodeExtractor()
        pipeline = EnrichmentPipeline(
            db_manager=self._db,
            ai_extractor=extractor,
            campaign_id=self._campaign_id,
        )
        await pipeline.process_campaign(self._campaign_id)
        self._post("Enrichment complete")


# ---------------------------------------------------------------------------
# BackgroundTaskRunner
# ---------------------------------------------------------------------------

class BackgroundTaskRunner:
    """
    Owns a permanent asyncio event loop running in a daemon thread.
    Submit coroutines from the main thread; get results via EventBus.
    """

    def __init__(self, event_bus: EventBus) -> None:
        self._event_bus = event_bus
        self._loop = asyncio.new_event_loop()
        self._thread = threading.Thread(
            target=self._run_loop, daemon=True, name="AsyncWorker"
        )
        self._futures: Dict[int, Future] = {}  # campaign_id -> Future
        self._thread.start()
        logger.info("BackgroundTaskRunner started (asyncio loop in daemon thread)")

    def _run_loop(self) -> None:
        asyncio.set_event_loop(self._loop)
        self._loop.run_forever()

    def submit(
        self,
        campaign_id: int,
        task_type: str,
        coro: Coroutine,
        on_done: Optional[Callable] = None,
    ) -> None:
        """
        Schedule a coroutine on the background loop.
        Posts TaskStartedEvent immediately, TaskDoneEvent when complete.
        on_done(success, result, error) is called from the main thread via event_bus drain.
        """
        self._event_bus.post(TaskStartedEvent(task_type=task_type, campaign_id=campaign_id))

        async def _wrapper():
            try:
                result = await coro
                self._event_bus.post(
                    TaskDoneEvent(
                        campaign_id=campaign_id,
                        task_type=task_type,
                        success=True,
                        result=result,
                    )
                )
                if on_done:
                    on_done(True, result, "")
            except asyncio.CancelledError:
                self._event_bus.post(
                    TaskDoneEvent(
                        campaign_id=campaign_id,
                        task_type=task_type,
                        success=False,
                        error="Cancelled by user",
                    )
                )
                if on_done:
                    on_done(False, None, "Cancelled by user")
            except Exception as exc:
                logger.exception("Background task '%s' failed: %s", task_type, exc)
                self._event_bus.post(
                    TaskDoneEvent(
                        campaign_id=campaign_id,
                        task_type=task_type,
                        success=False,
                        error=str(exc),
                    )
                )
                if on_done:
                    on_done(False, None, str(exc))

        future = asyncio.run_coroutine_threadsafe(_wrapper(), self._loop)
        self._futures[campaign_id] = future

    def submit_sync(
        self,
        campaign_id: int,
        task_type: str,
        fn: Callable,
        on_done: Optional[Callable] = None,
    ) -> None:
        """Submit a synchronous (blocking) function in a thread pool via asyncio."""
        async def _wrap():
            loop = asyncio.get_event_loop()
            return await loop.run_in_executor(None, fn)

        self.submit(campaign_id, task_type, _wrap(), on_done)

    def cancel(self, campaign_id: int) -> None:
        """Cancel the running task for this campaign."""
        future = self._futures.get(campaign_id)
        if future and not future.done():
            future.cancel()
            logger.info("Cancelled task for campaign %d", campaign_id)

    def is_running(self, campaign_id: int) -> bool:
        future = self._futures.get(campaign_id)
        return future is not None and not future.done()
