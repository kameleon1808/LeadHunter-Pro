# Phase 3 — Lead Enrichment: Technical Reference

## Overview

Phase 3 adds an **enrichment pipeline** that takes the raw URLs collected in Phase 2 and transforms them into structured lead records. For each URL the pipeline:

1. Fetches the company home page and discovers key sub-pages (About, Contact, Team, …).
2. Scrapes and cleans the content of each page.
3. Sends the content to Claude AI via the **Claude Code CLI** (`claude -p`), which returns structured JSON with all lead fields.
4. Persists the result as a `Lead` record in the SQLite database.

**No separate Anthropic API key is required.** The pipeline uses the locally installed `claude` CLI, which is covered by your existing Claude Pro / Max plan.

---

## Architecture

```
EnrichmentPipeline
│
├── SiteAnalyzer                          # per-site orchestrator
│   ├── PageScraper (aiohttp)             # HTTP + HTML parsing
│   └── ClaudeCodeExtractor (claude CLI)  # AI extraction via subprocess
│
└── DatabaseManager (SQLAlchemy)          # read URLs / write Leads
```

**Extractor auto-selection** (in `main.py`):
```
ANTHROPIC_API_KEY not set → ClaudeCodeExtractor  (default, free)
ANTHROPIC_API_KEY is set  → AIExtractor           (optional, paid API)
```

All network I/O is `async`; HTTP concurrency is controlled with `asyncio.Semaphore(ENRICHMENT_CONCURRENT_REQUESTS)` (default 5). Claude CLI subprocess concurrency is separately controlled by `CLAUDE_CODE_MAX_CONCURRENT` (default 3).

---

## Module Reference

### `enrichment/page_scraper.py` — `PageScraper`

Async HTTP scraper built on **aiohttp**.

#### Methods

| Method | Signature | Description |
|--------|-----------|-------------|
| `fetch_page` | `async (url: str) -> dict` | Fetches a URL. Returns `{url, html, status_code, error}`. |
| `find_key_pages` | `async (base_url: str) -> List[str]` | Fetches `base_url`, parses all `<a>` tags, returns up to `MAX_PAGES_PER_SITE` internal links whose path matches key-page keywords. |
| `scrape_multiple_pages` | `async (urls: List[str]) -> List[dict]` | Concurrently fetches many URLs (bounded by `ENRICHMENT_CONCURRENT_REQUESTS`). |
| `_clean_html` | `(html: str) -> str` | Removes `<script>`, `<style>`, and other non-content tags. Returns plain text with normalised whitespace. |
| `_extract_emails` | `(text: str) -> List[str]` | Regex email extraction. Returns unique addresses. |
| `_extract_phones` | `(text: str) -> List[str]` | Regex phone extraction. Returns unique numbers with ≥7 digits. |
| `close` | `async () -> None` | Closes the underlying aiohttp session. |

#### Key-page keywords

```python
["about", "contact", "team", "people", "work", "services",
 "portfolio", "projects", "clients", "who-we-are",
 "our-team", "our-work", "our-services"]
```

---

### `enrichment/claude_code_extractor.py` — `ClaudeCodeExtractor` *(primary)*

Uses the **Claude Code CLI** (`claude -p`) as an async subprocess. No API key or additional payment required.

#### How it works

```bash
# Equivalent shell command for each URL:
echo "<page content>" | claude -p "instruction" \
    --output-format json \
    --json-schema '{"type":"object",...}' \
    --no-session-persistence \
    --model claude-sonnet-4-5
```

- Page content is piped via **stdin** to avoid shell argument length limits.
- `--json-schema` ensures Claude returns a **guaranteed-valid JSON** object (`structured_output` field) — no markdown fence stripping needed.
- `--no-session-persistence` prevents cluttering the Claude Code session history.
- Each subprocess call is wrapped in `asyncio.wait_for` with a 120 s timeout.

#### Constructor

