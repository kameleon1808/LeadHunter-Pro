# LeadHunter Pro

Automated business lead generation tool. Scrapes target websites, extracts company
and contact information, and stores everything in a local SQLite database organised
into campaigns.

## Quick Start

```bash
# Install dependencies
pip install -r requirements.txt

# Initialise the database
python main.py
# Output: LeadHunter Pro initialized successfully

# Run the test suite
pytest tests/
```

## Project Structure

```
leadhunter-pro/
├── main.py                          # Entry point
├── config.py                        # Configuration & logging setup
├── requirements.txt
├── database/
│   ├── __init__.py
│   ├── models.py                    # SQLAlchemy ORM models
│   └── db_manager.py               # DatabaseManager class
├── tests/
│   ├── __init__.py
│   └── test_database.py            # pytest test suite
├── docs/
│   ├── technical/
│   │   └── phase1_database.md      # Full technical reference
│   └── user/
│       └── phase1_getting_started.md  # Beginner-friendly guide
├── data/                            # Created on first run
│   └── leadhunter.db
└── logs/                            # Created on first run
    └── leadhunter.log
```

## Requirements

- Python 3.10+
- See `requirements.txt` for package dependencies

## Documentation

| Audience    | Document                                      |
|-------------|-----------------------------------------------|
| Developers  | `docs/technical/phase1_database.md`           |
| End users   | `docs/user/phase1_getting_started.md`         |

## Configuration

Edit `config.py` to change defaults:

| Setting         | Default                 | Description                    |
|-----------------|-------------------------|--------------------------------|
| `DATABASE_PATH` | `data/leadhunter.db`    | SQLite database location       |
| `CHUNK_SIZE`    | `300`                   | URLs processed per chunk       |
| `MAX_RETRIES`   | `3`                     | Retry limit per failed URL     |
| `LOG_LEVEL`     | `INFO`                  | Logging verbosity              |
| `LOG_FILE`      | `logs/leadhunter.log`   | Log file path                  |

## Database Schema (summary)

| Table              | Purpose                                  |
|--------------------|------------------------------------------|
| `campaigns`        | Top-level scraping projects              |
| `urls`             | Individual URLs to scrape per campaign   |
| `leads`            | Extracted company/contact data           |
| `scraping_chunks`  | URL batch tracking for parallel scraping |
