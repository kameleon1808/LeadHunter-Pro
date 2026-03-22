# LeadHunter Pro — Technical Architecture

## High-Level Overview

```
┌─────────────────────────────────────────────────────────────────────┐
│                        main.py  (CLI entry point)                   │
│  init │ campaign create/list │ scrape │ enrich │ export │ dashboard  │
│       status │ run (full pipeline)                                   │
└───────────────────────────────┬─────────────────────────────────────┘
                                │
              ┌─────────────────┼──────────────────┐
              ▼                 ▼                  ▼
    ┌──────────────────┐ ┌───────────────┐ ┌──────────────────┐
    │  scrapers/       │ │  enrichment/  │ │  export/         │
    │  URLScraper      │ │  Pipeline     │ │  ExcelExporter   │
    │  (Playwright +   │ │  PageScraper  │ │                  │
    │   Google)        │ │  ClaudeCode   │ │  dashboard/      │
    └────────┬─────────┘ │  Extractor    │ │  CLIDashboard    │
             │           └──────┬────────┘ └──────────────────┘
             │                  │
             ▼                  ▼
    ┌──────────────────────────────────────────┐
    │           database/                      │
    │           DatabaseManager (SQLAlchemy)   │
    │           SQLite  leadhunter.db          │
    └──────────────────────────────────────────┘
```

---

## Module Reference

### `database/`

| File | Class | Responsibility |
|------|-------|----------------|
| `database_manager.py` | `DatabaseManager` | All DB operations: campaigns, URLs, leads, chunks |
| `models.py` | `Campaign`, `URL`, `Lead`, `ScrapingChunk` | SQLAlchemy ORM models |

**Key methods:**

```python
db = DatabaseManager("leadhunter.db")
db.initialize_db()                              # create tables
db.create_campaign(name, niche, country)        # → Campaign
db.add_url(campaign_id, url)                    # → URL (skip if duplicate)
db.get_pending_urls(campaign_id)                # → List[URL]
db.mark_url_completed(url_id)
db.mark_url_failed(url_id, reason)
db.add_lead(campaign_id, url_id, **fields)      # → Lead
db.get_leads(campaign_id)                       # → List[Lead]
db.get_campaign_stats(campaign_id)              # → dict with counts
```

### `scrapers/`

| File | Class | Responsibility |
|------|-------|----------------|
| `url_scraper.py` | `URLScraper` | Playwright + Google: collect company URLs |

**Flow:**

1. Launch Chromium (headless by default)
2. Navigate to Google, search query
3. Extract `<a href>` links, filter to company domains
4. Persist to DB via `db.add_url()`
5. Paginate through N result pages

### `enrichment/`

| File | Class | Responsibility |
|------|-------|----------------|
| `enrichment_pipeline.py` | `EnrichmentPipeline` | Orchestrates enrichment for all pending URLs |
| `page_scraper.py` | `PageScraper` | aiohttp: fetch pages, extract text/emails/phones |
| `claude_code_extractor.py` | `ClaudeCodeExtractor` | **Primary AI engine**: `claude -p` subprocess |
| `ai_extractor.py` | `AIExtractor` | Optional: Anthropic API (requires API key) |
| `site_analyzer.py` | `SiteAnalyzer` | Coordinates PageScraper + extractor |

**ClaudeCodeExtractor subprocess call:**

```bash
claude -p "<instruction>" \
    --output-format json \
    --json-schema '{"type":"object", ...}' \
    --no-session-persistence \
    --model claude-sonnet-4-5
# Content sent via stdin
```

**Lead extraction schema enforced by `--json-schema`:**

```json
{
  "company_name", "company_size", "industry", "description",
  "contact_name", "contact_title", "contact_email", "contact_linkedin",
  "company_email", "company_phone", "address", "clients_info",
  "quality_score"  ← integer 1–10, required
}
```

### `export/`

| File | Class | Responsibility |
|------|-------|----------------|
| `excel_exporter.py` | `ExcelExporter` | openpyxl: 3-sheet Excel workbook |

**Sheets generated:**

1. **Leads** — 15 columns, navy header, alternating row colours, filters, frozen row 1
2. **Stats** — campaign metadata and URL/lead counts
3. **Failed URLs** — URLs that errored during enrichment with reason

**Path resolution:** if output ends with `.xlsx`/`.xlsm` etc. → use as-is;
otherwise treat as directory and auto-generate `leads_<name>_campaign<id>_<date>.xlsx`.

### `dashboard/`

| File | Class | Responsibility |
|------|-------|----------------|
| `cli_dashboard.py` | `CLIDashboard` | Rich: live progress, stats, campaigns list |

**Key methods:**

```python
dash = CLIDashboard(db)
dash.show_campaigns_list()              # Table of all campaigns
dash.show_campaign_progress(id)         # Live 2s-refresh progress (Ctrl+C to exit)
dash.show_stats(id)                     # Single-shot stats panel
dash.show_leads_preview(id, limit=10)   # Last N leads as table
```

### `utils/`

