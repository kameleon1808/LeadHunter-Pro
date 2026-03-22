# Phase 4 — Export & Dashboard: User Guide

## What's New in Phase 4?

Phase 4 adds two major features:

1. **Excel Export** — download all your leads into a clean, formatted `.xlsx` file ready for outreach tools
2. **Terminal Dashboard** — live progress view, campaign stats, and leads preview — all inside your terminal

---

## Step by Step: From Zero to Exported Leads

Here's the complete workflow in one place:

```cmd
rem 1. Create a campaign
python main.py campaign create --name "Serbia Agencies" --niche "marketing agencies" --country "Serbia"

rem 2. Scrape URLs from Google
python main.py scrape --campaign-id 1 --query "marketing agencies in Serbia" --pages 10

rem 3. Enrich leads with Claude AI
python main.py enrich --campaign-id 1

rem 4. Export to Excel
python main.py export --campaign-id 1 --output "./exports/"
```

---

## How to Export Your Leads to Excel

Run the export command with your campaign ID:

```cmd
python main.py export --campaign-id 1
```

By default, the file is saved in `./exports/`. You can specify a different folder:

```cmd
python main.py export --campaign-id 1 --output "C:\Users\Marko\Desktop\leads\"
```

Or give it a specific filename:

```cmd
python main.py export --campaign-id 1 --output "C:\Users\Marko\Desktop\my_leads.xlsx"
```

Output:
```
Campaign : Serbia Agencies
Leads    : 214
Output   : ./exports/

Export complete: C:\...\exports\leads_serbia_agencies_campaign1_2026-03-21.xlsx
```

---

## Understanding the Excel File

The exported file has **three sheets**:

### Sheet 1 — Leads

Your main data. Every row is one company. Columns (left to right):

| Column | What it contains |
|--------|-----------------|
| # | Row number |
| Company Name | The company's name |
| Industry | Their industry (Digital Marketing, SEO, etc.) |
| Size | Estimated employee count ("10-50 employees") |
| Description | What the company does (max 200 chars) |
| Contact Name | CEO / founder / director name |
| Contact Title | Their job title |
| Contact Email | Their personal email |
| Contact LinkedIn | Their LinkedIn profile link |
| Company Email | General company email (info@, hello@, etc.) |
| Company Phone | Company phone number |
| Address | Office address |
| Website | Company website URL |
| Clients Info | Description of who their clients are |
| Quality Score | AI-assigned score from 1 to 10 |

**Colour coding:**
- Header row: dark blue
- Alternating rows: white and pale blue (easier to read)

### Sheet 2 — Stats

A summary of the campaign:
- Campaign name, niche, country, status
- Total URLs scraped
- How many were processed, completed, or failed
- Total leads found
- Lead conversion rate (leads ÷ completed URLs)

### Sheet 3 — Failed URLs

A list of websites that couldn't be processed:
- The URL that failed
- Why it failed (timeout, blocked, offline, etc.)
- How many times it was retried

Use this sheet to manually follow up on promising companies that the tool couldn't access automatically.

---

## How to Filter Leads in Excel

The header row in all sheets has **auto-filters** enabled (the little dropdown arrows ▼).

**Useful filters:**

1. **Filter by Quality Score** — click ▼ on "Quality Score" → Number Filters → Greater Than → 7
2. **Filter by Industry** — click ▼ on "Industry" → select specific industries
3. **Sort by Score** — click ▼ on "Quality Score" → Sort Largest to Smallest

**Pro tip:** After filtering, select all visible rows, copy, and paste into a new sheet for your outreach list.

---

## How to Use the Live Dashboard

While enrichment is running (in another terminal window), open a dashboard:

```cmd
python main.py dashboard --campaign-id 1
```

You'll see a live view that updates every 2 seconds:

```
╭──────────────── LeadHunter Pro — Live Progress ────────────────╮
│                                                                 │
│  Serbia Agencies  |  Status: running  |  Elapsed: 12m 34s      │
│  ETA: ~47 minutes                                               │
│                                                                 │
│  URLs Processed  ████████████░░░░░░░░░░░░░░░░░░░░░░  87/300    │
│  Leads Found     ████████░░░░░░░░░░░░░░░░░░░░░░░░░░  62/87     │
│                                                                 │
│  Completed: 71  Failed: 16  Pending: 213  Leads: 62            │
│                                                                 │
│ ╭─ Recent Activity ─────────────────────────────────────╮      │
│ │  ✓ https://agencyone.rs                               │      │
│ │  ✓ https://agencytwo.rs                               │      │
│ │  ✗ https://broken-site.rs                             │      │
│ │  ✓ https://agencythree.rs                             │      │
│ ╰───────────────────────────────────────────────────────╯      │
╰─────────────────────────────────────────────────────────────────╯
```

Press **Ctrl+C** to exit the dashboard (enrichment keeps running in the other window).

---

## How to Read the Statistics

For a quick one-shot stats view (no live updating):

```cmd
python main.py status --campaign-id 1
```

This shows:
- Campaign details (name, niche, country, status)
- URL processing progress
- Lead count and conversion rate
- A preview of your 10 most recent leads

**Key metrics explained:**

| Metric | Meaning |
|--------|---------|
| Completed | URLs successfully visited and analysed |
| Failed | URLs that couldn't be processed (blocked, offline, etc.) |
| Success Rate | Completed ÷ Total (60–80% is normal) |
| Lead Conversion | Leads found ÷ Completed URLs (50–80% is normal) |

---

## List All Your Campaigns

```cmd
python main.py campaign list
```

Shows all campaigns with their status, URL count, lead count, and creation date.

---

## Recommended Outreach Tools

Once you export your Excel file, import it into:

| Tool | How to Import |
|------|--------------|
| **HubSpot CRM** | Contacts → Import → Excel file |
| **Apollo.io** | Lists → Import CSV (save Excel as CSV first) |
| **Lemlist** | Leads → Import → CSV/Excel |
| **Instantly.ai** | Leads → Import → CSV (save as CSV first) |
| **Google Sheets** | File → Import → Upload the .xlsx file |
| **Notion** | New page → Database → Import → CSV |

**To save as CSV:** Open the file in Excel → File → Save As → CSV (Comma delimited).

> **Tip:** Filter the Leads sheet to `Quality Score >= 7` before exporting to CSV so you only import high-quality leads.

---

## Common Questions

### How do I know when enrichment is done?

The status in `campaign list` or `dashboard` will change from `running` to `completed`. You'll also see a summary in the enrichment terminal window.

### Can I export while enrichment is still running?

Yes! The export captures all leads found up to that moment. Run it again later to get the full set.

### The Excel file is empty / only has headers

This means no leads were found yet. Check that enrichment ran successfully:
```cmd
python main.py status --campaign-id 1
```

### Some leads are missing fields (blank cells)

That's normal — if the company's website didn't list their CEO's email, Claude couldn't find it. Blank fields mean the information wasn't publicly available. Use the Quality Score to prioritize leads that have the most complete data.
