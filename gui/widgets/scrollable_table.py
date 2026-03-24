"""
ScrollableTable — lightweight table widget using CTkScrollableFrame.

Rows are plain CTkFrame objects with CTkLabel children.
Each row calls on_select(row_index, row_data) when clicked.
"""

from typing import Callable, List, Optional

import customtkinter as ctk

ROW_ODD  = ("gray17", "gray20")   # dark/light mode bg for odd rows
ROW_EVEN = ("gray14", "gray17")
ROW_SEL  = ("#1D4ED8", "#1D4ED8")
HDR_BG   = ("#1F4E79", "#1F4E79")


class ScrollableTable(ctk.CTkScrollableFrame):
    def __init__(
        self,
        parent,
        columns: List[str],
        col_widths: Optional[List[int]] = None,
        on_select: Optional[Callable] = None,
        **kwargs,
    ):
        super().__init__(parent, **kwargs)
        self._columns = columns
        self._col_widths = col_widths or [140] * len(columns)
        self._on_select = on_select
        self._rows: List[ctk.CTkFrame] = []
        self._selected: Optional[int] = None
        self._data: List[tuple] = []

        self._build_header()

    def _build_header(self):
        hdr = ctk.CTkFrame(self, fg_color=HDR_BG, corner_radius=0)
        hdr.pack(fill="x")
        for i, (col, w) in enumerate(zip(self._columns, self._col_widths)):
            ctk.CTkLabel(
                hdr,
                text=col,
                font=ctk.CTkFont(size=12, weight="bold"),
                text_color="white",
                width=w,
                anchor="w",
            ).grid(row=0, column=i, padx=(8, 4), pady=6, sticky="w")

    def clear(self):
        for row in self._rows:
            row.destroy()
        self._rows.clear()
        self._data.clear()
        self._selected = None

    def add_row(self, values: tuple, tags: Optional[dict] = None):
        idx = len(self._rows)
        bg = ROW_ODD if idx % 2 == 0 else ROW_EVEN
        row = ctk.CTkFrame(self, fg_color=bg, corner_radius=0)
        row.pack(fill="x")

        for i, (val, w) in enumerate(zip(values, self._col_widths)):
            lbl = ctk.CTkLabel(
                row,
                text=str(val) if val is not None else "—",
                font=ctk.CTkFont(size=12),
                width=w,
                anchor="w",
                wraplength=w - 10,
            )
            if tags and "fg_color" in tags:
                lbl.configure(text_color=tags["fg_color"])
            lbl.grid(row=0, column=i, padx=(8, 4), pady=5, sticky="w")
            lbl.bind("<Button-1>", lambda e, r=idx: self._on_click(r))

        row.bind("<Button-1>", lambda e, r=idx: self._on_click(r))
        self._rows.append(row)
        self._data.append(values)

    def _on_click(self, idx: int):
        if self._selected is not None and self._selected < len(self._rows):
            old_bg = ROW_ODD if self._selected % 2 == 0 else ROW_EVEN
            self._rows[self._selected].configure(fg_color=old_bg)
        self._selected = idx
        self._rows[idx].configure(fg_color=ROW_SEL)
        if self._on_select:
            self._on_select(idx, self._data[idx])

    def populate(self, rows: List[tuple]):
        self.clear()
        for row in rows:
            self.add_row(row)
