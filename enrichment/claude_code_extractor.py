"""
ClaudeCodeExtractor — koristi Claude Code CLI (`claude -p`) kao AI engine.

Isti interfejs kao AIExtractor, ali umjesto Anthropic Python paketa i API ključa,
poziva lokalno instalirani `claude` CLI kao asyncio subprocess.

Prednosti:
  - Ne zahtijeva ANTHROPIC_API_KEY ni zasebno plaćanje
  - Koristi Claude koji je već uključen u Claude Pro / Max plan
  - `--json-schema` flag garantuje validni JSON izlaz bez dodatnog parsiranja

Napomena o performansama:
  Svaki `claude -p` subprocess ima ~10-12s overhead inicijalizacije.
  Konkurentnost je ograničena na CLAUDE_CODE_MAX_CONCURRENT (default 3).
"""

import asyncio
import json
import logging
from typing import List

import config

logger = logging.getLogger(__name__)

# Timeout za jedan claude subprocess poziv (sekunde)
_SUBPROCESS_TIMEOUT = 120

# JSON schema za lead ekstrakciju — Claude mora vratiti ovaj format
_LEAD_SCHEMA = {
    "type": "object",
    "properties": {
        "company_name":     {"type": ["string", "null"]},
        "company_size":     {"type": ["string", "null"]},
        "industry":         {"type": ["string", "null"]},
        "description":      {"type": ["string", "null"]},
        "contact_name":     {"type": ["string", "null"]},
        "contact_title":    {"type": ["string", "null"]},
        "contact_email":    {"type": ["string", "null"]},
        "contact_linkedin": {"type": ["string", "null"]},
        "company_email":    {"type": ["string", "null"]},
        "company_phone":    {"type": ["string", "null"]},
        "address":          {"type": ["string", "null"]},
        "clients_info":     {"type": ["string", "null"]},
        "quality_score":    {"type": "integer", "minimum": 1, "maximum": 10},
    },
    "required": ["quality_score"],
}

# JSON schema za filtriranje linkova
_LINKS_SCHEMA = {
    "type": "object",
    "properties": {
        "urls": {
            "type": "array",
            "items": {"type": "string"},
        }
    },
    "required": ["urls"],
}

# Instrukcija za identifikaciju ključnih stranica
_IDENTIFY_PAGES_INSTRUCTION = (
    "You are a URL classifier. The text piped to stdin contains a list of URLs "
    "from a company website, one per line. "
    "Identify ONLY the URLs that are About, Contact, Team, Work, Portfolio, or Services pages. "
    "Return them in the 'urls' array. Return an empty array if none match."
)

# Instrukcija za ekstrakciju lead podataka
_EXTRACT_LEAD_INSTRUCTION = (
    "You are a B2B lead extraction specialist. The text piped to stdin contains "
    "scraped web page content from a company website. "
    "Extract all available lead information and return it in the required JSON format. "
    "Quality score guide: "
    "10=decision-maker contact + full company profile, "
    "7=good company info + partial contacts, "
    "4=basic company info only, "
    "1=almost no useful data. "
    "Use null for any field you cannot find. "
    "Keep description under 200 characters."
)