```python
ClaudeCodeExtractor()   # no arguments — uses installed claude CLI
```

#### Methods

| Method | Signature | Description |
|--------|-----------|-------------|
| `identify_key_pages` | `async (all_links: List[str]) -> List[str]` | Asks Claude to filter a list of URLs to About/Contact/Team/Work pages. Returns subset of input list (hallucinated URLs are filtered out). |
| `extract_lead_data` | `async (pages_content: List[dict]) -> dict` | Sends cleaned page text to Claude. Returns structured lead dict. Returns `{}` on failure. |
| `_call_claude` | `async (instruction, content, schema) -> dict` | Core subprocess call. Returns `structured_output` dict or `{}` on any error. |

#### Lead extraction JSON schema (passed as `--json-schema`)

```json
{
  "type": "object",
  "properties": {
    "company_name":     {"type": ["string", "null"]},
    "company_size":     {"type": ["string", "null"]},
    "industry":         {"type": ["string", "null"]},
    "description":      {"type": ["string", "null"]},
    "contact_name":     {"type": ["string", "null"]},
    "contact_title":    {"type": ["string", "null"]},
    "contact_email":    {"type": ["string", "null"]},
    "contact_linkedin": {"type": ["string", "null"]},
    "company_email":    {"type": ["string", "null"]},
    "company_phone":    {"type": ["string", "null"]},
    "address":          {"type": ["string", "null"]},
    "clients_info":     {"type": ["string", "null"]},
    "quality_score":    {"type": "integer", "minimum": 1, "maximum": 10}
  },
  "required": ["quality_score"]
}
```

#### Error handling

| Situation | Behaviour |
|-----------|-----------|
| `claude` not in PATH | Logs error, returns `{}` |
| Subprocess timeout (120 s) | Process killed, returns `{}` |
| Non-zero exit code | Logs stderr, returns `{}` |
| Invalid JSON stdout | Logs warning, returns `{}` |
| Empty stdout | Logs warning, returns `{}` |

In all error cases the URL is marked `failed` in the DB and the pipeline continues with the next URL.

---

### `enrichment/ai_extractor.py` — `AIExtractor` *(optional)*

Alternative extractor using the **Anthropic Python SDK** directly. Requires `pip install anthropic` and `ANTHROPIC_API_KEY` environment variable. Automatically selected by `main.py` when the env var is set.

The `anthropic` package import is **lazy** (inside `__init__`) so the module loads without the package installed.

---

### `enrichment/site_analyzer.py` — `SiteAnalyzer`

Per-site orchestrator combining `PageScraper` and whichever extractor is active.

#### Constructor

```python
SiteAnalyzer(page_scraper: PageScraper, ai_extractor: ClaudeCodeExtractor | AIExtractor)
```

#### Methods

| Method | Signature | Description |
|--------|-----------|-------------|
| `analyse` | `async (base_url: str, use_ai_filter: bool = False) -> List[dict]` | Full site analysis. Returns list of `{url, text, emails, phones}` dicts. If `use_ai_filter=True`, Claude also filters the discovered links (costs extra subprocess calls). |

---

### `enrichment/enrichment_pipeline.py` — `EnrichmentPipeline`

Top-level driver for an entire campaign enrichment run.

#### Constructor

```python
EnrichmentPipeline(
    db_manager: DatabaseManager,
    ai_extractor: ClaudeCodeExtractor | AIExtractor,
    campaign_id: int,
)
```

#### Methods

| Method | Signature | Description |
|--------|-----------|-------------|
| `process_campaign` | `async (campaign_id: int) -> None` | Loads all pending URLs, splits into chunks of `CHUNK_SIZE`, processes each chunk, updates campaign status. |
| `process_chunk` | `async (chunk_id: int) -> None` | Processes a `ScrapingChunk` by its DB id. Sets chunk status to processing → completed. |
| `process_single_url` | `async (url_record: URL) -> Lead or None` | Full enrichment for one URL: analyse → extract → save lead. Updates URL status to completed / failed. |
| `_update_progress` | `(campaign_id: int) -> None` | Logs progress stats (processed / total, lead count). |

