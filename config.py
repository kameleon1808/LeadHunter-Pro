import logging
import os

# Database
DATABASE_PATH = "data/leadhunter.db"

# Scraping (general)
CHUNK_SIZE = 300
MAX_RETRIES = 3

# URL Scraper — Phase 2
PLAYWRIGHT_HEADLESS = False  # Keep visible so the user can solve CAPTCHAs
SEARCH_PAGES_DEFAULT = 5
MIN_DELAY_SECONDS = 1.5
MAX_DELAY_SECONDS = 4.0

# Windows + Brave settings
# Set USE_BRAVE = True on Windows to use your existing Brave browser with its
# real profile (cookies, history) — significantly reduces Google CAPTCHAs.
# IMPORTANT: Brave must be fully closed before running the scraper.
USE_BRAVE = False
BRAVE_EXECUTABLE_PATH = r"C:\Program Files\BraveSoftware\Brave-Browser\Application\brave.exe"
BRAVE_USER_DATA_DIR = r"C:\Users\YOUR_USERNAME\AppData\Local\BraveSoftware\Brave-Browser\User Data"

BLOCKED_DOMAINS = [
    "google.com",
    "google.co",
    "facebook.com",
    "instagram.com",
    "linkedin.com",
    "twitter.com",
    "x.com",
    "yelp.com",
    "wikipedia.org",
    "youtube.com",
    "tiktok.com",
    "pinterest.com",
    "reddit.com",
    "amazon.com",
    "trustpilot.com",
    "glassdoor.com",
    "indeed.com",
    "yellowpages.com",
    "bbb.org",
    "crunchbase.com",
    "clutch.co",
    "g2.com",
    "capterra.com",
    "tripadvisor.com",
    "mapquest.com",
    "bing.com",
    "yahoo.com",
    "apple.com",
    "microsoft.com",
]

# Logging
LOG_LEVEL = "INFO"
LOG_FILE = "logs/leadhunter.log"


def setup_logging():
    os.makedirs("logs", exist_ok=True)

    log_format = "[%(asctime)s] [%(levelname)s] [%(module)s] %(message)s"
    date_format = "%Y-%m-%d %H:%M:%S"

    logging.basicConfig(
        level=getattr(logging, LOG_LEVEL),
        format=log_format,
        datefmt=date_format,
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler(LOG_FILE),
        ],
    )