class ClaudeCodeExtractor:
    """
    Async lead extractor koji koristi `claude -p` CLI subprocess.

    Isti javni interfejs kao AIExtractor — mogu se koristiti naizmjenično.
    """

    def __init__(self) -> None:
        self._semaphore = asyncio.Semaphore(config.CLAUDE_CODE_MAX_CONCURRENT)

    # ------------------------------------------------------------------
    # Javni API (isti interfejs kao AIExtractor)
    # ------------------------------------------------------------------

    async def identify_key_pages(self, all_links: List[str]) -> List[str]:
        """
        Filtriraj *all_links* na About/Contact/Team/Work stranice koristeći Claude.

        Vraća podskup input liste. Vraća [] ako poziv ne uspije.
        """
        if not all_links:
            return []

        content = "\n".join(all_links)
        result = await self._call_claude(
            instruction=_IDENTIFY_PAGES_INSTRUCTION,
            content=content,
            schema=_LINKS_SCHEMA,
        )

        urls = result.get("urls", [])
        if not isinstance(urls, list):
            return []

        # Vrati samo URL-ove koji su bili u originalnoj listi
        valid = set(all_links)
        return [u for u in urls if u in valid]

    async def extract_lead_data(self, pages_content: List[dict]) -> dict:
        """
        Ekstrahuj strukturirane lead podatke iz scraped sadržaja stranica.

        *pages_content* je lista dict-ova s ključevima: url, text.
        Vraća dict s lead poljima ili {} ako ekstrakcija ne uspije.
        """
        if not pages_content:
            return {}

        # Spoji sadržaj svih stranica u jedan blob
        content_parts = []
        for page in pages_content:
            url = page.get("url", "unknown")
            text = (page.get("text") or page.get("html") or "")[:8_000]
            content_parts.append(f"--- Page: {url} ---\n{text}")
        content = "\n\n".join(content_parts)

        result = await self._call_claude(
            instruction=_EXTRACT_LEAD_INSTRUCTION,
            content=content,
            schema=_LEAD_SCHEMA,
        )

        # Osiguraj da quality_score bude u rasponu 1-10
        score = result.get("quality_score")
        if score is not None:
            try:
                result["quality_score"] = max(1, min(10, int(score)))
            except (TypeError, ValueError):
                result["quality_score"] = 1

        return result

    # ------------------------------------------------------------------
    # Interni helper
    # ------------------------------------------------------------------

    async def _call_claude(
        self,
        instruction: str,
        content: str,
        schema: dict,
    ) -> dict:
        """
        Pozovi `claude -p` kao asyncio subprocess.

        - *instruction* se proslijeđuje kao argument `-p` (šta da uradi)
        - *content* se šalje putem stdin (sadržaj koji analizira)
        - *schema* se proslijeđuje kao `--json-schema` (format odgovora)

        Vraća `structured_output` dict iz Claude odgovora, ili {} pri grešci.
        """
        async with self._semaphore:
            cmd = [
                "claude",
                "-p", instruction,
                "--output-format", "json",
                "--json-schema", json.dumps(schema),
                "--no-session-persistence",
                "--model", config.CLAUDE_MODEL,
            ]

            try:
                proc = await asyncio.create_subprocess_exec(
                    *cmd,
                    stdin=asyncio.subprocess.PIPE,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )

                try:
                    stdout, stderr = await asyncio.wait_for(
                        proc.communicate(input=content.encode("utf-8", errors="replace")),
                        timeout=_SUBPROCESS_TIMEOUT,
                    )
                except asyncio.TimeoutError:
                    proc.kill()
                    await proc.communicate()
                    logger.warning("claude subprocess timed out after %ds", _SUBPROCESS_TIMEOUT)
                    return {}

                if proc.returncode != 0:
                    err = stderr.decode("utf-8", errors="replace").strip()
                    logger.warning("claude subprocess exited with code %d: %s", proc.returncode, err[:200])
                    return {}

                raw = stdout.decode("utf-8", errors="replace").strip()
                if not raw:
                    logger.warning("claude subprocess returned empty output")
                    return {}

                response = json.loads(raw)

                # `structured_output` je popunjeno kad se koristi --json-schema
                structured = response.get("structured_output")
                if structured and isinstance(structured, dict):
                    return structured

                # Fallback: pokušaj parsirati polje `result` ako structured nije dostupan
                result_text = response.get("result", "")
                if result_text:
                    try:
                        parsed = json.loads(result_text)
                        if isinstance(parsed, dict):
                            return parsed
                    except json.JSONDecodeError:
                        pass

                logger.warning("claude response missing structured_output and parseable result")
                return {}

            except FileNotFoundError:
                logger.error(
                    "claude CLI nije pronađen. Provjeri da je Claude Code instaliran i dostupan u PATH-u."
                )
                return {}
            except json.JSONDecodeError as exc:
                logger.warning("Nevažeći JSON iz claude subprocess-a: %s", exc)
                return {}
            except Exception as exc:  # noqa: BLE001
                logger.error("Neočekivana greška pri pozivu claude subprocess-a: %s", exc)
                return {}
