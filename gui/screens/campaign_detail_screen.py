"""
CampaignDetailScreen — per-campaign action cards and stats header.
"""

import os
from tkinter import filedialog, messagebox
from typing import Callable

import customtkinter as ctk

from database import DatabaseManager
from export import ExcelExporter
from gui.event_bus import EventBus, TaskDoneEvent
from gui.task_runner import BackgroundTaskRunner, GUIPipelineRunner
from gui.widgets import StatCard, StatusBadge


class CampaignDetailScreen(ctk.CTkFrame):
    def __init__(
        self,
        parent,
        db: DatabaseManager,
        runner: BackgroundTaskRunner,
        event_bus: EventBus,
        on_open_monitor: Callable,
        on_open_leads: Callable,
        **kwargs,
    ):
        super().__init__(parent, fg_color="transparent", **kwargs)
        self._db = db
        self._runner = runner
        self._event_bus = event_bus
        self._on_open_monitor = on_open_monitor
        self._on_open_leads = on_open_leads
        self._campaign_id: int | None = None
        self._build()

    # ── Public ──────────────────────────────────────────────────────────────

    def load_campaign(self, campaign_id: int):
        self._campaign_id = campaign_id
        self._refresh_header()
        self._refresh_stats()
        self._update_button_states()

    def refresh(self):
        if self._campaign_id:
            self._refresh_header()
            self._refresh_stats()

    def on_task_done(self, event: TaskDoneEvent):
        """Called by app.py when a TaskDoneEvent arrives for this campaign."""
        self._update_button_states()
        self._refresh_stats()
        if not event.success:
            messagebox.showerror(
                "Task Failed",
                f"{event.task_type.title()} failed:\n\n{event.error}",
            )
        else:
            if event.task_type == "export":
                messagebox.showinfo("Export Complete", f"File saved:\n{event.result}")
            elif event.task_type == "pipeline":
                messagebox.showinfo("Pipeline Complete", f"Excel file:\n{event.result}")

    # ── Build UI ─────────────────────────────────────────────────────────────

    def _build(self):
        self.columnconfigure(0, weight=1)

        # ── Header ──────────────────────────────────────────────────────────
        self._hdr_frame = ctk.CTkFrame(self, fg_color="transparent")
        self._hdr_frame.grid(row=0, column=0, sticky="ew", padx=20, pady=(20, 0))

        self._name_lbl = ctk.CTkLabel(
            self._hdr_frame, text="Campaign", font=ctk.CTkFont(size=22, weight="bold")
        )
        self._name_lbl.pack(side="left")

        self._status_badge = StatusBadge(self._hdr_frame, "pending")
        self._status_badge.pack(side="left", padx=12)

        btn_row = ctk.CTkFrame(self._hdr_frame, fg_color="transparent")
        btn_row.pack(side="right")
        ctk.CTkButton(
            btn_row, text="📊 Monitor", width=110, command=lambda: self._on_open_monitor(self._campaign_id)
        ).pack(side="left", padx=4)
        ctk.CTkButton(
            btn_row, text="📋 Leads", width=110, command=lambda: self._on_open_leads(self._campaign_id)
        ).pack(side="left", padx=4)
        ctk.CTkButton(
            btn_row, text="↻ Refresh", width=90, fg_color="transparent",
            border_width=1, command=self.refresh
        ).pack(side="left", padx=4)

        # ── Stat cards row ───────────────────────────────────────────────────
        stats_row = ctk.CTkFrame(self, fg_color="transparent")
        stats_row.grid(row=1, column=0, sticky="ew", padx=20, pady=12)
        self._card_urls     = StatCard(stats_row, "Total URLs")
        self._card_pending  = StatCard(stats_row, "Pending")
        self._card_done     = StatCard(stats_row, "Completed")
        self._card_failed   = StatCard(stats_row, "Failed")
        self._card_leads    = StatCard(stats_row, "Leads Found")
        for card in (self._card_urls, self._card_pending, self._card_done,
                     self._card_failed, self._card_leads):
            card.pack(side="left", padx=6, pady=4, ipadx=4)

        # ── 4 action cards ───────────────────────────────────────────────────
        cards_area = ctk.CTkFrame(self, fg_color="transparent")
        cards_area.grid(row=2, column=0, sticky="nsew", padx=20, pady=4)
        cards_area.columnconfigure((0, 1), weight=1)
        self.rowconfigure(2, weight=1)

        self._scrape_card   = self._build_scrape_card(cards_area)
        self._enrich_card   = self._build_enrich_card(cards_area)
        self._export_card   = self._build_export_card(cards_area)
        self._pipeline_card = self._build_pipeline_card(cards_area)

        self._scrape_card.grid(row=0, column=0, padx=6, pady=6, sticky="nsew")
        self._enrich_card.grid(row=0, column=1, padx=6, pady=6, sticky="nsew")
        self._export_card.grid(row=1, column=0, padx=6, pady=6, sticky="nsew")
        self._pipeline_card.grid(row=1, column=1, padx=6, pady=6, sticky="nsew")

    # ── Action cards ─────────────────────────────────────────────────────────

    def _build_scrape_card(self, parent) -> ctk.CTkFrame:
        card = ctk.CTkFrame(parent)
        ctk.CTkLabel(card, text="🔍  Scrape URLs", font=ctk.CTkFont(size=14, weight="bold")).pack(
            padx=16, pady=(14, 6), anchor="w"
        )
        ctk.CTkLabel(card, text="Google search query:", font=ctk.CTkFont(size=12)).pack(
            padx=16, anchor="w"
        )
        self._scrape_query = ctk.CTkEntry(card, placeholder_text='e.g. "marketing agencies Belgrade"', width=340)
        self._scrape_query.pack(padx=16, pady=4, anchor="w")

        row = ctk.CTkFrame(card, fg_color="transparent")
        row.pack(padx=16, fill="x")
        ctk.CTkLabel(row, text="Pages:", font=ctk.CTkFont(size=12)).pack(side="left")
        self._scrape_pages = ctk.CTkEntry(row, width=60, placeholder_text="5")
        self._scrape_pages.pack(side="left", padx=8)

        self._scrape_btn = ctk.CTkButton(
            card, text="Start Scrape", command=self._start_scrape
        )
        self._scrape_btn.pack(padx=16, pady=12, anchor="w")

        self._scrape_status = ctk.CTkLabel(card, text="Idle", text_color="gray60", font=ctk.CTkFont(size=11))
        self._scrape_status.pack(padx=16, pady=(0, 12), anchor="w")
        return card

    def _build_enrich_card(self, parent) -> ctk.CTkFrame:
        card = ctk.CTkFrame(parent)
        ctk.CTkLabel(card, text="🤖  Enrich with AI", font=ctk.CTkFont(size=14, weight="bold")).pack(
            padx=16, pady=(14, 6), anchor="w"
        )
        self._enrich_pending_lbl = ctk.CTkLabel(
            card, text="Pending URLs: —", font=ctk.CTkFont(size=12)
        )
        self._enrich_pending_lbl.pack(padx=16, pady=4, anchor="w")
        ctk.CTkLabel(
            card,
            text="Visits each URL and extracts contact data\nusing Claude AI.",
            font=ctk.CTkFont(size=11),
            text_color="gray60",
            justify="left",
        ).pack(padx=16, pady=4, anchor="w")

        self._enrich_btn = ctk.CTkButton(
            card, text="Start Enrichment", command=self._start_enrich
        )
        self._enrich_btn.pack(padx=16, pady=12, anchor="w")

        self._enrich_status = ctk.CTkLabel(card, text="Idle", text_color="gray60", font=ctk.CTkFont(size=11))
        self._enrich_status.pack(padx=16, pady=(0, 12), anchor="w")
        return card

    def _build_export_card(self, parent) -> ctk.CTkFrame:
        card = ctk.CTkFrame(parent)
        ctk.CTkLabel(card, text="📥  Export to Excel", font=ctk.CTkFont(size=14, weight="bold")).pack(
            padx=16, pady=(14, 6), anchor="w"
        )
        row = ctk.CTkFrame(card, fg_color="transparent")
        row.pack(padx=16, fill="x")
        self._export_path = ctk.CTkEntry(row, placeholder_text="./exports/  (default)", width=270)
        self._export_path.pack(side="left")
        ctk.CTkButton(
            row, text="📂", width=36, command=self._browse_export
        ).pack(side="left", padx=6)

        self._export_btn = ctk.CTkButton(card, text="Export", command=self._start_export)
        self._export_btn.pack(padx=16, pady=12, anchor="w")

        self._export_status = ctk.CTkLabel(card, text="Idle", text_color="gray60", font=ctk.CTkFont(size=11))
        self._export_status.pack(padx=16, pady=(0, 12), anchor="w")
        return card

    def _build_pipeline_card(self, parent) -> ctk.CTkFrame:
        card = ctk.CTkFrame(parent)
        ctk.CTkLabel(card, text="🚀  Full Pipeline", font=ctk.CTkFont(size=14, weight="bold")).pack(
            padx=16, pady=(14, 6), anchor="w"
        )
        ctk.CTkLabel(card, text="Query:", font=ctk.CTkFont(size=12)).pack(padx=16, anchor="w")
        self._pipeline_query = ctk.CTkEntry(card, placeholder_text='Search query', width=340)
        self._pipeline_query.pack(padx=16, pady=4, anchor="w")

        row = ctk.CTkFrame(card, fg_color="transparent")
        row.pack(padx=16, fill="x")
        ctk.CTkLabel(row, text="Pages:", font=ctk.CTkFont(size=12)).pack(side="left")
        self._pipeline_pages = ctk.CTkEntry(row, width=60, placeholder_text="5")
        self._pipeline_pages.pack(side="left", padx=8)
        ctk.CTkLabel(row, text="Output:", font=ctk.CTkFont(size=12)).pack(side="left", padx=(16, 4))
        self._pipeline_output = ctk.CTkEntry(row, width=140, placeholder_text="./exports/")
        self._pipeline_output.pack(side="left")

        self._pipeline_btn = ctk.CTkButton(
            card, text="Run Full Pipeline", command=self._start_pipeline,
            fg_color="#16A34A", hover_color="#15803D",
        )
        self._pipeline_btn.pack(padx=16, pady=12, anchor="w")

        self._pipeline_status = ctk.CTkLabel(card, text="Idle", text_color="gray60", font=ctk.CTkFont(size=11))
        self._pipeline_status.pack(padx=16, pady=(0, 12), anchor="w")
        return card

    # ── Header helpers ────────────────────────────────────────────────────────

    def _refresh_header(self):
        if not self._campaign_id:
            return
        c = self._db.get_campaign(self._campaign_id)
        if c:
            self._name_lbl.configure(text=c.name)
            self._status_badge.set_status(c.status)

    def _refresh_stats(self):
        if not self._campaign_id:
            return
        try:
            stats = self._db.get_campaign_stats(self._campaign_id)
            self._card_urls.set(str(stats["total_urls"]))
            self._card_pending.set(str(stats["pending_urls"]))
            self._card_done.set(str(stats["completed_urls"]))
            self._card_failed.set(str(stats["failed_urls"]))
            self._card_leads.set(str(stats["total_leads"]))
            self._enrich_pending_lbl.configure(
                text=f"Pending URLs: {stats['pending_urls']}"
            )
        except Exception:
            pass

    def _update_button_states(self):
        running = self._runner.is_running(self._campaign_id) if self._campaign_id else False
        state = "disabled" if running else "normal"
        for btn in (self._scrape_btn, self._enrich_btn, self._export_btn, self._pipeline_btn):
            btn.configure(state=state)

    # ── Actions ──────────────────────────────────────────────────────────────

    def _start_scrape(self):
        if not self._campaign_id:
            return
        query = self._scrape_query.get().strip()
        if not query:
            messagebox.showwarning("Missing", "Enter a search query.")
            return
        pages = int(self._scrape_pages.get().strip() or "5")

        pipeline = GUIPipelineRunner(self._db, self._campaign_id, self._event_bus)
        self._scrape_status.configure(text="Running…", text_color="#22C55E")
        self._runner.submit(
            self._campaign_id,
            "scrape",
            pipeline.run_scrape_only(query, pages),
            on_done=lambda ok, r, e: self._scrape_status.configure(
                text=f"Done: {r} URLs" if ok else f"Error: {e}",
                text_color="#22C55E" if ok else "#EF4444",
            ),
        )
        self._update_button_states()

    def _start_enrich(self):
        if not self._campaign_id:
            return
        pipeline = GUIPipelineRunner(self._db, self._campaign_id, self._event_bus)
        self._enrich_status.configure(text="Running…", text_color="#22C55E")
        self._runner.submit(
            self._campaign_id,
            "enrich",
            pipeline.run_enrich_only(),
            on_done=lambda ok, r, e: self._enrich_status.configure(
                text="Done" if ok else f"Error: {e}",
                text_color="#22C55E" if ok else "#EF4444",
            ),
        )
        self._update_button_states()

    def _browse_export(self):
        path = filedialog.askdirectory(title="Select export directory")
        if path:
            self._export_path.delete(0, "end")
            self._export_path.insert(0, path)

    def _start_export(self):
        if not self._campaign_id:
            return
        output = self._export_path.get().strip() or "./exports/"
        exporter = ExcelExporter(self._db)

        def _do_export():
            return exporter.export_campaign(self._campaign_id, output)

        self._export_status.configure(text="Exporting…", text_color="#22C55E")
        self._runner.submit_sync(
            self._campaign_id,
            "export",
            _do_export,
            on_done=lambda ok, r, e: self._export_status.configure(
                text=f"Saved: {os.path.basename(r)}" if ok else f"Error: {e}",
                text_color="#22C55E" if ok else "#EF4444",
            ),
        )
        self._update_button_states()

    def _start_pipeline(self):
        if not self._campaign_id:
            return
        query = self._pipeline_query.get().strip()
        if not query:
            messagebox.showwarning("Missing", "Enter a search query.")
            return
        pages = int(self._pipeline_pages.get().strip() or "5")
        output = self._pipeline_output.get().strip() or "./exports/"

        pipeline = GUIPipelineRunner(self._db, self._campaign_id, self._event_bus)
        self._pipeline_status.configure(text="Running…", text_color="#22C55E")
        self._runner.submit(
            self._campaign_id,
            "pipeline",
            pipeline.run_full_pipeline(query, pages, output),
            on_done=lambda ok, r, e: self._pipeline_status.configure(
                text=f"Done: {os.path.basename(r)}" if ok else f"Error: {e}",
                text_color="#22C55E" if ok else "#EF4444",
            ),
        )
        self._update_button_states()
        self._on_open_monitor(self._campaign_id)
