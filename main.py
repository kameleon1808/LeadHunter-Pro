import config
from database import DatabaseManager


def main():
    config.setup_logging()

    import logging
    logger = logging.getLogger(__name__)

    db = DatabaseManager(config.DATABASE_PATH)
    db.initialize_db()

    logger.info("LeadHunter Pro initialised successfully")
    print("LeadHunter Pro initialized successfully")


if __name__ == "__main__":
    main()
