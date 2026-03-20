# Phase 1 — Database Layer: Technical Documentation

## 1. Architecture Overview

LeadHunter Pro uses a layered architecture:

```
main.py
  └─ DatabaseManager   (database/db_manager.py)
       └─ SQLAlchemy ORM
            └─ SQLite  (data/leadhunter.db)
```

All persistence is handled through `DatabaseManager`, which wraps SQLAlchemy sessions.
Each public method opens its own `Session`, commits, then expunges returned objects so
callers receive detached (plain Python) instances that are safe to use outside a
session context.

Models are defined in `database/models.py` using SQLAlchemy's **Declarative** API
(SQLAlchemy ≥ 2.0 style with `DeclarativeBase`).

---

## 2. Database Schema

### 2.1 Table: `campaigns`

| Column            | Type      | Constraints                                      | Default         |
|-------------------|-----------|--------------------------------------------------|-----------------|
| `id`              | INTEGER   | PRIMARY KEY, AUTOINCREMENT                       |                 |
| `name`            | TEXT      | NOT NULL                                         |                 |
| `niche`           | TEXT      | NOT NULL                                         |                 |
| `target_country`  | TEXT      |                                                  | NULL            |
| `status`          | TEXT      | `pending\|running\|paused\|completed\|failed`    | `'pending'`     |
| `created_at`      | DATETIME  |                                                  | `utcnow()`      |
| `updated_at`      | DATETIME  | auto-updated on write                            | `utcnow()`      |
| `total_urls`      | INTEGER   |                                                  | `0`             |
| `processed_urls`  | INTEGER   |                                                  | `0`             |
| `total_leads`     | INTEGER   |                                                  | `0`             |

### 2.2 Table: `urls`

| Column           | Type      | Constraints                                              | Default     |
|------------------|-----------|----------------------------------------------------------|-------------|
| `id`             | INTEGER   | PRIMARY KEY, AUTOINCREMENT                               |             |
| `campaign_id`    | INTEGER   | NOT NULL, FOREIGN KEY → `campaigns.id`                  |             |
| `url`            | TEXT      | NOT NULL                                                 |             |
| `status`         | TEXT      | `pending\|processing\|completed\|failed\|skipped`        | `'pending'` |
| `retry_count`    | INTEGER   |                                                          | `0`         |
| `created_at`     | DATETIME  |                                                          | `utcnow()`  |
| `processed_at`   | DATETIME  |                                                          | NULL        |
| `error_message`  | TEXT      |                                                          | NULL        |

### 2.3 Table: `leads`

| Column             | Type      | Constraints                             | Default    |
|--------------------|-----------|-----------------------------------------|------------|
| `id`               | INTEGER   | PRIMARY KEY, AUTOINCREMENT              |            |
| `campaign_id`      | INTEGER   | NOT NULL, FOREIGN KEY → `campaigns.id` |            |
| `url_id`           | INTEGER   | NOT NULL, FOREIGN KEY → `urls.id`      |            |
| `company_name`     | TEXT      |                                         | NULL       |
| `company_size`     | TEXT      |                                         | NULL       |
| `industry`         | TEXT      |                                         | NULL       |
| `website_url`      | TEXT      |                                         | NULL       |
| `description`      | TEXT      |                                         | NULL       |
| `contact_name`     | TEXT      |                                         | NULL       |
| `contact_title`    | TEXT      |                                         | NULL       |
| `contact_email`    | TEXT      |                                         | NULL       |
| `contact_linkedin` | TEXT      |                                         | NULL       |
| `company_email`    | TEXT      |                                         | NULL       |
| `company_phone`    | TEXT      |                                         | NULL       |
| `address`          | TEXT      |                                         | NULL       |
| `clients_info`     | TEXT      |                                         | NULL       |
| `raw_data`         | TEXT      |                                         | NULL       |
| `quality_score`    | INTEGER   |                                         | NULL       |
| `created_at`       | DATETIME  |                                         | `utcnow()` |

### 2.4 Table: `scraping_chunks`

| Column            | Type      | Constraints                             | Default     |
|-------------------|-----------|-----------------------------------------|-------------|
| `id`              | INTEGER   | PRIMARY KEY, AUTOINCREMENT              |             |
| `campaign_id`     | INTEGER   | NOT NULL, FOREIGN KEY → `campaigns.id` |             |
| `chunk_number`    | INTEGER   |                                         |             |
| `start_index`     | INTEGER   |                                         |             |
| `end_index`       | INTEGER   |                                         |             |
| `status`          | TEXT      | `pending\|processing\|completed\|failed`| `'pending'` |
| `processed_count` | INTEGER   |                                         | `0`         |
| `created_at`      | DATETIME  |                                         | `utcnow()`  |
| `completed_at`    | DATETIME  |                                         | NULL        |

---

## 3. DatabaseManager API Reference

All methods are synchronous. Sessions are managed internally — callers never touch
a session directly.

### 3.1 Initialisation

```python
DatabaseManager(db_path: str)
```
Constructor. Creates the `data/` directory if missing. Does **not** create tables —
call `initialize_db()` first.

```python
initialize_db() -> None
```
Runs `CREATE TABLE IF NOT EXISTS` for all four tables. Safe to call multiple times.

```python
get_existing_tables() -> List[str]
```
Returns the names of tables that currently exist. Useful for health checks.

---

### 3.2 Campaign Methods

```python
create_campaign(name: str, niche: str, target_country: str | None = None) -> Campaign
```
Creates and returns a new `Campaign` with `status='pending'`.

