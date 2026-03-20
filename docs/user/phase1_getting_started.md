# Getting Started with LeadHunter Pro

Welcome! This guide will walk you through everything you need to get LeadHunter Pro
running on your computer — no technical experience required.

---

## What is LeadHunter Pro?

LeadHunter Pro is a tool that helps you find business leads automatically.

You give it a list of websites, it visits each one, collects information about the
company (name, contact email, phone number, etc.), and saves everything neatly into
a database you can export or search later.

Think of it like having a research assistant that never gets tired and can process
hundreds of websites in the time it would take a human to check five.

---

## System Requirements

Before you start, make sure your computer has:

- **Python 3.10 or newer** — the programming language LeadHunter Pro is written in.
  Download it free from [python.org](https://python.org).
- **pip** — Python's package installer. It comes bundled with Python automatically.
- **~50 MB of free disk space** — for the program and its database.
- **Internet connection** — to scrape websites (not needed just for installation).

> **Not sure if you have Python?**
> Open a terminal (Command Prompt on Windows, Terminal on Mac/Linux) and type:
> ```
> python --version
> ```
> If you see something like `Python 3.11.4`, you're good to go.

---

## Step-by-Step Installation

### Step 1 — Download the project

If you received a ZIP file, extract it somewhere easy to find, like your Desktop.

If you're using Git, open a terminal and run:
```
git clone <repository-url>
cd leadhunter-pro
```

### Step 2 — Open a terminal in the project folder

- **Windows**: Open File Explorer, navigate to the `leadhunter-pro` folder,
  hold Shift, right-click, and choose "Open PowerShell window here".
- **Mac/Linux**: Open Terminal and type `cd ` (with a space), then drag the
  `leadhunter-pro` folder into the terminal window and press Enter.

### Step 3 — Install the required packages

In your terminal, type exactly:
```
pip install -r requirements.txt
```

Press Enter and wait. You'll see text scrolling — that's normal. When it stops and
shows no errors, the installation is complete.

> **Tip:** If you see a "permission denied" error, try:
> `pip install --user -r requirements.txt`

### Step 4 — Run for the first time

```
python main.py
```

You should see:
```
LeadHunter Pro initialized successfully
```

That's it — the program is working!

---

## What Happens When You Run It?

The first time you run `python main.py`, LeadHunter Pro:

1. **Creates a `data/` folder** — this is where your database lives.
2. **Creates `data/leadhunter.db`** — a SQLite database file that stores all your
   campaigns, URLs, and leads.
3. **Creates a `logs/` folder** and a `logs/leadhunter.log` file — this records
   everything the program does, which helps you troubleshoot issues.

Your project folder will look like this after the first run:

```
leadhunter-pro/
├── data/
│   └── leadhunter.db      ← your database
├── logs/
│   └── leadhunter.log     ← activity log
├── main.py
├── ... (other files)
```

> **Important:** Do not delete `data/leadhunter.db` — it contains all your leads!
> Back it up regularly by copying it somewhere safe.

---

## Running the Tests

The project includes automated tests to make sure everything is working correctly.

Run them with:
```
pytest tests/
```

You should see output ending with something like:
```
========== 15 passed in 1.23s ==========
```

If all tests pass, the database layer is working perfectly.

---

## FAQ

**Q: Do I need to create the `data/` folder myself?**
No. LeadHunter Pro creates it automatically on first run.

**Q: Can I move the database file?**
Yes, but you'll need to update `DATABASE_PATH` in `config.py` to point to the new
location.

**Q: Will running `python main.py` again overwrite my data?**
No. The database is only created if it doesn't exist. Running the program again
is safe and will not delete anything.

**Q: What is a "campaign"?**
A campaign is one lead-hunting project. For example: "Find SaaS companies in the US."
Each campaign has its own list of URLs to scrape and its own list of leads.

**Q: Where are my leads stored?**
All leads are in the `data/leadhunter.db` file. Future versions of LeadHunter Pro
will include an export feature (CSV, Excel).

**Q: The program printed an error. What do I do?**
Check the `logs/leadhunter.log` file — it has the full error with more detail.
See the Troubleshooting section below.

---

## Troubleshooting

### "python: command not found" or "'python' is not recognized"

Python is not installed or not on your PATH.
- Download Python from [python.org](https://python.org).
- During installation on Windows, tick the box that says **"Add Python to PATH"**.
- After installing, close and reopen your terminal, then try again.
- On some systems you may need to type `python3` instead of `python`.

### "pip: command not found"

Try `pip3` instead of `pip`. If that also fails, try:
```
python -m pip install -r requirements.txt
```

### "ModuleNotFoundError: No module named 'sqlalchemy'"

The packages were not installed. Run:
```
pip install -r requirements.txt
```

### "PermissionError" when creating the database

The program cannot write to the `data/` folder. Try running your terminal as an
Administrator (Windows) or using `sudo` (Mac/Linux). Alternatively, make sure
the project folder is somewhere you have write access to (e.g., your home directory,
not `C:\Program Files`).

### Tests fail with "FAILED tests/test_database.py"

Read the error message carefully — it tells you which test failed and why.
Common causes:
- Packages not installed (run `pip install -r requirements.txt`).
- Python version too old (check with `python --version`, needs 3.10+).

### The log file is growing very large

Open `config.py` and change `LOG_LEVEL = "INFO"` to `LOG_LEVEL = "WARNING"`.
This reduces how much gets written to the log. You can also safely delete
`logs/leadhunter.log` — a new one will be created on next run.

---

## Need More Help?

- Check the **technical documentation** in `docs/technical/phase1_database.md`
  for in-depth details about how the system works.
- If you found a bug, please report it with the contents of `logs/leadhunter.log`
  included.
