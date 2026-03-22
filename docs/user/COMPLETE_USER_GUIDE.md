# LeadHunter Pro — Complete User Guide

## Table of Contents

1. [Installation](#1-installation)
2. [First-Time Setup](#2-first-time-setup)
3. [Workflow Overview](#3-workflow-overview)
4. [Command Reference](#4-command-reference)
5. [Running the Full Pipeline](#5-running-the-full-pipeline)
6. [Understanding Your Results](#6-understanding-your-results)
7. [Tips for Better Leads](#7-tips-for-better-leads)
8. [Troubleshooting](#8-troubleshooting)
9. [FAQ](#9-faq)
10. [Glossary](#10-glossary)

---

## 1. Installation

### Prerequisites

- Python 3.10 or higher
- Claude Code CLI installed and authenticated (`claude --version`)
- Claude Pro subscription (or any paid Claude plan with CLI access)

### Steps

```bash
# 1. Clone the repository
git clone https://github.com/your-username/leadhunter-pro.git
cd leadhunter-pro

# 2. Create and activate virtual environment
python -m venv .venv

# Windows (PowerShell):
.venv\Scripts\Activate.ps1

# macOS / Linux:
source .venv/bin/activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Install Playwright browser
playwright install chromium

# 5. Copy and review environment config
cp .env.example .env
```

### Verify Installation

```bash
python main.py init
# Expected: "LeadHunter Pro initialized successfully"
```

---

## 2. First-Time Setup

### Environment Variables (`.env`)

Open `.env` in a text editor. The defaults work fine for most users.
Key settings to review:

```bash
# How many Google pages to scrape per search (more = more leads, slower)
SEARCH_PAGES_DEFAULT=5

# Run browser visibly or hidden (true = hidden, faster)
PLAYWRIGHT_HEADLESS=true

# How many websites to analyse at the same time
CLAUDE_CODE_MAX_CONCURRENT=3
```

### Do I Need an API Key?

No. LeadHunter Pro uses the **Claude Code CLI** (`claude -p`), which is
included in your Claude Pro subscription at no extra cost.

If you have an Anthropic API key and want faster enrichment, add it:

```bash
ANTHROPIC_API_KEY=sk-ant-your-key-here
```

When the API key is set, the Anthropic API is used instead of the CLI
(significantly faster, but billed per token).

---

## 3. Workflow Overview

```
Campaign → Scrape → Enrich → Export
```

| Step | What happens | Time estimate |
|------|-------------|---------------|
| **Campaign** | Create a named container for your leads | Instant |
| **Scrape** | Google search → collect company website URLs | 1–5 min |
| **Enrich** | Visit each site → Claude extracts contact data | 15–90 min |
| **Export** | Write leads to Excel | < 1 min |

---

## 4. Command Reference

### `campaign create` — Create a new campaign

```bash
python main.py campaign create \
    --name "Q1 Marketing Agencies" \
    --niche "digital marketing agencies" \
    --country "Serbia"           # optional
```

### `campaign list` — List all campaigns

```bash
python main.py campaign list
```

### `scrape` — Collect URLs from Google

```bash
python main.py scrape \
    --campaign-id 1 \
    --query "digital marketing agencies Belgrade" \
    --pages 5
```

- `--pages`: number of Google result pages (10 results per page = ~50 URLs per page)
- Results are saved to the database; duplicate URLs are skipped automatically

### `enrich` — Extract lead data from collected URLs

```bash
python main.py enrich --campaign-id 1
```

- Only processes URLs with `status=pending`
- Safe to interrupt (Ctrl+C) and resume — completed URLs are not reprocessed

### `export` — Export leads to Excel

```bash
# To a directory (auto-named file):
python main.py export --campaign-id 1 --output ./exports/

# To a specific file:
python main.py export --campaign-id 1 --output leads_q1.xlsx
```

### `run` — Full pipeline in one command

```bash
python main.py run \
    --campaign-id 1 \
    --query "marketing agencies Serbia" \
    --pages 5 \
    --output ./exports/
```

Runs scrape → enrich → export automatically. Resumable — if interrupted,
restart the same command and it continues from where it stopped.

### `status` — Campaign statistics and lead preview

```bash
python main.py status --campaign-id 1
```

Shows URL counts by status and a preview of the last 10 leads found.

### `dashboard` — Live progress monitor

```bash
python main.py dashboard --campaign-id 1
```

Refreshes every 2 seconds. Press **Ctrl+C** to exit.

---

## 5. Running the Full Pipeline

### Step-by-step example

```bash
# 1. Create campaign
python main.py campaign create \
    --name "Marketing Agencies Serbia 2025" \
    --niche "digital marketing" \
    --country "Serbia"
# → Campaign created — id=1

# 2. Run the full pipeline
python main.py run \
    --campaign-id 1 \
    --query "marketing agencija Beograd" \
    --pages 5 \
    --output ./exports/

# Pipeline output:
# ════════════════════════════════════════════════════════════
#   LeadHunter Pro — Full Pipeline
# ════════════════════════════════════════════════════════════
#   Campaign  : Marketing Agencies Serbia 2025
#   Niche     : digital marketing
#   Query     : marketing agencija Beograd
#   Pages     : 5
# ════════════════════════════════════════════════════════════
# [Step 1/3] Scraping URLs from Google…
#     ✓ Collected 43 unique URLs
# [Step 2/3] Enriching 43 URLs with Claude AI…
#     AI engine : Claude Code CLI
# [Step 3/3] Exporting leads to Excel…
#     ✓ Exported to: ./exports/leads_marketing_agencies_serbia_2025_campaign1_20250322.xlsx
```

### Running in the Background (while continuing your work)

On Windows PowerShell:

```powershell
Start-Process python -ArgumentList "main.py run --campaign-id 1 --query '...' --pages 5" -NoNewWindow
```

Check progress at any time:

```bash
python main.py status --campaign-id 1
```

### Resuming an Interrupted Run

If you press Ctrl+C or the process is killed, just run the same command again:

```bash
python main.py run --campaign-id 1 --query "..." --pages 5 --output ./exports/
```

LeadHunter Pro will:
- Skip scraping (URLs already collected)
- Continue enrichment from the last pending URL
- Export when done

---

## 6. Understanding Your Results

### Excel File — Leads Sheet

| Column | Description |
|--------|-------------|
| ID | Internal lead identifier |
| Company Name | Company name extracted by AI |
| Industry | Industry / niche |
| Company Size | Employee count estimate |
| Description | Short company description |
| Contact Name | Key person found on website |
| Contact Title | Their job title |
| Contact Email | Direct contact email |
| Contact LinkedIn | LinkedIn profile URL |
| Company Email | General company email |
| Company Phone | Company phone number |
| Address | Physical address |
| Clients Info | Notable clients or case studies |
| Quality Score | AI rating 1–10 (10 = best lead) |
| Source URL | Website that was analysed |

### Quality Score

The AI assigns a score from 1–10 based on:
- How much useful contact information was found
- How relevant the company appears to be to your niche
- Quality of the website and content

**Recommended filters:**
- Quality score ≥ 6 → solid leads
- Quality score ≥ 8 → high-priority outreach

### Excel File — Stats Sheet

Campaign-level summary: total URLs scraped, completed, failed, leads found.

### Excel File — Failed URLs

URLs where enrichment failed (site down, bot protection, no content).
You can manually check these and add leads if relevant.

---

## 7. Tips for Better Leads

### Search Query Tips

**Be specific:**
```
"digital marketing agency Belgrade site:rs"
"SEO agency Serbia filetype:html"
"marketing agencija Srbija"
```

**Use industry terms in target language:**
- Native-language queries return local results that English queries miss
- Add city names to narrow to a specific region

**Combine queries:**
- Run multiple scrape commands against the same campaign
- Duplicates are automatically deduplicated

```bash
python main.py scrape --campaign-id 1 --query "marketing agency Belgrade" --pages 3
python main.py scrape --campaign-id 1 --query "reklamna agencija Beograd" --pages 3
python main.py scrape --campaign-id 1 --query "digital marketing Novi Sad" --pages 2
```

### Concurrency vs. Quality

- Setting `CLAUDE_CODE_MAX_CONCURRENT=1` is slowest but most reliable if you hit rate limits
- `CLAUDE_CODE_MAX_CONCURRENT=5` is faster but may hit resource limits on slower machines

### Running Multiple Campaigns

Each campaign is independent. You can run different niches simultaneously
(in separate terminals) since they use separate database rows.

---

## 8. Troubleshooting

### "claude: command not found"

Claude Code CLI is not on your PATH.

1. Ensure you have Claude Code installed: `npm install -g @anthropic-ai/claude-code`
2. Restart your terminal after installation
3. Verify: `claude --version`

### Google is showing a CAPTCHA

Playwright was detected as a bot. Solutions:

1. Set `PLAYWRIGHT_HEADLESS=false` in `.env` to run visibly — harder to detect
2. Reduce `--pages` to scrape fewer pages per run
3. Add a delay between runs (search manually in browser first to pass CAPTCHA)

### Enrichment is very slow

Each URL takes ~12–15 seconds (Claude CLI startup overhead). This is normal.

For 100 URLs with 3 concurrent processes: `100 / 3 * 12s ≈ 7 minutes`

To speed up: set `ANTHROPIC_API_KEY` to use the direct API (~1–2s per URL).

### Excel file has no leads

The enrichment may not have found data. Check:

```bash
python main.py status --campaign-id 1
```

If `completed_urls > 0` but `total_leads = 0`, the scraped URLs may not be
company websites (could be directories, social media, etc.).

Try a more targeted search query with specific company keywords.

### "No pending URLs to enrich"

Scraping hasn't been run yet, or all URLs are already processed.

```bash
python main.py scrape --campaign-id 1 --query "..." --pages 5
```

### Permission error on `.venv\Scripts\Activate.ps1` (Windows)

```powershell
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
```

Then retry activation.

---

## 9. FAQ

**Q: Does this cost extra beyond my Claude Pro subscription?**

No. LeadHunter Pro uses the `claude -p` CLI command which is included in
Claude Pro. The optional `ANTHROPIC_API_KEY` is a separate product that's
billed per token — it's not required.

**Q: How accurate is the extracted data?**

Claude achieves ~85–90% accuracy on companies with well-structured websites.
Accuracy drops for sites with no About/Contact pages. Always verify key data
before outreach.

**Q: Can I add my own fields to the export?**

Modify `export/excel_exporter.py` — add columns to the `LEAD_COLUMNS` list
and ensure the corresponding database field exists.

**Q: Is the database persistent between runs?**

Yes. `leadhunter.db` stores all campaigns, URLs, and leads permanently.
You can run the tool tomorrow and pick up where you left off.

**Q: Can I run multiple campaigns at the same time?**

Yes, in separate terminal windows. Each `--campaign-id` is independent.

**Q: How do I delete a campaign?**

Currently, deletes must be done directly in the database (SQLite):

```bash
sqlite3 leadhunter.db "DELETE FROM campaigns WHERE id=1;"
```

A `campaign delete` CLI command is planned for a future release.

**Q: What websites does LeadHunter Pro work best on?**

- Company websites with About, Team, and Contact pages
- Sites in any language (Claude is multilingual)
- Sites without heavy JavaScript rendering (static or server-rendered)

**Q: Can I import leads into HubSpot / Salesforce?**

Export the Excel file, then use the CSV import feature of your CRM.
In Excel, File → Save As → CSV for a format compatible with all CRMs.

---

## 10. Glossary

| Term | Definition |
|------|-----------|
| **Campaign** | A named container grouping a set of URLs and their extracted leads |
| **Niche** | The industry or business type you're targeting (e.g., "digital marketing agencies") |
| **URL** | A company website address collected during the scrape step |
| **Lead** | Structured contact + company data extracted from a URL |
| **Enrichment** | The process of visiting a URL and extracting lead data with AI |
| **Quality Score** | AI-assigned rating 1–10 indicating how useful a lead is |
| **Pending** | URL status: scraped but not yet enriched |
| **Completed** | URL status: enrichment finished (may or may not have a lead) |
| **Failed** | URL status: enrichment encountered an error |
| **Claude Code CLI** | The `claude` command-line tool included with Claude Pro |
| **Pipeline** | The full sequence: scrape → enrich → export |
| **Resumable** | The pipeline can be safely interrupted and restarted |
