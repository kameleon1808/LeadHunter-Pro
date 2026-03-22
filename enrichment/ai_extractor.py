"""
AIExtractor — wraps the Anthropic Claude API to:

  1. Identify which scraped links are About / Contact / Team / Work pages.
  2. Extract structured lead data from scraped page content.

All API calls are async (AsyncAnthropic client).
"""

import json
import logging
import re
from typing import List

import config

logger = logging.getLogger(__name__)

# Maximum characters of page text sent to Claude per page to keep prompt size
# manageable (≈ 2 000 tokens ≈ 8 000 chars).
_MAX_CHARS_PER_PAGE = 8_000


class AIExtractor:
    """Async Claude-powered extractor for lead data."""

    def __init__(self, api_key: str) -> None:
        try:
            import anthropic as _anthropic
        except ImportError as exc:
            raise ImportError(
                "Paket 'anthropic' nije instaliran. Instaliraj ga sa: pip install anthropic>=0.20.0\n"
                "Ili koristi ClaudeCodeExtractor koji ne zahtijeva ovaj paket."
            ) from exc
        self._client = _anthropic.AsyncAnthropic(api_key=api_key)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def identify_key_pages(self, all_links: List[str]) -> List[str]:
        """
        Ask Claude to filter *all_links* down to the ones that are most likely
        About / Contact / Team / Work pages.

        Returns a list of URLs (subset of *all_links*).
        """
        if not all_links:
            return []

        links_text = "\n".join(all_links)
        prompt = (
            "You are a URL classifier. Below is a list of URLs from a company website.\n"
            "Identify and return ONLY the URLs that are About, Contact, Team, Work, "
            "Portfolio, or Services pages.\n"
            "Return ONLY a JSON array of URL strings — nothing else.\n\n"
            f"URLs:\n{links_text}"
        )

        try:
            message = await self._client.messages.create(
                model=config.CLAUDE_MODEL,
                max_tokens=1024,
                messages=[{"role": "user", "content": prompt}],
            )
            response_text = message.content[0].text.strip()
            filtered = json.loads(response_text)
            if isinstance(filtered, list):
                # Keep only URLs that were in the original list
                valid = set(all_links)
                return [u for u in filtered if u in valid]
        except (json.JSONDecodeError, IndexError, Exception) as exc:
            logger.warning("identify_key_pages failed: %s", exc)

        return []

    async def extract_lead_data(self, pages_content: List[dict]) -> dict:
        """
        Send scraped page content to Claude and return structured lead data.

        *pages_content* is a list of dicts with keys: url, html (or text).
        Returns a dict with lead fields; returns {} on failure.
        """
        if not pages_content:
            return {}

        prompt = self._build_extraction_prompt(pages_content)

        try:
            message = await self._client.messages.create(
                model=config.CLAUDE_MODEL,
                max_tokens=2048,
                messages=[{"role": "user", "content": prompt}],
            )
            response_text = message.content[0].text.strip()
            return self._parse_claude_response(response_text)
        except Exception as exc:
            logger.error("Claude API error during extraction: %s", exc)
            return {}
        except Exception as exc:  # noqa: BLE001
            logger.error("Unexpected error during extraction: %s", exc)
            return {}

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _build_extraction_prompt(self, pages_content: List[dict]) -> str:
        """Build the extraction prompt from a list of page content dicts."""
        pages_block = ""
        for page in pages_content:
            url = page.get("url", "unknown")
            # Accept either pre-cleaned text or raw html in "text" key
            text = page.get("text") or page.get("html") or ""
            # Truncate to keep prompt manageable
            text = text[:_MAX_CHARS_PER_PAGE]
            pages_block += f"\n--- Page: {url} ---\n{text}\n"

        return (
            "You are a B2B lead extraction specialist. Analyse the following web page "
            "content and extract lead information.\n\n"
            "Return ONLY a valid JSON object with these exact keys (use null for "
            "missing values):\n"
            "{\n"
            '  "company_name": string,\n'
            '  "company_size": string (e.g. "10-50 employees"),\n'
            '  "industry": string,\n'
            '  "description": string (what the company does, max 200 chars),\n'
            '  "contact_name": string (CEO / founder / director name),\n'
            '  "contact_title": string,\n'
            '  "contact_email": string,\n'
            '  "contact_linkedin": string (LinkedIn profile URL),\n'
            '  "company_email": string (general contact email),\n'
            '  "company_phone": string,\n'
            '  "address": string,\n'
            '  "clients_info": string (description of their clients / industries served),\n'
            '  "quality_score": integer between 1 and 10\n'
            "}\n\n"
            "Quality score guide:\n"
            "  10 = decision-maker contact details + company info fully complete\n"
            "   7 = good company info, partial contact details\n"
            "   4 = only basic company info, no contacts\n"
            "   1 = almost no useful data\n\n"
            "Page content:\n"
            f"{pages_block}\n\n"
            "Respond with ONLY the JSON object — no markdown, no explanation."
        )

    @staticmethod
    def _parse_claude_response(response_text: str) -> dict:
        """
        Parse Claude's JSON response into a dict.

        Handles common issues:
          - Markdown code fences (```json ... ```)
          - Leading/trailing whitespace
          - Invalid JSON → returns {}
        """
        # Strip markdown fences if present
        text = re.sub(r"^```(?:json)?\s*", "", response_text, flags=re.MULTILINE)
        text = re.sub(r"```\s*$", "", text, flags=re.MULTILINE).strip()

        try:
            data = json.loads(text)
            if not isinstance(data, dict):
                logger.warning("Claude returned non-dict JSON: %s", type(data))
                return {}

            # Clamp quality_score to 1-10
            score = data.get("quality_score")
            if score is not None:
                try:
                    data["quality_score"] = max(1, min(10, int(score)))
                except (TypeError, ValueError):
                    data["quality_score"] = None

            return data
        except json.JSONDecodeError as exc:
            logger.warning("Failed to parse Claude JSON response: %s", exc)
            return {}