```python
get_campaign(campaign_id: int) -> Campaign | None
```
Returns the `Campaign` with the given id, or `None` if not found.

```python
get_all_campaigns() -> List[Campaign]
```
Returns every campaign in the database, unordered.

```python
update_campaign_status(campaign_id: int, status: str) -> None
```
Updates `status` and `updated_at`. Valid values: `pending`, `running`, `paused`,
`completed`, `failed`. Raises `ValueError` for unknown values or missing campaigns.

---

### 3.3 URL Methods

```python
add_url(campaign_id: int, url: str) -> URL
```
Inserts a single URL and increments `campaigns.total_urls`.

```python
add_urls_bulk(campaign_id: int, urls_list: List[str]) -> int
```
Bulk-inserts a list of URLs in one transaction. Returns the count inserted.
Increments `campaigns.total_urls` by that count.

```python
get_pending_urls(campaign_id: int, limit: int = 100) -> List[URL]
```
Returns up to `limit` URLs with `status='pending'` for the given campaign.

```python
update_url_status(url_id: int, status: str, error_message: str | None = None) -> None
```
Updates URL status and `processed_at`. When `status='failed'`, also increments
`retry_count`. When status is terminal (`completed`, `failed`, `skipped`), increments
`campaigns.processed_urls`.

---

### 3.4 Lead Methods

```python
add_lead(campaign_id: int, url_id: int, lead_data: dict) -> Lead
```
Creates a `Lead` from the provided dict. Valid keys mirror the `leads` table columns
(excluding `id`, `campaign_id`, `url_id`, `created_at`). Increments
`campaigns.total_leads`.

```python
get_leads(campaign_id: int) -> List[Lead]
```
Returns all leads for a campaign.

---

### 3.5 Stats

```python
get_campaign_stats(campaign_id: int) -> dict
```
Returns:
```python
{
    "campaign_id": int,
    "campaign_name": str,
    "campaign_status": str,
    "total_urls": int,
    "pending_urls": int,
    "completed_urls": int,
    "failed_urls": int,
    "total_leads": int,
}
```

---

### 3.6 Chunk Methods

```python
create_chunks(campaign_id: int, chunk_size: int = 300) -> List[ScrapingChunk]
```
Divides all URLs of a campaign into sequential chunks of `chunk_size`. Returns the
created `ScrapingChunk` objects ordered by `chunk_number`.

```python
get_pending_chunks(campaign_id: int) -> List[ScrapingChunk]
```
Returns all chunks with `status='pending'`, ordered by `chunk_number`.

```python
update_chunk_status(chunk_id: int, status: str) -> None
```
Updates chunk status. When `status='completed'`, also sets `completed_at`.

---

## 4. Configuration Reference (`config.py`)

| Constant        | Default                  | Description                        |
|-----------------|--------------------------|------------------------------------|
| `DATABASE_PATH` | `"data/leadhunter.db"`   | Path to the SQLite database file   |
| `CHUNK_SIZE`    | `300`                    | URLs per scraping chunk            |
| `MAX_RETRIES`   | `3`                      | Max retry attempts per URL         |
| `LOG_LEVEL`     | `"INFO"`                 | Logging verbosity                  |
| `LOG_FILE`      | `"logs/leadhunter.log"`  | Log file path                      |

Call `config.setup_logging()` once at startup to initialise console + file handlers.

---

## 5. Initialisation & Usage Examples

### Initialise the database

```python
from database import DatabaseManager
import config

config.setup_logging()
db = DatabaseManager(config.DATABASE_PATH)
db.initialize_db()
```

### Create a campaign and add URLs

```python
campaign = db.create_campaign("Q2 Outreach", "SaaS", "US")

urls = ["https://company-a.com", "https://company-b.com"]
count = db.add_urls_bulk(campaign.id, urls)
print(f"Added {count} URLs")
```

### Process URLs in chunks

```python
db.update_campaign_status(campaign.id, "running")
chunks = db.create_chunks(campaign.id, chunk_size=config.CHUNK_SIZE)

for chunk in chunks:
    db.update_chunk_status(chunk.id, "processing")
    pending = db.get_pending_urls(campaign.id, limit=config.CHUNK_SIZE)

    for url in pending:
        db.update_url_status(url.id, "processing")
        try:
            lead_data = {"company_name": "Scraped Co", "quality_score": 70}
            db.add_lead(campaign.id, url.id, lead_data)
            db.update_url_status(url.id, "completed")
        except Exception as e:
            db.update_url_status(url.id, "failed", error_message=str(e))

    db.update_chunk_status(chunk.id, "completed")

db.update_campaign_status(campaign.id, "completed")
```

### Fetch stats

```python
stats = db.get_campaign_stats(campaign.id)
print(stats)
```

---

## 6. Error Handling

| Situation                       | Behaviour                                              |
|---------------------------------|--------------------------------------------------------|
| Invalid status value            | `ValueError` raised with a descriptive message        |
| Missing campaign / URL / chunk  | `ValueError` raised                                   |
| Foreign key violation           | SQLAlchemy `IntegrityError` propagated to caller      |
| Duplicate / constraint error    | SQLAlchemy `IntegrityError` propagated to caller      |

All database operations are wrapped in a `with Session(...) as session` block.
The session is rolled back automatically on any unhandled exception (SQLAlchemy
default behaviour).

Callers should catch `ValueError` for business-logic errors and
`sqlalchemy.exc.IntegrityError` for constraint violations.
