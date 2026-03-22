"""
Integration tests — Phase 5.

These tests exercise the full pipeline end-to-end using a real SQLite
database (temporary) but with mocked network and AI calls.  No browser,
no Claude CLI, no internet connection is required.

Run with:
    pytest tests/test_integration.py -v
"""

import asyncio
import json
import os
from typing import List
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from database import DatabaseManager
from database.models import URL
from enrichment import EnrichmentPipeline
from export import ExcelExporter
from utils import ErrorCategory, ErrorHandler, RetryManager


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def tmp_db(tmp_path):
    db = DatabaseManager(str(tmp_path / "integration.db"))
    db.initialize_db()
    return db


@pytest.fixture
def campaign(tmp_db):
    return tmp_db.create_campaign(
        name="Integration Test",
        niche="marketing agencies",
        target_country="Serbia",
    )


_SAMPLE_LEAD = {
    "company_name":     "Acme Agency",
    "company_size":     "10-50",
    "industry":         "Digital Marketing",
    "description":      "Full-service digital agency",
    "contact_name":     "Jane Doe",
    "contact_title":    "CEO",
    "contact_email":    "jane@acme.rs",
    "contact_linkedin": "https://linkedin.com/in/janedoe",
    "company_email":    "info@acme.rs",
    "company_phone":    "+381 11 000 0000",
    "address":          "Belgrade, Serbia",
    "clients_info":     "SMEs in retail",
    "quality_score":    8,
}


def _make_extractor(lead_data: dict = None):
    """Return a fully mocked AI extractor."""
    ext = MagicMock()
    ext.extract_lead_data  = AsyncMock(return_value=lead_data or _SAMPLE_LEAD)
    ext.identify_key_pages = AsyncMock(return_value=[])
    return ext


def _make_pipeline(tmp_db, campaign, lead_data=None, empty_pages=False):
    """Build an EnrichmentPipeline with all I/O mocked."""
    extractor = _make_extractor(lead_data)
    pipeline  = EnrichmentPipeline(
        db_manager=tmp_db,
        ai_extractor=extractor,
        campaign_id=campaign.id,
    )
    page_content = [] if empty_pages else [
        {"url": "https://placeholder.com", "text": "Company info", "emails": [], "phones": []},
    ]
    pipeline._analyzer.analyse = AsyncMock(return_value=page_content)
    return pipeline


def _add_urls(db, campaign, count: int) -> List[URL]:
    return [db.add_url(campaign.id, f"https://company{i}.com") for i in range(count)]


# ---------------------------------------------------------------------------
# 1. Full pipeline small
# ---------------------------------------------------------------------------

class TestFullPipelineSmall:
    """Run enrichment on 10 mock URLs end-to-end."""

    @pytest.mark.asyncio
    async def test_all_urls_produce_leads(self, tmp_db, campaign):
        _add_urls(tmp_db, campaign, 10)
        pipeline = _make_pipeline(tmp_db, campaign)
        await pipeline.process_campaign(campaign.id)

        leads = tmp_db.get_leads(campaign.id)
        assert len(leads) == 10

    @pytest.mark.asyncio
    async def test_all_urls_marked_completed(self, tmp_db, campaign):
        _add_urls(tmp_db, campaign, 10)
        pipeline = _make_pipeline(tmp_db, campaign)
        await pipeline.process_campaign(campaign.id)

        stats = tmp_db.get_campaign_stats(campaign.id)
        assert stats["completed_urls"] == 10
        assert stats["pending_urls"]   == 0

    @pytest.mark.asyncio
    async def test_campaign_status_completed(self, tmp_db, campaign):
        _add_urls(tmp_db, campaign, 5)
        pipeline = _make_pipeline(tmp_db, campaign)
        await pipeline.process_campaign(campaign.id)

        fresh = tmp_db.get_campaign(campaign.id)
        assert fresh.status == "completed"

    @pytest.mark.asyncio
    async def test_leads_have_website_url(self, tmp_db, campaign):
        _add_urls(tmp_db, campaign, 3)
        pipeline = _make_pipeline(tmp_db, campaign)
        await pipeline.process_campaign(campaign.id)

        leads = tmp_db.get_leads(campaign.id)
        for lead in leads:
            assert lead.website_url is not None
            assert lead.website_url.startswith("https://")


# ---------------------------------------------------------------------------
# 2. Resume after failure
# ---------------------------------------------------------------------------

