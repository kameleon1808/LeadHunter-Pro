# Phase 4 — Export & Dashboard: Technical Reference

## Overview

Phase 4 adds:

1. **ExcelExporter** — exports all leads for a campaign into a formatted `.xlsx` workbook with three sheets (Leads, Stats, Failed URLs).
2. **CLIDashboard** — Rich-powered terminal views: live progress dashboard, campaigns list, leads preview, and stats panel.
3. **Full CLI** — expanded `main.py` with `campaign create/list`, `export`, `dashboard`, and `status` commands.

---

## ExcelExporter (`export/excel_exporter.py`)

### Constructor

```python
ExcelExporter(db_manager: DatabaseManager)
```

### Public Method

```python
export_campaign(campaign_id: int, output_path: str) -> str
```

Creates a `.xlsx` file and returns its absolute path.

- If `output_path` is a directory (or ends with `/`), the filename is auto-generated.
- If `output_path` is a full file path, it is used as-is.

**Filename convention:**
```
leads_{safe_campaign_name}_campaign{id}_{YYYY-MM-DD}.xlsx
```
Example: `leads_marketing_agencies_campaign1_2026-03-21.xlsx`

---

### Excel File Structure

#### Sheet 1 — Leads

| Column | Source field | Max width |
|--------|-------------|-----------|
| # | Row number | 5 |
| Company Name | `company_name` | 30 |
| Industry | `industry` | 20 |
| Size | `company_size` | 15 |
| Description | `description` | 45 |
| Contact Name | `contact_name` | 22 |
| Contact Title | `contact_title` | 20 |
| Contact Email | `contact_email` | 30 |
| Contact LinkedIn | `contact_linkedin` | 35 |
| Company Email | `company_email` | 30 |
| Company Phone | `company_phone` | 18 |
| Address | `address` | 30 |
| Website | `website_url` | 30 |
| Clients Info | `clients_info` | 40 |
| Quality Score | `quality_score` | 14 |

**Formatting:**
- Header: bold white text on dark navy (`#1F4E79`), height 20 px
- Odd rows: white (`#FFFFFF`)
- Even rows: pale blue (`#EBF3FB`)
- Filters enabled on header row (`ws.auto_filter.ref`)
- First row frozen (`ws.freeze_panes = "A2"`)
- Column widths: auto-calculated, capped at the values above

#### Sheet 2 — Stats

Key–value layout with campaign metadata and processing statistics:

| Field | Description |
|-------|-------------|
| Campaign Name | Name of the campaign |
| Niche | Target niche/industry |
| Target Country | Country (or —) |
| Status | Current campaign status |
| Created At | Creation timestamp |
| Total URLs | All scraped URLs |
| Processed | Completed + Failed |
| Completed | Successfully enriched |
| Failed | Failed enrichment |
| Success Rate | Completed / Total |
| Leads Found | Lead records created |
| Lead Conversion | Leads / Completed |

Header style: dark navy background, white bold text.
Key column: light steel blue (`#D6E4F0`), bold.

#### Sheet 3 — Failed URLs

| Column | Description |
|--------|-------------|
| # | Row number |
| URL | The failed URL |
| Error Message | Last error recorded |
| Retry Count | Number of retries |

Same formatting rules as Leads sheet. Filters and freeze enabled.

---

### Private Methods

| Method | Description |
|--------|-------------|
| `_format_leads_sheet(ws, leads)` | Writes and styles the Leads worksheet |
| `_format_stats_sheet(ws, stats, campaign)` | Writes and styles the Stats worksheet |
| `_format_failed_sheet(ws, failed_urls)` | Writes and styles the Failed URLs worksheet |
| `_write_header_row(ws, headers)` | Applies header style to row 1 of any sheet |
| `_get_failed_urls(campaign_id)` | Queries URLs with `status='failed'` directly via SQLAlchemy Session |
| `_resolve_output_path(output_path, campaign)` | Resolves directory or file path to final `.xlsx` path |

