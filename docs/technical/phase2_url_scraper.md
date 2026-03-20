# Phase 2 — URL Scraper: Technical Reference

## Overview

The URL Scraper module (`scrapers/`) collects company website URLs from Google search results
using Playwright browser automation. It is designed to behave like a real human user:
random delays, viewport rotation, user-agent rotation, and human-like scrolling.

---

## Module Structure

```
scrapers/
├── __init__.py          # Public exports
├── url_scraper.py       # URLScraper class (Playwright, async)
└── scraper_utils.py     # Pure utility functions (no browser dependency)
```

---

## URLScraper Class API

### Constructor

```python
URLScraper(db_manager: DatabaseManager, campaign_id: int)
```

| Parameter     | Type              | Description                                      |
|---------------|-------------------|--------------------------------------------------|
| `db_manager`  | `DatabaseManager` | Initialised DB manager from Phase 1              |
| `campaign_id` | `int`             | ID of the campaign to attach collected URLs to   |

---

### `async start_browser() -> None`

Launches a Chromium browser instance with anti-detection settings.

**What it does:**

1. Starts the Playwright async context.
2. Launches Chromium with `headless=config.PLAYWRIGHT_HEADLESS` (default `False`).
3. Creates a browser context with:
   - A randomly selected user agent from the pool of 10 real desktop UAs.
   - A randomly selected viewport (1280–1920px wide).
   - `locale="en-US"` and `timezone_id="America/New_York"`.
4. Injects an init script that masks `navigator.webdriver`.

---

### `async close_browser() -> None`

Closes the browser context, browser instance, and Playwright process. Always call this
in a `finally` block to avoid zombie browser processes.

---

### `async search_and_collect(query: str, num_pages: int = 5) -> List[str]`

Main scraping method. Performs a Google search and collects company URLs.

| Parameter   | Type   | Default | Description                          |
|-------------|--------|---------|--------------------------------------|
| `query`     | `str`  | —       | Google search query string           |
| `num_pages` | `int`  | `5`     | Number of result pages to paginate   |

**Returns:** `List[str]` — deduplicated list of collected URLs (unique by domain).

**Flow:**

```
For each page (0 … num_pages-1):
  1. Navigate to Google Search with ?start=page*10
  2. Wait for domcontentloaded
  3. Random delay (MIN_DELAY_SECONDS – MAX_DELAY_SECONDS)
  4. Check for CAPTCHA → if found, pause for manual solve
  5. Human-like scroll through the page
  6. Extract organic result URLs (_extract_urls_from_page)
  7. Filter already-seen URLs
  8. Bulk-save new URLs to database
  9. Check for "Next" button → stop early if absent
  10. Random delay before next page
```

---

### `async _extract_urls_from_page(page) -> List[str]`

Extracts organic result URLs from the current Google search result page.

**Selector strategy:**

```javascript
document.querySelectorAll('#search a[href], #rso a[href]')
```

Only `http`/`https` links are kept. Google-internal redirect links (`/url?q=…`) are
unwrapped to their real destination.

**Filters applied:**

- Must pass `is_valid_url()` check.
- Domain must not appear in `BLOCKED_DOMAINS` (`is_blocked_domain()`).
- URL is normalized via `normalize_url()` before storage.

---

### `async _human_like_scroll(page) -> None`

Scrolls the page from top to bottom in random increments of 200–500 px with 100–400 ms
pauses between steps.

---

### `async _random_delay(min_sec=1.5, max_sec=4.0) -> None`

Awaits `asyncio.sleep(random.uniform(min_sec, max_sec))`.
Defaults are read from `config.MIN_DELAY_SECONDS` / `config.MAX_DELAY_SECONDS`.

---

## scraper_utils Module

### `normalize_url(url: str) -> str`

- Prepends `https://` if no scheme is present.
- Upgrades `http://` to `https://`.
- Lowercases the domain.
- Strips UTM/tracking parameters: `utm_source`, `utm_medium`, `utm_campaign`,
  `utm_term`, `utm_content`, `utm_id`, `fbclid`, `gclid`, `msclkid`, `ref`, `referrer`.
- Removes trailing slashes from paths.
- Strips URL fragments (`#section`).

```python
normalize_url("http://EXAMPLE.COM/?utm_source=google#top")
# → "https://example.com"
```

---

### `is_valid_url(url: str) -> bool`

Returns `True` if `url` is a well-formed `http` or `https` URL with a non-empty netloc.

---

