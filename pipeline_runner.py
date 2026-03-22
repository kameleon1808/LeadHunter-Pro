"""
PipelineRunner — orchestrates the full LeadHunter Pro workflow.

Steps:
  1. Scrape  — collect URLs from Google (skipped if URLs already exist)
  2. Enrich  — visit each URL, extract lead data with Claude AI
  3. Export  — generate Excel file automatically when enrichment finishes

Resumable: if a run is interrupted, re-running continues from where it
stopped — the scrape step is skipped if URLs are already present, and
enrichment only processes URLs with status="pending".

Usage:
    runner = PipelineRunner(db, campaign_id)
    await runner.run_full_pipeline(
        search_query="marketing agencies Serbia",
        num_pages=10,
        output_dir="./exports/",
    )
"""

import asyncio
import logging
import sys
from datetime import datetime, timezone

import config
from dashboard import CLIDashboard
from database import DatabaseManager
from export import ExcelExporter
from utils import ErrorHandler, RetryManager

logger = logging.getLogger(__name__)


class PipelineRunner:
    """Runs the complete scrape → enrich → export pipeline for one campaign."""

    def __init__(self, db: DatabaseManager, campaign_id: int) -> None:
        self._db            = db
        self._campaign_id   = campaign_id
        self._error_handler = ErrorHandler()
        self._retry_manager = RetryManager(max_retries=3, base_delay=2.0)
        self._dashboard     = CLIDashboard(db)
        self._start_time    = datetime.now(timezone.utc)

        # Register graceful shutdown — marks campaign as paused before exit
        self._error_handler.register_shutdown_handler(self._on_shutdown)

    # ── Public entry point ───────────────────────────────────────────────

    async def run_full_pipeline(
        self,
        search_query: str,
        num_pages: int,
        output_dir: str = "./exports/",
    ) -> str:
        """
        Execute the full pipeline and return the path to the exported file.

        Resumable: each step checks existing DB state before doing work.
        """
        campaign = self._db.get_campaign(self._campaign_id)
        if campaign is None:
            print(f"Error: campaign id={self._campaign_id} not found.")
            sys.exit(1)

        self._print_header(campaign, search_query, num_pages)

        # ── Step 1: Scrape ──────────────────────────────────────────────
        stats = self._db.get_campaign_stats(self._campaign_id)
        if stats["total_urls"] == 0:
            print("\n[Step 1/3] Scraping URLs from Google…")
            await self._run_scrape(search_query, num_pages)
        else:
            pending = stats["pending_urls"]
            total   = stats["total_urls"]
            print(
                f"\n[Step 1/3] Scrape skipped — "
                f"{total} URLs already collected ({pending} pending)"
            )

        # ── Step 2: Enrich ──────────────────────────────────────────────
        stats = self._db.get_campaign_stats(self._campaign_id)
        if stats["pending_urls"] > 0:
            print(f"\n[Step 2/3] Enriching {stats['pending_urls']} URLs with Claude AI…")
            await self._run_enrich()
        else:
            print("\n[Step 2/3] Enrichment skipped — no pending URLs")

        # ── Step 3: Export ──────────────────────────────────────────────
        print("\n[Step 3/3] Exporting leads to Excel…")
        file_path = self._run_export(output_dir)

        # ── Summary ─────────────────────────────────────────────────────
        self._print_summary(file_path)

        return file_path

    # ── Step implementations ─────────────────────────────────────────────

    async def _run_scrape(self, search_query: str, num_pages: int) -> None:
        """Scrape Google for URLs and persist them to the database."""
        from scrapers import URLScraper

        scraper = URLScraper(
            db_manager=self._db,
            campaign_id=self._campaign_id,
        )

        try:
            await scraper.start_browser()
            urls = await self._retry_manager.exponential_backoff(
                scraper.search_and_collect,
                search_query,
                num_pages,
                url="Google search",
            )
            print(f"    ✓ Collected {len(urls)} unique URLs")
            logger.info("Scraping complete — %d URLs for campaign %d", len(urls), self._campaign_id)
        except Exception as exc:  # noqa: BLE001
            self._error_handler.handle(exc, context="scrape")
            logger.error("Scraping failed: %s", exc)
            raise
        finally:
            await scraper.close_browser()

    async def _run_enrich(self) -> None:
        """Enrich all pending URLs using the configured AI extractor."""
        from enrichment import AIExtractor, ClaudeCodeExtractor, EnrichmentPipeline

        api_key = config.ANTHROPIC_API_KEY
        if api_key:
            extractor = AIExtractor(api_key=api_key)
            label = "Anthropic API"
        else:
            extractor = ClaudeCodeExtractor()
            label = "Claude Code CLI"

        print(f"    AI engine : {label}")

        pipeline = EnrichmentPipeline(
            db_manager=self._db,
            ai_extractor=extractor,
            campaign_id=self._campaign_id,
        )

        try:
            await pipeline.process_campaign(self._campaign_id)
        except Exception as exc:  # noqa: BLE001
            self._error_handler.handle(exc, context="enrich")
            logger.error("Enrichment failed: %s", exc)
            raise

    def _run_export(self, output_dir: str) -> str:
        """Export leads to Excel and return the file path."""
        exporter = ExcelExporter(self._db)
        try:
            file_path = exporter.export_campaign(self._campaign_id, output_dir)
            print(f"    ✓ Exported to: {file_path}")
            return file_path
        except Exception as exc:  # noqa: BLE001
            self._error_handler.handle(exc, context="export")
            logger.error("Export failed: %s", exc)
            raise

    # ── Output helpers ────────────────────────────────────────────────────

    @staticmethod
    def _print_header(campaign, search_query: str, num_pages: int) -> None:
        print("\n" + "═" * 60)
        print("  LeadHunter Pro — Full Pipeline")
        print("═" * 60)
        print(f"  Campaign  : {campaign.name}")
        print(f"  Niche     : {campaign.niche}")
        print(f"  Query     : {search_query}")
        print(f"  Pages     : {num_pages}")
        print("═" * 60)

    def _print_summary(self, file_path: str) -> None:
        stats = self._db.get_campaign_stats(self._campaign_id)
        elapsed = (datetime.now(timezone.utc) - self._start_time).total_seconds()
        minutes = int(elapsed // 60)
        seconds = int(elapsed % 60)

        print("\n" + "═" * 60)
        print("  Pipeline Complete")
        print("═" * 60)
        print(f"  URLs collected : {stats['total_urls']}")
        print(f"  Completed      : {stats['completed_urls']}")
        print(f"  Failed         : {stats['failed_urls']}")
        print(f"  Leads found    : {stats['total_leads']}")
        print(f"  Elapsed        : {minutes}m {seconds}s")
        print(f"  Excel file     : {file_path}")

        if self._error_handler.total_errors:
            print(f"\n  Errors encountered: {self._error_handler.total_errors}")
            for cat, count in self._error_handler.errors_by_category.items():
                print(f"    {cat:<12}: {count}")

        print("═" * 60)

        # Show dashboard stats panel
        print()
        self._dashboard.show_stats(self._campaign_id)

    # ── Shutdown ─────────────────────────────────────────────────────────

    def _on_shutdown(self) -> None:
        """Called on SIGINT / SIGTERM — mark campaign as paused."""
        try:
            self._db.update_campaign_status(self._campaign_id, "paused")
            logger.info("Campaign %d marked as paused", self._campaign_id)
            print(f"Campaign {self._campaign_id} paused. Resume with:")
            print(f"  python main.py run --campaign-id {self._campaign_id} "
                  f"--query '...' --pages 0")
        except Exception as exc:  # noqa: BLE001
            logger.error("Could not mark campaign as paused: %s", exc)
