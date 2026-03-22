"""
E2E / unit tests for the Phase 3 enrichment module.

Run with:
    pytest tests/test_enrichment.py -v

Tests that exercise the database use a temporary SQLite file so they are
fully isolated.  Tests that call external services (Claude API, real URLs)
are mocked via unittest.mock.
"""

import asyncio
import json
import re
from typing import List
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio

from database import DatabaseManager
from enrichment.ai_extractor import AIExtractor
from enrichment.enrichment_pipeline import EnrichmentPipeline
from enrichment.page_scraper import PageScraper


# ---------------------------------------------------------------------------
# Helpers / fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def tmp_db(tmp_path):
    db_path = str(tmp_path / "test_enrichment.db")
    db = DatabaseManager(db_path)
    db.initialize_db()
    return db


@pytest.fixture
def campaign(tmp_db):
    return tmp_db.create_campaign(name="Test Campaign", niche="agencies")


@pytest.fixture
def scraper():
    return PageScraper()


@pytest.fixture
def ai_extractor():
    # AIExtractor._parse_claude_response is a static method — returns the class itself
    # so tests can call AIExtractor._parse_claude_response(...) without the anthropic package.
    return AIExtractor


# ---------------------------------------------------------------------------
# PageScraper — static helpers (no network)
# ---------------------------------------------------------------------------

class TestCleanHtml:
    def test_removes_script_tags(self):
        html = "<html><body><script>alert('x')</script><p>Hello</p></body></html>"
        result = PageScraper._clean_html(html)
        assert "alert" not in result
        assert "Hello" in result

    def test_removes_style_tags(self):
        html = "<html><head><style>body{color:red}</style></head><body><p>World</p></body></html>"
        result = PageScraper._clean_html(html)
        assert "color:red" not in result
        assert "World" in result

    def test_collapses_whitespace(self):
        html = "<p>  Hello   World  </p>"
        result = PageScraper._clean_html(html)
        assert "  " not in result

    def test_returns_string(self):
        assert isinstance(PageScraper._clean_html("<p>test</p>"), str)

    def test_empty_html(self):
        result = PageScraper._clean_html("")
        assert result == ""


class TestExtractEmails:
    def test_finds_single_email(self):
        emails = PageScraper._extract_emails("Contact us at hello@example.com today.")
        assert "hello@example.com" in emails

    def test_finds_multiple_emails(self):
        text = "Send to admin@acme.org or support@acme.org"
        emails = PageScraper._extract_emails(text)
        assert len(emails) == 2

    def test_deduplicates_emails(self):
        text = "hello@example.com and hello@example.com again"
        emails = PageScraper._extract_emails(text)
        assert emails.count("hello@example.com") == 1

    def test_no_emails_returns_empty(self):
        emails = PageScraper._extract_emails("No contacts here.")
        assert emails == []

    def test_ignores_invalid_patterns(self):
        emails = PageScraper._extract_emails("not-an-email@@double.com")
        # Should not crash; may or may not find something but must be a list
        assert isinstance(emails, list)


class TestExtractPhones:
    def test_finds_us_phone(self):
        phones = PageScraper._extract_phones("Call us: +1 (555) 123-4567")
        assert len(phones) >= 1

    def test_finds_international_phone(self):
        phones = PageScraper._extract_phones("UK office: +44 20 7946 0958")
        assert len(phones) >= 1

    def test_no_phones_returns_empty(self):
        phones = PageScraper._extract_phones("No phone number listed.")
        assert phones == []

    def test_returns_list(self):
        assert isinstance(PageScraper._extract_phones("text"), list)


# ---------------------------------------------------------------------------
# PageScraper — async network methods (mocked)
# ---------------------------------------------------------------------------

class TestFindKeyPages:
    @pytest.mark.asyncio
    async def test_finds_about_and_contact_links(self, scraper):
        html = """
        <html><body>
          <a href="/about">About Us</a>
          <a href="/contact">Contact</a>
          <a href="/blog">Blog</a>
        </body></html>
        """
        with patch.object(scraper, "fetch_page", new_callable=AsyncMock) as mock_fetch:
            mock_fetch.return_value = {
                "url": "https://example.com",
                "html": html,
                "status_code": 200,
                "error": None,
            }
            pages = await scraper.find_key_pages("https://example.com")

        assert any("about" in p.lower() for p in pages)
        assert any("contact" in p.lower() for p in pages)

    @pytest.mark.asyncio
    async def test_returns_empty_on_fetch_failure(self, scraper):
        with patch.object(scraper, "fetch_page", new_callable=AsyncMock) as mock_fetch:
            mock_fetch.return_value = {
                "url": "https://example.com",
                "html": None,
                "status_code": 500,
                "error": "HTTP 500",
            }
            pages = await scraper.find_key_pages("https://example.com")

        assert pages == []

    @pytest.mark.asyncio
    async def test_respects_max_pages_limit(self, scraper):
        # Generate many matching links
        links = "".join(
            f'<a href="/about-{i}">About {i}</a>' for i in range(20)
        )
        html = f"<html><body>{links}</body></html>"

        with patch.object(scraper, "fetch_page", new_callable=AsyncMock) as mock_fetch:
            mock_fetch.return_value = {
                "url": "https://example.com",
                "html": html,
                "status_code": 200,
                "error": None,
            }
            import config
            pages = await scraper.find_key_pages("https://example.com")

        assert len(pages) <= config.MAX_PAGES_PER_SITE