### `extract_domain(url: str) -> str`

Returns the bare domain without `www.` prefix or port number.

```python
extract_domain("https://www.myagency.rs:443/about")
# → "myagency.rs"
```

---

### `deduplicate_urls(urls: List[str]) -> List[str]`

Removes URLs that share the same domain as an earlier URL in the list.
Preserves first-seen order.

```python
deduplicate_urls(["https://acme.com", "https://acme.com/about", "https://beta.com"])
# → ["https://acme.com", "https://beta.com"]
```

---

### `BLOCKED_DOMAINS`

A list of domain strings (without scheme) that are always filtered out. Currently
includes 29 domains covering social networks, directories, review sites, and ad
platforms. The same list is mirrored in `config.BLOCKED_DOMAINS` for runtime access.

---

## Anti-Detection Measures

| Measure                          | Implementation                                                       |
|----------------------------------|----------------------------------------------------------------------|
| User-agent rotation              | 10 real desktop UAs, one chosen randomly per browser session         |
| Randomised viewport              | 5 realistic resolutions, one chosen randomly per session             |
| `navigator.webdriver` masking    | `add_init_script` injects property override before any page loads    |
| No automation flags              | `--disable-blink-features=AutomationControlled` in Chromium args     |
| Human-like scrolling             | Random scroll increments with short pauses                           |
| Random delays between actions    | `asyncio.sleep(random.uniform(min, max))` between every major step   |
| Visible browser                  | `PLAYWRIGHT_HEADLESS = False` — matches real user behaviour profile  |

---

## CAPTCHA Handling Flow

```
1. After navigating to each search result page:
   → check page URL and body text for CAPTCHA indicators
      ("sorry", "recaptcha", "captcha", "unusual traffic", "automated queries")

2. If CAPTCHA detected:
   → log WARNING
   → print message to console asking user to solve CAPTCHA in the browser
   → await input() — script pauses until user presses ENTER

3. After ENTER:
   → check page again
   → if CAPTCHA still present → log ERROR, stop scraping
   → if resolved → continue with next page
```

The browser is kept visible (`PLAYWRIGHT_HEADLESS = False`) specifically to support
this manual CAPTCHA resolution flow.

---

## Configuration Options (`config.py`)

| Variable               | Default | Description                                      |
|------------------------|---------|--------------------------------------------------|
| `PLAYWRIGHT_HEADLESS`  | `False` | Run browser visibly (required for CAPTCHA solve) |
| `SEARCH_PAGES_DEFAULT` | `5`     | Default number of Google pages per search        |
| `MIN_DELAY_SECONDS`    | `1.5`   | Minimum random delay between actions             |
| `MAX_DELAY_SECONDS`    | `4.0`   | Maximum random delay between actions             |
| `BLOCKED_DOMAINS`      | list    | Domains to always skip during URL extraction     |

---

## Error Handling

| Scenario                        | Behaviour                                              |
|---------------------------------|--------------------------------------------------------|
| Navigation timeout              | Logs warning, stops pagination for current session     |
| CAPTCHA detected                | Pauses for manual solve, stops if still present after  |
| No "Next" button found          | Stops pagination early (fewer results than requested)  |
| Invalid URL extracted           | Silently skipped by `is_valid_url()` check             |
| Database error                  | Propagated — the caller (`main.py`) sees the exception |
| Browser not started             | `RuntimeError` raised by `search_and_collect()`        |

---

## Code Examples

### Minimal usage

```python
import asyncio
import config
from database import DatabaseManager
from scrapers import URLScraper

async def main():
    db = DatabaseManager(config.DATABASE_PATH)
    db.initialize_db()

    # Assumes campaign with id=1 already exists
    scraper = URLScraper(db_manager=db, campaign_id=1)
    await scraper.start_browser()
    try:
        urls = await scraper.search_and_collect(
            query="digital marketing agencies in Belgrade",
            num_pages=5,
        )
        print(f"Collected {len(urls)} URLs")
    finally:
        await scraper.close_browser()

asyncio.run(main())
```

### CLI usage

```bash
python main.py scrape --campaign-id 1 --query "marketing agencies in Serbia" --pages 10
```

### Running tests

```bash
# Unit tests only (no browser required)
pytest tests/test_url_scraper.py -v

# Include integration tests (browser must be available)
pytest tests/test_url_scraper.py -v -m integration
```

---

## Dependencies

- `playwright>=1.40.0` — browser automation
- After installing: `playwright install chromium`
