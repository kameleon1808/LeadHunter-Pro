"""
CampaignsScreen — home screen showing all campaigns and a create-campaign form.
"""

import customtkinter as ctk
from tkinter import messagebox

from database import DatabaseManager
from gui.widgets import ScrollableTable, StatusBadge


class CampaignsScreen(ctk.CTkFrame):
    def __init__(self, parent, db: DatabaseManager, on_open_campaign, **kwargs):
        super().__init__(parent, fg_color="transparent", **kwargs)
        self._db = db
        self._on_open_campaign = on_open_campaign
        self._build()

    def _build(self):
        # ── Header ──────────────────────────────────────────────────────────
        hdr = ctk.CTkFrame(self, fg_color="transparent")
        hdr.pack(fill="x", padx=20, pady=(20, 0))
        ctk.CTkLabel(
            hdr, text="Campaigns", font=ctk.CTkFont(size=24, weight="bold")
        ).pack(side="left")
        ctk.CTkButton(
            hdr, text="↻  Refresh", width=100, command=self._load_campaigns
        ).pack(side="right")

        # ── Create form ──────────────────────────────────────────────────────
        form_frame = ctk.CTkFrame(self)
        form_frame.pack(fill="x", padx=20, pady=12)

        ctk.CTkLabel(
            form_frame, text="New Campaign", font=ctk.CTkFont(size=14, weight="bold")
        ).grid(row=0, column=0, columnspan=7, padx=12, pady=(10, 4), sticky="w")

        fields = [
            ("Name *", "e.g. Marketing Agencies Serbia"),
            ("Niche *", "e.g. digital marketing"),
            ("Country", "e.g. Serbia  (optional)"),
        ]
        self._entries: list[ctk.CTkEntry] = []
        for i, (lbl, ph) in enumerate(fields):
            ctk.CTkLabel(form_frame, text=lbl, font=ctk.CTkFont(size=12)).grid(
                row=1, column=i * 2, padx=(12, 4), pady=8, sticky="w"
            )
            entry = ctk.CTkEntry(form_frame, placeholder_text=ph, width=200)
            entry.grid(row=1, column=i * 2 + 1, padx=(0, 16), pady=8, sticky="w")
            self._entries.append(entry)

        ctk.CTkButton(
            form_frame, text="＋  Create Campaign", command=self._create_campaign
        ).grid(row=1, column=6, padx=12, pady=8)

        # ── Table ────────────────────────────────────────────────────────────
        ctk.CTkLabel(
            self, text="All Campaigns", font=ctk.CTkFont(size=14, weight="bold")
        ).pack(padx=20, pady=(4, 0), anchor="w")

        self._table = ScrollableTable(
            self,
            columns=["ID", "Name", "Niche", "Country", "Status", "URLs", "Leads", "Created"],
            col_widths=[40, 200, 160, 100, 100, 60, 60, 100],
            on_select=self._on_row_select,
            height=400,
        )
        self._table.pack(fill="both", expand=True, padx=20, pady=(4, 20))

        self._load_campaigns()

    def _load_campaigns(self):
        self._table.clear()
        campaigns = self._db.get_all_campaigns()
        for c in campaigns:
            created = c.created_at.strftime("%Y-%m-%d") if c.created_at else "—"
            self._table.add_row((
                c.id,
                c.name,
                c.niche,
                c.target_country or "—",
                c.status.upper(),
                c.total_urls,
                c.total_leads,
                created,
            ))

    def _create_campaign(self):
        name_entry, niche_entry, country_entry = self._entries
        name = name_entry.get().strip()
        niche = niche_entry.get().strip()
        country = country_entry.get().strip() or None

        if not name or not niche:
            messagebox.showwarning("Missing fields", "Name and Niche are required.")
            return

        try:
            self._db.create_campaign(name=name, niche=niche, target_country=country)
            name_entry.delete(0, "end")
            niche_entry.delete(0, "end")
            country_entry.delete(0, "end")
            self._load_campaigns()
            # Notify app to refresh sidebar
            self._on_open_campaign(None)
        except Exception as e:
            messagebox.showerror("Error", f"Failed to create campaign:\n{e}")

    def _on_row_select(self, idx, row_data):
        campaign_id = row_data[0]
        self._on_open_campaign(campaign_id)

    def refresh(self):
        self._load_campaigns()
