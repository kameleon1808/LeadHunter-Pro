"""
EnrichmentPipeline — drives the full enrichment workflow for a campaign.

Flow:
  1. Load all pending URLs for the campaign.
  2. Split into chunks of CHUNK_SIZE (default 300).
  3. For each chunk, process each URL:
       a. Fetch the site and discover key pages (SiteAnalyzer).
       b. Extract lead data via Claude (AIExtractor).
       c. Persist the lead to the database.
       d. Update the URL status (completed / failed).
  4. Report progress after every URL.
"""

import asyncio
import logging
from typing import List, Optional

import config
from database import DatabaseManager
from database.models import Lead, URL

from .ai_extractor import AIExtractor
from .page_scraper import PageScraper
from .site_analyzer import SiteAnalyzer

logger = logging.getLogger(__name__)


class EnrichmentPipeline:
    """Orchestrates end-to-end enrichment of all URLs in a campaign."""

    def __init__(
        self,
        db_manager: DatabaseManager,
        ai_extractor: AIExtractor,
        campaign_id: int,
    ) -> None:
        self._db = db_manager
        self._extractor = ai_extractor
        self._campaign_id = campaign_id
        self._scraper = PageScraper()
        self._analyzer = SiteAnalyzer(self._scraper, self._extractor)

    # ------------------------------------------------------------------
    # Campaign-level entry point
    # ------------------------------------------------------------------

    async def process_campaign(self, campaign_id: int) -> None:
        """
        Process all pending URLs in *campaign_id*.

        URLs are processed in chunks of ``config.CHUNK_SIZE`` to keep
        memory usage predictable.  Progress is logged after every URL.
        """
        self._db.update_campaign_status(campaign_id, "running")
        logger.info("Enrichment started for campaign id=%d", campaign_id)

        try:
            # Collect all pending URLs in one shot (chunking is logical, not DB)
            all_pending = self._db.get_pending_urls(campaign_id, limit=999_999)
            total = len(all_pending)
            logger.info("Found %d pending URLs to enrich", total)

            # Split into logical chunks of CHUNK_SIZE
            chunk_size = config.CHUNK_SIZE
            chunks: List[List[URL]] = [
                all_pending[i : i + chunk_size]
                for i in range(0, total, chunk_size)
            ]

            for chunk_number, chunk in enumerate(chunks, start=1):
                logger.info(
                    "Processing chunk %d/%d (%d URLs)",
                    chunk_number, len(chunks), len(chunk),
                )
                await self._process_chunk(chunk, campaign_id)

            self._db.update_campaign_status(campaign_id, "completed")
            logger.info("Enrichment completed for campaign id=%d", campaign_id)

        except Exception as exc:  # noqa: BLE001
            logger.error("Enrichment failed for campaign id=%d: %s", campaign_id, exc)
            self._db.update_campaign_status(campaign_id, "failed")
            raise
        finally:
            await self._scraper.close()

    # ------------------------------------------------------------------
    # Chunk-level processing
    # ------------------------------------------------------------------

    async def process_chunk(self, chunk_id: int) -> None:
        """
        Process a *ScrapingChunk* identified by its database ID.

        Retrieves the URL slice referenced by the chunk record and delegates
        to ``_process_chunk``.
        """
        from database.models import ScrapingChunk
        from sqlalchemy.orm import Session

        with Session(self._db.engine) as session:
            chunk_record = session.get(ScrapingChunk, chunk_id)
            if chunk_record is None:
                raise ValueError(f"Chunk id={chunk_id} not found")
            campaign_id = chunk_record.campaign_id
            start = chunk_record.start_index
            end = chunk_record.end_index
            session.expunge(chunk_record)

        self._db.update_chunk_status(chunk_id, "processing")

        urls = self._db.get_pending_urls(campaign_id, limit=999_999)
        chunk_urls = urls[start : end + 1]

        await self._process_chunk(chunk_urls, campaign_id)
        self._db.update_chunk_status(chunk_id, "completed")

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _process_chunk(self, urls: List[URL], campaign_id: int) -> None:
        """Process a list of URL records with controlled concurrency."""
        semaphore = asyncio.Semaphore(config.ENRICHMENT_CONCURRENT_REQUESTS)

        async def _process_with_sem(url_record: URL) -> None:
            async with semaphore:
                await self.process_single_url(url_record)
                self._update_progress(campaign_id)

        await asyncio.gather(*[_process_with_sem(u) for u in urls])

    async def process_single_url(self, url_record: URL) -> Optional[Lead]:
        """
        Enrich a single URL record.

        Returns the saved Lead on success, or None if extraction failed.
        """
        url = url_record.url
        url_id = url_record.id
        campaign_id = url_record.campaign_id

        self._db.update_url_status(url_id, "processing")

        try:
            # Step 1: Fetch home page + key sub-pages, clean content
            pages_content = await self._analyzer.analyse(url)

            if not pages_content:
                self._db.update_url_status(url_id, "failed", "No page content retrieved")
                logger.warning("No content for %s", url)
                return None

            # Step 2: AI extraction
            lead_data = await self._extractor.extract_lead_data(pages_content)

            if not lead_data:
                self._db.update_url_status(url_id, "failed", "AI extraction returned empty result")
                logger.warning("Empty AI extraction for %s", url)
                return None

            # Step 3: Supplement with regex-found contacts
            all_emails = [e for p in pages_content for e in p.get("emails", [])]
            all_phones = [ph for p in pages_content for ph in p.get("phones", [])]

            if not lead_data.get("company_email") and all_emails:
                lead_data["company_email"] = all_emails[0]
            if not lead_data.get("company_phone") and all_phones:
                lead_data["company_phone"] = all_phones[0]

            # Step 4: Always record the source URL
            lead_data["website_url"] = url

            # Step 5: Persist
            lead = self._db.add_lead(
                campaign_id=campaign_id,
                url_id=url_id,
                lead_data=lead_data,
            )
            self._db.update_url_status(url_id, "completed")
            logger.info("Lead saved id=%d for %s (score=%s)", lead.id, url, lead_data.get("quality_score"))
            return lead

        except Exception as exc:  # noqa: BLE001
            error_msg = f"{type(exc).__name__}: {exc}"
            self._db.update_url_status(url_id, "failed", error_msg)
            logger.error("Error processing %s: %s", url, error_msg)
            return None

    def _update_progress(self, campaign_id: int) -> None:
        """Log current campaign progress stats."""
        try:
            stats = self._db.get_campaign_stats(campaign_id)
            processed = stats["completed_urls"] + stats["failed_urls"]
            total = stats["total_urls"]
            leads = stats["total_leads"]
            pct = (processed / total * 100) if total else 0
            logger.info(
                "Progress: %d/%d URLs (%.1f%%) | %d leads found",
                processed, total, pct, leads,
            )
        except Exception as exc:  # noqa: BLE001
            logger.debug("Could not update progress: %s", exc)
