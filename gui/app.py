"""
GUIApp — main application window.

Layout:
  ┌─────────┬─────────────────────────────────┐
  │ Sidebar │  Main content (active screen)   │
  │ 200px   │                                 │
  └─────────┴─────────────────────────────────┘

The sidebar lists all campaigns (refreshed periodically).
The main area stacks all screens; only one is visible at a time.
A root.after(200) loop drains EventBus and dispatches events.
"""

import logging
import os
import sys

import customtkinter as ctk
from dotenv import load_dotenv

from database import DatabaseManager
from gui.event_bus import CaptchaEvent, EventBus, TaskDoneEvent, TaskStartedEvent
from gui.task_runner import BackgroundTaskRunner
from gui.screens import (
    CampaignsScreen,
    CampaignDetailScreen,
    MonitorScreen,
    LeadsBrowserScreen,
    SettingsScreen,
)

logger = logging.getLogger(__name__)

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

SIDEBAR_WIDTH = 210
WINDOW_MIN_W  = 1100
WINDOW_MIN_H  = 720


class GUIApp(ctk.CTk):
    def __init__(self, db: DatabaseManager) -> None:
        super().__init__()
        self._db = db
        self._event_bus = EventBus()
        self._runner = BackgroundTaskRunner(self._event_bus)
        self._active_campaign_id: int | None = None

        self.title("LeadHunter Pro")
        self.geometry(f"{WINDOW_MIN_W}x{WINDOW_MIN_H}")
        self.minsize(WINDOW_MIN_W, WINDOW_MIN_H)

        # Try to set icon (silently skip if not found)
        icon_path = os.path.join(os.path.dirname(__file__), "assets", "icon.ico")
        if os.path.exists(icon_path):
            try:
                self.iconbitmap(icon_path)
            except Exception:
                pass

        self._build_layout()
        self._build_sidebar()
        self._build_screens()
        self._build_toast()
        self._show_campaigns()

        # Start event bus poll loop
        self._poll_events()
        # Refresh sidebar campaign list periodically
        self._refresh_sidebar()

    # ── Toast notification ────────────────────────────────────────────────────

    def _build_toast(self):
        """Floating toast label at the bottom of the window."""
        self._toast = ctk.CTkLabel(
            self,
            text="",
            font=ctk.CTkFont(size=12),
            fg_color=("#1D4ED8", "#1D4ED8"),
            text_color="white",
            corner_radius=8,
            padx=16,
            pady=6,
        )
        # Not packed yet — shown on demand

    def show_toast(self, msg: str, duration_ms: int = 3500):
        self._toast.configure(text=msg)
        self._toast.place(relx=0.5, rely=0.97, anchor="s")
        self.after(duration_ms, lambda: self._toast.place_forget())

    # ── Layout ────────────────────────────────────────────────────────────────

    def _build_layout(self):
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        self._sidebar = ctk.CTkScrollableFrame(
            self, width=SIDEBAR_WIDTH, corner_radius=0, fg_color=("gray90", "gray13")
        )
        self._sidebar.grid(row=0, column=0, sticky="nsew")

        self._main = ctk.CTkFrame(self, corner_radius=0, fg_color="transparent")
        self._main.grid(row=0, column=1, sticky="nsew")
        self._main.grid_columnconfigure(0, weight=1)
        self._main.grid_rowconfigure(0, weight=1)

    def _build_sidebar(self):
        # App title
        ctk.CTkLabel(
            self._sidebar,
            text="LeadHunter Pro",
            font=ctk.CTkFont(size=15, weight="bold"),
            anchor="w",
        ).pack(padx=14, pady=(16, 4), fill="x")

        ctk.CTkLabel(
            self._sidebar, text="Campaigns", font=ctk.CTkFont(size=11),
            text_color="gray50", anchor="w"
        ).pack(padx=14, anchor="w")

        # Campaign list container
        self._campaign_btn_frame = ctk.CTkFrame(self._sidebar, fg_color="transparent")
        self._campaign_btn_frame.pack(fill="x")

        # Separator
        ctk.CTkFrame(self._sidebar, height=1, fg_color="gray30").pack(
            fill="x", padx=14, pady=10
        )

        # New campaign
        ctk.CTkButton(
            self._sidebar,
            text="＋  New Campaign",
            command=self._show_campaigns,
            fg_color="#1D4ED8",
            hover_color="#1E40AF",
        ).pack(padx=14, pady=4, fill="x")

        # Settings
        ctk.CTkButton(
            self._sidebar,
            text="⚙  Settings",
            command=self._show_settings,
            fg_color="transparent",
            border_width=1,
        ).pack(padx=14, pady=4, fill="x")

        # All campaigns button
        ctk.CTkButton(
            self._sidebar,
            text="🏠  All Campaigns",
            command=self._show_campaigns,
            fg_color="transparent",
            border_width=1,
        ).pack(padx=14, pady=(4, 12), fill="x")

    def _build_screens(self):
        """Instantiate all screens; only one is visible at a time."""
        # Campaigns (home)
        self._screen_campaigns = CampaignsScreen(
            self._main, db=self._db, on_open_campaign=self._open_campaign
        )
        self._screen_campaigns.grid(row=0, column=0, sticky="nsew")

        # Campaign detail
        self._screen_detail = CampaignDetailScreen(
            self._main,
            db=self._db,
            runner=self._runner,
            event_bus=self._event_bus,
            on_open_monitor=self._open_monitor,
            on_open_leads=self._open_leads,
        )
        self._screen_detail.grid(row=0, column=0, sticky="nsew")
        self._screen_detail.grid_remove()

        # Monitor
        self._screen_monitor = MonitorScreen(
            self._main,
            db=self._db,
            runner=self._runner,
            event_bus=self._event_bus,
        )
        self._screen_monitor.grid(row=0, column=0, sticky="nsew")
        self._screen_monitor.grid_remove()

        # Leads browser
        self._screen_leads = LeadsBrowserScreen(self._main, db=self._db)
        self._screen_leads.grid(row=0, column=0, sticky="nsew")
        self._screen_leads.grid_remove()

        # Settings
        self._screen_settings = SettingsScreen(self._main)
        self._screen_settings.grid(row=0, column=0, sticky="nsew")
        self._screen_settings.grid_remove()

        self._all_screens = [
            self._screen_campaigns,
            self._screen_detail,
            self._screen_monitor,
            self._screen_leads,
            self._screen_settings,
        ]

    # ── Navigation ────────────────────────────────────────────────────────────

    def _show_screen(self, screen):
        for s in self._all_screens:
            s.grid_remove()
        screen.grid()

    def _show_campaigns(self):
        self._screen_campaigns.refresh()
        self._show_screen(self._screen_campaigns)

    def _show_settings(self):
        self._show_screen(self._screen_settings)

    def _open_campaign(self, campaign_id: int | None):
        self._refresh_sidebar_campaigns()
        if campaign_id is None:
            self._show_campaigns()
            return
        self._active_campaign_id = campaign_id
        self._screen_detail.load_campaign(campaign_id)
        self._show_screen(self._screen_detail)
        self._highlight_sidebar_campaign(campaign_id)

    def _open_monitor(self, campaign_id: int):
        self._active_campaign_id = campaign_id
        self._screen_monitor.load_campaign(campaign_id)
        self._show_screen(self._screen_monitor)

    def _open_leads(self, campaign_id: int):
        self._active_campaign_id = campaign_id
        self._screen_leads.load_campaign(campaign_id)
        self._show_screen(self._screen_leads)

    # ── Sidebar campaign list ─────────────────────────────────────────────────

    STATUS_DOT = {
        "pending":   "🟡",
        "running":   "🟢",
        "paused":    "🔵",
        "completed": "✅",
        "failed":    "🔴",
    }

    def _refresh_sidebar_campaigns(self):
        for widget in self._campaign_btn_frame.winfo_children():
            widget.destroy()
        campaigns = self._db.get_all_campaigns()
        for c in campaigns:
            dot = self.STATUS_DOT.get(c.status, "⚪")
            cid = c.id
            btn = ctk.CTkButton(
                self._campaign_btn_frame,
                text=f"{dot}  {c.name[:22]}",
                anchor="w",
                fg_color="transparent",
                hover_color=("gray80", "gray25"),
                font=ctk.CTkFont(size=12),
                command=lambda cid=cid: self._open_campaign(cid),
            )
            btn.pack(padx=8, pady=2, fill="x")

    def _highlight_sidebar_campaign(self, campaign_id: int):
        # Simple visual feedback — not needed for functionality
        pass

    def _refresh_sidebar(self):
        """Refresh sidebar every 5 seconds to pick up new campaigns."""
        self._refresh_sidebar_campaigns()
        self.after(5000, self._refresh_sidebar)

    # ── Event bus poll ────────────────────────────────────────────────────────

    def _poll_events(self):
        events = self._event_bus.drain()
        for event in events:
            self._dispatch(event)
        self.after(200, self._poll_events)

    def _dispatch(self, event):
        if isinstance(event, TaskStartedEvent):
            logger.info("Task started: %s campaign=%d", event.task_type, event.campaign_id)
            if event.campaign_id == self._active_campaign_id:
                self._screen_detail.refresh()

        elif isinstance(event, TaskDoneEvent):
            logger.info("Task done: %s success=%s campaign=%d", event.task_type, event.success, event.campaign_id)
            if event.campaign_id == self._active_campaign_id:
                self._screen_detail.on_task_done(event)
                self._screen_detail.refresh()
            self._refresh_sidebar_campaigns()
            if event.success:
                self.show_toast(f"✓  {event.task_type.title()} completed")
            else:
                self.show_toast(f"✗  {event.task_type.title()} failed: {event.error[:60]}", duration_ms=6000)

        elif isinstance(event, CaptchaEvent):
            logger.warning("CAPTCHA event — campaign %d", event.campaign_id)
            if event.campaign_id == self._active_campaign_id:
                self._screen_monitor.on_captcha_event(event)
            else:
                # Switch to monitor so user can see the dialog
                self._open_monitor(event.campaign_id)
                self._screen_monitor.on_captcha_event(event)