---

## CLIDashboard (`dashboard/cli_dashboard.py`)

### Constructor

```python
CLIDashboard(db_manager: DatabaseManager)
```

Uses `rich.console.Console` internally.

### Public Methods

#### `show_campaigns_list()`

Prints a Rich table of all campaigns with columns:
ID, Name, Niche, Country, Status (colour-coded), URLs, Leads, Created.

Status colours: `yellow` (pending), `green` (running), `bold green` (completed), `bold red` (failed).

#### `show_campaign_progress(campaign_id)`

Live-updating dashboard. Blocks until the campaign status becomes `completed` or `failed`, or until the user presses **Ctrl+C**.

Refreshes every **2 seconds** using `rich.live.Live`.

Display elements:
- Header: campaign name, status, elapsed time, ETA
- URL progress bar (ASCII `█░` style, 40 chars wide)
- Lead progress bar
- Stats row: Completed / Failed / Pending / Leads
- Recent Activity panel: last 10 processed URLs (✓ green for completed, ✗ red for failed)

**ETA algorithm:**
```python
rate      = (current_done - start_done) / elapsed_seconds
remaining = total_urls - current_done
eta       = remaining / rate   # seconds
```
Shown as `N/A` until at least 5 seconds and 1 URL have been processed.

#### `show_leads_preview(campaign_id, limit=20)`

Rich table of the `limit` most recent leads. Quality score colour-coded:
- ≥ 8: bold green
- 5–7: yellow
- < 5: red

Columns: #, Company, Industry, Contact (name + title), Email, Phone, Score.

#### `show_stats(campaign_id)`

One-shot Rich panel with campaign metadata and all processing statistics. Used by the `status` CLI command.

### Private Methods

| Method | Description |
|--------|-------------|
| `_build_progress_display(...)` | Builds the `rich.console.Group` renderable for `Live` |
| `_make_bar(label, value, total, color)` | Returns a `rich.text.Text` ASCII progress bar |
| `_get_recent_activity(campaign_id, limit)` | Queries last N completed/failed URLs by `processed_at DESC` |

---

## CLI Command Reference

### `campaign create`
```
python main.py campaign create --name "Name" --niche "Niche" [--country "Country"]
```
Creates a new campaign and prints its ID.

### `campaign list`
```
python main.py campaign list
```
Displays a Rich table of all campaigns with stats.

### `scrape`
```
python main.py scrape --campaign-id 1 --query "marketing agencies Serbia" [--pages 10]
```
Launches Playwright browser and scrapes Google search results.

### `enrich`
```
python main.py enrich --campaign-id 1
```
Enriches all pending URLs using Claude Code CLI (or Anthropic API if `ANTHROPIC_API_KEY` is set).

### `export`
```
python main.py export --campaign-id 1 [--output "./exports/"]
```
Exports leads to Excel. `--output` may be a directory or full file path.

### `status`
```
python main.py status --campaign-id 1
```
Prints a one-shot stats panel and a 10-lead preview. Exits immediately.

### `dashboard`
```
python main.py dashboard --campaign-id 1
```
Opens the live-updating dashboard. Press **Ctrl+C** to exit.

### `init`
```
python main.py init
```
Initialises the database (creates tables if they don't exist).

---

## Rich Library Usage

| Component | Usage |
|-----------|-------|
| `Console` | Base output renderer |
| `Table` | Campaigns list, leads preview, activity log |
| `Panel` | Stats view, live dashboard wrapper |
| `Live` | Live-updating display (2 s refresh) |
| `Text` | Progress bars, styled inline text |
| `Group` (console) | Composing multiple renderables in Live |

---

## Dependencies

| Package | Version | Purpose |
|---------|---------|---------|
| `openpyxl` | ≥ 3.1.0 | Excel workbook creation and formatting |
| `rich` | ≥ 13.0.0 | Terminal tables, panels, live display |
