from datetime import datetime, timezone

from sqlalchemy import (
    Column,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import DeclarativeBase, relationship


class Base(DeclarativeBase):
    pass


class Campaign(Base):
    __tablename__ = "campaigns"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String, nullable=False)
    niche = Column(String, nullable=False)
    target_country = Column(String)
    status = Column(String, default="pending")  # pending|running|paused|completed|failed
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
    total_urls = Column(Integer, default=0)
    processed_urls = Column(Integer, default=0)
    total_leads = Column(Integer, default=0)

    urls = relationship("URL", back_populates="campaign", cascade="all, delete-orphan")
    leads = relationship("Lead", back_populates="campaign", cascade="all, delete-orphan")
    chunks = relationship("ScrapingChunk", back_populates="campaign", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<Campaign id={self.id} name={self.name!r} status={self.status!r}>"


class URL(Base):
    __tablename__ = "urls"

    id = Column(Integer, primary_key=True, autoincrement=True)
    campaign_id = Column(Integer, ForeignKey("campaigns.id"), nullable=False)
    url = Column(Text, nullable=False)
    status = Column(String, default="pending")  # pending|processing|completed|failed|skipped
    retry_count = Column(Integer, default=0)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    processed_at = Column(DateTime)
    error_message = Column(Text)

    campaign = relationship("Campaign", back_populates="urls")
    leads = relationship("Lead", back_populates="url", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<URL id={self.id} url={self.url!r} status={self.status!r}>"


class Lead(Base):
    __tablename__ = "leads"

    id = Column(Integer, primary_key=True, autoincrement=True)
    campaign_id = Column(Integer, ForeignKey("campaigns.id"), nullable=False)
    url_id = Column(Integer, ForeignKey("urls.id"), nullable=False)
    company_name = Column(String)
    company_size = Column(String)
    industry = Column(String)
    website_url = Column(String)
    description = Column(Text)
    contact_name = Column(String)
    contact_title = Column(String)
    contact_email = Column(String)
    contact_linkedin = Column(String)
    company_email = Column(String)
    company_phone = Column(String)
    address = Column(String)
    clients_info = Column(Text)
    raw_data = Column(Text)
    quality_score = Column(Integer)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    campaign = relationship("Campaign", back_populates="leads")
    url = relationship("URL", back_populates="leads")

    def __repr__(self):
        return f"<Lead id={self.id} company={self.company_name!r} score={self.quality_score}>"


class ScrapingChunk(Base):
    __tablename__ = "scraping_chunks"

    id = Column(Integer, primary_key=True, autoincrement=True)
    campaign_id = Column(Integer, ForeignKey("campaigns.id"), nullable=False)
    chunk_number = Column(Integer)
    start_index = Column(Integer)
    end_index = Column(Integer)
    status = Column(String, default="pending")  # pending|processing|completed|failed
    processed_count = Column(Integer, default=0)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    completed_at = Column(DateTime)

    campaign = relationship("Campaign", back_populates="chunks")

    def __repr__(self):
        return f"<ScrapingChunk id={self.id} chunk={self.chunk_number} status={self.status!r}>"
