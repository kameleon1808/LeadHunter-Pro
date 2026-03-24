"""
gui_main.py — entry point for the LeadHunter Pro GUI.

Handles:
  - Frozen (PyInstaller EXE) path resolution via os.chdir(APP_DIR)
  - Database initialisation
  - First-run Playwright check
  - Launching the GUIApp window
"""

import os
import sys

# ---------------------------------------------------------------------------
# Path resolution — must happen before any relative-path imports
# ---------------------------------------------------------------------------
if getattr(sys, "frozen", False):
    # Running as a PyInstaller EXE — use the directory containing the .exe
    APP_DIR = os.path.dirname(sys.executable)
else:
    APP_DIR = os.path.dirname(os.path.abspath(__file__))

os.chdir(APP_DIR)

# ---------------------------------------------------------------------------
# Load .env before importing config (config reads os.getenv at import time)
# ---------------------------------------------------------------------------
from dotenv import load_dotenv  # noqa: E402
load_dotenv(os.path.join(APP_DIR, ".env"), override=False)

# ---------------------------------------------------------------------------
# Now safe to import project modules
# ---------------------------------------------------------------------------
import config  # noqa: E402
config.setup_logging(gui_mode=True)

import logging  # noqa: E402
logger = logging.getLogger(__name__)

from database import DatabaseManager  # noqa: E402


def _check_playwright():
    """Warn if Playwright Chromium is not installed."""
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            exe = p.chromium.executable_path
            if not os.path.exists(exe):
                raise FileNotFoundError(exe)
    except Exception:
        import tkinter.messagebox as mb
        mb.showwarning(
            "Playwright not installed",
            "Playwright Chromium browser was not found.\n\n"
            "Please run setup.bat (or: playwright install chromium) "
            "before using the Scrape feature.",
        )


def main():
    logger.info("LeadHunter Pro GUI starting — APP_DIR=%s", APP_DIR)

    # Ensure required directories exist
    os.makedirs("data",    exist_ok=True)
    os.makedirs("logs",    exist_ok=True)
    os.makedirs("exports", exist_ok=True)

    # Init database
    db = DatabaseManager(config.DATABASE_PATH)
    db.initialize_db()
    logger.info("Database ready: %s", config.DATABASE_PATH)

    # Non-blocking Playwright check (only warns, doesn't block launch)
    _check_playwright()

    # Launch GUI
    from gui import GUIApp
    app = GUIApp(db)
    app.mainloop()


if __name__ == "__main__":
    main()
