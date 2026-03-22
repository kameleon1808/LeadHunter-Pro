"""
CLIDashboard — terminal dashboard for LeadHunter Pro using Rich.

Commands:
  show_campaigns_list()             — table of all campaigns
  show_campaign_progress(id)        — live-updating progress view (Ctrl+C to exit)
  show_leads_preview(id, limit=20)  — table of the most recent leads
  show_stats(id)                    — one-shot statistics panel

Requires: rich>=13.0.0
"""

import time
from collections import deque
from datetime import datetime, timezone
from typing import Optional

from rich.align import Align
from rich.columns import Columns
from rich.console import Console
from rich.live import Live
from rich.panel import Panel
from rich.progress import BarColumn, MofNCompleteColumn, Progress, TextColumn
from rich.table import Table
from rich.text import Text

from database import DatabaseManager
from database.models import URL


def _pct(part: int, total: int) -> str:
    return f"{part / total * 100:.1f}%" if total else "0.0%"


def _fmt_time(seconds: float) -> str:
    if seconds < 60:
        return f"{int(seconds)}s"
    if seconds < 3600:
        return f"{int(seconds // 60)}m {int(seconds % 60)}s"
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    return f"{h}h {m}m"


class CLIDashboard:
    """Rich-powered terminal dashboard for LeadHunter Pro."""

    def __init__(self, db_manager: DatabaseManager) -> None:
        self._db = db_manager
        self._console = Console()

    # ── Public views ─────────────────────────────────────────────────────────

    def show_campaigns_list(self) -> None:
        """Print a table of all campaigns with key stats."""
        campaigns = self._db.get_all_campaigns()

        if not campaigns:
            self._console.print("[yellow]No campaigns found. Create one with:[/yellow]")
            self._console.print("  python main.py campaign create --name '...' --niche '...'")
            return

        table = Table(
            title="[bold blue]LeadHunter Pro — Campaigns[/bold blue]",
            show_lines=True,
            header_style="bold white on dark_blue",
        )
        table.add_column("ID",      style="dim",          width=5,  justify="right")
        table.add_column("Name",    style="bold",          width=25)
        table.add_column("Niche",                          width=22)
        table.add_column("Country",                        width=12)
        table.add_column("Status",                         width=12)
        table.add_column("URLs",    justify="right",       width=8)
        table.add_column("Leads",   justify="right",       width=8)
        table.add_column("Created",                        width=12)

        status_style = {
            "pending":   "yellow",
            "running":   "green",
            "paused":    "cyan",
            "completed": "bold green",
            "failed":    "bold red",
        }

        for c in campaigns:
            created = c.created_at.strftime("%Y-%m-%d") if c.created_at else "—"
            s_style = status_style.get(c.status, "white")
            table.add_row(
                str(c.id),
                c.name,
                c.niche,
                c.target_country or "—",
                f"[{s_style}]{c.status}[/{s_style}]",
                str(c.total_urls),
                str(c.total_leads),
                created,
            )

        self._console.print(table)

    def show_campaign_progress(self, campaign_id: int) -> None:
        """
        Live-updating progress view.  Refreshes every 2 seconds.
        Press Ctrl+C to exit.
        """
        campaign = self._db.get_campaign(campaign_id)
        if campaign is None:
            self._console.print(f"[red]Campaign {campaign_id} not found.[/red]")
            return

        start_time = time.time()
        start_stats = self._db.get_campaign_stats(campaign_id)
        start_done  = start_stats["completed_urls"] + start_stats["failed_urls"]
        activity_log: deque = deque(maxlen=10)

        self._console.print(
            f"\n[bold blue]LeadHunter Pro[/bold blue] — Live Dashboard   "
            "[dim](Ctrl+C to exit)[/dim]\n"
        )

        try:
            with Live(
                self._build_progress_display(
                    campaign, self._db.get_campaign_stats(campaign_id),
                    0, start_done, activity_log,
                ),
                console=self._console,
                refresh_per_second=1,
                transient=False,
            ) as live:
                while True:
                    time.sleep(2)
                    stats   = self._db.get_campaign_stats(campaign_id)
                    elapsed = time.time() - start_time
                    current_done = stats["completed_urls"] + stats["failed_urls"]

                    # Collect recent activity
                    recent = self._get_recent_activity(campaign_id, limit=10)
                    for rec in recent:
                        entry = (
                            f"[green]✓[/green] {rec.url[:55]}"
                            if rec.status == "completed"
                            else f"[red]✗[/red] {rec.url[:55]}"
                        )
                        if entry not in activity_log:
                            activity_log.append(entry)

                    live.update(
                        self._build_progress_display(
                            campaign, stats, elapsed, start_done, activity_log,
                        )
                    )

                    # Reload campaign to check status
                    fresh = self._db.get_campaign(campaign_id)
                    if fresh and fresh.status in ("completed", "failed"):
                        time.sleep(2)
                        break

        except KeyboardInterrupt:
            self._console.print("\n[dim]Dashboard closed.[/dim]")

    def show_leads_preview(self, campaign_id: int, limit: int = 20) -> None:
        """Print a preview table of the most recently found leads."""
        leads = self._db.get_leads(campaign_id)
        if not leads:
            self._console.print("[yellow]No leads found for this campaign yet.[/yellow]")
            return

        recent = leads[-limit:]

        table = Table(
            title=f"[bold blue]Recent Leads — Campaign {campaign_id}[/bold blue] "
                  f"(showing {len(recent)} of {len(leads)})",
            show_lines=True,
            header_style="bold white on dark_blue",
        )
        table.add_column("#",             width=5,  justify="right")
        table.add_column("Company",       width=25, style="bold")
        table.add_column("Industry",      width=18)
        table.add_column("Contact",       width=22)
        table.add_column("Email",         width=28)
        table.add_column("Phone",         width=16)
        table.add_column("Score",         width=7,  justify="center")

        for idx, lead in enumerate(recent, start=1):
            score = lead.quality_score or 0
            if score >= 8:
                score_text = f"[bold green]{score}[/bold green]"
            elif score >= 5:
                score_text = f"[yellow]{score}[/yellow]"
            else:
                score_text = f"[red]{score}[/red]"

            contact = lead.contact_name or "—"
            if lead.contact_title:
                contact += f"\n[dim]{lead.contact_title}[/dim]"

            table.add_row(
                str(idx),
                lead.company_name or "—",
                lead.industry or "—",
                contact,
                lead.contact_email or lead.company_email or "—",
                lead.company_phone or "—",
                score_text,
            )

        self._console.print(table)

    def show_stats(self, campaign_id: int) -> None:
        """Print a one-shot statistics panel for a campaign."""
        campaign = self._db.get_campaign(campaign_id)
        if campaign is None:
            self._console.print(f"[red]Campaign {campaign_id} not found.[/red]")
            return

        stats = self._db.get_campaign_stats(campaign_id)
        total  = stats["total_urls"]
        done   = stats["completed_urls"] + stats["failed_urls"]
        leads  = stats["total_leads"]

        succ_pct = _pct(stats["completed_urls"], total)
        lead_pct = _pct(leads, stats["completed_urls"]) if stats["completed_urls"] else "N/A"

        status_style = {
            "pending": "yellow", "running": "green",
            "completed": "bold green", "failed": "bold red",
        }
        s_style = status_style.get(campaign.status, "white")

        lines = [
            f"[bold]Campaign:[/bold]      {campaign.name}",
            f"[bold]Niche:[/bold]         {campaign.niche}",
            f"[bold]Country:[/bold]       {campaign.target_country or '—'}",
            f"[bold]Status:[/bold]        [{s_style}]{campaign.status}[/{s_style}]",
            "",
            f"[bold]Total URLs:[/bold]    {total}",
            f"[bold]Processed:[/bold]     {done} / {total}  ({_pct(done, total)})",
            f"[bold]Completed:[/bold]     {stats['completed_urls']}  ({succ_pct})",
            f"[bold]Failed:[/bold]        {stats['failed_urls']}",
            f"[bold]Pending:[/bold]       {stats['pending_urls']}",
            "",
            f"[bold]Leads Found:[/bold]   [bold green]{leads}[/bold green]",
            f"[bold]Conversion:[/bold]    {lead_pct}",
        ]

        panel = Panel(
            "\n".join(lines),
            title=f"[bold blue]Campaign Stats — ID {campaign_id}[/bold blue]",
            border_style="blue",
            padding=(1, 2),
        )
        self._console.print(panel)

    # ── Internal helpers ─────────────────────────────────────────────────────

    def _build_progress_display(
        self,
        campaign,
        stats: dict,
        elapsed: float,
        start_done: int,
        activity_log: deque,
    ):
        """Build the Rich renderable for the live dashboard."""
        total = stats["total_urls"]
        done  = stats["completed_urls"] + stats["failed_urls"]
        leads = stats["total_leads"]

        # ETA calculation
        if elapsed > 5 and (done - start_done) > 0:
            rate      = (done - start_done) / elapsed
            remaining = max(0, total - done)
            eta       = f"~{_fmt_time(remaining / rate)}"
        else:
            eta = "Calculating…"

        # ── Header panel ────────────────────────────────────────────────────
        status_style = {
            "pending": "yellow", "running": "green bold",
            "completed": "bold green", "failed": "bold red",
        }
        s_style = status_style.get(campaign.status, "white")
        header_text = (
            f"[bold]{campaign.name}[/bold]  |  "
            f"Status: [{s_style}]{campaign.status}[/{s_style}]  |  "
            f"Elapsed: [cyan]{_fmt_time(elapsed)}[/cyan]  |  "
            f"ETA: [yellow]{eta}[/yellow]"
        )

        # ── Progress bars ────────────────────────────────────────────────────
        url_bar = self._make_bar("URLs Processed", done, total, "blue")
        lead_bar = self._make_bar("Leads Found   ", leads, max(done, 1), "green")

        # ── Activity log ─────────────────────────────────────────────────────
        log_table = Table(box=None, show_header=False, padding=(0, 1))
        log_table.add_column(width=70)
        for entry in list(activity_log)[-10:]:
            log_table.add_row(entry)
        while log_table.row_count < 5:
            log_table.add_row("[dim]—[/dim]")

        activity_panel = Panel(
            log_table,
            title="[dim]Recent Activity[/dim]",
            border_style="dim",
            padding=(0, 1),
        )

        # ── Stats row ────────────────────────────────────────────────────────
        stats_text = (
            f"  Completed: [green]{stats['completed_urls']}[/green]  "
            f"Failed: [red]{stats['failed_urls']}[/red]  "
            f"Pending: [yellow]{stats['pending_urls']}[/yellow]  "
            f"Leads: [bold green]{leads}[/bold green]"
        )

        from rich.console import Group
        return Panel(
            Group(
                Text.from_markup(header_text),
                Text(""),
                url_bar,
                lead_bar,
                Text(""),
                Text.from_markup(stats_text),
                Text(""),
                activity_panel,
            ),
            title="[bold blue]LeadHunter Pro — Live Progress[/bold blue]",
            border_style="blue",
            padding=(1, 2),
        )

    @staticmethod
    def _make_bar(label: str, value: int, total: int, color: str) -> Text:
        """Build a simple ASCII progress bar as a Rich Text object."""
        width  = 40
        filled = int(width * value / total) if total else 0
        bar    = "█" * filled + "░" * (width - filled)
        pct    = _pct(value, total)
        return Text.from_markup(
            f"  [bold]{label}[/bold]  [{color}]{bar}[/{color}]  "
            f"[cyan]{value}[/cyan]/[dim]{total}[/dim]  ({pct})"
        )

    def _get_recent_activity(self, campaign_id: int, limit: int = 10) -> list:
        """Return the most recently processed URLs (completed or failed)."""
        from sqlalchemy.orm import Session
        with Session(self._db.engine) as session:
            records = (
                session.query(URL)
                .filter(
                    URL.campaign_id == campaign_id,
                    URL.status.in_(["completed", "failed"]),
                )
                .order_by(URL.processed_at.desc())
                .limit(limit)
                .all()
            )
            for r in records:
                session.expunge(r)
            return records
