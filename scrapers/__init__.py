from .url_scraper import URLScraper
from .scraper_utils import normalize_url, is_valid_url, extract_domain, deduplicate_urls, BLOCKED_DOMAINS

__all__ = [
    "URLScraper",
    "normalize_url",
    "is_valid_url",
    "extract_domain",
    "deduplicate_urls",
    "BLOCKED_DOMAINS",
]