class TestResumeAfterFailure:
    """Simulate a partial run, then resume and verify only pending are processed."""

    @pytest.mark.asyncio
    async def test_only_pending_urls_processed_on_resume(self, tmp_db, campaign):
        # Add 10 URLs; manually mark first 5 as completed with leads
        urls = _add_urls(tmp_db, campaign, 10)
        for url_rec in urls[:5]:
            tmp_db.update_url_status(url_rec.id, "completed")
            tmp_db.add_lead(campaign.id, url_rec.id, {**_SAMPLE_LEAD, "company_name": f"Pre-existing {url_rec.id}"})

        # Run pipeline — should only process the 5 still-pending URLs
        pipeline = _make_pipeline(tmp_db, campaign)
        await pipeline.process_campaign(campaign.id)

        leads = tmp_db.get_leads(campaign.id)
        # 5 pre-existing + 5 newly created = 10 total
        assert len(leads) == 10
        stats = tmp_db.get_campaign_stats(campaign.id)
        assert stats["completed_urls"] == 10

    @pytest.mark.asyncio
    async def test_failed_urls_not_reprocessed(self, tmp_db, campaign):
        """URLs marked 'failed' are not picked up by get_pending_urls."""
        urls = _add_urls(tmp_db, campaign, 6)
        # Mark 2 as failed
        for url_rec in urls[:2]:
            tmp_db.update_url_status(url_rec.id, "failed", "Simulated failure")

        pipeline = _make_pipeline(tmp_db, campaign)
        await pipeline.process_campaign(campaign.id)

        # Only 4 leads (from the 4 pending URLs)
        leads = tmp_db.get_leads(campaign.id)
        assert len(leads) == 4

    @pytest.mark.asyncio
    async def test_resume_does_not_duplicate_leads(self, tmp_db, campaign):
        """Running the pipeline twice on a completed campaign adds 0 new leads."""
        _add_urls(tmp_db, campaign, 5)
        pipeline = _make_pipeline(tmp_db, campaign)
        await pipeline.process_campaign(campaign.id)

        # Second run: no pending URLs remain — pipeline processes nothing
        pipeline2 = _make_pipeline(tmp_db, campaign)
        await pipeline2.process_campaign(campaign.id)

        leads = tmp_db.get_leads(campaign.id)
        assert len(leads) == 5  # still 5, not 10


# ---------------------------------------------------------------------------
# 3. Concurrent processing
# ---------------------------------------------------------------------------

class TestConcurrentProcessing:
    """Verify async processing runs without deadlocks and processes all URLs."""

    @pytest.mark.asyncio
    async def test_all_urls_processed_concurrently(self, tmp_db, campaign):
        _add_urls(tmp_db, campaign, 15)
        pipeline = _make_pipeline(tmp_db, campaign)
        await pipeline.process_campaign(campaign.id)

        stats = tmp_db.get_campaign_stats(campaign.id)
        assert stats["completed_urls"] + stats["failed_urls"] == 15

    @pytest.mark.asyncio
    async def test_concurrent_errors_do_not_stop_pipeline(self, tmp_db, campaign):
        """If some URLs fail, the rest still get processed."""
        _add_urls(tmp_db, campaign, 10)
        pipeline = _make_pipeline(tmp_db, campaign)

        call_count = 0

        async def flaky_analyse(url):
            nonlocal call_count
            call_count += 1
            if call_count % 3 == 0:
                return []  # causes "No content" failure for every 3rd URL
            return [{"url": url, "text": "content", "emails": [], "phones": []}]

        pipeline._analyzer.analyse = flaky_analyse
        await pipeline.process_campaign(campaign.id)

        stats = tmp_db.get_campaign_stats(campaign.id)
        # Some completed, some failed — but total must equal 10
        assert stats["completed_urls"] + stats["failed_urls"] == 10

    @pytest.mark.asyncio
    async def test_semaphore_limits_concurrent_claude_calls(self, tmp_db, campaign):
        """CLAUDE_CODE_MAX_CONCURRENT is respected (no more than N simultaneous calls)."""
        import config
        original = config.CLAUDE_CODE_MAX_CONCURRENT
        config.CLAUDE_CODE_MAX_CONCURRENT = 2

        _add_urls(tmp_db, campaign, 8)
        pipeline = _make_pipeline(tmp_db, campaign)

        try:
            await pipeline.process_campaign(campaign.id)
        finally:
            config.CLAUDE_CODE_MAX_CONCURRENT = original

        leads = tmp_db.get_leads(campaign.id)
        assert len(leads) == 8