# ---------------------------------------------------------------------------
# AIExtractor
# ---------------------------------------------------------------------------

class TestAiExtractorParseResponse:
    def test_valid_json_parsed(self, ai_extractor):
        payload = {
            "company_name": "Acme Corp",
            "company_size": "10-50",
            "industry": "Marketing",
            "description": "Full-service agency",
            "contact_name": "Jane Doe",
            "contact_title": "CEO",
            "contact_email": "jane@acme.com",
            "contact_linkedin": None,
            "company_email": "info@acme.com",
            "company_phone": "+1 555 000 0000",
            "address": "123 Main St",
            "clients_info": "SMEs in retail",
            "quality_score": 8,
        }
        result = AIExtractor._parse_claude_response(json.dumps(payload))
        assert result["company_name"] == "Acme Corp"
        assert result["quality_score"] == 8

    def test_handles_markdown_fences(self, ai_extractor):
        payload = '```json\n{"company_name": "Test", "quality_score": 5}\n```'
        result = AIExtractor._parse_claude_response(payload)
        assert result["company_name"] == "Test"

    def test_clamps_quality_score_above_10(self, ai_extractor):
        result = AIExtractor._parse_claude_response('{"quality_score": 99}')
        assert result["quality_score"] == 10

    def test_clamps_quality_score_below_1(self, ai_extractor):
        result = AIExtractor._parse_claude_response('{"quality_score": -5}')
        assert result["quality_score"] == 1


class TestAiExtractorHandlesInvalidJson:
    def test_returns_empty_dict_on_invalid_json(self, ai_extractor):
        result = AIExtractor._parse_claude_response("This is not JSON at all.")
        assert result == {}

    def test_returns_empty_dict_on_empty_string(self, ai_extractor):
        result = AIExtractor._parse_claude_response("")
        assert result == {}

    def test_returns_empty_dict_on_json_array(self, ai_extractor):
        # Claude returning an array instead of an object
        result = AIExtractor._parse_claude_response("[1, 2, 3]")
        assert result == {}


# ---------------------------------------------------------------------------
# EnrichmentPipeline — process_single_url
# ---------------------------------------------------------------------------

_SAMPLE_LEAD_DATA = {
    "company_name": "Acme Corp",
    "company_size": "10-50",
    "industry": "Marketing",
    "description": "Full-service agency",
    "contact_name": "Jane Doe",
    "contact_title": "CEO",
    "contact_email": "jane@acme.com",
    "contact_linkedin": None,
    "company_email": "info@acme.com",
    "company_phone": "+1 555 000 0000",
    "address": "123 Main St",
    "clients_info": "SMEs in retail",
    "quality_score": 8,
}


def _make_pipeline(tmp_db, campaign_id, lead_data=None):
    """Build an EnrichmentPipeline with fully mocked AI extractor and analyzer."""
    extractor = MagicMock(spec=AIExtractor)
    # Use _SAMPLE_LEAD_DATA only when lead_data is not provided (None), not when it's {}
    return_value = _SAMPLE_LEAD_DATA if lead_data is None else lead_data
    extractor.extract_lead_data = AsyncMock(return_value=return_value)
    extractor.identify_key_pages = AsyncMock(return_value=[])

    pipeline = EnrichmentPipeline(
        db_manager=tmp_db,
        ai_extractor=extractor,
        campaign_id=campaign_id,
    )

    # Mock the site analyzer to return pre-built page content
    pipeline._analyzer.analyse = AsyncMock(
        return_value=[
            {
                "url": "https://example.com",
                "text": "We are Acme Corp, a marketing agency.",
                "emails": ["info@acme.com"],
                "phones": ["+1 555 000 0000"],
            }
        ]
    )
    return pipeline


