"""
LeadsBrowserScreen — filterable lead table with row-detail expand.
"""

from typing import List, Optional

import customtkinter as ctk

from database import DatabaseManager


class LeadsBrowserScreen(ctk.CTkFrame):
    def __init__(self, parent, db: DatabaseManager, **kwargs):
        super().__init__(parent, fg_color="transparent", **kwargs)
        self._db = db
        self._campaign_id: Optional[int] = None
        self._all_leads: list = []
        self._filtered: list = []
        self._page = 0
        self._page_size = 100
        self._build()

    # ── Public ───────────────────────────────────────────────────────────────

    def load_campaign(self, campaign_id: int):
        self._campaign_id = campaign_id
        self._page = 0
        self._detail_frame.grid_remove()
        self._load_leads()

    def refresh(self):
        if self._campaign_id:
            self._load_leads()

    # ── Build UI ──────────────────────────────────────────────────────────────

    def _build(self):
        self.columnconfigure(0, weight=1)
        self.rowconfigure(2, weight=1)

        # ── Header ──────────────────────────────────────────────────────────
        hdr = ctk.CTkFrame(self, fg_color="transparent")
        hdr.grid(row=0, column=0, sticky="ew", padx=20, pady=(20, 4))
        self._title_lbl = ctk.CTkLabel(
            hdr, text="Leads", font=ctk.CTkFont(size=22, weight="bold")
        )
        self._title_lbl.pack(side="left")
        ctk.CTkButton(hdr, text="↻ Refresh", width=90, command=self.refresh).pack(side="right")

        # ── Filter bar ───────────────────────────────────────────────────────
        filter_bar = ctk.CTkFrame(self)
        filter_bar.grid(row=1, column=0, sticky="ew", padx=20, pady=4)

        ctk.CTkLabel(filter_bar, text="Search:", font=ctk.CTkFont(size=12)).pack(side="left", padx=(12, 4))
        self._search_var = ctk.StringVar()
        self._search_var.trace_add("write", lambda *_: self._apply_filters())
        ctk.CTkEntry(filter_bar, textvariable=self._search_var, placeholder_text="Company, email…", width=200).pack(
            side="left", padx=4
        )

        ctk.CTkLabel(filter_bar, text="Quality:", font=ctk.CTkFont(size=12)).pack(side="left", padx=(12, 4))
        self._quality_var = ctk.StringVar(value="Any")
        ctk.CTkOptionMenu(
            filter_bar,
            variable=self._quality_var,
            values=["Any", "8+ (High)", "5–7 (Medium)", "< 5 (Low)"],
            width=130,
            command=lambda _: self._apply_filters(),
        ).pack(side="left", padx=4)

        ctk.CTkLabel(filter_bar, text="Industry:", font=ctk.CTkFont(size=12)).pack(side="left", padx=(12, 4))
        self._industry_var = ctk.StringVar(value="Any")
        self._industry_menu = ctk.CTkOptionMenu(
            filter_bar,
            variable=self._industry_var,
            values=["Any"],
            width=160,
            command=lambda _: self._apply_filters(),
        )
        self._industry_menu.pack(side="left", padx=4)

        ctk.CTkButton(filter_bar, text="Clear", width=60, command=self._clear_filters).pack(
            side="left", padx=8
        )
        self._count_lbl = ctk.CTkLabel(filter_bar, text="0 leads", text_color="gray60", font=ctk.CTkFont(size=11))
        self._count_lbl.pack(side="right", padx=12)

        # ── Table area ───────────────────────────────────────────────────────
        table_area = ctk.CTkFrame(self, fg_color="transparent")
        table_area.grid(row=2, column=0, sticky="nsew", padx=20, pady=4)
        table_area.columnconfigure(0, weight=1)
        table_area.rowconfigure(0, weight=1)

        # Header row
        hdr_row = ctk.CTkFrame(table_area, fg_color=("#1F4E79", "#1F4E79"), corner_radius=0)
        hdr_row.grid(row=0, column=0, sticky="ew")
        cols = ["#", "Company", "Industry", "Size", "Contact", "Email", "Phone", "Score"]
        widths = [40, 180, 140, 100, 140, 180, 120, 60]
        for i, (col, w) in enumerate(zip(cols, widths)):
            ctk.CTkLabel(
                hdr_row, text=col, font=ctk.CTkFont(size=12, weight="bold"),
                text_color="white", width=w, anchor="w"
            ).grid(row=0, column=i, padx=(8, 4), pady=6, sticky="w")

        self._scroll = ctk.CTkScrollableFrame(table_area, height=300)
        self._scroll.grid(row=1, column=0, sticky="nsew")
        self._col_widths = widths
        self._row_frames: list = []

        # ── Pagination ───────────────────────────────────────────────────────
        page_bar = ctk.CTkFrame(self, fg_color="transparent")
        page_bar.grid(row=3, column=0, sticky="ew", padx=20, pady=4)
        self._load_more_btn = ctk.CTkButton(
            page_bar, text="Load more (next 100)", width=180, command=self._load_more
        )
        self._load_more_btn.pack(side="left")
        self._page_lbl = ctk.CTkLabel(page_bar, text="", text_color="gray60", font=ctk.CTkFont(size=11))
        self._page_lbl.pack(side="left", padx=12)

        # ── Detail panel ─────────────────────────────────────────────────────
        self._detail_frame = ctk.CTkFrame(self)
        self._detail_frame.grid(row=4, column=0, sticky="ew", padx=20, pady=(4, 20))
        self._detail_frame.grid_remove()
        self._detail_text = ctk.CTkTextbox(self._detail_frame, height=160, font=ctk.CTkFont(family="Courier", size=11))
        self._detail_text.pack(fill="both", expand=True, padx=12, pady=12)

    # ── Data loading ──────────────────────────────────────────────────────────

    def _load_leads(self):
        self._all_leads = self._db.get_leads(self._campaign_id)
        # Update industry dropdown
        industries = sorted(set(l.industry or "—" for l in self._all_leads if l.industry))
        self._industry_menu.configure(values=["Any"] + industries)
        self._title_lbl.configure(text=f"Leads — {len(self._all_leads)} total")
        self._apply_filters()

    def _apply_filters(self):
        search = self._search_var.get().lower()
        quality = self._quality_var.get()
        industry = self._industry_var.get()

        filtered = []
        for lead in self._all_leads:
            # Search filter
            if search:
                haystack = " ".join([
                    lead.company_name or "", lead.contact_email or "",
                    lead.company_email or "", lead.industry or "",
                    lead.contact_name or "",
                ]).lower()
                if search not in haystack:
                    continue
            # Quality filter
            score = lead.quality_score or 0
            if quality == "8+ (High)" and score < 8:
                continue
            if quality == "5–7 (Medium)" and not (5 <= score <= 7):
                continue
            if quality == "< 5 (Low)" and score >= 5:
                continue
            # Industry filter
            if industry != "Any" and (lead.industry or "—") != industry:
                continue
            filtered.append(lead)

        self._filtered = filtered
        self._page = 0
        self._count_lbl.configure(text=f"{len(filtered)} leads")
        self._render_page()

    def _render_page(self):
        for frame in self._row_frames:
            frame.destroy()
        self._row_frames.clear()

        start = 0
        end = (self._page + 1) * self._page_size
        visible = self._filtered[start:end]

        for idx, lead in enumerate(visible):
            bg = ("gray17", "gray20") if idx % 2 == 0 else ("gray14", "gray17")
            row = ctk.CTkFrame(self._scroll, fg_color=bg, corner_radius=0)
            row.pack(fill="x")

            score = lead.quality_score or 0
            score_color = "#22C55E" if score >= 8 else ("#F59E0B" if score >= 5 else "#EF4444")

            vals = [
                idx + 1,
                lead.company_name or "—",
                lead.industry or "—",
                lead.company_size or "—",
                (lead.contact_name or "—") + (f"\n{lead.contact_title}" if lead.contact_title else ""),
                lead.contact_email or lead.company_email or "—",
                lead.company_phone or "—",
                score,
            ]
            for i, (val, w) in enumerate(zip(vals, self._col_widths)):
                color = score_color if i == 7 else None
                label_kwargs = dict(
                    text=str(val),
                    font=ctk.CTkFont(size=11),
                    width=w,
                    anchor="w",
                    wraplength=w - 10,
                )
                if color:
                    label_kwargs["text_color"] = color
                lbl = ctk.CTkLabel(row, **label_kwargs)
                lbl.grid(row=0, column=i, padx=(8, 4), pady=4, sticky="w")
                lbl.bind("<Button-1>", lambda e, l=lead: self._show_detail(l))
            row.bind("<Button-1>", lambda e, l=lead: self._show_detail(l))
            self._row_frames.append(row)

        shown = min(end, len(self._filtered))
        self._page_lbl.configure(text=f"Showing {shown} of {len(self._filtered)}")
        self._load_more_btn.configure(
            state="normal" if end < len(self._filtered) else "disabled"
        )

    def _load_more(self):
        self._page += 1
        self._render_page()

    def _clear_filters(self):
        self._search_var.set("")
        self._quality_var.set("Any")
        self._industry_var.set("Any")

    def _show_detail(self, lead):
        lines = [
            f"Company:       {lead.company_name or '—'}",
            f"Industry:      {lead.industry or '—'}",
            f"Size:          {lead.company_size or '—'}",
            f"Description:   {lead.description or '—'}",
            f"",
            f"Contact:       {lead.contact_name or '—'}  ({lead.contact_title or '—'})",
            f"Contact Email: {lead.contact_email or '—'}",
            f"LinkedIn:      {lead.contact_linkedin or '—'}",
            f"Company Email: {lead.company_email or '—'}",
            f"Phone:         {lead.company_phone or '—'}",
            f"Address:       {lead.address or '—'}",
            f"Clients:       {lead.clients_info or '—'}",
            f"",
            f"Quality Score: {lead.quality_score or '—'}",
            f"Source URL:    {lead.website_url or '—'}",
        ]
        self._detail_text.configure(state="normal")
        self._detail_text.delete("1.0", "end")
        self._detail_text.insert("1.0", "\n".join(lines))
        self._detail_text.configure(state="disabled")
        self._detail_frame.grid()
