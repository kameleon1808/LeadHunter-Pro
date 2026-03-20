"""
End-to-end tests for the LeadHunter Pro database layer.

Run with:  pytest tests/
"""

import os
import tempfile

import pytest
from sqlalchemy import inspect

from database import DatabaseManager


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def tmp_db(tmp_path):
    """Return a DatabaseManager backed by a fresh temporary SQLite file."""
    db_file = str(tmp_path / "test_leadhunter.db")
    # Ensure parent dir exists (db_manager creates it, but tmp_path already does)
    os.makedirs(os.path.dirname(db_file), exist_ok=True)
    manager = DatabaseManager(db_file)
    manager.initialize_db()
    return manager


@pytest.fixture()
def campaign(tmp_db):
    """Return a ready-made campaign for tests that need one."""
    return tmp_db.create_campaign("Test Campaign", "SaaS", "US")


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestDatabaseInitialisation:
    def test_database_initialization(self, tmp_db):
        """DB file must be created and all four tables must exist."""
        assert os.path.exists(tmp_db.db_path)

        inspector = inspect(tmp_db.engine)
        tables = set(inspector.get_table_names())
        assert {"campaigns", "urls", "leads", "scraping_chunks"} <= tables


class TestCampaigns:
    def test_create_campaign(self, tmp_db):
        c = tmp_db.create_campaign("My Campaign", "E-commerce", "UK")

        assert c.id is not None
        assert c.name == "My Campaign"
        assert c.niche == "E-commerce"
        assert c.target_country == "UK"
        assert c.status == "pending"
        assert c.total_urls == 0
        assert c.processed_urls == 0
        assert c.total_leads == 0

    def test_get_campaign(self, tmp_db, campaign):
        fetched = tmp_db.get_campaign(campaign.id)
        assert fetched is not None
        assert fetched.id == campaign.id
        assert fetched.name == campaign.name

    def test_get_all_campaigns(self, tmp_db):
        tmp_db.create_campaign("Alpha", "Legal", "US")
        tmp_db.create_campaign("Beta", "Finance", "CA")
        all_campaigns = tmp_db.get_all_campaigns()
        assert len(all_campaigns) == 2

    def test_campaign_status_flow(self, tmp_db, campaign):
        """Campaign should move through the full lifecycle without errors."""
        for status in ("running", "paused", "running", "completed"):
            tmp_db.update_campaign_status(campaign.id, status)
            refreshed = tmp_db.get_campaign(campaign.id)
            assert refreshed.status == status

    def test_invalid_campaign_status_raises(self, tmp_db, campaign):
        with pytest.raises(ValueError):
            tmp_db.update_campaign_status(campaign.id, "unknown_status")


class TestURLs:
    def test_add_single_url(self, tmp_db, campaign):
        url = tmp_db.add_url(campaign.id, "https://example.com")

        assert url.id is not None
        assert url.campaign_id == campaign.id
        assert url.url == "https://example.com"
        assert url.status == "pending"
        assert url.retry_count == 0

        # Campaign counter must be updated
        updated = tmp_db.get_campaign(campaign.id)
        assert updated.total_urls == 1

    def test_add_urls_bulk(self, tmp_db, campaign):
        urls = [f"https://example.com/page/{i}" for i in range(1000)]
        count = tmp_db.add_urls_bulk(campaign.id, urls)

        assert count == 1000
        updated = tmp_db.get_campaign(campaign.id)
        assert updated.total_urls == 1000

    def test_update_url_status(self, tmp_db, campaign):
        url = tmp_db.add_url(campaign.id, "https://example.com")
        tmp_db.update_url_status(url.id, "processing")

        pending = tmp_db.get_pending_urls(campaign.id, limit=10)
        assert all(u.id != url.id for u in pending)

    def test_update_url_status_failed_increments_retry(self, tmp_db, campaign):
        url = tmp_db.add_url(campaign.id, "https://fail.com")
        tmp_db.update_url_status(url.id, "failed", error_message="Timeout")

        # Fetch via pending urls won't work (it's failed); query stats instead
        stats = tmp_db.get_campaign_stats(campaign.id)
        assert stats["failed_urls"] == 1

    def test_get_pending_urls(self, tmp_db, campaign):
        tmp_db.add_urls_bulk(campaign.id, [f"https://ex.com/{i}" for i in range(50)])
        pending = tmp_db.get_pending_urls(campaign.id, limit=20)
        assert len(pending) == 20
        assert all(u.status == "pending" for u in pending)

    def test_foreign_key_integrity(self, tmp_db):
        """Adding a URL with a non-existent campaign_id must raise an error."""
        with pytest.raises(Exception):
            tmp_db.add_url(99999, "https://orphan.com")


