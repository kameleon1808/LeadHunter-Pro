"""StatCard — compact label+value tile used on detail and monitor screens."""

import customtkinter as ctk


class StatCard(ctk.CTkFrame):
    def __init__(self, parent, label: str, value: str = "—", **kwargs):
        super().__init__(parent, corner_radius=8, **kwargs)
        self._label = ctk.CTkLabel(
            self, text=label, font=ctk.CTkFont(size=11), text_color="gray70"
        )
        self._label.pack(padx=10, pady=(8, 0))
        self._value_var = ctk.StringVar(value=value)
        self._value_lbl = ctk.CTkLabel(
            self,
            textvariable=self._value_var,
            font=ctk.CTkFont(size=20, weight="bold"),
        )
        self._value_lbl.pack(padx=10, pady=(0, 8))

    def set(self, value: str) -> None:
        self._value_var.set(value)
