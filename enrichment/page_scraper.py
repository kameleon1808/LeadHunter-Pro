"""
PageScraper — async HTTP scraper for fetching and analysing company websites.

Uses aiohttp for non-blocking HTTP requests.  Heavy parsing (BeautifulSoup)
is kept purely in-process; no browser is spun up at this stage.
"""

import asyncio
import logging
import re
from typing import List
from urllib.parse import urljoin, urlparse

import aiohttp
from bs4 import BeautifulSoup

import config

logger = logging.getLogger(__name__)

# Href fragments that suggest a page is worth reading for lead extraction
_KEY_PAGE_KEYWORDS = [
    "about",
    "contact",
    "team",
    "people",
    "work",
    "services",
    "portfolio",
    "projects",
    "clients",
    "who-we-are",
    "our-team",
    "our-work",
    "our-services",
]

_EMAIL_RE = re.compile(
    r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}",
)

_PHONE_RE = re.compile(
    r"(?:\+?\d{1,3}[\s\-.]?)?"          # optional country code
    r"(?:\(?\d{2,4}\)?[\s\-.]?)"         # area code
    r"\d{3,4}[\s\-.]?\d{3,4}"            # subscriber number
    r"(?:[\s\-.]?\d{1,4})?",             # optional extension
)

_DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}


class PageScraper:
    """Async scraper that fetches pages and extracts text / contact data."""

    def __init__(self) -> None:
        self._session: aiohttp.ClientSession | None = None

    # ------------------------------------------------------------------
    # Session lifecycle
    # ------------------------------------------------------------------

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            timeout = aiohttp.ClientTimeout(total=config.REQUEST_TIMEOUT_SECONDS)
            self._session = aiohttp.ClientSession(
                headers=_DEFAULT_HEADERS,
                timeout=timeout,
            )
        return self._session

    async def close(self) -> None:
        """Release the underlying aiohttp session."""
        if self._session and not self._session.closed:
            await self._session.close()

    # ------------------------------------------------------------------
    # Core fetch
    # ------------------------------------------------------------------

    async def fetch_page(self, url: str) -> dict:
        """
        Fetch a single URL and return a result dict.

        Returns:
            {
                "url": str,
                "html": str | None,
                "status_code": int | None,
                "error": str | None,
            }
        """
        result = {"url": url, "html": None, "status_code": None, "error": None}
        session = await self._get_session()
        try:
            async with session.get(url, allow_redirects=True, ssl=False) as resp:
                result["status_code"] = resp.status
                if resp.status == 200:
                    result["html"] = await resp.text(errors="replace")
                else:
                    result["error"] = f"HTTP {resp.status}"
        except asyncio.TimeoutError:
            result["error"] = "Request timed out"
            logger.warning("Timeout fetching %s", url)
        except aiohttp.ClientError as exc:
            result["error"] = str(exc)
            logger.warning("Client error fetching %s: %s", url, exc)
        except Exception as exc:  # noqa: BLE001
            result["error"] = str(exc)
            logger.error("Unexpected error fetching %s: %s", url, exc)
        return result

    # ------------------------------------------------------------------
    # Key-page discovery
    # ------------------------------------------------------------------

    async def find_key_pages(self, base_url: str) -> List[str]:
        """
        Fetch *base_url*, parse all internal links, and return up to
        ``config.MAX_PAGES_PER_SITE`` URLs whose href matches key-page keywords.

        Returns a list of fully-qualified URLs (may be empty on failure).
        """
        result = await self.fetch_page(base_url)
        if not result["html"]:
            return []

        base_parsed = urlparse(base_url)
        base_domain = base_parsed.netloc

        soup = BeautifulSoup(result["html"], "html.parser")
        seen: set[str] = set()
        key_pages: List[str] = []

        for tag in soup.find_all("a", href=True):
            href: str = tag["href"].strip()
            full_url = urljoin(base_url, href)
            parsed = urlparse(full_url)

            # Only same-domain links
            if parsed.netloc != base_domain:
                continue
            if full_url in seen:
                continue
            seen.add(full_url)

            path_lower = parsed.path.lower()
            if any(kw in path_lower for kw in _KEY_PAGE_KEYWORDS):
                key_pages.append(full_url)
                if len(key_pages) >= config.MAX_PAGES_PER_SITE:
                    break

        logger.debug("Found %d key pages for %s", len(key_pages), base_url)
        return key_pages

    # ------------------------------------------------------------------
    # Batch operations
    # ------------------------------------------------------------------

    async def scrape_multiple_pages(self, urls: List[str]) -> List[dict]:
        """
        Fetch multiple pages concurrently (up to ENRICHMENT_CONCURRENT_REQUESTS
        at a time) and return a list of result dicts.
        """
        semaphore = asyncio.Semaphore(config.ENRICHMENT_CONCURRENT_REQUESTS)

        async def _fetch(url: str) -> dict:
            async with semaphore:
                return await self.fetch_page(url)

        results = await asyncio.gather(*[_fetch(u) for u in urls], return_exceptions=False)
        return list(results)

    # ------------------------------------------------------------------
    # HTML cleaning & extraction helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _clean_html(html: str) -> str:
        """
        Strip <script>, <style>, and other non-content tags.
        Returns plain text, with excess whitespace collapsed.
        """
        soup = BeautifulSoup(html, "html.parser")
        for tag in soup(["script", "style", "noscript", "svg", "img", "meta", "link"]):
            tag.decompose()
        text = soup.get_text(separator=" ")
        # Collapse whitespace
        text = re.sub(r"[ \t]+", " ", text)
        text = re.sub(r"\n{3,}", "\n\n", text)
        return text.strip()

    @staticmethod
    def _extract_emails(text: str) -> List[str]:
        """Return unique email addresses found in *text*."""
        matches = _EMAIL_RE.findall(text)
        seen: set[str] = set()
        result: List[str] = []
        for m in matches:
            normalised = m.lower()
            if normalised not in seen:
                seen.add(normalised)
                result.append(m)
        return result

    @staticmethod
    def _extract_phones(text: str) -> List[str]:
        """Return unique phone numbers found in *text* (basic extraction)."""
        matches = _PHONE_RE.findall(text)
        seen: set[str] = set()
        result: List[str] = []
        for m in matches:
            stripped = m.strip()
            # Filter out very short matches (noise)
            digits = re.sub(r"\D", "", stripped)
            if len(digits) < 7:
                continue
            if stripped not in seen:
                seen.add(stripped)
                result.append(stripped)
        return result