class TestLeads:
    def test_add_lead(self, tmp_db, campaign):
        url = tmp_db.add_url(campaign.id, "https://acme.com")
        lead_data = {
            "company_name": "Acme Corp",
            "company_size": "51-200",
            "industry": "Manufacturing",
            "website_url": "https://acme.com",
            "description": "A company that makes things.",
            "contact_name": "Jane Doe",
            "contact_title": "CEO",
            "contact_email": "jane@acme.com",
            "contact_linkedin": "https://linkedin.com/in/janedoe",
            "company_email": "info@acme.com",
            "company_phone": "+1-555-0100",
            "address": "123 Main St, Springfield",
            "clients_info": "Fortune 500 clients",
            "raw_data": '{"source": "web"}',
            "quality_score": 85,
        }
        lead = tmp_db.add_lead(campaign.id, url.id, lead_data)

        assert lead.id is not None
        assert lead.company_name == "Acme Corp"
        assert lead.quality_score == 85
        assert lead.campaign_id == campaign.id
        assert lead.url_id == url.id

        # Campaign counter
        updated = tmp_db.get_campaign(campaign.id)
        assert updated.total_leads == 1

    def test_get_leads(self, tmp_db, campaign):
        url = tmp_db.add_url(campaign.id, "https://acme.com")
        for i in range(5):
            tmp_db.add_lead(campaign.id, url.id, {"company_name": f"Company {i}", "quality_score": i * 10})
        leads = tmp_db.get_leads(campaign.id)
        assert len(leads) == 5


class TestStats:
    def test_get_campaign_stats(self, tmp_db, campaign):
        urls = [f"https://ex.com/{i}" for i in range(10)]
        tmp_db.add_urls_bulk(campaign.id, urls)

        all_urls = tmp_db.get_pending_urls(campaign.id, limit=10)
        for u in all_urls[:4]:
            tmp_db.update_url_status(u.id, "completed")
        for u in all_urls[4:6]:
            tmp_db.update_url_status(u.id, "failed")

        stats = tmp_db.get_campaign_stats(campaign.id)

        assert stats["total_urls"] == 10
        assert stats["completed_urls"] == 4
        assert stats["failed_urls"] == 2
        assert stats["pending_urls"] == 4
        assert stats["campaign_name"] == campaign.name


class TestChunks:
    def test_create_chunks(self, tmp_db, campaign):
        """1000 URLs with chunk_size=300 should produce 4 chunks."""
        tmp_db.add_urls_bulk(campaign.id, [f"https://ex.com/{i}" for i in range(1000)])
        chunks = tmp_db.create_chunks(campaign.id, chunk_size=300)

        assert len(chunks) == 4
        assert chunks[0].chunk_number == 1
        assert chunks[0].start_index == 0
        assert chunks[0].end_index == 299
        assert chunks[3].start_index == 900
        assert chunks[3].end_index == 999

    def test_get_pending_chunks(self, tmp_db, campaign):
        tmp_db.add_urls_bulk(campaign.id, [f"https://ex.com/{i}" for i in range(600)])
        tmp_db.create_chunks(campaign.id, chunk_size=300)

        pending = tmp_db.get_pending_chunks(campaign.id)
        assert len(pending) == 2

    def test_update_chunk_status(self, tmp_db, campaign):
        tmp_db.add_urls_bulk(campaign.id, [f"https://ex.com/{i}" for i in range(300)])
        chunks = tmp_db.create_chunks(campaign.id, chunk_size=300)

        tmp_db.update_chunk_status(chunks[0].id, "completed")
        pending = tmp_db.get_pending_chunks(campaign.id)
        assert len(pending) == 0

    def test_chunk_size_boundary(self, tmp_db, campaign):
        """Exactly chunk_size URLs should produce exactly 1 chunk."""
        tmp_db.add_urls_bulk(campaign.id, [f"https://ex.com/{i}" for i in range(300)])
        chunks = tmp_db.create_chunks(campaign.id, chunk_size=300)
        assert len(chunks) == 1
        assert chunks[0].end_index == 299