class TestProcessSingleUrlSuccess:
    @pytest.mark.asyncio
    async def test_lead_saved_to_db(self, tmp_db, campaign):
        url_record = tmp_db.add_url(campaign.id, "https://example.com")
        pipeline = _make_pipeline(tmp_db, campaign.id)

        lead = await pipeline.process_single_url(url_record)

        assert lead is not None
        assert lead.company_name == "Acme Corp"
        assert lead.quality_score == 8

        # URL should be marked completed
        stats = tmp_db.get_campaign_stats(campaign.id)
        assert stats["completed_urls"] == 1

    @pytest.mark.asyncio
    async def test_website_url_populated(self, tmp_db, campaign):
        url_record = tmp_db.add_url(campaign.id, "https://example.com")
        pipeline = _make_pipeline(tmp_db, campaign.id)

        lead = await pipeline.process_single_url(url_record)

        assert lead is not None
        assert lead.website_url == "https://example.com"


class TestProcessSingleUrlFailure:
    @pytest.mark.asyncio
    async def test_url_marked_failed_when_no_content(self, tmp_db, campaign):
        url_record = tmp_db.add_url(campaign.id, "https://broken.com")
        pipeline = _make_pipeline(tmp_db, campaign.id)
        # Override analyzer to return no content
        pipeline._analyzer.analyse = AsyncMock(return_value=[])

        lead = await pipeline.process_single_url(url_record)

        assert lead is None
        stats = tmp_db.get_campaign_stats(campaign.id)
        assert stats["failed_urls"] == 1

    @pytest.mark.asyncio
    async def test_url_marked_failed_when_ai_returns_empty(self, tmp_db, campaign):
        url_record = tmp_db.add_url(campaign.id, "https://empty.com")
        pipeline = _make_pipeline(tmp_db, campaign.id, lead_data={})

        lead = await pipeline.process_single_url(url_record)

        assert lead is None
        stats = tmp_db.get_campaign_stats(campaign.id)
        assert stats["failed_urls"] == 1


# ---------------------------------------------------------------------------
# EnrichmentPipeline — chunk processing
# ---------------------------------------------------------------------------

class TestChunkProcessing:
    @pytest.mark.asyncio
    async def test_all_urls_in_chunk_processed(self, tmp_db, campaign):
        urls = [
            tmp_db.add_url(campaign.id, f"https://company{i}.com")
            for i in range(5)
        ]
        pipeline = _make_pipeline(tmp_db, campaign.id)

        await pipeline._process_chunk(urls, campaign.id)

        stats = tmp_db.get_campaign_stats(campaign.id)
        # All 5 should be either completed or failed (none still pending)
        assert stats["completed_urls"] + stats["failed_urls"] == 5

    @pytest.mark.asyncio
    async def test_chunk_creates_leads(self, tmp_db, campaign):
        urls = [
            tmp_db.add_url(campaign.id, f"https://agency{i}.com")
            for i in range(3)
        ]
        pipeline = _make_pipeline(tmp_db, campaign.id)

        await pipeline._process_chunk(urls, campaign.id)

        leads = tmp_db.get_leads(campaign.id)
        assert len(leads) == 3


# ---------------------------------------------------------------------------
# Quality score constraints
# ---------------------------------------------------------------------------

class TestQualityScoreRange:
    @pytest.mark.parametrize("raw_score,expected", [
        (1, 1),
        (5, 5),
        (10, 10),
        (0, 1),     # clamped up
        (-3, 1),    # clamped up
        (11, 10),   # clamped down
        (100, 10),  # clamped down
    ])
    def test_score_always_between_1_and_10(self, ai_extractor, raw_score, expected):
        payload = json.dumps({"quality_score": raw_score})
        result = AIExtractor._parse_claude_response(payload)
        assert result["quality_score"] == expected

    @pytest.mark.asyncio
    async def test_lead_score_saved_within_range(self, tmp_db, campaign):
        url_record = tmp_db.add_url(campaign.id, "https://scored.com")
        lead_data = {**_SAMPLE_LEAD_DATA, "quality_score": 7}
        pipeline = _make_pipeline(tmp_db, campaign.id, lead_data=lead_data)

        lead = await pipeline.process_single_url(url_record)

        assert lead is not None
        assert 1 <= lead.quality_score <= 10


# ---------------------------------------------------------------------------
# ClaudeCodeExtractor — subprocess-based extractor
# ---------------------------------------------------------------------------

