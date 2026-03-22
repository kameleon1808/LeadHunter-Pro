# Phase 3 Enrichment — User Guide

## What Does Enrichment Do?

After you've collected a list of company URLs in Phase 2 (the scraper), enrichment visits each website automatically and reads its pages to find out:

- **Company details** — name, industry, size, what they do
- **Contact people** — CEO/founder name, email, LinkedIn profile
- **Contact info** — company email, phone number, address
- **Client info** — who their customers are

All of this is extracted by **Claude AI** (using your existing Claude Code installation — no extra payment needed) and saved to your database as a structured lead record, ready to export or use in outreach.

---

## Requirements

- Claude Code must be installed and you must be logged in (`claude` command works in your terminal)
- Phase 1 and Phase 2 already completed (database initialised, URLs scraped)
- Python dependencies installed: `pip install -r requirements.txt`

**No API key setup needed.** Enrichment uses Claude Code CLI which is already covered by your Claude Pro / Max plan.

---

## How to Start Enrichment

Run this command, replacing `1` with your campaign ID:

```cmd
python main.py enrich --campaign-id 1
```

You'll see output like this:

```
Campaign  : Marketing Agencies Serbia
Pending   : 287 URLs to enrich
Ekstraktor: Claude Code CLI — besplatno (model: claude-sonnet-4-5)

[2026-03-21 10:00:01] [INFO] Enrichment started for campaign id=1
[2026-03-21 10:00:13] [INFO] Lead saved id=1 for https://agencyone.rs (score=8)
[2026-03-21 10:00:26] [INFO] Progress: 1/287 URLs (0.3%) | 1 leads found
[2026-03-21 10:00:38] [INFO] Lead saved id=2 for https://agencytwo.rs (score=6)
...

Enrichment complete.
Leads found : 214
Completed   : 261
Failed      : 26
```

---

## How Long Does It Take?

| URLs | Estimated Time |
|------|---------------|
| 50   | ~15–20 minutes |
| 300  | ~90–120 minutes |
| 1000 | ~5–7 hours |

> **Why slower than the scraper?** Each URL requires Claude Code CLI to start up (~10–12 seconds per site). The tool processes 3 Claude calls and 5 website fetches in parallel to keep things moving.

Times also vary depending on:
- How fast each website responds
- How much content Claude needs to read
- Whether websites are online or blocking automated requests

---

## What Data Gets Collected?

For each website that can be successfully analysed, a lead record is created with:

| Field | Example |
|-------|---------|
| Company name | Acme Marketing d.o.o. |
| Company size | 10–50 employees |
| Industry | Digital Marketing |
| Description | Full-service digital agency specialising in SEO and paid ads |
| Contact name | Marko Nikolić |
| Contact title | CEO |
| Contact email | marko@acme.rs |
| Contact LinkedIn | linkedin.com/in/markonikolic |
| Company email | hello@acme.rs |
| Company phone | +381 11 123 4567 |
| Address | Knez Mihailova 10, Belgrade |
| Clients info | Works with retail and hospitality brands |
| Quality score | 8/10 |

If information can't be found on the website, that field is left blank.

---

## Understanding Quality Scores

Every lead gets a **quality score from 1 to 10** assigned by Claude AI:

| Score | What It Means | Action |
|-------|--------------|--------|
| **9–10** | Decision-maker email + full company profile | Reach out immediately |
| **7–8** | Good company info, some contact details | Worth pursuing |
| **5–6** | Company info only, no personal contacts | Do manual research first |
| **3–4** | Very little data | Low priority |
| **1–2** | Almost nothing useful | Skip |

> **Pro tip:** Filter your leads by `quality_score >= 7` when exporting for outreach.

---

## What If Enrichment Stops?

Enrichment can be safely re-run at any time. Every URL is marked `completed` or `failed` as it's processed, so re-running **only picks up the remaining pending URLs** — already-processed ones are automatically skipped.

```cmd
python main.py enrich --campaign-id 1
```

If enrichment stops due to a power cut, network drop, or you closing the terminal — just run the same command again and it continues from where it left off.

---

## Common Errors and Fixes

### `claude CLI nije pronađen` / `claude: command not found`

Claude Code is not installed or not in your PATH. Fix:
1. Install Claude Code from [claude.ai/code](https://claude.ai/code)
2. Log in with `claude login`
3. Verify it works: `claude -p "say hello" --output-format json`

### `No pending URLs to enrich. Run 'scrape' first.`

The campaign has no URLs yet. Run the scraper first:
```cmd
python main.py scrape --campaign-id 1 --query "marketing agencies in Serbia" --pages 5
```

### `Error: campaign with id=1 not found`

Your campaign ID is wrong. Check existing campaigns:
```cmd
python main.py init
```

### Many URLs showing as `failed` (>20%)

Some websites block automated requests, are offline, or have no readable content. A 5–20% failure rate is normal and expected. Failed URLs are skipped on re-runs — they won't block the rest of the campaign.

If failure rate is very high (>50%), check your internet connection or try reducing HTTP concurrency in `config.py`:
```python
ENRICHMENT_CONCURRENT_REQUESTS = 2   # was 5
```

### Enrichment is very slow

This is expected — each URL takes ~10–15 seconds due to Claude Code startup time. You can increase parallelism slightly (at your own risk of hitting rate limits):
```python
CLAUDE_CODE_MAX_CONCURRENT = 5   # was 3
```

### `claude subprocess timed out after 120s`

A specific website had very large content that took too long to process. The URL is marked `failed` and the pipeline continues. This is rare and normal.

---

## Checking Your Results

After enrichment, query the database to see leads:

```bash
sqlite3 data/leadhunter.db "SELECT company_name, contact_name, contact_email, quality_score FROM leads WHERE campaign_id=1 AND quality_score >= 7 ORDER BY quality_score DESC;"
```

Or see a full campaign summary:
```bash
sqlite3 data/leadhunter.db "SELECT campaign_name, total_urls, completed_urls, failed_urls, total_leads FROM campaigns WHERE id=1;"
```
