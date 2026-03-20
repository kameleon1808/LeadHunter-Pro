# How to Run the URL Scraper

This guide explains how to collect company website URLs using LeadHunter Pro.
No technical knowledge required — just follow the steps below.

---

## Before You Start

Make sure you have completed the setup from the Getting Started guide (Phase 1).

Install the browser automation tool by running these two commands **once**:

```
pip install playwright
playwright install chromium
```

---

## Step 1 — Create a Campaign (if you haven't already)

The scraper needs an existing campaign to attach the URLs to.
If you already have a campaign, skip to Step 2.

Open a terminal and run:

```
python main.py init
```

Then use the Python shell or the database tool to create a campaign.
Make a note of the **campaign ID** — you will need it in Step 2.

---

## Step 2 — Start a Scraping Session

Run the following command, replacing the values with your own:

```
python main.py scrape --campaign-id 1 --query "marketing agencies in Serbia" --pages 10
```

**What each part means:**

| Part              | What to change                                      |
|-------------------|-----------------------------------------------------|
| `--campaign-id 1` | Replace `1` with your actual campaign ID            |
| `--query "..."`   | Your search phrase (see tips below for good phrases)|
| `--pages 10`      | How many pages of Google results to go through      |

---

## What You Will See on Screen

As soon as you run the command:

1. **A Chrome browser window will open.** This is normal — the tool needs to show you
   the browser so you can help if Google asks you to prove you are human.

2. The tool will start searching Google automatically. You will see it navigating
   through search result pages one by one.

3. In the terminal, you will see progress messages like:
   ```
   Campaign  : My First Campaign
   Query     : marketing agencies in Serbia
   Pages     : 10

   [INFO] Starting search: 'marketing agencies in Serbia' | pages=10
   [INFO] Page 1/10: extracted 8 URLs
   [INFO] Saved 8 new URLs to database
   [INFO] Page 2/10: extracted 6 URLs
   ...
   Done. Collected 62 unique URLs.
   ```

4. When finished, the browser will close automatically.

---

## What to Do When a CAPTCHA Appears

Sometimes Google will show a CAPTCHA (a puzzle to prove you are human).
When this happens:

1. The tool will **pause** and print this message in the terminal:
   ```
   ⚠️  CAPTCHA detected! Please solve it in the browser window.
      Press ENTER here once you have solved the CAPTCHA and are back on search results.
   ```

2. **Go to the browser window** — you will see a CAPTCHA challenge.

3. **Solve the CAPTCHA** (tick the checkbox, or complete the image puzzle).

4. Wait until you see the Google search results page again in the browser.

5. **Go back to the terminal** and press **ENTER**.

6. The tool will continue automatically.

> **Tip:** CAPTCHAs are more common if you scrape many pages quickly or run the tool
> several times in a row. Stick to 5–10 pages per session and wait a few minutes
> between sessions to avoid them.

---

## How to Know When Scraping Is Done

The tool is finished when you see this message in the terminal:

```
Done. Collected 62 unique URLs.
```

The browser will close by itself. The URLs are already saved to the database.

---

## Where Results Are Saved

All collected URLs are saved automatically to the database file at:

```
data/leadhunter.db
```

They are attached to the campaign you specified with `--campaign-id`.

You can check the log file for a detailed record of everything that happened:

```
logs/leadhunter.log
```

---

## Tips for Better Results

**Use specific search phrases.** The more specific you are, the better the URLs you get.

| Instead of…             | Try…                                             |
|-------------------------|--------------------------------------------------|
| "agencies"              | "digital marketing agencies in Belgrade"         |
| "companies"             | "web design studios in Novi Sad Serbia"          |
| "lawyers"               | "corporate law firms in Serbia contact"          |
| "restaurants"           | "fine dining restaurants Belgrade website"       |

**Add location** — this significantly improves result quality for local lead generation.

**Add keywords that signal a website** — phrases like "official website", "contact us",
or "services" help Google surface actual company websites rather than directories.

**Avoid running too many pages at once** — 5–10 pages per session is a good balance
between speed and avoiding CAPTCHAs.

---

## Common Problems and Solutions

### "campaign with id=X not found"

The campaign ID you entered does not exist in the database.
Double-check the ID of your campaign and try again.

### Browser opens but nothing happens / browser closes immediately

Make sure Chromium is installed:
```
playwright install chromium
```

### "Error: Navigation timeout"

Your internet connection may be slow or Google is temporarily blocking requests.
Wait a few minutes, then try again with fewer pages (`--pages 3`).

### CAPTCHA keeps coming back after solving

- Make sure you completed the full CAPTCHA challenge before pressing ENTER.
- Try waiting a bit longer on the results page before pressing ENTER.
- Take a break of 10–15 minutes before running the scraper again.

### Terminal says "Done. Collected 0 unique URLs."

- Check that your search query returns results in a regular browser.
- Try a different or more specific query.
- The tool filters out social media and directory sites — if your query returns
  mostly those, try adding words like "official site" or "company website".

### The log file shows errors

Check `logs/leadhunter.log` — it contains detailed information about what went wrong.
Share this file if you need help troubleshooting.

---

## How Many Pages Should You Scrape?

| Goal                       | Recommended pages |
|----------------------------|-------------------|
| Quick test / trial run     | 2–3               |
| Standard lead research     | 5–10              |
| Deep research              | 10–20             |

Each Google result page contains about 10 links. After filtering out social media and
directories, you can expect 5–8 real company websites per page.
