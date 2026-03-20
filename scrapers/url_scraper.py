"""
URL Scraper — Phase 2
Performs Google searches and collects company website URLs via Playwright.
"""

import asyncio
import logging
import random
import urllib.parse
from typing import List, Optional

from playwright.async_api import async_playwright, Browser, BrowserContext, Page

import config
from .scraper_utils import normalize_url, is_valid_url, is_blocked_domain, deduplicate_urls

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# User-agent pool — 10 real desktop user agents
# ---------------------------------------------------------------------------
USER_AGENTS: List[str] = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 13_6) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Safari/605.1.15",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/118.0.0.0 Safari/537.36 Edg/118.0.2088.76",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 OPR/106.0.0.0",
    "Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:120.0) Gecko/20100101 Firefox/120.0",
]

# Realistic viewport sizes
VIEWPORTS = [
    {"width": 1920, "height": 1080},
    {"width": 1440, "height": 900},
    {"width": 1366, "height": 768},
    {"width": 1536, "height": 864},
    {"width": 1280, "height": 800},
]

GOOGLE_SEARCH_URL = "https://www.google.com/search"
CAPTCHA_INDICATORS = [
    "google.com/sorry",
    "recaptcha",
    "captcha",
    "unusual traffic",
    "automated queries",
]


class URLScraper:
    """
    Collects company website URLs from Google search results using Playwright.

    Usage::

        scraper = URLScraper(db_manager=db, campaign_id=1)
        await scraper.start_browser()
        urls = await scraper.search_and_collect("marketing agencies in Serbia", num_pages=10)
        await scraper.close_browser()
    """

    def __init__(self, db_manager, campaign_id: int) -> None:
        self.db = db_manager
        self.campaign_id = campaign_id
        self._playwright = None
        self._browser: Optional[Browser] = None
        self._context: Optional[BrowserContext] = None

    # ------------------------------------------------------------------
    # Browser lifecycle
    # ------------------------------------------------------------------

    async def start_browser(self) -> None:
        """
        Launch browser with human-like settings.

        Two modes:
        - USE_BRAVE=True  (Windows): launches Brave with your real persistent profile.
                          Brave must be fully closed before running.
        - USE_BRAVE=False (default): launches Playwright's own Chromium with a clean profile.
        """
        self._playwright = await async_playwright().start()

        launch_args = [
            "--disable-blink-features=AutomationControlled",
            "--disable-infobars",
            "--no-first-run",
            "--no-default-browser-check",
            "--disable-popup-blocking",
            "--start-maximized",
            "--disable-dev-shm-usage",
            "--no-sandbox",
        ]

        if config.USE_BRAVE:
            logger.info("Starting Brave browser with persistent profile: %s", config.BRAVE_USER_DATA_DIR)
            # launch_persistent_context returns a context directly (no separate browser object)
            self._context = await self._playwright.chromium.launch_persistent_context(
                user_data_dir=config.BRAVE_USER_DATA_DIR,
                executable_path=config.BRAVE_EXECUTABLE_PATH,
                headless=False,  # must be False for persistent context
                args=launch_args,
            )
            await self._context.add_init_script(
                "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
            )
            logger.info("Brave started with persistent profile")
        else:
            logger.info("Starting Playwright Chromium (headless=%s)", config.PLAYWRIGHT_HEADLESS)
            self._browser = await self._playwright.chromium.launch(
                headless=config.PLAYWRIGHT_HEADLESS,
                args=launch_args,
            )
            user_agent = random.choice(USER_AGENTS)
            viewport = random.choice(VIEWPORTS)
            self._context = await self._browser.new_context(
                user_agent=user_agent,
                viewport=viewport,
                java_script_enabled=True,
                locale="en-US",
                timezone_id="America/New_York",
            )
            await self._context.add_init_script(
                "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
            )
            logger.info("Chromium started — UA: %s | viewport: %sx%s",
                        user_agent[:60], viewport["width"], viewport["height"])

    async def close_browser(self) -> None:
        """Close browser and Playwright instance."""
        if self._context:
            await self._context.close()
        if self._browser:
            await self._browser.close()
        if self._playwright:
            await self._playwright.stop()
        logger.info("Browser closed")

    # ------------------------------------------------------------------
    # Main scraping method
    # ------------------------------------------------------------------

    async def search_and_collect(self, query: str, num_pages: int = None) -> List[str]:
        """
        Perform a Google search and collect company URLs across *num_pages* pages.

        Returns the list of new (unique) URLs collected during this run.
        """
        if num_pages is None:
            num_pages = config.SEARCH_PAGES_DEFAULT

        if not self._context:
            raise RuntimeError("Browser not started. Call start_browser() first.")

        logger.info("Starting search: '%s' | pages=%d | campaign=%d",
                    query, num_pages, self.campaign_id)

        all_urls: List[str] = []
        page = await self._context.new_page()

        try:
            for page_num in range(num_pages):
                start_index = page_num * 10
                search_url = (
                    f"{GOOGLE_SEARCH_URL}?q={urllib.parse.quote_plus(query)}"
                    f"&start={start_index}&num=10&hl=en"
                )

                logger.info("Navigating to page %d/%d (start=%d)", page_num + 1, num_pages, start_index)

                try:
                    await page.goto(search_url, wait_until="domcontentloaded", timeout=30000)
                except Exception as exc:
                    logger.warning("Navigation error on page %d: %s", page_num + 1, exc)
                    break

                await self._random_delay()

                # CAPTCHA check
                if await self._is_captcha_page(page):
                    logger.warning("CAPTCHA detected on page %d. Waiting for manual solve…", page_num + 1)
                    print("\n⚠️  CAPTCHA detected! Please solve it in the browser window.")
                    print("   Press ENTER here once you have solved the CAPTCHA and are back on search results.")
                    input()
                    await self._random_delay(2.0, 5.0)

                    if await self._is_captcha_page(page):
                        logger.error("CAPTCHA still present after manual solve attempt. Stopping.")
                        break

                await self._human_like_scroll(page)
                await self._random_delay(0.5, 1.5)

                page_urls = await self._extract_urls_from_page(page)
                logger.info("Page %d: extracted %d URLs", page_num + 1, len(page_urls))

                # Save to database and accumulate
                new_urls = self._filter_new(page_urls, all_urls)
                if new_urls:
                    saved = self.db.add_urls_bulk(self.campaign_id, new_urls)
                    logger.info("Saved %d new URLs to database (campaign %d)", saved, self.campaign_id)
                    all_urls.extend(new_urls)

                # Check for next-page button before sleeping between pages
                has_next = await self._has_next_page(page)
                if not has_next and page_num < num_pages - 1:
                    logger.info("No more result pages available. Stopping early.")
                    break

                if page_num < num_pages - 1:
                    await self._random_delay()

        finally:
            await page.close()

        unique_urls = deduplicate_urls(all_urls)
        logger.info("Search complete. Total unique URLs collected: %d", len(unique_urls))
        return unique_urls

    # ------------------------------------------------------------------
    # URL extraction
    # ------------------------------------------------------------------

    async def _extract_urls_from_page(self, page: Page) -> List[str]:
        """Extract organic result URLs, skipping blocked domains and ads."""
        raw_hrefs: List[str] = await page.evaluate("""() => {
            const anchors = document.querySelectorAll('#search a[href], #rso a[href]');
            const hrefs = [];
            for (const a of anchors) {
                const href = a.href;
                if (href && href.startsWith('http') && !href.includes('google.com/search')) {
                    hrefs.push(href);
                }
            }
            return hrefs;
        }""")

        collected: List[str] = []
        for href in raw_hrefs:
            # Skip Google redirect URLs
            if "/url?q=" in href:
                try:
                    parsed_qs = urllib.parse.parse_qs(urllib.parse.urlparse(href).query)
                    if "q" in parsed_qs:
                        href = parsed_qs["q"][0]
                except Exception:
                    continue

            if not is_valid_url(href):
                continue
            if is_blocked_domain(href):
                continue

            normalized = normalize_url(href)
            if normalized:
                collected.append(normalized)

        return list(dict.fromkeys(collected))  # preserve order, remove exact dupes

    # ------------------------------------------------------------------
    # Human-like behaviour helpers
    # ------------------------------------------------------------------

    async def _human_like_scroll(self, page: Page) -> None:
        """Scroll the page in random increments to mimic human reading."""
        total_height: int = await page.evaluate("document.body.scrollHeight")
        current_pos = 0
        while current_pos < total_height:
            scroll_step = random.randint(200, 500)
            current_pos = min(current_pos + scroll_step, total_height)
            await page.evaluate(f"window.scrollTo(0, {current_pos})")
            await asyncio.sleep(random.uniform(0.1, 0.4))

    async def _random_delay(
        self,
        min_sec: float = None,
        max_sec: float = None,
    ) -> None:
        """Wait a random amount of time to mimic human behaviour."""
        if min_sec is None:
            min_sec = config.MIN_DELAY_SECONDS
        if max_sec is None:
            max_sec = config.MAX_DELAY_SECONDS
        delay = random.uniform(min_sec, max_sec)
        logger.debug("Sleeping %.2f seconds", delay)
        await asyncio.sleep(delay)

    # ------------------------------------------------------------------
    # Utility helpers
    # ------------------------------------------------------------------

    async def _is_captcha_page(self, page: Page) -> bool:
        """Return True if current page shows a CAPTCHA / ratelimit page."""
        current_url = page.url.lower()
        page_text: str = await page.evaluate("document.body.innerText || ''")
        page_text = page_text.lower()
        for indicator in CAPTCHA_INDICATORS:
            if indicator in current_url or indicator in page_text:
                return True
        return False

    async def _has_next_page(self, page: Page) -> bool:
        """Return True if a 'Next' pagination button is present."""
        try:
            next_btn = await page.query_selector("#pnnext, a[aria-label='Next page']")
            return next_btn is not None
        except Exception:
            return False

    @staticmethod
    def _filter_new(candidates: List[str], existing: List[str]) -> List[str]:
        """Return candidates not already in existing (exact match)."""
        existing_set = set(existing)
        return [u for u in candidates if u not in existing_set]
