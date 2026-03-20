import logging
import os

# Database
DATABASE_PATH = "data/leadhunter.db"

# Scraping
CHUNK_SIZE = 300
MAX_RETRIES = 3

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
