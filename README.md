# LeadHunter Pro

Automated B2B lead generation CLI tool. Searches Google for company websites,
visits each site, and uses Claude AI to extract structured contact data —
exported to Excel, ready for outreach.

**No extra API cost.** Uses the Claude Code CLI (`claude -p`) included in your
existing Claude Pro subscription.

---

## Quick Start

```bash
# Install dependencies
pip install -r requirements.txt
playwright install chromium

# Initialize
python main.py init

# Create a campaign
python main.py campaign create \
    --name "Marketing Agencies Q1" \
    --niche "digital marketing agencies" \
    --country "Serbia"

# Run the full pipeline (scrape → enrich → export)
python main.py run \
    --campaign-id 1 \
    --query "marketing agencija Beograd" \
    --pages 5 \
    --output ./exports/
```

---

## How It Works

```
Google Search (Playwright)
       ↓
Company URLs → SQLite Database
       ↓
Page Scraping (aiohttp + BeautifulSoup)
       ↓
AI Extraction (Claude Code CLI)
       ↓
Excel Export (openpyxl)
```

Each step is resumable — interrupt at any point and re-run to continue from
where it stopped.

---

## Commands

| Command | Description |
|---------|-------------|
| `campaign create` | Create a named campaign |
| `campaign list` | List all campaigns |
| `scrape` | Collect company URLs from Google |
| `enrich` | Visit URLs and extract lead data with AI |
| `export` | Export leads to Excel |
| `run` | Full pipeline in one command |
| `status` | Show campaign statistics |
| `dashboard` | Live progress monitor |

```bash
python main.py --help
python main.py run --help
```

---

## What Gets Extracted

| Field | Example |
|-------|---------|
| Company Name | Acme Digital d.o.o. |
| Industry | Digital Marketing |
| Company Size | 10–50 employees |
| Contact Name | Marko Petrovic |
| Contact Title | Managing Director |
| Contact Email | marko@acme.rs |
| Company Email | info@acme.rs |
| Company Phone | +381 11 123 4567 |
| Address | Bulevar Mihajla Pupina 10, Beograd |
| Clients Info | Worked with Telekom, NIS, Henkel |
| Quality Score | 8 / 10 |

---

## Project Structure

```
leadhunter-pro/
├── main.py                    # CLI entry point
├── config.py                  # Configuration & logging
├── pipeline_runner.py         # Full pipeline orchestration
├── requirements.txt
├── .env.example
├── database/                  # SQLAlchemy ORM + DatabaseManager
├── scrapers/                  # Playwright + Google URL scraper
├── enrichment/                # Page fetching + Claude AI extraction
├── export/                    # Excel exporter (openpyxl)
├── dashboard/                 # Rich terminal dashboard
├── utils/                     # RetryManager + ErrorHandler
└── tests/                     # 125+ pytest tests
```

---

## Tech Stack

| Component | Library |
|-----------|---------|
| Database | SQLAlchemy + SQLite |
| URL scraping | Playwright + Chromium |
| Page fetching | aiohttp |
| HTML parsing | BeautifulSoup4 |
| AI extraction | Claude Code CLI (`claude -p`) |
| Excel export | openpyxl |
| Terminal UI | Rich |

---

## Documentation

| Document | Description |
|----------|-------------|
| [Complete User Guide](docs/user/COMPLETE_USER_GUIDE.md) | Installation to export, all commands, troubleshooting, FAQ |
| [Architecture](docs/technical/ARCHITECTURE.md) | Component diagram, data flow, DB schema, config reference |
| [Integration & Error Handling](docs/technical/phase5_integration.md) | Retry logic, graceful shutdown, test strategy |
| [Enrichment — Technical](docs/technical/phase3_enrichment.md) | Claude Code CLI integration details |
| [Export & Dashboard Guide](docs/user/phase4_export_guide.md) | Excel output and terminal dashboard usage |

---

## Configuration

Copy `.env.example` to `.env`:

```bash
cp .env.example .env
```

Key settings:

```bash
SEARCH_PAGES_DEFAULT=5          # Google result pages per query
PLAYWRIGHT_HEADLESS=true        # Hide browser window
CLAUDE_CODE_MAX_CONCURRENT=3    # Parallel Claude CLI processes

# Optional: direct Anthropic API (faster, billed separately)
# ANTHROPIC_API_KEY=sk-ant-...
```

---

## Testing

```bash
# All tests (no browser required)
pytest --ignore=tests/test_url_scraper.py -v

# Integration tests only
pytest tests/test_integration.py -v

# Full suite (requires Chromium)
pytest -v
```

---

## License

MIT
