"""
SiteAnalyzer — orchestrates PageScraper + AIExtractor for a single website.

Provides a high-level ``analyse(base_url)`` coroutine that:
  1. Fetches the home page.
  2. Discovers key sub-pages (about, contact, team, …).
  3. Optionally lets Claude filter the discovered links.
  4. Scrapes all identified pages.
  5. Returns cleaned page content ready for lead extraction.
"""

import logging
from typing import List

from .ai_extractor import AIExtractor
from .page_scraper import PageScraper

logger = logging.getLogger(__name__)


class SiteAnalyzer:
    """
    Combines PageScraper and AIExtractor to analyse a single company website
    and produce a list of cleaned page-content dicts.
    """

    def __init__(self, page_scraper: PageScraper, ai_extractor: AIExtractor) -> None:
        self._scraper = page_scraper
        self._extractor = ai_extractor

    async def analyse(self, base_url: str, use_ai_filter: bool = False) -> List[dict]:
        """
        Analyse *base_url* and return a list of page-content dicts::

            [{"url": str, "text": str, "emails": list, "phones": list}, …]

        *use_ai_filter* — if True, sends discovered links to Claude for a
        second-pass filter (costs extra tokens; useful when regex alone picks
        up noisy links).
        """
        # 1. Find key pages via link-pattern matching
        key_urls = await self._scraper.find_key_pages(base_url)

        # Always include the home page itself
        all_urls = [base_url] + [u for u in key_urls if u != base_url]

        # 2. Optional AI filter on discovered sub-page URLs
        if use_ai_filter and key_urls:
            ai_filtered = await self._extractor.identify_key_pages(key_urls)
            all_urls = [base_url] + ai_filtered

        logger.info("Analysing %d pages for %s", len(all_urls), base_url)

        # 3. Scrape all pages concurrently
        raw_pages = await self._scraper.scrape_multiple_pages(all_urls)

        # 4. Clean and enrich each result
        results: List[dict] = []
        for page in raw_pages:
            if not page.get("html"):
                continue
            clean_text = PageScraper._clean_html(page["html"])
            results.append(
                {
                    "url": page["url"],
                    "text": clean_text,
                    "emails": PageScraper._extract_emails(clean_text),
                    "phones": PageScraper._extract_phones(clean_text),
                }
            )

        return results