#### `process_single_url` flow

```
URL record
│
├── SiteAnalyzer.analyse(url)                 # fetch home + key pages
│   ├── PageScraper.find_key_pages()          # regex link discovery
│   └── PageScraper.scrape_multiple_pages()   # concurrent fetch + clean
│
├── ClaudeCodeExtractor.extract_lead_data()   # claude -p subprocess
│
├── Supplement: regex emails/phones fallback
│
└── DatabaseManager.add_lead()               # persist Lead row
    └── update_url_status("completed")
```

---

## Claude Code CLI Integration

| Property | Value |
|----------|-------|
| Binary | `claude` (must be in PATH) |
| Mode | `claude -p "instruction" --output-format json --json-schema '...' --no-session-persistence` |
| Content delivery | stdin pipe |
| Response field | `structured_output` (primary) → `result` (fallback) |
| Model | `config.CLAUDE_MODEL` (default: `claude-sonnet-4-5`) |
| Per-call timeout | 120 s |
| Subprocess overhead | ~10–12 s per call (CLI initialisation) |

---

## Chunking and Async Processing

- All pending URLs are loaded once; split into logical chunks of `CHUNK_SIZE` (default 300).
- HTTP fetching: `asyncio.Semaphore(ENRICHMENT_CONCURRENT_REQUESTS)` — default 5 parallel requests.
- Claude CLI calls: `asyncio.Semaphore(CLAUDE_CODE_MAX_CONCURRENT)` — default 3 parallel subprocesses.
- `asyncio.gather` runs all URLs in a chunk concurrently within both semaphore bounds.

---

## Rate Limiting and Error Handling

| Concern | Strategy |
|---------|----------|
| HTTP timeouts | `aiohttp.ClientTimeout(total=REQUEST_TIMEOUT_SECONDS)` (default 30 s) |
| Claude subprocess timeout | `asyncio.wait_for(..., timeout=120)` — process killed on expiry |
| Claude CLI not found | `FileNotFoundError` caught → returns `{}` → URL marked `failed` |
| Invalid JSON from Claude | Caught → returns `{}` → URL marked `failed` |
| Network errors | Caught in `fetch_page` → returns `{html: None}` |
| Max pages per site | `MAX_PAGES_PER_SITE` (default 5) prevents runaway crawling |

---

## Data Quality Scoring

Claude assigns a score 1–10 based on data completeness (enforced by `--json-schema`):

| Score | Meaning |
|-------|---------|
| 9–10 | Decision-maker name + email + full company profile |
| 7–8 | Good company info + partial contact details |
| 5–6 | Company info only, no personal contacts |
| 3–4 | Sparse info, maybe just a name and phone |
| 1–2 | Almost no usable data |

`quality_score` is always clamped to [1, 10] in `extract_lead_data()` after the subprocess call.

---

## Configuration Reference

All values live in `config.py`.

| Key | Default | Description |
|-----|---------|-------------|
| `CLAUDE_MODEL` | `"claude-sonnet-4-5"` | Model passed to `claude --model` flag |
| `CLAUDE_CODE_MAX_CONCURRENT` | `3` | Max parallel `claude -p` subprocesses |
| `MAX_PAGES_PER_SITE` | `5` | Max sub-pages fetched per company |
| `ENRICHMENT_CONCURRENT_REQUESTS` | `5` | Max parallel aiohttp HTTP requests |
| `REQUEST_TIMEOUT_SECONDS` | `30` | Per-request HTTP timeout (seconds) |
| `CHUNK_SIZE` | `300` | URLs per processing chunk |
| `ANTHROPIC_API_KEY` | `None` (from env) | Optional — activates `AIExtractor` if set |
