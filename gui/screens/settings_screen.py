"""
SettingsScreen — GUI editor for .env settings.
Writes individual keys with python-dotenv.set_key() without destroying the file.
"""

import os
from tkinter import filedialog, messagebox

import customtkinter as ctk
from dotenv import load_dotenv, set_key

import config

DOTENV_PATH = ".env"


class SettingsScreen(ctk.CTkFrame):
    def __init__(self, parent, **kwargs):
        super().__init__(parent, fg_color="transparent", **kwargs)
        self._entries: dict = {}
        self._checkboxes: dict = {}
        self._build()
        self._load_values()

    # ── Build UI ──────────────────────────────────────────────────────────────

    def _build(self):
        ctk.CTkLabel(
            self, text="Settings", font=ctk.CTkFont(size=24, weight="bold")
        ).pack(padx=20, pady=(20, 4), anchor="w")
        ctk.CTkLabel(
            self,
            text="Changes are saved to .env and take effect on the next run (browser path changes require restart).",
            font=ctk.CTkFont(size=11),
            text_color="gray60",
        ).pack(padx=20, pady=(0, 12), anchor="w")

        scroll = ctk.CTkScrollableFrame(self)
        scroll.pack(fill="both", expand=True, padx=20, pady=(0, 4))

        self._build_section(scroll, "AI Extractor", [
            ("ANTHROPIC_API_KEY", "Anthropic API Key (optional)", "password"),
            ("CLAUDE_MODEL",      "Claude Model", "text"),
            ("CLAUDE_CODE_MAX_CONCURRENT", "Claude CLI Max Concurrent (1–10)", "text"),
        ])
        self._build_section(scroll, "Scraping", [
            ("SEARCH_PAGES_DEFAULT",          "Default Search Pages", "text"),
            ("MIN_DELAY_SECONDS",             "Min Delay Between Pages (seconds)", "text"),
            ("MAX_DELAY_SECONDS",             "Max Delay Between Pages (seconds)", "text"),
            ("PLAYWRIGHT_HEADLESS",           "Headless Browser", "checkbox"),
            ("USE_BRAVE",                     "Use Brave Browser", "checkbox"),
            ("BRAVE_EXECUTABLE_PATH",         "Brave Executable Path", "browse_file"),
            ("BRAVE_USER_DATA_DIR",           "Brave User Data Dir", "browse_dir"),
        ])
        self._build_section(scroll, "Enrichment", [
            ("ENRICHMENT_CONCURRENT_REQUESTS", "Concurrent HTTP Requests (1–20)", "text"),
            ("MAX_PAGES_PER_SITE",             "Max Pages Per Site", "text"),
            ("REQUEST_TIMEOUT_SECONDS",        "Request Timeout (seconds)", "text"),
        ])
        self._build_section(scroll, "Database", [
            ("DATABASE_PATH", "Database Path", "readonly"),
        ])

        btn_row = ctk.CTkFrame(self, fg_color="transparent")
        btn_row.pack(padx=20, pady=12, anchor="w")
        ctk.CTkButton(btn_row, text="💾  Save Settings", command=self._save).pack(side="left")
        ctk.CTkButton(
            btn_row, text="↺  Reset to Defaults", width=150,
            fg_color="transparent", border_width=1, command=self._load_values
        ).pack(side="left", padx=12)

        self._toast_lbl = ctk.CTkLabel(self, text="", text_color="#22C55E", font=ctk.CTkFont(size=12))
        self._toast_lbl.pack(padx=20, pady=(0, 12), anchor="w")

    def _build_section(self, parent, title: str, fields: list):
        section = ctk.CTkFrame(parent)
        section.pack(fill="x", pady=8)

        ctk.CTkLabel(
            section, text=title, font=ctk.CTkFont(size=14, weight="bold")
        ).grid(row=0, column=0, columnspan=3, padx=14, pady=(10, 4), sticky="w")

        for row_idx, (key, label, widget_type) in enumerate(fields, start=1):
            ctk.CTkLabel(section, text=label, font=ctk.CTkFont(size=12), width=260, anchor="w").grid(
                row=row_idx, column=0, padx=(14, 8), pady=6, sticky="w"
            )

            if widget_type == "checkbox":
                var = ctk.BooleanVar()
                cb = ctk.CTkCheckBox(section, text="", variable=var)
                cb.grid(row=row_idx, column=1, padx=4, pady=6, sticky="w")
                self._checkboxes[key] = var

            elif widget_type == "password":
                entry = ctk.CTkEntry(section, width=360, show="•")
                entry.grid(row=row_idx, column=1, padx=4, pady=6, sticky="w")
                self._entries[key] = entry

            elif widget_type == "readonly":
                entry = ctk.CTkEntry(section, width=360, state="disabled")
                entry.grid(row=row_idx, column=1, padx=4, pady=6, sticky="w")
                self._entries[key] = entry

            elif widget_type in ("browse_file", "browse_dir"):
                row_frame = ctk.CTkFrame(section, fg_color="transparent")
                row_frame.grid(row=row_idx, column=1, padx=4, pady=6, sticky="w")
                entry = ctk.CTkEntry(row_frame, width=320)
                entry.pack(side="left")
                browse_fn = (
                    (lambda e=entry: self._browse_file(e))
                    if widget_type == "browse_file"
                    else (lambda e=entry: self._browse_dir(e))
                )
                ctk.CTkButton(row_frame, text="📂", width=36, command=browse_fn).pack(side="left", padx=4)
                self._entries[key] = entry

            else:
                entry = ctk.CTkEntry(section, width=360)
                entry.grid(row=row_idx, column=1, padx=4, pady=6, sticky="w")
                self._entries[key] = entry

    # ── Values ────────────────────────────────────────────────────────────────

    def _load_values(self):
        """Populate fields from current os.environ / config values."""
        str_fields = {
            "ANTHROPIC_API_KEY":             config.ANTHROPIC_API_KEY or "",
            "CLAUDE_MODEL":                  config.CLAUDE_MODEL,
            "CLAUDE_CODE_MAX_CONCURRENT":    str(config.CLAUDE_CODE_MAX_CONCURRENT),
            "SEARCH_PAGES_DEFAULT":          str(config.SEARCH_PAGES_DEFAULT),
            "MIN_DELAY_SECONDS":             str(config.MIN_DELAY_SECONDS),
            "MAX_DELAY_SECONDS":             str(config.MAX_DELAY_SECONDS),
            "BRAVE_EXECUTABLE_PATH":         config.BRAVE_EXECUTABLE_PATH or "",
            "BRAVE_USER_DATA_DIR":           config.BRAVE_USER_DATA_DIR or "",
            "ENRICHMENT_CONCURRENT_REQUESTS": str(config.ENRICHMENT_CONCURRENT_REQUESTS),
            "MAX_PAGES_PER_SITE":            str(config.MAX_PAGES_PER_SITE),
            "REQUEST_TIMEOUT_SECONDS":       str(config.REQUEST_TIMEOUT_SECONDS),
            "DATABASE_PATH":                 config.DATABASE_PATH,
        }
        bool_fields = {
            "PLAYWRIGHT_HEADLESS": config.PLAYWRIGHT_HEADLESS,
            "USE_BRAVE":           config.USE_BRAVE,
        }
        for key, val in str_fields.items():
            if key in self._entries:
                entry = self._entries[key]
                entry.configure(state="normal")
                entry.delete(0, "end")
                entry.insert(0, val)
                if key == "DATABASE_PATH":
                    entry.configure(state="disabled")
        for key, val in bool_fields.items():
            if key in self._checkboxes:
                self._checkboxes[key].set(val)

    def _save(self):
        if not os.path.exists(DOTENV_PATH):
            # Create minimal .env from example or blank
            with open(DOTENV_PATH, "w") as f:
                f.write("# LeadHunter Pro .env\n")

        for key, entry in self._entries.items():
            if key == "DATABASE_PATH":
                continue
            val = entry.get().strip()
            set_key(DOTENV_PATH, key, val)

        for key, var in self._checkboxes.items():
            set_key(DOTENV_PATH, key, "true" if var.get() else "false")

        # Re-read .env and update config globals in memory
        load_dotenv(DOTENV_PATH, override=True)
        _refresh_config()

        self._show_toast("Settings saved. Restart required for browser path changes.")

    def _show_toast(self, msg: str):
        self._toast_lbl.configure(text=msg)
        self.after(5000, lambda: self._toast_lbl.configure(text=""))

    def _browse_file(self, entry: ctk.CTkEntry):
        path = filedialog.askopenfilename(title="Select file")
        if path:
            entry.delete(0, "end")
            entry.insert(0, path)

    def _browse_dir(self, entry: ctk.CTkEntry):
        path = filedialog.askdirectory(title="Select directory")
        if path:
            entry.delete(0, "end")
            entry.insert(0, path)


