"""
MonitorScreen — live progress dashboard.
Polls db.get_campaign_stats() every 2 seconds via root.after().
"""

import asyncio
import time
from collections import deque
from typing import Optional

import customtkinter as ctk

from database import DatabaseManager
from gui.event_bus import CaptchaEvent, EventBus
from gui.task_runner import BackgroundTaskRunner
from gui.widgets import ProgressRow, StatCard, StatusBadge


def _fmt_time(seconds: float) -> str:
    if seconds < 60:
        return f"{int(seconds)}s"
    if seconds < 3600:
        return f"{int(seconds // 60)}m {int(seconds % 60)}s"
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    return f"{h}h {m}m"


class MonitorScreen(ctk.CTkFrame):
    def __init__(
        self,
        parent,
        db: DatabaseManager,
        runner: BackgroundTaskRunner,
        event_bus: EventBus,
        on_export: Optional[callable] = None,
        **kwargs,
    ):
        super().__init__(parent, fg_color="transparent", **kwargs)
        self._db = db
        self._runner = runner
        self._event_bus = event_bus
        self._on_export = on_export

        self._campaign_id: Optional[int] = None
        self._poll_after_id = None
        self._start_time: Optional[float] = None
        self._start_done: int = 0
        self._activity: deque = deque(maxlen=20)
        self._seen_urls: set = set()

        self._build()

    # ── Public ───────────────────────────────────────────────────────────────

    def load_campaign(self, campaign_id: int):
        self._campaign_id = campaign_id
        self._start_time = time.time()
        self._activity.clear()
        self._seen_urls.clear()
        try:
            stats = self._db.get_campaign_stats(campaign_id)
            self._start_done = stats["completed_urls"] + stats["failed_urls"]
        except Exception:
            self._start_done = 0
        self._tick()

    def stop_polling(self):
        if self._poll_after_id:
            self.after_cancel(self._poll_after_id)
            self._poll_after_id = None

    def on_captcha_event(self, event: CaptchaEvent):
        """Show a modal dialog when CAPTCHA is detected."""
        self._show_captcha_dialog(event.asyncio_event, self._runner._loop)

    # ── Build UI ──────────────────────────────────────────────────────────────

    def _build(self):
        self.columnconfigure(0, weight=1)
        self.rowconfigure(3, weight=1)

        # ── Header ──────────────────────────────────────────────────────────
        hdr = ctk.CTkFrame(self, fg_color="transparent")
        hdr.grid(row=0, column=0, sticky="ew", padx=20, pady=(20, 8))

        self._campaign_lbl = ctk.CTkLabel(
            hdr, text="Monitor", font=ctk.CTkFont(size=22, weight="bold")
        )
        self._campaign_lbl.pack(side="left")

        self._status_badge = StatusBadge(hdr, "pending")
        self._status_badge.pack(side="left", padx=12)

        self._elapsed_lbl = ctk.CTkLabel(
            hdr, text="Elapsed: —", font=ctk.CTkFont(size=12), text_color="gray60"
        )
        self._elapsed_lbl.pack(side="left", padx=12)

        self._eta_lbl = ctk.CTkLabel(
            hdr, text="ETA: —", font=ctk.CTkFont(size=12), text_color="#F59E0B"
        )
        self._eta_lbl.pack(side="left")

        btn_row = ctk.CTkFrame(hdr, fg_color="transparent")
        btn_row.pack(side="right")
        self._stop_btn = ctk.CTkButton(
            btn_row, text="⏹ Stop / Pause", fg_color="#DC2626", hover_color="#B91C1C",
            width=130, command=self._stop_task
        )
        self._stop_btn.pack(side="left", padx=4)

        # ── Progress bars ────────────────────────────────────────────────────
        prog_frame = ctk.CTkFrame(self)
        prog_frame.grid(row=1, column=0, sticky="ew", padx=20, pady=4)
        prog_frame.columnconfigure(0, weight=1)

        self._url_bar = ProgressRow(prog_frame, "URLs Processed", color="#3B82F6")
        self._url_bar.grid(row=0, column=0, sticky="ew", padx=16, pady=8)

        self._lead_bar = ProgressRow(prog_frame, "Leads Found", color="#22C55E")
        self._lead_bar.grid(row=1, column=0, sticky="ew", padx=16, pady=(0, 8))

        # ── Stat cards ───────────────────────────────────────────────────────
        stats_row = ctk.CTkFrame(self, fg_color="transparent")
        stats_row.grid(row=2, column=0, sticky="ew", padx=20, pady=4)

        self._card_completed = StatCard(stats_row, "Completed")
        self._card_failed    = StatCard(stats_row, "Failed")
        self._card_pending   = StatCard(stats_row, "Pending")
        self._card_leads     = StatCard(stats_row, "Leads")
        for card in (self._card_completed, self._card_failed, self._card_pending, self._card_leads):
            card.pack(side="left", padx=8, ipadx=4)

        # ── Activity log ─────────────────────────────────────────────────────
        log_frame = ctk.CTkFrame(self)
        log_frame.grid(row=3, column=0, sticky="nsew", padx=20, pady=(4, 20))
        log_frame.columnconfigure(0, weight=1)
        log_frame.rowconfigure(1, weight=1)

        ctk.CTkLabel(
            log_frame, text="Recent Activity", font=ctk.CTkFont(size=13, weight="bold")
        ).grid(row=0, column=0, padx=12, pady=(8, 4), sticky="w")

        self._log_box = ctk.CTkTextbox(log_frame, font=ctk.CTkFont(family="Courier", size=11), state="disabled")
        self._log_box.grid(row=1, column=0, sticky="nsew", padx=12, pady=(0, 12))

    # ── Polling loop ──────────────────────────────────────────────────────────

    def _tick(self):
        if not self._campaign_id:
            return
        try:
            self._update_display()
        except Exception:
            pass
        self._poll_after_id = self.after(2000, self._tick)

    def _update_display(self):
        stats = self._db.get_campaign_stats(self._campaign_id)
        campaign = self._db.get_campaign(self._campaign_id)

        total = stats["total_urls"]
        done  = stats["completed_urls"] + stats["failed_urls"]
        leads = stats["total_leads"]

        # Header
        if campaign:
            self._campaign_lbl.configure(text=campaign.name)
            self._status_badge.set_status(campaign.status)
        if self._start_time:
            elapsed = time.time() - self._start_time
            self._elapsed_lbl.configure(text=f"Elapsed: {_fmt_time(elapsed)}")
            # ETA
            delta = done - self._start_done
            if elapsed > 5 and delta > 0:
                rate = delta / elapsed
                remaining = max(0, total - done)
                eta_str = f"ETA: ~{_fmt_time(remaining / rate)}"
            else:
                eta_str = "ETA: calculating…"
            self._eta_lbl.configure(text=eta_str)

        # Progress bars
        self._url_bar.update(done, total)
        self._lead_bar.update(leads, max(done, 1))

        # Stat cards
        self._card_completed.set(str(stats["completed_urls"]))
        self._card_failed.set(str(stats["failed_urls"]))
        self._card_pending.set(str(stats["pending_urls"]))
        self._card_leads.set(str(leads))

        # Activity log
        recent = self._db.get_recent_activity(self._campaign_id, limit=20)
        new_entries = []
        for rec in reversed(recent):
            if rec.id not in self._seen_urls:
                self._seen_urls.add(rec.id)
                icon = "✓" if rec.status == "completed" else "✗"
                url_short = rec.url[:70] if rec.url else "—"
                new_entries.append(f"{icon}  {url_short}")

        if new_entries:
            self._log_box.configure(state="normal")
            for entry in new_entries:
                self._log_box.insert("end", entry + "\n")
            self._log_box.see("end")
            self._log_box.configure(state="disabled")

    # ── CAPTCHA dialog ────────────────────────────────────────────────────────

    def _show_captcha_dialog(self, solve_event: asyncio.Event, loop):
        dialog = ctk.CTkToplevel(self)
        dialog.title("CAPTCHA Detected")
        dialog.geometry("420x200")
        dialog.grab_set()

        ctk.CTkLabel(
            dialog,
            text="⚠️  CAPTCHA Detected",
            font=ctk.CTkFont(size=16, weight="bold"),
        ).pack(pady=(20, 8))
        ctk.CTkLabel(
            dialog,
            text="Please solve the CAPTCHA in the browser window,\nthen click Done to continue.",
            font=ctk.CTkFont(size=13),
            justify="center",
        ).pack(pady=4)

        def _done():
            dialog.destroy()
            # asyncio.Event.set() must be called from the asyncio loop thread
            loop.call_soon_threadsafe(solve_event.set)

        ctk.CTkButton(dialog, text="✓  Done — CAPTCHA Solved", command=_done).pack(pady=16)

    # ── Stop ──────────────────────────────────────────────────────────────────

    def _stop_task(self):
        if self._campaign_id:
            self._runner.cancel(self._campaign_id)
            try:
                self._db.update_campaign_status(self._campaign_id, "paused")
            except Exception:
                pass
            self._log_box.configure(state="normal")
            self._log_box.insert("end", "⏹  Task stopped by user\n")
            self._log_box.see("end")
            self._log_box.configure(state="disabled")