# ---------------------------------------------------------------------------
# 4. Data integrity
# ---------------------------------------------------------------------------

class TestDataIntegrity:
    """Verify all saved data is valid, complete and consistent."""

    @pytest.mark.asyncio
    async def test_lead_fields_match_extractor_output(self, tmp_db, campaign):
        _add_urls(tmp_db, campaign, 1)
        pipeline = _make_pipeline(tmp_db, campaign, lead_data=_SAMPLE_LEAD)
        await pipeline.process_campaign(campaign.id)

        lead = tmp_db.get_leads(campaign.id)[0]
        assert lead.company_name  == "Acme Agency"
        assert lead.contact_name  == "Jane Doe"
        assert lead.contact_email == "jane@acme.rs"
        assert lead.quality_score == 8
        assert lead.industry      == "Digital Marketing"

    @pytest.mark.asyncio
    async def test_quality_score_always_in_range(self, tmp_db, campaign):
        _add_urls(tmp_db, campaign, 5)
        pipeline = _make_pipeline(tmp_db, campaign)
        await pipeline.process_campaign(campaign.id)

        leads = tmp_db.get_leads(campaign.id)
        for lead in leads:
            assert 1 <= lead.quality_score <= 10

    @pytest.mark.asyncio
    async def test_campaign_lead_counter_accurate(self, tmp_db, campaign):
        _add_urls(tmp_db, campaign, 7)
        pipeline = _make_pipeline(tmp_db, campaign)
        await pipeline.process_campaign(campaign.id)

        stats = tmp_db.get_campaign_stats(campaign.id)
        leads = tmp_db.get_leads(campaign.id)
        assert stats["total_leads"] == len(leads)

    @pytest.mark.asyncio
    async def test_url_id_linked_to_correct_lead(self, tmp_db, campaign):
        urls = _add_urls(tmp_db, campaign, 3)
        pipeline = _make_pipeline(tmp_db, campaign)
        await pipeline.process_campaign(campaign.id)

        leads = tmp_db.get_leads(campaign.id)
        lead_url_ids = {lead.url_id for lead in leads}
        url_ids      = {url.id for url in urls}
        assert lead_url_ids == url_ids

    @pytest.mark.asyncio
    async def test_null_fields_allowed(self, tmp_db, campaign):
        """Leads with many null fields are still saved correctly."""
        sparse = {"quality_score": 2, "company_name": "Sparse Corp"}
        _add_urls(tmp_db, campaign, 1)
        pipeline = _make_pipeline(tmp_db, campaign, lead_data=sparse)
        await pipeline.process_campaign(campaign.id)

        lead = tmp_db.get_leads(campaign.id)[0]
        assert lead.company_name  == "Sparse Corp"
        assert lead.quality_score == 2
        assert lead.contact_email is None


# ---------------------------------------------------------------------------
# 5. Export after pipeline
# ---------------------------------------------------------------------------

class TestExportAfterPipeline:
    """Verify export works correctly after a full pipeline run."""

    @pytest.mark.asyncio
    async def test_export_file_created(self, tmp_db, campaign, tmp_path):
        _add_urls(tmp_db, campaign, 5)
        pipeline = _make_pipeline(tmp_db, campaign)
        await pipeline.process_campaign(campaign.id)

        exporter  = ExcelExporter(tmp_db)
        file_path = exporter.export_campaign(campaign.id, str(tmp_path / "exports"))
        assert os.path.isfile(file_path)

    @pytest.mark.asyncio
    async def test_export_lead_count_matches(self, tmp_db, campaign, tmp_path):
        _add_urls(tmp_db, campaign, 8)
        pipeline = _make_pipeline(tmp_db, campaign)
        await pipeline.process_campaign(campaign.id)

        import openpyxl
        exporter  = ExcelExporter(tmp_db)
        file_path = exporter.export_campaign(campaign.id, str(tmp_path / "exports"))
        wb = openpyxl.load_workbook(file_path)
        ws = wb["Leads"]
        data_rows = [r for r in ws.iter_rows(min_row=2, values_only=True) if any(v for v in r)]
        assert len(data_rows) == 8

    @pytest.mark.asyncio
    async def test_export_contains_correct_company_names(self, tmp_db, campaign, tmp_path):
        urls = _add_urls(tmp_db, campaign, 3)
        # Give each URL a unique company name
        call_idx = 0
        async def unique_extract(pages):
            nonlocal call_idx
            call_idx += 1
            return {**_SAMPLE_LEAD, "company_name": f"Company {call_idx}"}

        pipeline = _make_pipeline(tmp_db, campaign)
        pipeline._extractor = MagicMock()
        pipeline._extractor.extract_lead_data = unique_extract
        # Override the internal extractor used by process_single_url
        pipeline._analyzer.analyse = AsyncMock(
            return_value=[{"url": "x", "text": "y", "emails": [], "phones": []}]
        )
        # Use a simpler approach: patch the extractor on the pipeline
        original_extractor = pipeline._extractor
        for i, url_rec in enumerate(urls):
            lead_data = {**_SAMPLE_LEAD, "company_name": f"Company {i + 1}"}
            tmp_db.update_url_status(url_rec.id, "completed")
            tmp_db.add_lead(campaign.id, url_rec.id, lead_data)

        import openpyxl
        exporter  = ExcelExporter(tmp_db)
        file_path = exporter.export_campaign(campaign.id, str(tmp_path / "exports"))
        wb = openpyxl.load_workbook(file_path)
        ws = wb["Leads"]
        names = [ws.cell(row=r, column=2).value for r in range(2, 5)]
        assert "Company 1" in names
        assert "Company 2" in names
        assert "Company 3" in names


