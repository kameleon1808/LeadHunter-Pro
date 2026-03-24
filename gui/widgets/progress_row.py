"""ProgressRow — label + CTkProgressBar + fraction text in a single row."""

import customtkinter as ctk


class ProgressRow(ctk.CTkFrame):
    def __init__(self, parent, label: str, color: str = "#3B82F6", **kwargs):
        super().__init__(parent, fg_color="transparent", **kwargs)
        self.columnconfigure(1, weight=1)

        ctk.CTkLabel(
            self, text=label, font=ctk.CTkFont(size=12), width=140, anchor="w"
        ).grid(row=0, column=0, padx=(0, 8), sticky="w")

        self._bar = ctk.CTkProgressBar(self, height=14, progress_color=color)
        self._bar.set(0)
        self._bar.grid(row=0, column=1, sticky="ew")

        self._frac_var = ctk.StringVar(value="0 / 0  (0%)")
        ctk.CTkLabel(
            self, textvariable=self._frac_var, font=ctk.CTkFont(size=11),
            text_color="gray70", width=110, anchor="e"
        ).grid(row=0, column=2, padx=(8, 0), sticky="e")

    def update(self, value: int, total: int) -> None:
        ratio = value / total if total else 0
        pct = ratio * 100
        self._bar.set(ratio)
        self._frac_var.set(f"{value} / {total}  ({pct:.1f}%)")
