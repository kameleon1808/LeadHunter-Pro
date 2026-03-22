# Phase 5 — Integration, Error Handling & System Testing

## Overview

Phase 5 finalises LeadHunter Pro by wiring together all pipeline components
with production-grade error handling, exponential-backoff retry logic, graceful
shutdown, and a full integration-test suite.

New modules introduced in this phase:

| Module | Purpose |
|--------|---------|
| `utils/retry_manager.py` | Exponential backoff for transient I/O failures |
| `utils/error_handler.py` | Centralised error categorisation and SIGINT handling |
| `pipeline_runner.py` | Orchestrates scrape → enrich → export in one command |
| `tests/test_integration.py` | End-to-end tests against a real SQLite database |

---

## Component Interaction

```
main.py  ──  run command
              │
              └─► PipelineRunner.run_full_pipeline()
                     │
                     ├─[Step 1] URLScraper.search_and_collect()
                     │          wrapped in RetryManager.exponential_backoff()
                     │
                     ├─[Step 2] EnrichmentPipeline.process_campaign()
                     │          └─► ClaudeCodeExtractor._call_claude()  (subprocess)
                     │              PageScraper.scrape_multiple_pages()  (aiohttp)
                     │
                     └─[Step 3] ExcelExporter.export_campaign()
```

---

## Error Handling Strategy

### Error Categories

`ErrorHandler.categorize()` maps every exception to one of five categories:

| Category | Trigger conditions |
|----------|--------------------|
| `NETWORK` | `ConnectionError`, `TimeoutError`, `OSError`, aiohttp errors, "timeout/connection/network" in message |
| `PARSING` | `json.JSONDecodeError`, `ValueError`, `UnicodeDecodeError`, "json/parse/decode" in message |
| `AI_API` | "claude"/"anthropic" in message, `FileNotFoundError` for claude binary, subprocess errors |
| `DATABASE` | `SQLAlchemyError`, "sqlalchemy"/"sqlite"/"database" in message |
| `UNKNOWN` | Everything else |

### Retry Policy

`RetryManager` retries on `NETWORK` errors and selected HTTP status codes:

```
Retryable:     ConnectionError, TimeoutError, OSError, aiohttp.ClientConnectionError
               HTTP 429, 500, 502, 503, 504
Not retried:   JSONDecodeError, ValueError (permanent data errors)
               Authentication errors (would retry forever pointlessly)
```

Delay sequence for `max_retries=3, base_delay=2.0`:

| Attempt | Delay before next |
|---------|-------------------|
| 1       | 2 s               |
| 2       | 4 s               |
| 3       | raise             |

### Graceful Shutdown

`ErrorHandler.register_shutdown_handler(callback)` installs SIGINT (Ctrl+C)
and SIGTERM handlers. On signal:

1. Callback is called — `PipelineRunner._on_shutdown()` marks campaign `status="paused"` in DB
2. "State saved. Exiting." is printed
3. `sys.exit(0)` is called

Resuming a paused campaign:

```bash
python main.py run --campaign-id 1 --query "..." --pages 0
```

The pipeline skips scrape (URLs already exist) and re-processes only
URLs still in `status="pending"`.

---

## PipelineRunner Logic

```python
# Step 1: Scrape — skipped if URLs already in DB
if stats["total_urls"] == 0:
    await self._run_scrape(search_query, num_pages)

# Step 2: Enrich — skipped if no pending URLs
if stats["pending_urls"] > 0:
    await self._run_enrich()

# Step 3: Export — always runs
file_path = self._run_export(output_dir)
```

This makes `run` naturally resumable:
- First run: all 3 steps execute
- After Ctrl+C during enrich: restart → scrape skipped, enrich continues from last `pending` URL
- After full completion: restart → scrape + enrich both skipped, fresh export generated

---

## Concurrency Model

Two independent semaphores prevent resource exhaustion:

| Semaphore | Default | Controls |
|-----------|---------|---------|
| `ENRICHMENT_CONCURRENT_REQUESTS` | 5 | Simultaneous aiohttp page fetches |
| `CLAUDE_CODE_MAX_CONCURRENT` | 3 | Simultaneous `claude -p` subprocesses |

`asyncio.gather()` is used inside `EnrichmentPipeline` with these semaphores
rather than `asyncio.Semaphore` at the gather level, so the pipeline processes
all URLs truly concurrently up to the configured limits.

---

## Integration Tests

`tests/test_integration.py` runs 31 tests against a real temporary SQLite
database (`tmp_path` fixture from pytest). All network and AI calls are mocked.

### Test Classes

| Class | Scenario |
|-------|---------|
| `TestFullPipelineSmall` | 10 mock URLs, all return leads — verifies counts and export creation |
| `TestResumeAfterFailure` | 5 URLs pre-marked completed; verifies only 5 pending processed |
| `TestConcurrentProcessing` | Flaky analyse function; verifies error tolerance and semaphore |
| `TestDataIntegrity` | Field values, quality score range 1–10, null handling |
| `TestExportAfterPipeline` | File created, row count matches leads in DB |
| `TestRetryManager` | Backoff delays, retryable vs non-retryable classification |
| `TestErrorHandler` | Categorisation for all 5 categories, report generation |

### Running Tests

```bash
# All tests (excludes Playwright browser tests)
pytest --ignore=tests/test_url_scraper.py -v

# Integration tests only
pytest tests/test_integration.py -v

# Full suite including browser tests (requires Chromium)
pytest -v
```

---

## Performance Notes

| Operation | Rate | Notes |
|-----------|------|-------|
| URL scraping | ~50–100 URLs / page | Playwright, 1 browser instance |
| Page fetching | ~5 concurrent | aiohttp + semaphore |
| Claude Code CLI | ~12s per URL | Subprocess startup overhead |
| 300 URLs enrichment | ~20 min | 3 concurrent CLI processes |
| Excel export | < 5s | openpyxl, all in memory |

The ~12s overhead per Claude CLI call is inherent to subprocess initialisation.
For large campaigns, the Anthropic API (`AIExtractor`) is significantly faster
but requires a paid API key.
