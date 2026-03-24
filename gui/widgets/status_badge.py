"""StatusBadge — coloured pill label showing campaign/URL status."""

import customtkinter as ctk

STATUS_COLORS = {
    "pending":   ("#FFA500", "#8B6000"),
    "running":   ("#22C55E", "#166534"),
    "paused":    ("#38BDF8", "#0C4A6E"),
    "completed": ("#22C55E", "#166534"),
    "failed":    ("#EF4444", "#7F1D1D"),
}
DEFAULT_COLOR = ("#94A3B8", "#334155")


class StatusBadge(ctk.CTkLabel):
    def __init__(self, parent, status: str = "pending", **kwargs):
        fg, _ = STATUS_COLORS.get(status, DEFAULT_COLOR)
        super().__init__(
            parent,
            text=f"  {status.upper()}  ",
            font=ctk.CTkFont(size=11, weight="bold"),
            fg_color=fg,
            text_color="white",
            corner_radius=8,
            **kwargs,
        )

    def set_status(self, status: str) -> None:
        fg, _ = STATUS_COLORS.get(status, DEFAULT_COLOR)
        self.configure(text=f"  {status.upper()}  ", fg_color=fg)