def _refresh_config():
    """Update config module globals from the current os.environ after .env reload."""
    config.ANTHROPIC_API_KEY             = os.getenv("ANTHROPIC_API_KEY")
    config.CLAUDE_MODEL                  = os.getenv("CLAUDE_MODEL", config.CLAUDE_MODEL)
    config.CLAUDE_CODE_MAX_CONCURRENT    = int(os.getenv("CLAUDE_CODE_MAX_CONCURRENT", str(config.CLAUDE_CODE_MAX_CONCURRENT)))
    config.SEARCH_PAGES_DEFAULT          = int(os.getenv("SEARCH_PAGES_DEFAULT", str(config.SEARCH_PAGES_DEFAULT)))
    config.PLAYWRIGHT_HEADLESS           = os.getenv("PLAYWRIGHT_HEADLESS", "false").lower() == "true"
    config.USE_BRAVE                     = os.getenv("USE_BRAVE", "true").lower() == "true"
    config.BRAVE_EXECUTABLE_PATH         = os.getenv("BRAVE_EXECUTABLE_PATH", config.BRAVE_EXECUTABLE_PATH)
    config.BRAVE_USER_DATA_DIR           = os.getenv("BRAVE_USER_DATA_DIR", config.BRAVE_USER_DATA_DIR)
    config.ENRICHMENT_CONCURRENT_REQUESTS = int(os.getenv("ENRICHMENT_CONCURRENT_REQUESTS", str(config.ENRICHMENT_CONCURRENT_REQUESTS)))
    config.MAX_PAGES_PER_SITE            = int(os.getenv("MAX_PAGES_PER_SITE", str(config.MAX_PAGES_PER_SITE)))
    config.REQUEST_TIMEOUT_SECONDS       = int(os.getenv("REQUEST_TIMEOUT_SECONDS", str(config.REQUEST_TIMEOUT_SECONDS)))
    config.MIN_DELAY_SECONDS             = float(os.getenv("MIN_DELAY_SECONDS", str(config.MIN_DELAY_SECONDS)))
    config.MAX_DELAY_SECONDS             = float(os.getenv("MAX_DELAY_SECONDS", str(config.MAX_DELAY_SECONDS)))
