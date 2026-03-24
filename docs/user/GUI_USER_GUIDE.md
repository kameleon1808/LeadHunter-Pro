# LeadHunter Pro — GUI User Guide

## Table of Contents

1. [Overview](#1-overview)
2. [Installation & First Launch](#2-installation--first-launch)
3. [Window Layout](#3-window-layout)
4. [Campaigns Screen](#4-campaigns-screen)
5. [Campaign Detail Screen](#5-campaign-detail-screen)
6. [Live Monitor Screen](#6-live-monitor-screen)
7. [Leads Browser Screen](#7-leads-browser-screen)
8. [Settings Screen](#8-settings-screen)
9. [Building the Windows EXE](#9-building-the-windows-exe)
10. [Troubleshooting](#10-troubleshooting)

---

## 1. Overview

The LeadHunter Pro GUI is a desktop application built with **CustomTkinter** that provides a visual interface for all functionality previously available only via the terminal.

**Entry point:**
```bash
python gui_main.py
```

**All CLI features are available in the GUI:**

| CLI Command | GUI Equivalent |
|-------------|---------------|
| `campaign create` | Campaigns screen — Create form |
| `campaign list` | Campaigns screen — table |
| `scrape` | Campaign Detail — Scrape card |
| `enrich` | Campaign Detail — Enrich card |
| `export` | Campaign Detail — Export card |
| `run` (full pipeline) | Campaign Detail — Full Pipeline card |
| `status` | Campaign Detail — stat cards header |
| `dashboard` | Live Monitor screen (auto 2s refresh) |

---

## 2. Installation & First Launch

### Prerequisites

All existing prerequisites from the CLI guide apply. Additionally:

```bash
pip install customtkinter==5.2.2
```

This is already included in `requirements.txt` — a standard `pip install -r requirements.txt` is sufficient.

### Launching the GUI

```bash
python gui_main.py
```

On first launch, the app will:
1. Create `data/`, `logs/`, `exports/` directories if they don't exist
2. Initialize the SQLite database
3. Check that your configured browser (Brave or Playwright Chromium) is available
4. Open the main window

### Browser Check on Startup

The startup check is browser-aware:

- **USE_BRAVE=true** (default on Windows): checks that `BRAVE_EXECUTABLE_PATH` points to an existing file. If Brave is installed at the default path, no action is needed.
- **USE_BRAVE=false**: checks that Playwright Chromium is installed. If missing, run `setup.bat` or `playwright install chromium`.

The warning is informational — the app opens regardless. You only need the browser for the Scrape step.

---

## 3. Window Layout

```
┌─────────────────────┬────────────────────────────────────────┐
│  LeadHunter Pro     │                                        │
│  ─────────────────  │                                        │
│  Campaigns          │         MAIN CONTENT AREA              │
│  🟡 Campaign 1      │         (active screen)                │
│  ✅ Campaign 2      │                                        │
│  🟢 Campaign 3      │                                        │
│  ─────────────────  │                                        │
│  ＋ New Campaign    │                                        │
│  ⚙  Settings        │                                        │
│  🏠 All Campaigns   │                                        │
└─────────────────────┴────────────────────────────────────────┘
                              ↑
                  Toast notification bar (bottom)
```

**Sidebar** (left, 210px):
- Lists all campaigns with a coloured status dot
- Click any campaign → opens Campaign Detail
- "New Campaign" → opens Campaigns screen with form focused
- "Settings" → opens Settings screen
- "All Campaigns" → returns to home

**Status dots in sidebar:**

| Dot | Status |
|-----|--------|
| 🟡 | pending |
| 🟢 | running |
| 🔵 | paused |
| ✅ | completed |
| 🔴 | failed |

---

## 4. Campaigns Screen

The home screen. Shows on launch.

### Create Campaign (top section)

Fill in:
- **Name** *(required)* — e.g. "Marketing Agencies Serbia 2025"
- **Niche** *(required)* — e.g. "digital marketing"
- **Country** *(optional)* — e.g. "Serbia"

Click **＋ Create Campaign**. The campaign appears in the table and the sidebar immediately.

### Campaign Table (bottom section)

Columns: ID, Name, Niche, Country, Status, URLs, Leads, Created.

**Click any row** to open that campaign's detail screen.

Use the **↻ Refresh** button to reload from the database at any time.

---

## 5. Campaign Detail Screen

Opened by clicking a campaign in the sidebar or table. Shows 4 action cards plus a stats header.

### Stats Header

```
[Campaign Name]  [STATUS BADGE]    [📊 Monitor] [📋 Leads] [↻ Refresh]

Total URLs: 120   Pending: 80   Completed: 35   Failed: 5   Leads Found: 28
```

### Card 1 — 🔍 Scrape URLs

Equivalent to `python main.py scrape --campaign-id N --query "..." --pages N`

1. Enter a **Google search query** (e.g. `marketing agencija Beograd`)
2. Set **Pages** (default 5, each page = ~10 URLs)
3. Click **Start Scrape**

The status label updates to "Running…" while active. When done: "Done: 43 URLs".

If a CAPTCHA is detected during scraping, a modal dialog appears — see [CAPTCHA Handling](#captcha-handling).

### Card 2 — 🤖 Enrich with AI

Equivalent to `python main.py enrich --campaign-id N`

Shows the current **pending URL count**. Click **Start Enrichment** to process all pending URLs with Claude AI.

Safe to run multiple times — already-processed URLs are skipped. Can be interrupted via the Monitor screen's Stop button and resumed later.

### Card 3 — 📥 Export to Excel

Equivalent to `python main.py export --campaign-id N --output ./exports/`

1. Optionally set an **output directory** (default: `./exports/`) using the 📂 browse button
2. Click **Export**
3. A toast notification confirms the filename when done

The exported file has 3 sheets: Leads, Stats, Failed URLs — same as the CLI export.

### Card 4 — 🚀 Full Pipeline

Equivalent to `python main.py run --campaign-id N --query "..." --pages N --output ./exports/`

Runs Scrape → Enrich → Export in one click. The Monitor screen opens automatically.

- If URLs already exist for this campaign, scraping is skipped
- If no pending URLs remain, enrichment is skipped
- Fully resumable — safe to stop and restart

---

## 6. Live Monitor Screen

Opened via the **📊 Monitor** button on the detail screen, or automatically when "Run Full Pipeline" starts.

```
Campaign: Marketing Agencies Serbia 2025   🟢 RUNNING
Elapsed: 4m 23s   ETA: ~12m

URLs Processed   [████████░░░░░░░░░░░░]   45 / 120  (37.5%)
Leads Found      [█████░░░░░░░░░░░░░░░]   18 / 45   (40.0%)

Completed: 32   Failed: 13   Pending: 75   Leads: 18

Recent Activity:
  ✓  https://digitalagencija.rs
  ✓  https://mediaagentur.de
  ✗  https://example.com — FAILED
  ...

[⏹ Stop / Pause]
```

### Live Updates

The monitor polls the database every **2 seconds** — no page refresh needed.

- **Progress bars** show URLs processed and leads found
- **ETA** is calculated from the processing rate (appears after ~5 seconds)
- **Activity log** shows the 20 most recently processed URLs, auto-scrolling as new results arrive

### Stop / Pause

Click **⏹ Stop / Pause** to cancel the running task. The campaign is marked as `paused` in the database. Resume at any time by clicking "Start Enrichment" or "Run Full Pipeline" again — processing continues from the last pending URL.

### CAPTCHA Handling

When Google detects automated traffic during scraping, a dialog appears:

```
⚠️  CAPTCHA Detected

Please solve the CAPTCHA in the browser window,
then click Done to continue.

[✓  Done — CAPTCHA Solved]
```

The scraper is paused waiting for your click. Solve the CAPTCHA in the Brave/Chromium window, then click **Done**.

---

## 7. Leads Browser Screen

Opened via the **📋 Leads** button on the detail screen.

### Filter Bar

| Filter | Options |
|--------|---------|
| Search | Free text — matches company name, email, contact name, industry |
| Quality | Any / 8+ (High) / 5–7 (Medium) / < 5 (Low) |
| Industry | Any / (populated from leads in the campaign) |

Filters apply instantly as you type.

### Lead Table

Columns: #, Company, Industry, Size, Contact, Email, Phone, Score

Quality score colour coding:
- **Green** ≥ 8 — high priority
- **Amber** 5–7 — medium
- **Red** < 5 — low quality

**Click any row** to expand a detail panel below the table showing all fields:

```
Company:       Digital Agency d.o.o.
Industry:      Digital Marketing
Size:          10-50 employees
Description:   Full-service digital marketing agency…

Contact:       Marko Petrović  (CEO)
Contact Email: marko@digitalagency.rs
LinkedIn:      https://linkedin.com/in/marko-p
Company Email: info@digitalagency.rs
Phone:         +381 11 123 4567
Address:       Bulevar Oslobođenja 12, Beograd
Clients:       Works with SMBs in retail and hospitality

Quality Score: 9
Source URL:    https://digitalagency.rs
```

### Pagination

Shows 100 leads per page. Click **Load more (next 100)** to load additional leads.

---

## 8. Settings Screen

Provides a GUI editor for all `.env` configuration values.

### Sections

**AI Extractor**
- `ANTHROPIC_API_KEY` — optional; enables the direct Anthropic API (faster, billed per token)
- `CLAUDE_MODEL` — Claude model to use (e.g. `claude-sonnet-4-5`)
- `CLAUDE_CODE_MAX_CONCURRENT` — parallel Claude CLI processes (1–10, default 3)

**Scraping**
- `SEARCH_PAGES_DEFAULT` — default number of Google pages per search
- `MIN_DELAY_SECONDS` / `MAX_DELAY_SECONDS` — random delay range between pages
- `PLAYWRIGHT_HEADLESS` — run browser hidden (checked) or visible (unchecked)
- `USE_BRAVE` — use Brave browser with persistent profile (recommended on Windows)
- `BRAVE_EXECUTABLE_PATH` — path to `brave.exe` (use 📂 to browse)
- `BRAVE_USER_DATA_DIR` — path to Brave user data directory

**Enrichment**
- `ENRICHMENT_CONCURRENT_REQUESTS` — parallel HTTP requests (1–20, default 5)
- `MAX_PAGES_PER_SITE` — maximum pages visited per company website (default 5)
- `REQUEST_TIMEOUT_SECONDS` — HTTP request timeout (default 30)

**Database**
- `DATABASE_PATH` — read-only display of the current database file path

### Saving

Click **💾 Save Settings**. Changes are written to `.env` using `dotenv.set_key()` (existing comments and other keys are preserved).

A toast confirms the save: *"Settings saved. Restart required for browser path changes."*

String and numeric settings (model, concurrency, delays) take effect immediately without restart. Browser path changes (`BRAVE_EXECUTABLE_PATH`, `BRAVE_USER_DATA_DIR`) require a restart.

---

## 9. Building the Windows EXE

### Prerequisites

```bash
pip install pyinstaller==6.10.0
```

### Build

```bash
pyinstaller leadhunter_gui.spec --clean --noconfirm
```

Output: `dist/LeadHunterPro.exe` — single file, no console window.

### Distribution

Distribute these files together:
```
LeadHunterPro.exe
setup.bat         ← run once on new machine if USE_BRAVE=false
.env              ← copy from .env.example and fill in settings
```

### First Run on a New Machine

If `USE_BRAVE=false` (using Playwright Chromium):
```
setup.bat
```

If `USE_BRAVE=true` (using Brave):
- Install Brave browser normally
- Set `BRAVE_EXECUTABLE_PATH` and `BRAVE_USER_DATA_DIR` in `.env` or via Settings

### Runtime Files

The EXE writes runtime files next to itself (not inside the bundle):
```
LeadHunterPro.exe
data/leadhunter.db     ← SQLite database (created on first run)
logs/leadhunter.log    ← log file
exports/               ← Excel files written here
.env                   ← your configuration
```

---

## 10. Troubleshooting

### "Brave Browser not found" warning on startup

Check `BRAVE_EXECUTABLE_PATH` in Settings or `.env`. The default path is:
```
C:\Program Files\BraveSoftware\Brave-Browser\Application\brave.exe
```
Use the 📂 browse button in Settings to locate it.

### "Playwright Chromium not installed" warning on startup

Only shown when `USE_BRAVE=false`. Run:
```bash
setup.bat
# or:
playwright install chromium
```

### Scrape button does nothing / task silently fails

Check `logs/leadhunter.log` for detailed error messages. Common causes:
- Brave is open — close it before scraping (Playwright cannot attach to a running instance)
- `BRAVE_USER_DATA_DIR` not set — configure in Settings

### Monitor shows 0 progress after starting enrichment

The Claude CLI (`claude`) must be on your PATH. Verify:
```bash
claude --version
```
If not found: `npm install -g @anthropic-ai/claude-code` then restart the terminal.

### Settings changes not taking effect

- String/numeric settings take effect on the next run of a task (no restart needed)
- Browser paths require a full application restart
- After saving, verify the `.env` file contains the new values

### EXE crashes on launch with no error

Run from the terminal to see the error:
```bash
LeadHunterPro.exe
```
Or check `logs/leadhunter.log` next to the EXE.

---

## Architecture Notes (for developers)

### Threading Model

```
Tkinter main thread
  └─ root.after(200ms) → drains EventBus queue → updates GUI
  └─ root.after(2000ms) → DB poll in MonitorScreen._tick()

Daemon asyncio thread (BackgroundTaskRunner)
  └─ loop.run_forever()
  └─ coroutines: scrape, enrich, full pipeline
  └─ posts TaskStartedEvent / TaskProgressEvent / TaskDoneEvent / CaptchaEvent
```

### Key Files

| File | Role |
|------|------|
| `gui_main.py` | Entry point — path resolution, DB init, browser check |
| `gui/app.py` | Root window, sidebar, screen routing, event dispatch |
| `gui/event_bus.py` | `queue.Queue` wrapper with typed dataclass events |
| `gui/task_runner.py` | Asyncio-in-thread bridge + GUI-specific subclasses |
| `gui/screens/` | One file per screen (5 screens total) |
| `gui/widgets/` | Reusable components (StatCard, StatusBadge, ProgressRow, ScrollableTable) |
| `leadhunter_gui.spec` | PyInstaller build configuration |