class TestClaudeCodeExtractor:
    """Tests for ClaudeCodeExtractor — all subprocess calls are mocked."""

    @pytest.fixture
    def extractor(self):
        from enrichment.claude_code_extractor import ClaudeCodeExtractor
        return ClaudeCodeExtractor()

    def _make_mock_process(self, stdout_data: bytes, returncode: int = 0):
        """Build a mock asyncio subprocess with given stdout."""
        mock_proc = MagicMock()
        mock_proc.returncode = returncode
        mock_proc.communicate = AsyncMock(return_value=(stdout_data, b""))
        mock_proc.kill = MagicMock()
        return mock_proc

    @pytest.mark.asyncio
    async def test_call_claude_parses_structured_output(self, extractor):
        """structured_output from JSON response is returned as dict."""
        structured = {"company_name": "Acme", "quality_score": 8}
        response = json.dumps({"structured_output": structured, "result": "", "session_id": "x"})

        mock_proc = self._make_mock_process(response.encode())
        with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
            result = await extractor._call_claude("instruction", "content", {})

        assert result["company_name"] == "Acme"
        assert result["quality_score"] == 8

    @pytest.mark.asyncio
    async def test_call_claude_fallback_to_result_field(self, extractor):
        """Falls back to parsing 'result' field if structured_output is absent."""
        inner_json = json.dumps({"company_name": "Beta Corp", "quality_score": 5})
        response = json.dumps({"result": inner_json, "session_id": "y"})

        mock_proc = self._make_mock_process(response.encode())
        with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
            result = await extractor._call_claude("instruction", "content", {})

        assert result["company_name"] == "Beta Corp"

    @pytest.mark.asyncio
    async def test_handles_subprocess_failure(self, extractor):
        """Non-zero returncode → returns empty dict, does not raise."""
        mock_proc = self._make_mock_process(b"", returncode=1)
        with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
            result = await extractor._call_claude("instruction", "content", {})

        assert result == {}

    @pytest.mark.asyncio
    async def test_handles_invalid_json_from_claude(self, extractor):
        """Invalid JSON stdout → returns empty dict, does not raise."""
        mock_proc = self._make_mock_process(b"this is not json")
        with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
            result = await extractor._call_claude("instruction", "content", {})

        assert result == {}

    @pytest.mark.asyncio
    async def test_handles_empty_stdout(self, extractor):
        """Empty stdout → returns empty dict."""
        mock_proc = self._make_mock_process(b"")
        with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
            result = await extractor._call_claude("instruction", "content", {})

        assert result == {}

    @pytest.mark.asyncio
    async def test_handles_claude_not_found(self, extractor):
        """FileNotFoundError (claude CLI not in PATH) → returns empty dict."""
        with patch("asyncio.create_subprocess_exec", side_effect=FileNotFoundError):
            result = await extractor._call_claude("instruction", "content", {})

        assert result == {}

    @pytest.mark.asyncio
    async def test_extract_lead_data_calls_subprocess(self, extractor):
        """extract_lead_data() calls subprocess and returns structured lead dict."""
        structured = {**_SAMPLE_LEAD_DATA}
        response = json.dumps({"structured_output": structured, "result": ""})

        mock_proc = self._make_mock_process(response.encode())
        with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
            result = await extractor.extract_lead_data([
                {"url": "https://example.com", "text": "We are Acme Corp."}
            ])

        assert result["company_name"] == "Acme Corp"
        assert 1 <= result["quality_score"] <= 10

    @pytest.mark.asyncio
    async def test_extract_lead_data_returns_empty_on_no_content(self, extractor):
        """extract_lead_data() with empty list returns {} without calling subprocess."""
        with patch("asyncio.create_subprocess_exec") as mock_exec:
            result = await extractor.extract_lead_data([])

        mock_exec.assert_not_called()
        assert result == {}

    @pytest.mark.asyncio
    async def test_identify_key_pages_filters_links(self, extractor):
        """identify_key_pages() returns only URLs from the original list."""
        all_links = [
            "https://example.com/about",
            "https://example.com/contact",
            "https://example.com/blog",
        ]
        # Claude returns about + contact (valid) + a hallucinated URL
        structured = {"urls": ["https://example.com/about", "https://example.com/contact", "https://hallucinated.com"]}
        response = json.dumps({"structured_output": structured, "result": ""})

        mock_proc = self._make_mock_process(response.encode())
        with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
            result = await extractor.identify_key_pages(all_links)

        # Hallucinated URL must be filtered out
        assert "https://hallucinated.com" not in result
        assert "https://example.com/about" in result
        assert "https://example.com/contact" in result

    @pytest.mark.asyncio
    async def test_quality_score_clamped(self, extractor):
        """extract_lead_data() clamps quality_score to 1-10 even if Claude returns out-of-range."""
        structured = {"quality_score": 99, "company_name": "Test"}
        response = json.dumps({"structured_output": structured, "result": ""})

        mock_proc = self._make_mock_process(response.encode())
        with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
            result = await extractor.extract_lead_data([
                {"url": "https://example.com", "text": "content"}
            ])

        assert result["quality_score"] == 10