| File | Class | Responsibility |
|------|-------|----------------|
| `retry_manager.py` | `RetryManager` | Exponential backoff for async/sync callables |
| `error_handler.py` | `ErrorHandler` | Error recording, categorisation, SIGINT handling |

### `pipeline_runner.py`

`PipelineRunner` wires scrape → enrich → export into a single resumable command:

```python
runner = PipelineRunner(db, campaign_id)
await runner.run_full_pipeline(search_query, num_pages, output_dir)
```

---

## Database Schema

```
campaigns
  id          INTEGER  PK
  name        TEXT
  niche       TEXT
  target_country TEXT
  status      TEXT     (active | paused | completed)
  created_at  DATETIME
  updated_at  DATETIME

urls
  id          INTEGER  PK
  campaign_id INTEGER  FK → campaigns.id
  url         TEXT     UNIQUE per campaign
  status      TEXT     (pending | completed | failed)
  error_msg   TEXT
  created_at  DATETIME
  updated_at  DATETIME

leads
  id              INTEGER  PK
  campaign_id     INTEGER  FK → campaigns.id
  url_id          INTEGER  FK → urls.id
  company_name    TEXT
  company_size    TEXT
  industry        TEXT
  description     TEXT
  contact_name    TEXT
  contact_title   TEXT
  contact_email   TEXT
  contact_linkedin TEXT
  company_email   TEXT
  company_phone   TEXT
  address         TEXT
  clients_info    TEXT
  quality_score   INTEGER  (1–10)
  created_at      DATETIME

scraping_chunks
  id          INTEGER  PK
  campaign_id INTEGER  FK → campaigns.id
  chunk_index INTEGER
  status      TEXT
  created_at  DATETIME
  updated_at  DATETIME
```

---

## Configuration Reference

All settings are in `config.py` and can be overridden via environment variables
or a `.env` file (loaded by `python-dotenv`).

| Variable | Default | Description |
|----------|---------|-------------|
| `DATABASE_PATH` | `leadhunter.db` | SQLite file location |
| `ANTHROPIC_API_KEY` | `None` | If set, uses Anthropic API instead of CLI |
| `CLAUDE_MODEL` | `claude-sonnet-4-5` | Model for both API and CLI |
| `SEARCH_PAGES_DEFAULT` | `5` | Google result pages per scrape |
| `PLAYWRIGHT_HEADLESS` | `True` | Headless browser mode |
| `ENRICHMENT_CONCURRENT_REQUESTS` | `5` | Parallel HTTP fetches |
| `CLAUDE_CODE_MAX_CONCURRENT` | `3` | Parallel CLI subprocesses |
| `MAX_PAGES_PER_SITE` | `5` | Pages visited per company |
| `REQUEST_TIMEOUT_SECONDS` | `30` | aiohttp timeout |

---

## Data Flow — Single URL Enrichment

```
URL (pending in DB)
    │
    ▼
PageScraper.fetch_page(base_url)
    │   aiohttp GET → BeautifulSoup HTML clean → text + emails + phones
    │
    ▼
PageScraper.find_key_pages(base_url)
    │   extract <a href> links → filter to same domain
    │
    ▼
ClaudeCodeExtractor.identify_key_pages(links)  [optional AI filter]
    │   claude -p "pick best pages" → List[str]
    │
    ▼
PageScraper.scrape_multiple_pages(key_pages)
    │   parallel aiohttp fetches (semaphore=5)
    │
    ▼
ClaudeCodeExtractor.extract_lead_data(pages_content)
    │   claude -p "extract lead" --json-schema → structured dict
    │
    ▼
Supplement: regex emails/phones not already in AI result
    │
    ▼
DatabaseManager.add_lead(campaign_id, url_id, **fields)
DatabaseManager.mark_url_completed(url_id)
```

---

## AI Integration

### Claude Code CLI (default)

- Binary: `claude` (must be on PATH)
- Protocol: stdin for content, `--json-schema` for response format
- Output field: `response["structured_output"]` → fallback to `response["result"]`
- Concurrency: limited by `CLAUDE_CODE_MAX_CONCURRENT` semaphore
- Overhead: ~12s per call (subprocess startup)
- Cost: included in Claude Pro plan

### Anthropic API (optional)

- Activated by setting `ANTHROPIC_API_KEY` env var
- Uses `anthropic` Python package (install separately: `pip install anthropic`)
- Much lower latency (~1–2s per call)
- Billed per token at Anthropic API pricing

---

## Testing Strategy

```
tests/
  test_database.py        Unit: CRUD operations, constraints, stats
  test_enrichment.py      Unit: PageScraper, ClaudeCodeExtractor, AIExtractor, Pipeline
  test_export.py          Unit: ExcelExporter sheets, columns, file path resolution
  test_integration.py     Integration: full pipeline against real SQLite (mocked AI/network)
  test_url_scraper.py     Integration: Playwright + real browser (requires Chromium)
```

Run without browser tests: `pytest --ignore=tests/test_url_scraper.py -v`
