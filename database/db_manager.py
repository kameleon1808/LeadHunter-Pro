import logging
import math
import os
from datetime import datetime, timezone
from typing import List, Optional

from sqlalchemy import create_engine, event, inspect
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from .models import Base, Campaign, Lead, ScrapingChunk, URL

logger = logging.getLogger(__name__)


class DatabaseManager:
    def __init__(self, db_path: str):
        self.db_path = db_path
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        self.engine = create_engine(
            f"sqlite:///{db_path}",
            connect_args={"check_same_thread": False},
        )

        @event.listens_for(self.engine, "connect")
        def set_sqlite_pragma(dbapi_conn, _):
            cursor = dbapi_conn.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.close()

        self.Session = sessionmaker(bind=self.engine)

    # ------------------------------------------------------------------
    # Initialisation
    # ------------------------------------------------------------------

    def initialize_db(self) -> None:
        """Create all tables if they don't already exist."""
        Base.metadata.create_all(self.engine)
        logger.info("Database initialised at %s", self.db_path)

    def get_existing_tables(self) -> List[str]:
        """Return a list of table names that currently exist in the DB."""
        inspector = inspect(self.engine)
        return inspector.get_table_names()

    # ------------------------------------------------------------------
    # Campaigns
    # ------------------------------------------------------------------

    def create_campaign(self, name: str, niche: str, target_country: Optional[str] = None) -> Campaign:
        with Session(self.engine) as session:
            campaign = Campaign(name=name, niche=niche, target_country=target_country)
            session.add(campaign)
            session.commit()
            session.refresh(campaign)
            # Detach so the object is usable outside the session
            session.expunge(campaign)
            logger.info("Created campaign id=%s name=%r", campaign.id, campaign.name)
            return campaign

    def get_campaign(self, campaign_id: int) -> Optional[Campaign]:
        with Session(self.engine) as session:
            campaign = session.get(Campaign, campaign_id)
            if campaign:
                session.expunge(campaign)
            return campaign

    def get_all_campaigns(self) -> List[Campaign]:
        with Session(self.engine) as session:
            campaigns = session.query(Campaign).all()
            for c in campaigns:
                session.expunge(c)
            return campaigns

    def update_campaign_status(self, campaign_id: int, status: str) -> None:
        valid = {"pending", "running", "paused", "completed", "failed"}
        if status not in valid:
            raise ValueError(f"Invalid campaign status: {status!r}. Must be one of {valid}")
        with Session(self.engine) as session:
            campaign = session.get(Campaign, campaign_id)
            if not campaign:
                raise ValueError(f"Campaign {campaign_id} not found")
            campaign.status = status
            campaign.updated_at = datetime.now(timezone.utc)
            session.commit()
            logger.info("Campaign id=%s status -> %r", campaign_id, status)

    # ------------------------------------------------------------------
    # URLs
    # ------------------------------------------------------------------

    def add_url(self, campaign_id: int, url: str) -> URL:
        with Session(self.engine) as session:
            record = URL(campaign_id=campaign_id, url=url)
            session.add(record)
            # Keep campaign counter in sync
            campaign = session.get(Campaign, campaign_id)
            if campaign:
                campaign.total_urls += 1
                campaign.updated_at = datetime.now(timezone.utc)
            session.commit()
            session.refresh(record)
            session.expunge(record)
            logger.debug("Added URL id=%s to campaign id=%s", record.id, campaign_id)
            return record

    def add_urls_bulk(self, campaign_id: int, urls_list: List[str]) -> int:
        """Insert many URLs at once. Returns the number of rows inserted."""
        if not urls_list:
            return 0
        records = [URL(campaign_id=campaign_id, url=u) for u in urls_list]
        with Session(self.engine) as session:
            session.bulk_save_objects(records)
            campaign = session.get(Campaign, campaign_id)
            if campaign:
                campaign.total_urls += len(records)
                campaign.updated_at = datetime.now(timezone.utc)
            session.commit()
        logger.info("Bulk-added %d URLs to campaign id=%s", len(records), campaign_id)
        return len(records)

    def get_pending_urls(self, campaign_id: int, limit: int = 100) -> List[URL]:
        with Session(self.engine) as session:
            urls = (
                session.query(URL)
                .filter(URL.campaign_id == campaign_id, URL.status == "pending")
                .limit(limit)
                .all()
            )
            for u in urls:
                session.expunge(u)
            return urls

    def update_url_status(
        self,
        url_id: int,
        status: str,
        error_message: Optional[str] = None,
    ) -> None:
        valid = {"pending", "processing", "completed", "failed", "skipped"}
        if status not in valid:
            raise ValueError(f"Invalid URL status: {status!r}")
        with Session(self.engine) as session:
            record = session.get(URL, url_id)
            if not record:
                raise ValueError(f"URL {url_id} not found")
            record.status = status
            record.processed_at = datetime.now(timezone.utc)
            if error_message:
                record.error_message = error_message
            if status == "failed":
                record.retry_count += 1
            # Keep campaign processed counter in sync
            if status in {"completed", "failed", "skipped"}:
                campaign = session.get(Campaign, record.campaign_id)
                if campaign:
                    campaign.processed_urls += 1
                    campaign.updated_at = datetime.now(timezone.utc)
            session.commit()

    # ------------------------------------------------------------------
    # Leads
    # ------------------------------------------------------------------

    def add_lead(self, campaign_id: int, url_id: int, lead_data: dict) -> Lead:
        with Session(self.engine) as session:
            lead = Lead(campaign_id=campaign_id, url_id=url_id, **lead_data)
            session.add(lead)
            campaign = session.get(Campaign, campaign_id)
            if campaign:
                campaign.total_leads += 1
                campaign.updated_at = datetime.now(timezone.utc)
            session.commit()
            session.refresh(lead)
            session.expunge(lead)
            logger.debug("Added lead id=%s to campaign id=%s", lead.id, campaign_id)
            return lead

    def get_leads(self, campaign_id: int) -> List[Lead]:
        with Session(self.engine) as session:
            leads = session.query(Lead).filter(Lead.campaign_id == campaign_id).all()
            for lead in leads:
                session.expunge(lead)
            return leads

    # ------------------------------------------------------------------
    # Stats
    # ------------------------------------------------------------------

    def get_campaign_stats(self, campaign_id: int) -> dict:
        with Session(self.engine) as session:
            campaign = session.get(Campaign, campaign_id)
            if not campaign:
                raise ValueError(f"Campaign {campaign_id} not found")
            total_urls = session.query(URL).filter(URL.campaign_id == campaign_id).count()
            pending = (
                session.query(URL)
                .filter(URL.campaign_id == campaign_id, URL.status == "pending")
                .count()
            )
            completed = (
                session.query(URL)
                .filter(URL.campaign_id == campaign_id, URL.status == "completed")
                .count()
            )
            failed = (
                session.query(URL)
                .filter(URL.campaign_id == campaign_id, URL.status == "failed")
                .count()
            )
            total_leads = session.query(Lead).filter(Lead.campaign_id == campaign_id).count()
            return {
                "campaign_id": campaign_id,
                "campaign_name": campaign.name,
                "campaign_status": campaign.status,
                "total_urls": total_urls,
                "pending_urls": pending,
                "completed_urls": completed,
                "failed_urls": failed,
                "total_leads": total_leads,
            }

    def get_recent_activity(self, campaign_id: int, limit: int = 10) -> List[URL]:
        """Return most recently processed URLs (completed or failed) for the monitor."""
        with Session(self.engine) as session:
            records = (
                session.query(URL)
                .filter(
                    URL.campaign_id == campaign_id,
                    URL.status.in_(["completed", "failed"]),
                )
                .order_by(URL.processed_at.desc())
                .limit(limit)
                .all()
            )
            for r in records:
                session.expunge(r)
            return records

    # ------------------------------------------------------------------
    # Chunks
    # ------------------------------------------------------------------

    def create_chunks(self, campaign_id: int, chunk_size: int = 300) -> List[ScrapingChunk]:
        with Session(self.engine) as session:
            urls = (
                session.query(URL)
                .filter(URL.campaign_id == campaign_id)
                .order_by(URL.id)
                .all()
            )
            total = len(urls)
            if total == 0:
                return []

            num_chunks = math.ceil(total / chunk_size)
            chunks = []
            for i in range(num_chunks):
                start = i * chunk_size
                end = min(start + chunk_size - 1, total - 1)
                chunk = ScrapingChunk(
                    campaign_id=campaign_id,
                    chunk_number=i + 1,
                    start_index=start,
                    end_index=end,
                )
                session.add(chunk)
                chunks.append(chunk)

            session.commit()
            for c in chunks:
                session.refresh(c)
                session.expunge(c)

            logger.info(
                "Created %d chunks for campaign id=%s (chunk_size=%d)",
                len(chunks),
                campaign_id,
                chunk_size,
            )
            return chunks

    def get_pending_chunks(self, campaign_id: int) -> List[ScrapingChunk]:
        with Session(self.engine) as session:
            chunks = (
                session.query(ScrapingChunk)
                .filter(
                    ScrapingChunk.campaign_id == campaign_id,
                    ScrapingChunk.status == "pending",
                )
                .order_by(ScrapingChunk.chunk_number)
                .all()
            )
            for c in chunks:
                session.expunge(c)
            return chunks

    def update_chunk_status(self, chunk_id: int, status: str) -> None:
        valid = {"pending", "processing", "completed", "failed"}
        if status not in valid:
            raise ValueError(f"Invalid chunk status: {status!r}")
        with Session(self.engine) as session:
            chunk = session.get(ScrapingChunk, chunk_id)
            if not chunk:
                raise ValueError(f"Chunk {chunk_id} not found")
            chunk.status = status
            if status == "completed":
                chunk.completed_at = datetime.now(timezone.utc)
            session.commit()
            logger.debug("Chunk id=%s status -> %r", chunk_id, status)