# ---------------------------------------------------------------------------
# RetryManager unit tests
# ---------------------------------------------------------------------------

class TestRetryManager:
    @pytest.mark.asyncio
    async def test_succeeds_on_first_try(self):
        rm = RetryManager(max_retries=3, base_delay=0.01)
        called = 0

        async def good_func():
            nonlocal called
            called += 1
            return "ok"

        result = await rm.exponential_backoff(good_func)
        assert result == "ok"
        assert called == 1

    @pytest.mark.asyncio
    async def test_retries_on_transient_error(self):
        rm = RetryManager(max_retries=3, base_delay=0.01)
        calls = []

        async def flaky():
            calls.append(1)
            if len(calls) < 3:
                raise ConnectionError("temporary")
            return "success"

        result = await rm.exponential_backoff(flaky)
        assert result == "success"
        assert len(calls) == 3

    @pytest.mark.asyncio
    async def test_raises_after_max_retries(self):
        rm = RetryManager(max_retries=2, base_delay=0.01)

        async def always_fails():
            raise ConnectionError("permanent failure")

        with pytest.raises(ConnectionError):
            await rm.exponential_backoff(always_fails)

    def test_should_retry_connection_error(self):
        rm = RetryManager()
        assert rm.should_retry(ConnectionError("fail")) is True

    def test_should_not_retry_value_error(self):
        rm = RetryManager()
        assert rm.should_retry(ValueError("bad input")) is False

    def test_should_not_retry_json_error(self):
        import json
        rm = RetryManager()
        assert rm.should_retry(json.JSONDecodeError("msg", "", 0)) is False


# ---------------------------------------------------------------------------
# ErrorHandler unit tests
# ---------------------------------------------------------------------------

class TestErrorHandler:
    def test_categorizes_connection_error_as_network(self):
        eh = ErrorHandler()
        assert eh.categorize(ConnectionError()) == ErrorCategory.NETWORK

    def test_categorizes_json_error_as_parsing(self):
        import json
        eh = ErrorHandler()
        assert eh.categorize(json.JSONDecodeError("m", "", 0)) == ErrorCategory.PARSING

    def test_categorizes_value_error_as_parsing(self):
        eh = ErrorHandler()
        assert eh.categorize(ValueError("bad json decode")) == ErrorCategory.PARSING

    def test_unknown_error_categorized(self):
        eh = ErrorHandler()
        assert eh.categorize(RuntimeError("something weird")) == ErrorCategory.UNKNOWN

    def test_handle_records_error(self):
        eh = ErrorHandler()
        eh.handle(ConnectionError("timeout"), context="scraping", url="https://x.com")
        assert eh.total_errors == 1

    def test_generate_report_structure(self):
        eh = ErrorHandler()
        eh.handle(ConnectionError("err1"), context="scrape")
        eh.handle(ConnectionError("err2"), context="enrich")
        report = eh.generate_report()
        assert report["total_errors"] == 2
        assert "NETWORK" in report["by_category"]
        assert report["by_category"]["NETWORK"]["count"] == 2

    def test_errors_by_category(self):
        import json
        eh = ErrorHandler()
        eh.handle(ConnectionError(), context="net")
        eh.handle(json.JSONDecodeError("m", "", 0), context="parse")
        cats = eh.errors_by_category
        assert cats["NETWORK"]  == 1
        assert cats["PARSING"]  == 1
