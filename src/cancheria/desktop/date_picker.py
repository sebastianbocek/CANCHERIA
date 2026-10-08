from __future__ import annotations

import calendar
import datetime as dt
import tkinter as tk
from typing import Callable


MONTH_NAMES = (
    "", "Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio",
    "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre",
)
WEEKDAYS = ("Lu", "Ma", "Mi", "Ju", "Vi", "Sá", "Do")


class DatePicker(tk.Toplevel):
    """Small dependency-free calendar that writes an ISO date into a Tk variable."""

    def __init__(
        self,
        parent: tk.Misc,
        variable: tk.StringVar,
        *,
        anchor: tk.Widget | None = None,
        title: str = "Seleccionar fecha",
        on_select: Callable[[], None] | None = None,
    ) -> None:
        super().__init__(parent)
        self.variable = variable
        self.on_select = on_select
        try:
            selected = dt.date.fromisoformat(variable.get().strip())
        except (TypeError, ValueError):
            selected = dt.date.today()
        self.selected = selected
        self.year = selected.year
        self.month = selected.month

        self.title(title)
        self.configure(bg="white")
        self.resizable(False, False)
        self.transient(parent.winfo_toplevel())
        self.protocol("WM_DELETE_WINDOW", self.destroy)
        self.bind("<Escape>", lambda _event: self.destroy())

        header = tk.Frame(self, bg="white")
        header.pack(fill="x", padx=10, pady=(10, 4))
        tk.Button(
            header, text="◀", command=lambda: self._move_month(-1), relief="flat",
            bg="#061632", fg="white", cursor="hand2", width=3,
        ).pack(side="left")
        self.month_label = tk.Label(
            header, font=("Segoe UI", 11, "bold"), bg="white", fg="#061632",
        )
        self.month_label.pack(side="left", fill="x", expand=True, padx=10)
        tk.Button(
            header, text="▶", command=lambda: self._move_month(1), relief="flat",
            bg="#061632", fg="white", cursor="hand2", width=3,
        ).pack(side="right")

        self.days = tk.Frame(self, bg="white")
        self.days.pack(padx=10, pady=(0, 7))
        footer = tk.Frame(self, bg="white")
        footer.pack(fill="x", padx=10, pady=(0, 10))
        tk.Button(
            footer, text="Hoy", command=self._select_today, relief="flat",
            bg="#1677ff", fg="white", cursor="hand2", padx=12, pady=4,
        ).pack()
        self._render()
        self.update_idletasks()
        self._position(anchor)
        self.grab_set()
        self.focus_force()

    def _position(self, anchor: tk.Widget | None) -> None:
        if anchor is None:
            owner = self.master.winfo_toplevel()
            x = owner.winfo_rootx() + max(0, (owner.winfo_width() - self.winfo_width()) // 2)
            y = owner.winfo_rooty() + max(0, (owner.winfo_height() - self.winfo_height()) // 2)
        else:
            x = anchor.winfo_rootx()
            y = anchor.winfo_rooty() + anchor.winfo_height() + 4
        self.geometry(f"+{max(0, x)}+{max(0, y)}")

    def _move_month(self, delta: int) -> None:
        index = self.year * 12 + self.month - 1 + delta
        self.year, zero_based = divmod(index, 12)
        self.month = zero_based + 1
        self._render()

    def _select_today(self) -> None:
        today = dt.date.today()
        self._select(today.year, today.month, today.day)

    def _select(self, year: int, month: int, day: int) -> None:
        self.variable.set(dt.date(year, month, day).isoformat())
        if self.on_select is not None:
            self.on_select()
        self.destroy()

    def _render(self) -> None:
        self.month_label.configure(text=f"{MONTH_NAMES[self.month]} {self.year}")
        for widget in self.days.winfo_children():
            widget.destroy()
        for column, label in enumerate(WEEKDAYS):
            tk.Label(
                self.days, text=label, bg="white", fg="#667085",
                font=("Segoe UI", 8, "bold"), width=4, pady=4,
            ).grid(row=0, column=column)

        today = dt.date.today()
        weeks = calendar.Calendar(firstweekday=0).monthdayscalendar(self.year, self.month)
        for row, week in enumerate(weeks, start=1):
            for column, day in enumerate(week):
                if day == 0:
                    tk.Label(self.days, text="", bg="white", width=4, pady=5).grid(
                        row=row, column=column
                    )
                    continue
                value = dt.date(self.year, self.month, day)
                is_selected = value == self.selected
                is_today = value == today
                background = "#061632" if is_selected else "#1677ff" if is_today else "white"
                foreground = "white" if is_selected or is_today else "#101828"
                tk.Button(
                    self.days,
                    text=str(day),
                    command=lambda d=day: self._select(self.year, self.month, d),
                    relief="flat",
                    bg=background,
                    fg=foreground,
                    activebackground="#dbeafe",
                    activeforeground="#101828",
                    cursor="hand2",
                    width=3,
                    pady=3,
                ).grid(row=row, column=column, padx=1, pady=1)
