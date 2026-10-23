from __future__ import annotations

import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog, ttk
import datetime as dt
from pathlib import Path
from typing import Callable

from cancheria.admin.desktop_service import DesktopAdminService
from cancheria.desktop.date_picker import DatePicker


COMMAND_REFERENCE_FALLBACK = """CONTROL DEL AGENTE
pausar agente · reanudar agente · estado agente · casos pendientes · resolver caso ID 3

RESERVAS Y PAGOS
agenda mañana · agregar reserva lunes 20:00 Cancha 1 Juan · mostrar pendientes
confirmar seña ID 2 · confirmar total ID 2 · ver ID 2 · mover ID 2 mañana 20
cancelar ID 2 lluvia · liberar ID 2 · agregar quincho ID 2

OPERACIÓN
bloquear mañana cancha 1 mantenimiento · desbloquear mañana cancha 1
turnos fijos · clientes problema · motivos cancelacion · lista espera

REPORTES
reporte ocupación semanal · reporte facturación mensual · reporte conversión semanal
reporte demanda mensual · resumen semanal · resumen mensual

CONFIGURACIÓN
configuracion actual · cambiar horario de atencion de 14hs a 21hs
cambiar seña 50% · cambiar precio cancha 1 18000 · configurar canchas ...
agregar admin +549... · bloquear +549... · listar blacklist

TORNEOS
listar torneos · configurar torneo ... · editar torneo ... · borrar torneo ...
"""


def _hours_rounded_box(
    canvas: tk.Canvas,
    x1: float,
    y1: float,
    x2: float,
    y2: float,
    radius: float,
    *,
    fill: str,
    outline: str = "",
    width: float = 1,
    tag: str | None = None,
) -> None:
    """Draw a clean rounded surface without introducing image dependencies."""
    radius = max(0, min(radius, (x2 - x1) / 2, (y2 - y1) / 2))

    def layer(ax1, ay1, ax2, ay2, aradius, color):
        options = {"fill": color, "outline": color}
        if tag:
            options["tags"] = tag
        canvas.create_rectangle(ax1 + aradius, ay1, ax2 - aradius, ay2, **options)
        canvas.create_rectangle(ax1, ay1 + aradius, ax2, ay2 - aradius, **options)
        canvas.create_oval(ax1, ay1, ax1 + 2 * aradius, ay1 + 2 * aradius, **options)
        canvas.create_oval(ax2 - 2 * aradius, ay1, ax2, ay1 + 2 * aradius, **options)
        canvas.create_oval(ax1, ay2 - 2 * aradius, ax1 + 2 * aradius, ay2, **options)
        canvas.create_oval(ax2 - 2 * aradius, ay2 - 2 * aradius, ax2, ay2, **options)

    layer(x1, y1, x2, y2, radius, outline or fill)
    if outline and fill:
        inset = max(1.0, width)
        layer(
            x1 + inset,
            y1 + inset,
            x2 - inset,
            y2 - inset,
            max(0, radius - inset),
            fill,
        )


def _hours_blend(first: str, second: str, ratio: float) -> str:
    ratio = max(0.0, min(1.0, ratio))
    a = tuple(int(first[index:index + 2], 16) for index in (1, 3, 5))
    b = tuple(int(second[index:index + 2], 16) for index in (1, 3, 5))
    values = tuple(round(left + (right - left) * ratio) for left, right in zip(a, b))
    return "#" + "".join(f"{value:02X}" for value in values)


def _draw_hours_calendar(
    canvas: tk.Canvas,
    x: float,
    y: float,
    color: str,
    *,
    tag: str | None = None,
) -> None:
    options = {"outline": color, "width": 2}
    line_options = {"fill": color, "width": 2}
    if tag:
        options["tags"] = tag
        line_options["tags"] = tag
    canvas.create_rectangle(x - 8, y - 8, x + 8, y + 9, **options)
    canvas.create_line(x - 8, y - 3, x + 8, y - 3, **line_options)
    canvas.create_line(x - 4, y - 11, x - 4, y - 5, **line_options)
    canvas.create_line(x + 4, y - 11, x + 4, y - 5, **line_options)


class HoursTile(tk.Canvas):
    """Rounded availability/header tile used only by the Hours tab."""

    def __init__(
        self,
        parent: tk.Widget,
        *,
        text: str,
        fill: str,
        foreground: str,
        command=None,
        border: str = "",
        hover_fill: str | None = None,
        gradient: bool = False,
        icon: str | None = None,
        width: int = 180,
        height: int = 46,
        font=("Segoe UI", 10, "bold"),
    ) -> None:
        super().__init__(
            parent,
            width=width,
            height=height,
            bg=parent.cget("bg"),
            bd=0,
            highlightthickness=0,
            cursor="hand2" if command else "arrow",
        )
        self.text = text
        self.fill = fill
        self.foreground = foreground
        self.command = command
        self.border = border or fill
        self.hover_fill = hover_fill or fill
        self.gradient = gradient
        self.icon = icon
        self.font = font
        self._hovered = False
        self.bind("<Configure>", self._redraw)
        if command:
            self.bind("<Enter>", self._enter)
            self.bind("<Leave>", self._leave)
            self.bind("<ButtonRelease-1>", self._invoke)
            self.bind("<Return>", self._invoke)
            self.bind("<space>", self._invoke)

    def _enter(self, _event=None) -> None:
        self._hovered = True
        self._redraw()

    def _leave(self, _event=None) -> None:
        self._hovered = False
        self._redraw()

    def _invoke(self, _event=None) -> None:
        if callable(self.command):
            self.command()

    def _redraw(self, _event=None) -> None:
        self.delete("all")
        width = max(8, self.winfo_width())
        height = max(8, self.winfo_height())
        fill = self.hover_fill if self._hovered else self.fill
        _hours_rounded_box(
            self,
            1,
            1,
            width - 1,
            height - 1,
            10,
            fill=fill,
            outline=self.border,
        )
        if self.gradient and not self._hovered:
            # A restrained highlight gives the green cards depth while the
            # rounded base keeps every edge clean on Windows/Tk.
            inner_top = 4
            inner_bottom = max(inner_top + 1, height - 5)
            bands = 20
            band_height = max(1, (inner_bottom - inner_top) / bands)
            for band in range(bands):
                top = inner_top + band * band_height
                bottom = inner_top + (band + 1) * band_height + 1
                shade = _hours_blend("#16AA70", fill, band / (bands - 1))
                self.create_rectangle(
                    10,
                    top,
                    width - 10,
                    bottom,
                    fill=shade,
                    outline=shade,
                )
        if self.icon == "calendar":
            probe = self.create_text(0, 0, text=self.text, font=self.font)
            bbox = self.bbox(probe) or (0, 0, 0, 0)
            self.delete(probe)
            text_width = bbox[2] - bbox[0]
            icon_x = max(18, (width - text_width - 28) / 2 + 8)
            _draw_hours_calendar(self, icon_x, height / 2, self.foreground)
            self.create_text(
                icon_x + 18,
                height / 2,
                text=self.text,
                fill=self.foreground,
                font=self.font,
                anchor="w",
            )
        else:
            self.create_text(
                width / 2,
                height / 2,
                text=self.text,
                fill=self.foreground,
                font=self.font,
                justify="center",
            )


class HoursDateField(tk.Canvas):
    """Rounded date field with an integrated calendar affordance."""

    def __init__(self, parent, variable, on_open, on_submit) -> None:
        super().__init__(
            parent,
            width=218,
            height=48,
            bg=parent.cget("bg"),
            bd=0,
            highlightthickness=0,
        )
        self._on_open = on_open
        self.entry = tk.Entry(
            self,
            textvariable=variable,
            relief="flat",
            bd=0,
            bg="#FFFFFF",
            fg="#142B50",
            insertbackground="#142B50",
            font=("Segoe UI", 11),
        )
        self.create_window(16, 24, window=self.entry, anchor="w", width=148, height=28)
        self.bind("<Configure>", self._redraw)
        self.bind("<Button-1>", lambda _event: on_open())
        self.entry.bind("<Return>", lambda _event: on_submit())
        self.entry.bind("<Double-Button-1>", lambda _event: on_open())

    def _redraw(self, _event=None) -> None:
        self.delete("hours_date_surface")
        width = max(8, self.winfo_width())
        height = max(8, self.winfo_height())
        _hours_rounded_box(
            self,
            1,
            1,
            width - 1,
            height - 1,
            10,
            fill="#FFFFFF",
            outline="#D7E1EF",
            tag="hours_date_surface",
        )
        self.create_rectangle(
            width - 43,
            10,
            width - 10,
            height - 10,
            fill="#F1F5FB",
            outline="#D7E1EF",
            tags="hours_date_surface",
        )
        _draw_hours_calendar(
            self,
            width - 26,
            height / 2,
            "#55739D",
            tag="hours_date_surface",
        )
        self.tag_lower("hours_date_surface")


class HoursPill(tk.Canvas):
    """Soft rounded status/summary label for the Hours toolbar."""

    def __init__(
        self,
        parent: tk.Widget,
        text: str,
        *,
        dot: str | None = None,
        fill: str = "#F1F5FF",
        foreground: str = "#142B50",
        width: int = 170,
        calendar: bool = False,
    ) -> None:
        super().__init__(
            parent,
            width=width,
            height=34,
            bg=parent.cget("bg"),
            bd=0,
            highlightthickness=0,
        )
        self._text = text
        self._dot = dot
        self._fill = fill
        self._foreground = foreground
        self._calendar = calendar
        self.bind("<Configure>", self._redraw)

    def set_text(self, text: str) -> None:
        self._text = text
        self._redraw()

    def _redraw(self, _event=None) -> None:
        self.delete("all")
        width = max(8, self.winfo_width())
        height = max(8, self.winfo_height())
        _hours_rounded_box(self, 1, 1, width - 1, height - 1, 18, fill=self._fill)
        icon_x = 22
        if self._dot:
            self.create_oval(13, height / 2 - 9, 31, height / 2 + 9, fill=self._dot, outline=self._dot)
        elif self._calendar:
            _draw_hours_calendar(self, 22, height / 2, "#1673FF")
        else:
            icon_x = 10
        self.create_text(
            icon_x + 20,
            height / 2,
            text=self._text,
            fill=self._foreground,
            font=("Segoe UI", 10),
            anchor="w",
        )


class BarButton(tk.Canvas):
    """Rounded, dependency-free action button used by the Bar dashboard."""

    def __init__(
        self,
        parent: tk.Widget,
        text: str,
        command,
        *,
        color: str,
        hover: str | None = None,
        width: int = 142,
        height: int = 42,
        font=("Segoe UI", 9, "bold"),
    ) -> None:
        super().__init__(
            parent, width=width, height=height, bg=parent.cget("bg"), bd=0,
            highlightthickness=0, cursor="hand2", takefocus=1,
        )
        self._text = text
        self._command = command
        self._color = color
        self._hover = hover or color
        self._hovered = False
        self._font = font
        self.bind("<Configure>", self._draw)
        self.bind("<Enter>", lambda _event: self._set_hover(True))
        self.bind("<Leave>", lambda _event: self._set_hover(False))
        self.bind("<ButtonRelease-1>", lambda _event: self._invoke())
        self.bind("<Return>", lambda _event: self._invoke())
        self.bind("<space>", lambda _event: self._invoke())

    def _set_hover(self, value: bool) -> None:
        self._hovered = value
        self._draw()

    def _invoke(self) -> None:
        if callable(self._command):
            self._command()

    def _draw(self, _event=None) -> None:
        self.delete("all")
        width = max(10, self.winfo_width())
        height = max(10, self.winfo_height())
        _hours_rounded_box(
            self, 1, 1, width - 1, height - 1, 9,
            fill=self._hover if self._hovered else self._color,
        )
        self.create_text(
            width / 2, height / 2, text=self._text, fill="white", font=self._font,
        )


class AdminTabView(tk.Frame):
    """Scrollable, theme-independent tab bar that preserves Notebook's API."""

    ACTIVE_BG = "#1673FF"
    ACTIVE_FG = "#FFFFFF"
    INACTIVE_BG = "#F8FAFC"
    INACTIVE_FG = "#243858"
    HOVER_BG = "#DBEAFE"
    HOVER_FG = "#1D4ED8"
    BORDER = "#E2E8F0"

    TAB_ICONS = {
        "Reservas y pagos": "▣",
        "Horas": "◷",
        "Caja": "$",
        "Bar": "☕",
        "Operación": "⚙",
        "Atención humana": "●",
        "Torneos": "♛",
        "Escuelita": "⚽",
        "Turnos Fijos": "▦",
        "Blacklist": "⊘",
        "Comandos y configuración": "☷",
    }

    def __init__(self, master: tk.Misc, **kwargs) -> None:
        super().__init__(
            master,
            bg="#FFFFFF",
            highlightbackground=self.BORDER,
            highlightthickness=1,
            bd=0,
            **kwargs,
        )
        self._records: dict[tk.Widget, dict] = {}
        self._selected: tk.Widget | None = None

        self._navigation = tk.Frame(self, bg=self.INACTIVE_BG, height=58)
        self._navigation.pack(fill="x")
        self._navigation.pack_propagate(False)
        self._canvas = tk.Canvas(
            self._navigation,
            bg=self.INACTIVE_BG,
            height=56,
            highlightthickness=0,
            bd=0,
        )
        self._scrollbar = ttk.Scrollbar(
            self._navigation,
            orient="horizontal",
            command=self._canvas.xview,
            style="Admin.Horizontal.TScrollbar",
        )
        self._canvas.configure(xscrollcommand=self._scrollbar.set)
        self._strip = tk.Frame(self._canvas, bg=self.INACTIVE_BG)
        self._strip_window = self._canvas.create_window(
            (0, 0), window=self._strip, anchor="nw"
        )
        self._canvas.pack(fill="both", expand=True)
        self._strip.bind("<Configure>", self._on_strip_configure)
        self._canvas.bind("<Configure>", self._on_canvas_configure)
        self._canvas.bind("<Shift-MouseWheel>", self._scroll_tabs)

    def add(self, child: tk.Widget, text: str = "") -> None:
        tab = tk.Frame(
            self._strip,
            bg=self.INACTIVE_BG,
            highlightbackground=self.BORDER,
            highlightthickness=1,
            bd=0,
            cursor="hand2",
        )
        tab.pack(side="left", fill="both", expand=True)
        content = tk.Frame(tab, bg=self.INACTIVE_BG, cursor="hand2")
        content.pack(fill="both", expand=True, padx=15, pady=(13, 10))
        icon = tk.Label(
            content,
            text=self.TAB_ICONS.get(text, "•"),
            font=("Segoe UI Symbol", 13, "bold"),
            fg=self.INACTIVE_FG,
            bg=self.INACTIVE_BG,
            cursor="hand2",
        )
        icon.pack(side="left", padx=(0, 8))
        label = tk.Label(
            content,
            text=text,
            font=("Segoe UI", 10, "bold"),
            fg=self.INACTIVE_FG,
            bg=self.INACTIVE_BG,
            cursor="hand2",
        )
        label.pack(side="left")
        badge = tk.Label(
            content,
            bg=self.INACTIVE_BG,
            bd=0,
            cursor="hand2",
        )
        underline = tk.Frame(tab, bg=self.INACTIVE_BG, height=4)
        underline.pack(fill="x", side="bottom")

        record = {
            "tab": tab,
            "content": content,
            "icon_label": icon,
            "text_label": label,
            "badge_label": badge,
            "underline": underline,
            "text": text,
            "image": "",
        }
        self._records[child] = record
        for widget in (tab, content, icon, label, badge, underline):
            widget.bind("<Button-1>", lambda _event, page=child: self._click_select(page))
            widget.bind("<Enter>", lambda _event, page=child: self._hover(page, True))
            widget.bind("<Leave>", lambda _event, page=child: self._hover(page, False))
            widget.bind("<Shift-MouseWheel>", self._scroll_tabs)

        child.pack_forget()
        if self._selected is None:
            self._activate(child, emit=False)

    def _click_select(self, child: tk.Widget) -> None:
        self.select(child)
        self.event_generate("<<NotebookTabClicked>>", when="tail")

    def tabs(self) -> tuple[str, ...]:
        return tuple(str(child) for child in self._records)

    def select(self, tab_id=None):
        if tab_id is None:
            return str(self._selected) if self._selected is not None else ""
        child = self._resolve(tab_id)
        if child is not None:
            self._activate(child, emit=True)
        return str(self._selected) if self._selected is not None else ""

    def tab(self, tab_id, option: str | None = None, **kwargs):
        child = self._resolve(tab_id)
        if child is None:
            raise tk.TclError(f"unknown tab {tab_id}")
        record = self._records[child]
        if option is not None:
            return record.get(option, "")
        if "text" in kwargs:
            record["text"] = kwargs["text"]
            record["text_label"].configure(text=kwargs["text"])
        if "image" in kwargs:
            image = kwargs["image"]
            record["image"] = image
            if image:
                record["badge_label"].configure(image=image)
                if not record["badge_label"].winfo_manager():
                    record["badge_label"].pack(side="left", padx=(8, 0))
            else:
                record["badge_label"].configure(image="")
                record["badge_label"].pack_forget()
        return None

    def _resolve(self, tab_id) -> tk.Widget | None:
        if tab_id in self._records:
            return tab_id
        target = str(tab_id)
        for child in self._records:
            if str(child) == target:
                return child
        return None

    def _activate(self, child: tk.Widget, *, emit: bool) -> None:
        if child == self._selected:
            return
        previous = self._selected
        if previous is not None:
            previous.pack_forget()
        self._selected = child
        child.pack(fill="both", expand=True)
        for page in self._records:
            self._paint_tab(page, active=page == child)
        self.after_idle(lambda: self._scroll_selected_into_view(child))
        if emit:
            self.event_generate("<<NotebookTabChanged>>", when="tail")

    def _paint_tab(self, child: tk.Widget, *, active: bool, hover: bool = False) -> None:
        record = self._records[child]
        if active:
            bg, fg, underline = self.ACTIVE_BG, self.ACTIVE_FG, self.ACTIVE_BG
        elif hover:
            bg, fg, underline = self.HOVER_BG, self.HOVER_FG, self.HOVER_BG
        else:
            bg, fg, underline = self.INACTIVE_BG, self.INACTIVE_FG, self.INACTIVE_BG
        for key in ("tab", "content", "icon_label", "text_label", "badge_label"):
            record[key].configure(bg=bg)
        record["icon_label"].configure(fg=fg)
        record["text_label"].configure(fg=fg)
        record["underline"].configure(bg=underline)

    def _hover(self, child: tk.Widget, entering: bool) -> None:
        if child != self._selected:
            self._paint_tab(child, active=False, hover=entering)

    def _on_strip_configure(self, _event=None) -> None:
        self._canvas.configure(scrollregion=self._canvas.bbox("all"))
        self._refresh_scrollbar()

    def _on_canvas_configure(self, event) -> None:
        requested = self._tabs_requested_width()
        self._canvas.itemconfigure(self._strip_window, width=max(event.width, requested))
        self._canvas.configure(scrollregion=self._canvas.bbox("all"))
        self._refresh_scrollbar(event.width, requested)

    def _refresh_scrollbar(self, width: int | None = None, requested: int | None = None) -> None:
        width = width if width is not None else self._canvas.winfo_width()
        requested = requested if requested is not None else self._tabs_requested_width()
        if requested > max(1, width):
            if not self._scrollbar.winfo_manager():
                self._scrollbar.pack(side="bottom", fill="x")
                self._navigation.configure(height=70)
        else:
            self._scrollbar.pack_forget()
            self._navigation.configure(height=58)
            self._canvas.xview_moveto(0)

    def _tabs_requested_width(self) -> int:
        return sum(
            max(1, int(record["tab"].winfo_reqwidth()))
            for record in self._records.values()
        )

    def _scroll_tabs(self, event) -> str:
        direction = -1 if event.delta > 0 else 1
        self._canvas.xview_scroll(direction * 3, "units")
        return "break"

    def _scroll_selected_into_view(self, child: tk.Widget) -> None:
        record = self._records.get(child)
        if not record:
            return
        tab = record["tab"]
        strip_width = max(1, self._strip.winfo_width())
        canvas_width = max(1, self._canvas.winfo_width())
        left = tab.winfo_x()
        right = left + tab.winfo_width()
        current_left = self._canvas.canvasx(0)
        current_right = current_left + canvas_width
        if left < current_left:
            self._canvas.xview_moveto(left / strip_width)
        elif right > current_right:
            self._canvas.xview_moveto(max(0.0, (right - canvas_width) / strip_width))


class AdminPanel(tk.Toplevel):
    NAVY = "#142B50"
    BLUE = "#1673FF"
    GREEN = "#07864C"
    ORANGE = "#F97316"
    RED = "#DC2626"
    FREE_GREEN = "#079455"
    PAST_GRAY = "#64748B"
    MUTED = "#64748B"
    BORDER = "#E2E8F0"
    SURFACE = "#FFFFFF"
    BG = "#F5F7FB"

    def __init__(
        self,
        parent: tk.Misc,
        service: DesktopAdminService,
        open_configurator: Callable[[], None],
        on_notifications_changed: Callable[[dict[str, int]], None] | None = None,
    ) -> None:
        super().__init__(parent)
        self.service = service
        self.open_configurator_callback = open_configurator
        self.on_notifications_changed = on_notifications_changed or (lambda _counts: None)
        self._notification_poll_id: str | None = None
        self._last_notification_counts: dict[str, int] | None = None
        self._initial_notification_tab_selected = False
        self.title("CANCHERIA · Administración")
        screen_width = max(1100, self.winfo_screenwidth())
        screen_height = max(720, self.winfo_screenheight())
        self._compact_height = screen_height < 900
        window_width = min(1460, screen_width - 50)
        window_height = min(920, screen_height - 12)
        self.geometry(f"{window_width}x{window_height}")
        self.minsize(1100, 700)
        self.configure(bg=self.BG)
        self._apply_cancheria_icon()
        self.transient(parent)

        self.summary_vars = {
            key: tk.StringVar(value="0") for key in ("active", "pending", "today", "cases")
        }
        self._build()
        self.refresh_all()
        self._schedule_notification_poll()

    def _apply_cancheria_icon(self) -> None:
        """Use the product icon instead of Tk's default feather on Windows."""
        service_root = getattr(self.service, "root", None)
        parent_root = getattr(self.master, "root_dir", None)
        root = Path(service_root or parent_root or Path(__file__).resolve().parents[3])
        icon_path = root / "assets" / "cancheria.ico"
        if not icon_path.is_file():
            return
        try:
            # The explicit bitmap fixes this Toplevel. ``default`` also makes
            # the reservation/tournament dialogs opened from it inherit the
            # same icon instead of falling back to Tk's feather.
            self.iconbitmap(str(icon_path))
            self.iconbitmap(default=str(icon_path))
        except tk.TclError:
            # Non-Windows Tk builds can reject .ico while the rest of the
            # administration panel remains fully usable.
            pass

    def _build(self) -> None:
        self._configure_ttk_styles()
        header = tk.Frame(
            self,
            bg=self.SURFACE,
            highlightbackground=self.BORDER,
            highlightthickness=1,
        )
        header.pack(
            fill="x", padx=20,
            pady=((10, 6) if self._compact_height else (18, 10)),
        )
        tk.Label(
            header,
            text="Panel de administración",
            font=("Segoe UI", 20 if self._compact_height else 24, "bold"),
            fg=self.NAVY,
            bg=self.SURFACE,
        ).pack(side="left", padx=24, pady=10 if self._compact_height else 18)
        tk.Button(
            header,
            text="↻  Actualizar",
            command=self._refresh_and_mark_notifications_read,
            font=("Segoe UI", 11, "bold"),
            bg=self.BLUE,
            fg="white",
            activebackground="#0F62E8",
            activeforeground="white",
            relief="flat",
            bd=0,
            padx=20,
            pady=8 if self._compact_height else 11,
            cursor="hand2",
        ).pack(side="right", padx=20)

        cards = tk.Frame(self, bg=self.BG)
        cards.pack(fill="x", padx=15, pady=(0, 7 if self._compact_height else 12))
        labels = (
            ("active", "Reservas activas", "▣", "#10B981", "#E1F7EE"),
            ("pending", "Pagos pendientes", "▤", "#7C3AED", "#F0EAFE"),
            ("today", "Turnos de hoy", "◷", "#1673FF", "#E7F0FF"),
            ("cases", "Casos humanos", "●", "#EF4444", "#FEEBEC"),
        )
        for index, (key, label, icon, icon_color, icon_bg) in enumerate(labels):
            cards.grid_columnconfigure(index, weight=1)
            card = tk.Frame(
                cards,
                bg=self.SURFACE,
                highlightbackground=self.BORDER,
                highlightthickness=1,
                bd=0,
                height=84 if self._compact_height else 112,
            )
            card.grid(row=0, column=index, sticky="nsew", padx=5)
            card.grid_propagate(False)
            icon_size = 48 if self._compact_height else 64
            icon_holder = tk.Frame(card, bg=icon_bg, width=icon_size, height=icon_size)
            icon_holder.pack(
                side="left", padx=((14, 12) if self._compact_height else (20, 15)),
                pady=17 if self._compact_height else 20,
            )
            icon_holder.pack_propagate(False)
            tk.Label(
                icon_holder,
                text=icon,
                font=("Segoe UI Symbol", 20 if self._compact_height else 24, "bold"),
                fg=icon_color,
                bg=icon_bg,
            ).pack(expand=True)
            values = tk.Frame(card, bg=self.SURFACE)
            values.pack(side="left", fill="y", pady=9 if self._compact_height else 16)
            tk.Label(
                values,
                textvariable=self.summary_vars[key],
                font=("Segoe UI", 20 if self._compact_height else 24, "bold"),
                fg=self.BLUE,
                bg=self.SURFACE,
                anchor="w",
            ).pack(anchor="w")
            tk.Label(
                values,
                text=label,
                font=("Segoe UI", 10),
                fg=self.MUTED,
                bg=self.SURFACE,
                anchor="w",
            ).pack(anchor="w", pady=(2, 0))

        self.notebook = AdminTabView(self)
        self.notebook.pack(fill="both", expand=True, padx=20, pady=(0, 18))
        self.bookings_tab = tk.Frame(self.notebook, bg=self.SURFACE)
        self.hours_tab = tk.Frame(self.notebook, bg=self.SURFACE)
        self.cash_tab = tk.Frame(self.notebook, bg=self.SURFACE)
        self.bar_tab = tk.Frame(self.notebook, bg=self.SURFACE)
        self.operation_tab = tk.Frame(self.notebook, bg=self.SURFACE)
        self.cases_tab = tk.Frame(self.notebook, bg=self.SURFACE)
        self.tournaments_tab = tk.Frame(self.notebook, bg=self.SURFACE)
        self.school_tab = tk.Frame(self.notebook, bg=self.SURFACE)
        self.fixed_turns_tab = tk.Frame(self.notebook, bg=self.SURFACE)
        self.blacklist_tab = tk.Frame(self.notebook, bg=self.SURFACE)
        self.commands_tab = tk.Frame(self.notebook, bg=self.SURFACE)
        self.notebook.add(self.bookings_tab, text="Reservas y pagos")
        self.notebook.add(self.hours_tab, text="Horas")
        self.notebook.add(self.cash_tab, text="Caja")
        self.notebook.add(self.bar_tab, text="Bar")
        self.notebook.add(self.operation_tab, text="Operación")
        self.notebook.add(self.cases_tab, text="Atención humana")
        self.notebook.add(self.tournaments_tab, text="Torneos")
        self.notebook.add(self.school_tab, text="Escuelita")
        self.notebook.add(self.fixed_turns_tab, text="Turnos Fijos")
        self.notebook.add(self.blacklist_tab, text="Blacklist")
        self.notebook.add(self.commands_tab, text="Comandos y configuración")
        self._tab_titles = {
            self.bookings_tab: "Reservas y pagos",
            self.hours_tab: "Horas",
            self.cash_tab: "Caja",
            self.bar_tab: "Bar",
            self.operation_tab: "Operación",
            self.cases_tab: "Atención humana",
            self.tournaments_tab: "Torneos",
            self.school_tab: "Escuelita",
            self.fixed_turns_tab: "Turnos Fijos",
            self.blacklist_tab: "Blacklist",
            self.commands_tab: "Comandos y configuración",
        }
        self._tab_notification_keys = {
            self.bookings_tab: "bookings",
            self.hours_tab: "hours",
            self.cash_tab: "cash",
            self.bar_tab: "bar",
            self.operation_tab: "operation",
            self.cases_tab: "cases",
            self.tournaments_tab: "tournaments",
            self.school_tab: "school",
            self.fixed_turns_tab: "fixed_turns",
            self.blacklist_tab: "blacklist",
            self.commands_tab: "commands",
        }
        self._tab_badge_images: dict[tk.Widget, tk.PhotoImage] = {}
        self._build_bookings()
        self._build_hours()
        self._build_cash()
        self._build_bar()
        self._build_operation()
        self._build_cases()
        self._build_tournaments()
        self._build_school()
        self._build_fixed_turns()
        self._build_blacklist()
        self._build_commands()
        self.notebook.bind("<<NotebookTabChanged>>", self._on_tab_changed)
        self.notebook.bind("<<NotebookTabClicked>>", self._on_notification_tab_clicked)

    def _configure_ttk_styles(self) -> None:
        style = ttk.Style(self)
        style.configure(
            "Admin.Treeview",
            background=self.SURFACE,
            fieldbackground=self.SURFACE,
            foreground="#334155",
            bordercolor=self.BORDER,
            lightcolor=self.BORDER,
            darkcolor=self.BORDER,
            borderwidth=1,
            relief="flat",
            rowheight=34,
            font=("Segoe UI", 10),
        )
        style.configure(
            "Admin.Treeview.Heading",
            background="#F8FAFC",
            foreground="#475569",
            bordercolor=self.BORDER,
            lightcolor=self.BORDER,
            darkcolor=self.BORDER,
            relief="flat",
            padding=(8, 10),
            font=("Segoe UI", 10, "bold"),
        )
        style.map(
            "Admin.Treeview",
            background=[("selected", "#DBEAFE")],
            foreground=[("selected", "#1D4ED8")],
        )
        style.map(
            "Admin.Treeview.Heading",
            background=[("active", "#EEF4FF")],
            foreground=[("active", self.NAVY)],
        )
        style.configure(
            "Admin.Vertical.TScrollbar",
            background="#CBD5E1",
            troughcolor="#F8FAFC",
            bordercolor="#F8FAFC",
            arrowcolor=self.MUTED,
        )
        style.configure(
            "Admin.Horizontal.TScrollbar",
            background="#CBD5E1",
            troughcolor="#F8FAFC",
            bordercolor="#F8FAFC",
            arrowcolor=self.MUTED,
        )
        style.configure(
            "Hours.Vertical.TScrollbar",
            background="#94A3B8",
            troughcolor="#F1F5F9",
            bordercolor="#F1F5F9",
            arrowcolor="#64748B",
            width=13,
            arrowsize=10,
        )
        style.configure(
            "Hours.Horizontal.TScrollbar",
            background="#CBD5E1",
            troughcolor="#F1F5F9",
            bordercolor="#F1F5F9",
            arrowcolor="#64748B",
            width=12,
            arrowsize=10,
        )

    def _action_button(self, parent: tk.Widget, text: str, command, color: str) -> tk.Button:
        return tk.Button(
            parent,
            text=text,
            command=command,
            font=("Segoe UI", 10, "bold"),
            bg=color,
            fg="white",
            activebackground=color,
            activeforeground="white",
            relief="flat",
            bd=0,
            padx=15,
            pady=11,
            cursor="hand2",
        )

    def _build_bookings(self) -> None:
        actions = tk.Frame(self.bookings_tab, bg=self.SURFACE)
        actions.pack(fill="x", padx=18, pady=(16, 14))
        self._action_button(actions, "+  Nueva reserva", self._new_booking_dialog, self.BLUE).pack(side="left", padx=(0, 8))
        self._action_button(actions, "✓  Confirmar seña", lambda: self._booking_action("deposit"), self.GREEN).pack(side="left", padx=(0, 8))
        self._action_button(actions, "▣  Confirmar total", lambda: self._booking_action("total"), self.GREEN).pack(side="left", padx=(0, 8))
        self._action_button(actions, "↗  Liberar pendiente", lambda: self._booking_action("release"), self.ORANGE).pack(side="left", padx=(0, 8))
        self._action_button(actions, "✕  Cancelar", lambda: self._booking_action("cancel"), self.RED).pack(side="left", padx=(0, 8))
        self._action_button(actions, "🗑  Borrar", lambda: self._booking_action("delete"), self.PAST_GRAY).pack(side="left", padx=(0, 8))
        self.show_past_bookings_var = tk.BooleanVar(value=False)
        tk.Checkbutton(
            actions,
            text="Ver reservas pasadas",
            variable=self.show_past_bookings_var,
            command=self._refresh_bookings,
            font=("Segoe UI", 10, "bold"),
            fg=self.NAVY,
            bg=self.SURFACE,
            activeforeground=self.NAVY,
            activebackground=self.SURFACE,
            selectcolor="#FFFFFF",
            cursor="hand2",
            bd=0,
            highlightthickness=0,
        ).pack(side="left", padx=(6, 0))

        columns = ("id", "fecha", "hora", "cancha", "nombre", "telefono", "estado", "senia", "saldo")
        self.booking_tree = ttk.Treeview(self.bookings_tab, columns=columns, show="headings", selectmode="browse", style="Admin.Treeview")
        self._booking_headings = {"id": "#  ID", "fecha": "▣  Fecha", "hora": "◷  Hora", "cancha": "⚽  Cancha", "nombre": "♙  Cliente", "telefono": "☎  Teléfono", "estado": "◇  Estado", "senia": "▤  Pago", "saldo": "$  Saldo"}
        self._booking_sort_column = "fecha"
        self._booking_sort_ascending = True
        widths = {"id": 55, "fecha": 120, "hora": 80, "cancha": 105, "nombre": 155, "telefono": 125, "estado": 90, "senia": 115, "saldo": 90}
        for key in columns:
            if key in {"fecha", "hora"}:
                self.booking_tree.heading(
                    key,
                    text=self._booking_headings[key],
                    command=lambda column=key: self._toggle_booking_sort(column),
                )
            else:
                self.booking_tree.heading(key, text=self._booking_headings[key])
            self.booking_tree.column(key, width=widths[key], anchor="center" if key not in {"nombre", "telefono"} else "w")
        self._update_booking_sort_headings()
        scrollbar = ttk.Scrollbar(self.bookings_tab, orient="vertical", command=self.booking_tree.yview, style="Admin.Vertical.TScrollbar")
        self.booking_tree.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side="right", fill="y", pady=(0, 10))
        self.booking_tree.pack(fill="both", expand=True, padx=(18, 0), pady=(0, 18))

    def _build_hours(self) -> None:
        section = tk.Frame(
            self.hours_tab,
            bg="#FFFFFF",
            highlightbackground=self.BORDER,
            highlightthickness=1,
            bd=0,
        )
        section.pack(fill="both", expand=True, padx=14, pady=8)

        toolbar = tk.Frame(section, bg="#FFFFFF")
        toolbar.pack(fill="x", padx=14, pady=(8, 2))
        toolbar.grid_columnconfigure(0, weight=1)
        controls = tk.Frame(toolbar, bg="#FFFFFF")
        controls.grid(row=0, column=0, sticky="w")
        self.hours_controls = controls

        date_caption = tk.Frame(controls, bg="#FFFFFF", cursor="hand2")
        date_caption.pack(side="left", padx=(0, 8))
        date_label = tk.Label(
            date_caption,
            text="Fecha",
            font=("Segoe UI", 11, "bold"),
            fg=self.NAVY,
            bg="#FFFFFF",
            cursor="hand2",
        )
        date_label.pack(side="left")
        date_icon = tk.Canvas(
            date_caption,
            width=24,
            height=24,
            bg="#FFFFFF",
            bd=0,
            highlightthickness=0,
            cursor="hand2",
        )
        date_icon.pack(side="left", padx=(7, 0))
        _draw_hours_calendar(date_icon, 12, 13, self.BLUE)
        self.hours_day_var = tk.StringVar(value=dt_today())
        date_field = HoursDateField(
            controls,
            self.hours_day_var,
            lambda: self._show_date_picker(
                self.hours_day_var,
                date_field.entry,
                "Fecha de horarios",
                self._refresh_hours,
            ),
            self._refresh_hours,
        )
        date_field.pack(side="left", padx=(0, 8))
        date_label.bind(
            "<Button-1>",
            lambda _event: self._show_date_picker(
                self.hours_day_var,
                date_field.entry,
                "Fecha de horarios",
                self._refresh_hours,
            ),
        )
        date_icon.bind(
            "<Button-1>",
            lambda _event: self._show_date_picker(
                self.hours_day_var,
                date_field.entry,
                "Fecha de horarios",
                self._refresh_hours,
            ),
        )

        HoursTile(
            controls,
            text="‹",
            fill="#F4F7FC",
            foreground="#36557E",
            border="#D7E1EF",
            hover_fill="#E8F1FF",
            command=lambda: self._move_hours_date(-1),
            width=48,
            height=48,
            font=("Segoe UI", 18, "bold"),
        ).pack(side="left", padx=(0, 8))
        HoursTile(
            controls,
            text="Hoy",
            fill=self.BLUE,
            foreground="#FFFFFF",
            hover_fill="#0F62E8",
            command=self._set_hours_today,
            width=80,
            height=48,
            font=("Segoe UI", 11, "bold"),
        ).pack(side="left", padx=(0, 8))
        HoursTile(
            controls,
            text="›",
            fill="#F4F7FC",
            foreground="#36557E",
            border="#D7E1EF",
            hover_fill="#E8F1FF",
            command=lambda: self._move_hours_date(1),
            width=48,
            height=48,
            font=("Segoe UI", 18, "bold"),
        ).pack(side="left", padx=(0, 8))
        HoursTile(
            controls,
            text="Ver horarios",
            fill=self.BLUE,
            foreground="#FFFFFF",
            hover_fill="#0F62E8",
            command=self._refresh_hours,
            icon="calendar",
            width=154,
            height=48,
            font=("Segoe UI", 10, "bold"),
        ).pack(side="left")

        self.hours_status_var = tk.StringVar(value="")
        self.hours_summary_pill = HoursPill(
            toolbar,
            "",
            fill="#F3F4FF",
            foreground="#243858",
            width=315,
            calendar=True,
        )
        self.hours_summary_pill.grid(row=0, column=1, sticky="e", padx=(12, 0))
        self.hours_legend = tk.Frame(toolbar, bg="#FFFFFF")
        self.hours_legend.grid(
            row=1,
            column=0,
            columnspan=2,
            sticky="w",
            pady=(2, 0),
        )
        self.hours_legend_pills = [
            self._legend_item(self.hours_legend, self.FREE_GREEN, "Disponible", "#E3F8EF", 155),
            self._legend_item(self.hours_legend, self.RED, "Ocupado / bloqueado", "#FDEBEC", 235),
            self._legend_item(self.hours_legend, self.PAST_GRAY, "Fuera de atención", "#EEF2F7", 205),
        ]
        self.hours_show_all_var = tk.BooleanVar(value=False)
        tk.Checkbutton(
            self.hours_legend,
            text="Mostrar todos",
            variable=self.hours_show_all_var,
            command=self._refresh_hours,
            font=("Segoe UI", 10, "bold"),
            fg=self.NAVY,
            bg="#FFFFFF",
            activeforeground=self.NAVY,
            activebackground="#FFFFFF",
            selectcolor="#FFFFFF",
            cursor="hand2",
            bd=0,
            highlightthickness=0,
        ).pack(side="left", padx=(4, 0))
        toolbar.bind("<Configure>", self._layout_hours_toolbar)

        grid_card = tk.Frame(
            section,
            bg="#FFFFFF",
            highlightbackground="#E5ECF5",
            highlightthickness=1,
            bd=0,
        )
        grid_card.pack(fill="both", expand=True, padx=14, pady=(0, 8))
        body = tk.Frame(grid_card, bg="#FFFFFF")
        body.pack(fill="both", expand=True, padx=4, pady=4)
        self.hours_canvas = tk.Canvas(body, bg="white", highlightthickness=0)
        vertical = ttk.Scrollbar(body, orient="vertical", command=self.hours_canvas.yview, style="Hours.Vertical.TScrollbar")
        horizontal = ttk.Scrollbar(body, orient="horizontal", command=self.hours_canvas.xview, style="Hours.Horizontal.TScrollbar")
        self.hours_canvas.configure(yscrollcommand=vertical.set, xscrollcommand=horizontal.set)
        vertical.pack(side="right", fill="y")
        horizontal.pack(side="bottom", fill="x")
        self.hours_canvas.pack(side="left", fill="both", expand=True)
        self.hours_grid = tk.Frame(self.hours_canvas, bg="white")
        self.hours_grid_window = self.hours_canvas.create_window((0, 0), window=self.hours_grid, anchor="nw")
        self.hours_grid.bind(
            "<Configure>",
            lambda _event: self.hours_canvas.configure(scrollregion=self.hours_canvas.bbox("all")),
        )
        self.hours_canvas.bind("<Configure>", self._resize_hours_grid)
        self._bind_hours_wheel(self.hours_canvas)
        self._bind_hours_wheel(self.hours_grid)

    def _legend_item(
        self,
        parent: tk.Widget,
        color: str,
        label: str,
        background: str,
        width: int,
    ) -> HoursPill:
        pill = HoursPill(
            parent,
            label,
            dot=color,
            fill=background,
            foreground=self.NAVY,
            width=width,
        )
        pill.pack(side="left", padx=(0, 10))
        return pill

    def _layout_hours_toolbar(self, event) -> None:
        if not hasattr(self, "hours_summary_pill"):
            return
        if event.width < 1080:
            self.hours_controls.grid_configure(columnspan=2)
            self.hours_summary_pill.configure(width=285)
            self.hours_summary_pill.grid_configure(
                row=1,
                column=1,
                sticky="e",
                padx=(0, 0),
                pady=(4, 0),
            )
            self.hours_legend.grid_configure(columnspan=1)
            for pill, width in zip(self.hours_legend_pills, (125, 190, 165)):
                pill.configure(width=width)
        else:
            self.hours_controls.grid_configure(columnspan=1)
            self.hours_summary_pill.configure(width=315)
            self.hours_summary_pill.grid_configure(
                row=0,
                column=1,
                sticky="e",
                padx=(12, 0),
                pady=(0, 0),
            )
            self.hours_legend.grid_configure(columnspan=2)
            for pill, width in zip(self.hours_legend_pills, (155, 235, 205)):
                pill.configure(width=width)

    def _show_date_picker(
        self,
        variable: tk.StringVar,
        anchor: tk.Widget,
        title: str,
        on_select: Callable[[], None] | None = None,
    ) -> None:
        DatePicker(self, variable, anchor=anchor, title=title, on_select=on_select)

    def _resize_hours_grid(self, event) -> None:
        requested = self.hours_grid.winfo_reqwidth()
        self.hours_canvas.itemconfigure(self.hours_grid_window, width=max(event.width, requested))

    def _bind_hours_wheel(self, widget: tk.Widget) -> None:
        """Make the schedule scroll naturally anywhere under the pointer."""
        if not getattr(widget, "_cancheria_hours_wheel_bound", False):
            widget.bind("<MouseWheel>", self._scroll_hours_vertical, add="+")
            widget.bind("<Shift-MouseWheel>", self._scroll_hours_horizontal, add="+")
            # X11/Tk uses buttons 4 and 5 instead of MouseWheel.
            widget.bind("<Button-4>", self._scroll_hours_vertical, add="+")
            widget.bind("<Button-5>", self._scroll_hours_vertical, add="+")
            setattr(widget, "_cancheria_hours_wheel_bound", True)
        for child in widget.winfo_children():
            self._bind_hours_wheel(child)

    def _scroll_hours_vertical(self, event) -> str:
        direction = -1 if getattr(event, "num", None) == 4 or getattr(event, "delta", 0) > 0 else 1
        self.hours_canvas.yview_scroll(direction * 3, "units")
        return "break"

    def _scroll_hours_horizontal(self, event) -> str:
        direction = -1 if getattr(event, "delta", 0) > 0 else 1
        self.hours_canvas.xview_scroll(direction * 3, "units")
        return "break"

    def _build_cash(self) -> None:
        """Build the approved financial dashboard without changing its business logic."""
        self.cash_tab.configure(bg=self.BG)
        today = dt.date.today()
        self.cash_start_var = tk.StringVar(value=today.replace(day=1).isoformat())
        self.cash_end_var = tk.StringVar(value=today.isoformat())
        self.cash_range_var = tk.StringVar(value="Mes actual")
        self.cash_method_var = tk.StringVar(value="Todos")
        self.cash_page = 0
        self.cash_page_size = 8
        self.cash_summary_vars = {
            key: tk.StringVar(value="$ 0") for key in ("today", "month", "pending", "future")
        }

        cards = tk.Frame(self.cash_tab, bg=self.BG)
        cards.pack(
            fill="x", padx=14,
            pady=((9, 7) if self._compact_height else (14, 10)),
        )
        card_specs = (
            ("today", "Ingresos de hoy", "$", "#079455", "#E1F7EE"),
            ("month", "Ingresos del mes", "▣", self.BLUE, "#E7F0FF"),
            ("pending", "Saldos pendientes", "$", "#F05A16", "#FFF3E6"),
            ("future", "Reservas futuras", "▦", "#7C3AED", "#F0EAFE"),
        )
        for column, (key, title, icon, color, icon_bg) in enumerate(card_specs):
            cards.grid_columnconfigure(column, weight=1, uniform="cash-card")
            card = tk.Frame(
                cards, bg=self.SURFACE, highlightbackground="#E6EDF7",
                highlightthickness=1, height=90 if self._compact_height else 108,
            )
            card.grid(row=0, column=column, sticky="nsew", padx=5)
            card.grid_propagate(False)
            cash_icon_size = 54 if self._compact_height else 66
            icon_holder = tk.Frame(card, bg=icon_bg, width=cash_icon_size, height=cash_icon_size)
            icon_holder.pack(
                side="left", padx=((14, 13) if self._compact_height else (20, 18)),
                pady=17 if self._compact_height else 20,
            )
            icon_holder.pack_propagate(False)
            tk.Label(
                icon_holder, text=icon, bg=icon_bg, fg=color,
                font=("Segoe UI Symbol", 21 if self._compact_height else 25, "bold"),
            ).pack(expand=True)
            value_area = tk.Frame(card, bg=self.SURFACE)
            value_area.pack(side="left", fill="y", pady=12 if self._compact_height else 18)
            tk.Label(
                value_area, text=title, bg=self.SURFACE, fg=self.MUTED,
                font=("Segoe UI", 10), anchor="w",
            ).pack(anchor="w")
            tk.Label(
                value_area, textvariable=self.cash_summary_vars[key],
                bg=self.SURFACE, fg=color,
                font=("Segoe UI", 18 if self._compact_height else 21, "bold"), anchor="w",
            ).pack(anchor="w", pady=(4, 0))

        toolbar = tk.Frame(
            self.cash_tab, bg=self.SURFACE, highlightbackground="#E6EDF7",
            highlightthickness=1,
        )
        toolbar.pack(fill="x", padx=14, pady=(0, 7 if self._compact_height else 10))
        toolbar.grid_columnconfigure(0, weight=1)
        filters = tk.Frame(toolbar, bg=self.SURFACE)
        filters.grid(row=0, column=0, sticky="w", padx=(16, 6), pady=7 if self._compact_height else 10)
        tk.Label(
            filters, text="Período:", bg=self.SURFACE, fg=self.NAVY,
            font=("Segoe UI", 10, "bold"),
        ).pack(side="left", padx=(0, 8))
        range_combo = ttk.Combobox(
            filters, textvariable=self.cash_range_var,
            values=("Hoy", "Ayer", "Últimos 7 días", "Mes actual", "Mes anterior", "Rango personalizado"),
            state="readonly", width=17, font=("Segoe UI", 10),
        )
        range_combo.pack(side="left", padx=(0, 12), ipady=6)
        range_combo.bind("<<ComboboxSelected>>", lambda _event: self._apply_cash_period())

        self.cash_method_buttons: dict[str, tk.Button] = {}
        for method_name in ("Todos", "Efectivo", "Transferencia"):
            button = tk.Button(
                filters, text=method_name,
                command=lambda value=method_name: self._set_cash_method(value),
                font=("Segoe UI", 9), relief="flat", bd=0, padx=15,
                pady=7 if self._compact_height else 9,
                cursor="hand2",
            )
            button.pack(side="left", padx=3)
            self.cash_method_buttons[method_name] = button
        self._style_cash_method_buttons()

        self.cash_custom_dates_holder = tk.Frame(toolbar, bg=self.SURFACE)
        self.cash_custom_dates_holder.grid(row=1, column=0, columnspan=2, sticky="w", padx=16, pady=(0, 9))
        self.cash_start_entry = self._cash_date_control(
            self.cash_custom_dates_holder, "Desde", self.cash_start_var, "Fecha inicial de Caja"
        )
        self.cash_end_entry = self._cash_date_control(
            self.cash_custom_dates_holder, "Hasta", self.cash_end_var, "Fecha final de Caja"
        )
        self.cash_custom_dates_holder.grid_remove()

        actions = tk.Frame(toolbar, bg=self.SURFACE)
        actions.grid(row=0, column=1, sticky="e", padx=(6, 12), pady=8)
        action_specs = (
            ("＋  Registrar ingreso", lambda: self._cash_movement_dialog("income"), self.BLUE, 154),
            ("−  Registrar gasto", lambda: self._cash_movement_dialog("expense"), self.ORANGE, 148),
            ("▣  Cerrar caja", self._close_cash, self.NAVY, 126),
            ("▤  Exportar CSV", self._export_cash, self.GREEN, 130),
        )
        for label, command, color, width in action_specs:
            button = tk.Button(
                actions, text=label, command=command, bg=color, fg="white",
                activebackground=color, activeforeground="white", relief="flat", bd=0,
                font=("Segoe UI", 9, "bold"), cursor="hand2", width=max(12, width // 9),
                pady=8 if self._compact_height else 10,
            )
            button.pack(side="left", padx=4)

        body = tk.Frame(self.cash_tab, bg=self.BG)
        body.pack(fill="both", expand=True, padx=14, pady=(0, 12))
        body.grid_rowconfigure(0, weight=1)
        body.grid_columnconfigure(0, weight=2, uniform="cash-body")
        body.grid_columnconfigure(1, weight=1, uniform="cash-body")
        movements_card = tk.Frame(
            body, bg=self.SURFACE, highlightbackground="#E6EDF7", highlightthickness=1,
        )
        movements_card.grid(row=0, column=0, sticky="nsew", padx=(0, 6))
        charts = tk.Frame(body, bg=self.BG)
        charts.grid(row=0, column=1, sticky="nsew", padx=(6, 0))

        heading = tk.Frame(movements_card, bg=self.SURFACE)
        heading.pack(fill="x", padx=18, pady=((9, 6) if self._compact_height else (14, 10)))
        tk.Label(
            heading, text="▤  Movimientos de caja", bg=self.SURFACE, fg=self.NAVY,
            font=("Segoe UI", 13 if self._compact_height else 15, "bold"),
        ).pack(side="left")
        self.cash_period_var = tk.StringVar(value="")
        tk.Label(
            heading, textvariable=self.cash_period_var, bg=self.SURFACE, fg=self.MUTED,
            font=("Segoe UI", 9),
        ).pack(side="right")

        table = tk.Frame(movements_card, bg=self.SURFACE)
        table.pack(fill="both", expand=True, padx=18)
        header = tk.Frame(table, bg="#F8FAFC", height=34 if self._compact_height else 40)
        header.pack(fill="x")
        header.pack_propagate(False)
        self.cash_table_weights = (16, 24, 19, 15, 13, 13)
        for index, (title, weight) in enumerate(zip(
            ("Fecha", "Concepto", "Cliente", "Método", "Importe", "Estado"),
            self.cash_table_weights,
        )):
            header.grid_columnconfigure(index, weight=weight, uniform="cash-table")
            tk.Label(
                header, text=title, bg="#F8FAFC", fg="#475569",
                font=("Segoe UI", 9, "bold"), anchor="w" if index < 4 else "center",
            ).grid(row=0, column=index, sticky="nsew", padx=10)
        self.cash_rows_frame = tk.Frame(table, bg=self.SURFACE)
        self.cash_rows_frame.pack(fill="both", expand=True)

        footer = tk.Frame(movements_card, bg=self.SURFACE)
        footer.pack(fill="x", padx=18, pady=((5, 7) if self._compact_height else (9, 13)))
        self.cash_pager_buttons = tk.Frame(footer, bg=self.SURFACE)
        self.cash_pager_buttons.pack(side="left")
        self.cash_page_var = tk.StringVar(value="Mostrando 0 movimientos")
        tk.Label(
            footer, textvariable=self.cash_page_var, bg=self.SURFACE, fg=self.MUTED,
            font=("Segoe UI", 9),
        ).pack(side="right")
        # Keep the ledger provenance available to the controller without adding
        # the technical banner that made the approved dashboard look cramped.
        self.cash_history_var = tk.StringVar(value="")

        self.cash_chart_canvases: dict[str, tk.Canvas] = {}
        chart_specs = (
            ("daily", "▥  Ingresos por día", 3),
            ("methods", "◔  Distribución por método", 2),
            ("courts", "▥  Por cancha", 2),
        )
        for row, (key, title, weight) in enumerate(chart_specs):
            charts.grid_rowconfigure(row, weight=weight, uniform="cash-chart")
            card = tk.Frame(
                charts, bg=self.SURFACE, highlightbackground="#E6EDF7", highlightthickness=1,
            )
            card.grid(row=row, column=0, sticky="nsew", pady=(0 if row == 0 else 6, 6 if row < 2 else 0))
            tk.Label(
                card, text=title, bg=self.SURFACE, fg=self.NAVY,
                font=("Segoe UI", 10 if self._compact_height else 11, "bold"), anchor="w",
            ).pack(
                fill="x", padx=16,
                pady=((7, 2) if self._compact_height else (12, 4)),
            )
            chart_height = (
                (70 if key == "daily" else 52)
                if self._compact_height else 96
            )
            canvas = tk.Canvas(
                card, bg=self.SURFACE, highlightthickness=0, height=chart_height,
            )
            canvas.pack(
                fill="both", expand=True, padx=14,
                pady=(0, 4 if self._compact_height else 10),
            )
            canvas.bind("<Configure>", lambda _event: self._draw_cash_charts())
            self.cash_chart_canvases[key] = canvas
        self._cash_snapshot = {}

    def _cash_date_control(
        self,
        parent: tk.Widget,
        label: str,
        variable: tk.StringVar,
        title: str,
    ) -> tk.Entry:
        tk.Label(parent, text=label, bg=self.SURFACE, fg=self.MUTED).pack(
            side="left", padx=(6, 3)
        )
        holder = tk.Frame(parent, bg="#F8FAFC", highlightbackground=self.BORDER, highlightthickness=1)
        holder.pack(side="left", padx=(0, 4))
        entry = tk.Entry(
            holder, textvariable=variable, width=11, relief="flat", bd=0,
            bg="#F8FAFC", fg=self.NAVY, font=("Segoe UI", 9),
        )
        entry.pack(side="left", padx=(7, 2), ipady=5)
        def refresh_custom() -> None:
            self.cash_range_var.set("Rango personalizado")
            self._refresh_cash(reset_page=True)

        open_calendar = lambda _event=None: self._show_date_picker(
            variable, entry, title, refresh_custom
        )
        entry.bind("<Double-Button-1>", open_calendar)
        entry.bind("<Return>", lambda _event: refresh_custom())
        tk.Button(
            holder, text="▦", command=open_calendar, relief="flat", bd=0,
            bg="#F8FAFC", fg=self.BLUE, activebackground="#DBEAFE",
            cursor="hand2", padx=5,
        ).pack(side="left")
        return entry

    def _apply_cash_period(self) -> None:
        today = dt.date.today()
        choice = self.cash_range_var.get()
        if choice == "Hoy":
            start = end = today
        elif choice == "Ayer":
            start = end = today - dt.timedelta(days=1)
        elif choice == "Últimos 7 días":
            start, end = today - dt.timedelta(days=6), today
        elif choice == "Mes anterior":
            end = today.replace(day=1) - dt.timedelta(days=1)
            start = end.replace(day=1)
        elif choice == "Rango personalizado":
            self.cash_custom_dates_holder.grid()
            self._refresh_cash(reset_page=True)
            return
        else:
            start, end = today.replace(day=1), today
        self.cash_custom_dates_holder.grid_remove()
        self.cash_start_var.set(start.isoformat())
        self.cash_end_var.set(end.isoformat())
        self._refresh_cash(reset_page=True)

    def _set_cash_method(self, value: str) -> None:
        self.cash_method_var.set(value)
        self._style_cash_method_buttons()
        self._refresh_cash(reset_page=True)

    def _style_cash_method_buttons(self) -> None:
        selected = self.cash_method_var.get()
        for value, button in getattr(self, "cash_method_buttons", {}).items():
            active = value == selected
            button.configure(
                bg="#DBEAFE" if active else "#F8FAFC",
                fg="#1D4ED8" if active else self.NAVY,
                activebackground="#DBEAFE",
                activeforeground="#1D4ED8",
                highlightbackground="#BFDBFE" if active else self.BORDER,
                highlightthickness=1,
            )

    def _cash_change_page(self, delta: int) -> None:
        movements = list(getattr(self, "_cash_snapshot", {}).get("movements") or [])
        pages = max(1, (len(movements) + self.cash_page_size - 1) // self.cash_page_size)
        self.cash_page = min(max(0, self.cash_page + delta), pages - 1)
        self._render_cash_movements(movements)

    def _cash_movement_dialog(self, kind: str) -> None:
        is_income = kind == "income"
        dialog = tk.Toplevel(self)
        dialog.title("Registrar ingreso" if is_income else "Registrar gasto")
        dialog.configure(bg=self.SURFACE)
        dialog.resizable(False, False)
        dialog.transient(self)
        values = {
            "date": tk.StringVar(value=dt.date.today().isoformat()),
            "concept": tk.StringVar(),
            "client": tk.StringVar(),
            "method": tk.StringVar(value="Efectivo"),
            "amount": tk.StringVar(),
            "court": tk.StringVar(),
            "category": tk.StringVar(value="Ingreso manual" if is_income else "Mantenimiento"),
            "related_id": tk.StringVar(),
            "notes": tk.StringVar(),
        }
        labels = (
            ("Fecha", "date"), ("Concepto", "concept"), ("Cliente / proveedor", "client"),
            ("Método", "method"), ("Importe", "amount"), ("Categoría", "category"),
            ("Cancha / área", "court"), ("Reserva relacionada (opcional)", "related_id"),
            ("Observaciones", "notes"),
        )
        for row_index, (label, key) in enumerate(labels):
            tk.Label(
                dialog, text=label, bg=self.SURFACE, fg=self.NAVY,
                font=("Segoe UI", 9, "bold"),
            ).grid(row=row_index, column=0, sticky="w", padx=16, pady=8)
            if key == "method":
                widget = ttk.Combobox(
                    dialog, textvariable=values[key],
                    values=("Efectivo", "Transferencia", "Otros"),
                    state="readonly", width=31,
                )
            elif key == "category":
                widget = ttk.Combobox(
                    dialog, textvariable=values[key],
                    values=(("Ingreso manual", "Ajuste", "Otros") if is_income else
                            ("Mantenimiento", "Servicios", "Personal", "Insumos", "Devolución", "Ajuste", "Otros")),
                    state="readonly", width=31,
                )
            else:
                widget = tk.Entry(dialog, textvariable=values[key], width=34)
            widget.grid(row=row_index, column=1, padx=(4, 8), pady=8, ipady=3)
            if key == "date":
                tk.Button(
                    dialog, text="▦", relief="flat", bg=self.BLUE, fg="white",
                    command=lambda anchor=widget: self._show_date_picker(
                        values["date"], anchor, "Fecha del movimiento"
                    ),
                ).grid(row=row_index, column=2, padx=(0, 14), pady=8)

        def save(allow_duplicate: bool = False) -> None:
            try:
                occurred = dt.datetime.combine(
                    dt.date.fromisoformat(values["date"].get().strip()),
                    dt.datetime.now().time().replace(microsecond=0),
                ).isoformat(timespec="seconds")
                self.service.add_cash_movement(
                    kind=kind,
                    occurred_at=occurred,
                    concept=values["concept"].get(),
                    client=values["client"].get(),
                    method=values["method"].get(),
                    amount=values["amount"].get(),
                    court=values["court"].get(),
                    related_id=values["related_id"].get(),
                    notes=values["notes"].get(),
                    category=values["category"].get(),
                    allow_duplicate=allow_duplicate,
                )
                dialog.destroy()
                self._refresh_cash(reset_page=True)
            except ValueError as exc:
                if str(exc).startswith("POSSIBLE_DUPLICATE:"):
                    if messagebox.askyesno(
                        "Posible duplicado",
                        f"{str(exc).split(':', 1)[1].strip()}\n\n¿Registrarlo igualmente?",
                        parent=dialog,
                    ):
                        save(True)
                    return
                messagebox.showerror("Caja", str(exc), parent=dialog)
            except Exception as exc:
                messagebox.showerror("Caja", str(exc), parent=dialog)

        self._action_button(
            dialog,
            "Registrar ingreso" if is_income else "Registrar gasto",
            save,
            self.GREEN if is_income else self.ORANGE,
        ).grid(row=len(labels), column=0, columnspan=3, pady=14)

    def _close_cash(self) -> None:
        try:
            day = self.cash_end_var.get().strip()
            preview = self.service.cash_close_preview(day)
        except Exception as exc:
            messagebox.showerror("Caja", str(exc), parent=self)
            return
        dialog = tk.Toplevel(self)
        dialog.title("Cerrar caja")
        dialog.configure(bg=self.SURFACE)
        dialog.resizable(False, False)
        dialog.transient(self)
        counted = tk.StringVar(value=str(preview.get("cash_expected", 0)))
        responsible = tk.StringVar(value="Administrador")
        notes = tk.StringVar()
        summary = (
            f"Fecha: {day}\n"
            f"Total cobrado: {self._money(preview.get('income'))}\n"
            f"Gastos: {self._money(preview.get('expenses'))}\n"
            f"Resultado: {self._money(preview.get('net'))}\n"
            f"Efectivo esperado: {self._money(preview.get('cash_expected'))}\n"
            f"Movimientos: {preview.get('movement_count', 0)}"
        )
        tk.Label(
            dialog, text=summary, justify="left", bg="#EFF6FF", fg=self.NAVY,
            font=("Segoe UI", 10), padx=16, pady=12,
        ).grid(row=0, column=0, columnspan=2, sticky="ew", padx=16, pady=14)
        fields = (("Efectivo contado", counted), ("Responsable", responsible), ("Observaciones", notes))
        for row, (label, variable) in enumerate(fields, start=1):
            tk.Label(dialog, text=label, bg=self.SURFACE, fg=self.NAVY, font=("Segoe UI", 9, "bold")).grid(
                row=row, column=0, sticky="w", padx=16, pady=7
            )
            tk.Entry(dialog, textvariable=variable, width=34).grid(row=row, column=1, padx=16, pady=7, ipady=3)

        def save_close() -> None:
            try:
                result = self.service.close_cash(
                    day, cash_counted=counted.get(), responsible=responsible.get(), notes=notes.get()
                )
                dialog.destroy()
                messagebox.showinfo(
                    "Caja cerrada",
                    f"Cierre auditable guardado.\nResultado: {self._money(result.get('balance'))}\n"
                    f"Diferencia de efectivo: {self._money(result.get('difference'))}",
                    parent=self,
                )
            except Exception as exc:
                messagebox.showerror("Caja", str(exc), parent=dialog)

        self._action_button(dialog, "Guardar cierre", save_close, self.NAVY).grid(
            row=4, column=0, columnspan=2, pady=14
        )

    def _export_cash(self) -> None:
        suggested = f"caja_{self.cash_start_var.get()}_{self.cash_end_var.get()}.csv"
        path = filedialog.asksaveasfilename(
            parent=self,
            title="Exportar movimientos de Caja",
            defaultextension=".csv",
            initialfile=suggested,
            filetypes=(("Archivo CSV", "*.csv"),),
        )
        if not path:
            return
        try:
            count = self.service.export_cash_csv(
                path,
                start_date=self.cash_start_var.get(),
                end_date=self.cash_end_var.get(),
                method=self.cash_method_var.get(),
            )
            messagebox.showinfo(
                "Caja", f"Se exportaron {count} movimientos.\n\n{path}", parent=self
            )
        except Exception as exc:
            messagebox.showerror("Caja", str(exc), parent=self)

    def _refresh_cash(self, reset_page: bool = False) -> None:
        if not hasattr(self, "cash_rows_frame"):
            return
        method = getattr(self.service, "cash_snapshot", None)
        if not callable(method):
            return
        snapshot = method(
            start_date=self.cash_start_var.get().strip(),
            end_date=self.cash_end_var.get().strip(),
            method=self.cash_method_var.get(),
        )
        self._cash_snapshot = dict(snapshot)
        self.cash_summary_vars["today"].set(self._money(snapshot.get("income_today")))
        self.cash_summary_vars["month"].set(self._money(snapshot.get("income_month")))
        self.cash_summary_vars["pending"].set(self._money(snapshot.get("pending_balances")))
        self.cash_summary_vars["future"].set(self._money(snapshot.get("future_reservations")))
        movements = list(snapshot.get("movements") or [])
        self.cash_history_var.set(str(snapshot.get("history_notice") or ""))
        self.cash_period_var.set(f"Saldo del período: {self._money(snapshot.get('period_balance'))}")
        if reset_page:
            self.cash_page = 0
        self._render_cash_movements(movements)
        self.after_idle(self._draw_cash_charts)

    def _render_cash_movements(self, movements: list[dict]) -> None:
        for child in self.cash_rows_frame.winfo_children():
            child.destroy()
        pages = max(1, (len(movements) + self.cash_page_size - 1) // self.cash_page_size)
        self.cash_page = min(self.cash_page, pages - 1)
        start = self.cash_page * self.cash_page_size
        visible = movements[start:start + self.cash_page_size]
        end = start + len(visible)
        self.cash_page_var.set(
            f"Mostrando {start + 1 if visible else 0} a {end} de {len(movements)} movimientos"
        )
        for child in self.cash_pager_buttons.winfo_children():
            child.destroy()
        self._cash_page_button("‹", max(0, self.cash_page - 1), enabled=self.cash_page > 0)
        first_page = max(0, min(self.cash_page - 1, pages - 3))
        for page in range(first_page, min(pages, first_page + 3)):
            self._cash_page_button(str(page + 1), page, selected=page == self.cash_page)
        self._cash_page_button("›", min(pages - 1, self.cash_page + 1), enabled=self.cash_page < pages - 1)
        if not visible:
            tk.Label(
                self.cash_rows_frame, text="Todavía no hay movimientos para este período.",
                bg=self.SURFACE, fg=self.MUTED, font=("Segoe UI", 10), pady=50,
            ).pack(fill="both", expand=True)
            return
        for index, row in enumerate(visible, start=start):
            moment = str(row.get("occurred_at") or "")
            try:
                moment = dt.datetime.fromisoformat(moment).strftime("%d/%m/%Y %H:%M")
            except ValueError:
                pass
            amount = int(row.get("amount") or 0)
            line = tk.Frame(
                self.cash_rows_frame, bg=self.SURFACE,
                height=32 if self._compact_height else 38,
                highlightbackground="#EEF2F7", highlightthickness=0,
            )
            line.pack(fill="x")
            line.pack_propagate(False)
            for column, weight in enumerate(self.cash_table_weights):
                line.grid_columnconfigure(column, weight=weight, uniform="cash-table")
            values = (
                moment, str(row.get("concept") or ""), str(row.get("client") or ""),
                str(row.get("method") or "Otros"), self._money(amount),
                str(row.get("status") or "Completado"),
            )
            for column, value in enumerate(values):
                if column == 3:
                    method_key = value.casefold()
                    badge_bg = "#DCFCE7" if "efectivo" in method_key else "#DBEAFE" if "transfer" in method_key else "#F3E8FF"
                    badge_fg = "#087A45" if "efectivo" in method_key else "#1565D8" if "transfer" in method_key else "#7C3AED"
                    holder = tk.Frame(line, bg=self.SURFACE)
                    holder.grid(
                        row=0, column=column, sticky="nsew", padx=6,
                        pady=3 if self._compact_height else 6,
                    )
                    tk.Label(
                        holder, text=value, bg=badge_bg, fg=badge_fg,
                        font=("Segoe UI", 8), padx=7, pady=1 if self._compact_height else 2,
                    ).pack(anchor="center")
                elif column == 5:
                    tk.Label(
                        line, text=value, bg="#DCFCE7", fg="#087A45",
                        font=("Segoe UI", 8), padx=7, pady=2,
                    ).grid(row=0, column=column, padx=8, pady=4 if self._compact_height else 7)
                else:
                    tk.Label(
                        line, text=value, bg=self.SURFACE,
                        fg=(self.GREEN if column == 4 and amount >= 0 else self.RED if column == 4 else "#475569"),
                        font=("Segoe UI", 9, "bold" if column == 4 else "normal"),
                        anchor="e" if column == 4 else "w",
                    ).grid(row=0, column=column, sticky="nsew", padx=10)
            tk.Frame(self.cash_rows_frame, bg="#E6EDF7", height=1).pack(fill="x")

    def _cash_page_button(
        self, text: str, page: int, *, selected: bool = False, enabled: bool = True
    ) -> None:
        tk.Button(
            self.cash_pager_buttons, text=text,
            command=lambda target=page: self._cash_go_to_page(target),
            state="normal" if enabled else "disabled",
            bg=self.BLUE if selected else self.SURFACE,
            fg="white" if selected else self.NAVY,
            disabledforeground="#94A3B8", activebackground="#DBEAFE",
            relief="flat", bd=0, highlightbackground=self.BORDER,
            highlightthickness=1, width=3, pady=5, cursor="hand2",
            font=("Segoe UI", 9, "bold" if selected else "normal"),
        ).pack(side="left", padx=2)

    def _cash_go_to_page(self, page: int) -> None:
        self.cash_page = max(0, page)
        self._render_cash_movements(list(self._cash_snapshot.get("movements") or []))

    def _draw_cash_charts(self) -> None:
        if not getattr(self, "cash_chart_canvases", None):
            return
        snapshot = getattr(self, "_cash_snapshot", {}) or {}
        self._draw_cash_daily_chart(
            self.cash_chart_canvases["daily"], snapshot.get("daily_income") or {}
        )
        method_values = dict(snapshot.get("method_income") or {})
        method_values["Otros"] = int(method_values.get("Otros", 0)) + int(method_values.pop("Mixto", 0))
        method_values = {
            key: int(method_values.get(key, 0))
            for key in ("Efectivo", "Transferencia", "Otros")
        }
        self._draw_cash_rank_chart(
            self.cash_chart_canvases["methods"], method_values,
            ("#079455", self.BLUE, "#7C3AED", self.ORANGE), percent=True,
        )
        self._draw_cash_rank_chart(
            self.cash_chart_canvases["courts"], snapshot.get("court_income") or {},
            (self.BLUE,), percent=False, limit=None,
            full_labels=True,
        )

    def _draw_cash_daily_chart(self, canvas: tk.Canvas, values: dict[str, int]) -> None:
        canvas.delete("all")
        canvas._cash_daily_bars = []
        canvas._cash_daily_tooltip_key = None
        canvas.bind(
            "<Motion>",
            lambda event: self._handle_cash_daily_motion(canvas, event.x, event.y),
        )
        canvas.bind(
            "<Leave>",
            lambda _event: self._hide_cash_daily_tooltip(canvas),
        )
        width, height = max(80, canvas.winfo_width()), max(55, canvas.winfo_height())
        items = sorted(values.items())[-7:]
        if not items:
            canvas.create_text(
                width / 2, height / 2, text="Sin ingresos en el período",
                fill=self.MUTED, font=("Segoe UI", 9),
            )
            return
        top = max(value for _key, value in items) or 1
        plot_left, plot_right, plot_top, plot_bottom = 42, width - 8, 8, height - 22
        for fraction in (0.0, 0.5, 1.0):
            y = plot_bottom - (plot_bottom - plot_top) * fraction
            canvas.create_line(plot_left, y, plot_right, y, fill="#E6EDF7")
            canvas.create_text(
                plot_left - 5, y, text=self._money(round(top * fraction)),
                anchor="e", fill="#64748B", font=("Segoe UI", 7),
            )
        gap = 7
        bar_width = max(8, (plot_right - plot_left - gap * (len(items) - 1)) / len(items))
        for index, (day, value) in enumerate(items):
            x1 = plot_left + index * (bar_width + gap)
            x2 = x1 + bar_width
            bar_height = max(3, (plot_bottom - plot_top) * value / top)
            canvas.create_rectangle(
                x1,
                plot_bottom - bar_height,
                x2,
                plot_bottom,
                fill=self.BLUE,
                outline="",
                tags=("cash-daily-bar",),
            )
            canvas._cash_daily_bars.append(
                (x1, plot_bottom - bar_height, x2, plot_bottom, day, value)
            )
            canvas.create_text((x1 + x2) / 2, height - 9, text=day[8:10], fill=self.MUTED, font=("Segoe UI", 8))

    def _handle_cash_daily_motion(
        self,
        canvas: tk.Canvas,
        mouse_x: float,
        mouse_y: float,
    ) -> None:
        hovered = next(
            (
                (day, amount)
                for x1, y1, x2, y2, day, amount
                in getattr(canvas, "_cash_daily_bars", ())
                if x1 <= mouse_x <= x2 and y1 <= mouse_y <= y2
            ),
            None,
        )
        if hovered is None:
            self._hide_cash_daily_tooltip(canvas)
            return
        day, amount = hovered
        tooltip_key = (str(day), int(amount))
        if getattr(canvas, "_cash_daily_tooltip_key", None) == tooltip_key:
            return
        self._show_cash_daily_tooltip(canvas, mouse_x, mouse_y, day, amount)

    def _show_cash_daily_tooltip(
        self,
        canvas: tk.Canvas,
        mouse_x: float,
        mouse_y: float,
        day: str,
        amount: int,
    ) -> None:
        canvas.delete("cash-daily-tooltip")
        try:
            label_day = dt.date.fromisoformat(day).strftime("%d/%m/%Y")
        except ValueError:
            label_day = str(day)
        label = f"{label_day}  ·  {self._money(amount)}"
        tooltip_x = min(max(70, mouse_x), max(70, canvas.winfo_width() - 70))
        tooltip_y = max(13, mouse_y - 18)
        text_id = canvas.create_text(
            tooltip_x,
            tooltip_y,
            text=label,
            fill="white",
            font=("Segoe UI", 8, "bold"),
            tags=("cash-daily-tooltip",),
        )
        bounds = canvas.bbox(text_id)
        if bounds:
            background_id = canvas.create_rectangle(
                bounds[0] - 7,
                bounds[1] - 4,
                bounds[2] + 7,
                bounds[3] + 4,
                fill=self.NAVY,
                outline="",
                tags=("cash-daily-tooltip",),
            )
            canvas.tag_lower(background_id, text_id)
        canvas.tag_raise(text_id)
        canvas._cash_daily_tooltip_key = (str(day), int(amount))

    @staticmethod
    def _hide_cash_daily_tooltip(canvas: tk.Canvas) -> None:
        if getattr(canvas, "_cash_daily_tooltip_key", None) is None:
            return
        canvas.delete("cash-daily-tooltip")
        canvas._cash_daily_tooltip_key = None

    def _draw_cash_rank_chart(
        self,
        canvas: tk.Canvas,
        values: dict[str, int],
        colors: tuple[str, ...],
        *,
        percent: bool,
        limit: int | None = 3,
        full_labels: bool = False,
    ) -> None:
        canvas.delete("all")
        width, height = max(120, canvas.winfo_width()), max(28, canvas.winfo_height())
        items = sorted(values.items(), key=lambda item: item[1], reverse=True)
        if limit is not None:
            items = items[:max(0, int(limit))]
        if not items:
            canvas.create_text(
                width / 2, height / 2, text="Sin datos en el período",
                fill=self.MUTED, font=("Segoe UI", 9),
            )
            return
        total = sum(value for _key, value in items) or 1
        maximum = max(value for _key, value in items) or 1
        row_height = max(10, min(27, (height - 3) / max(1, len(items))))
        bar_height = max(6, min(10, row_height - 3))
        chart_font = ("Segoe UI", 7 if row_height < 15 else 8)
        amount_font = ("Segoe UI", 7 if row_height < 15 else 8, "bold")
        label_width = (
            min(180, max(120, width * .38))
            if full_labels else min(135, max(78, width * .31))
        )
        amount_width = 88
        for index, (label, value) in enumerate(items):
            y = 2 + index * row_height
            color = colors[index % len(colors)]
            center_y = y + bar_height / 2
            canvas.create_text(
                2, center_y, text=label if full_labels else label[:16],
                anchor="w", fill=self.NAVY,
                font=chart_font,
            )
            bar_left, bar_right = label_width, max(label_width + 10, width - amount_width)
            canvas.create_rectangle(
                bar_left, y, bar_right, y + bar_height, fill="#E2E8F0", outline="",
            )
            canvas.create_rectangle(
                bar_left, y, bar_left + (bar_right - bar_left) * value / maximum,
                y + bar_height, fill=color, outline="",
            )
            suffix = f"{round(value * 100 / total)}%" if percent else self._money(value)
            canvas.create_text(
                width - 2, center_y, text=suffix, anchor="e", fill=self.NAVY,
                font=amount_font,
            )

    def _build_bar(self) -> None:
        """Build the Bar POS dashboard following the supplied visual reference."""
        self.bar_tab.configure(bg=self.BG)
        today = dt.date.today()
        self.bar_start_var = tk.StringVar(value=today.isoformat())
        self.bar_end_var = tk.StringVar(value=today.isoformat())
        self.bar_period_var = tk.StringVar(value="Hoy")
        self.bar_category_var = tk.StringVar(value="Todos")
        self.bar_summary_vars = {
            "sales": tk.StringVar(value="$ 0"),
            "active": tk.StringVar(value="0"),
            "low": tk.StringVar(value="0"),
        }
        self.bar_page = 0
        self.bar_page_size = 7 if self._compact_height else 9
        self._bar_snapshot: dict = {}
        self._bar_selected_order_id = ""

        self.bar_tab.grid_columnconfigure(0, weight=3, uniform="bar-main")
        self.bar_tab.grid_columnconfigure(1, weight=1, uniform="bar-main")
        self.bar_tab.grid_rowconfigure(2, weight=1)

        cards = tk.Frame(self.bar_tab, bg=self.BG)
        cards.grid(row=0, column=0, sticky="nsew", padx=(14, 5), pady=(9, 6))
        specs = (
            ("sales", "Ventas de hoy", "$", self.GREEN, "#DDF9EC"),
            ("active", "Pedidos activos", "▤", self.BLUE, "#E8F1FF"),
            ("low", "Productos bajos", "◇", self.ORANGE, "#FFF3E6"),
        )
        for column, (key, title, icon, color, icon_bg) in enumerate(specs):
            cards.grid_columnconfigure(column, weight=1, uniform="bar-card")
            card = tk.Frame(
                cards, bg=self.SURFACE, highlightbackground=self.BORDER,
                highlightthickness=1, height=86 if self._compact_height else 104,
            )
            card.grid(row=0, column=column, sticky="nsew", padx=4)
            card.grid_propagate(False)
            icon_holder = tk.Frame(
                card, bg=icon_bg, width=52 if self._compact_height else 62,
                height=52 if self._compact_height else 62,
            )
            icon_holder.pack(side="left", padx=(15, 12), pady=16 if self._compact_height else 20)
            icon_holder.pack_propagate(False)
            tk.Label(
                icon_holder, text=icon, bg=icon_bg, fg=color,
                font=("Segoe UI Symbol", 21, "bold"),
            ).pack(expand=True)
            value_area = tk.Frame(card, bg=self.SURFACE)
            value_area.pack(side="left", fill="y", pady=11 if self._compact_height else 17)
            tk.Label(
                value_area, textvariable=self.bar_summary_vars[key], bg=self.SURFACE,
                fg=color if key != "active" else self.BLUE,
                font=("Segoe UI", 19 if self._compact_height else 22, "bold"), anchor="w",
            ).pack(anchor="w")
            tk.Label(
                value_area, text=title, bg=self.SURFACE, fg=self.MUTED,
                font=("Segoe UI", 9), anchor="w",
            ).pack(anchor="w", pady=(2, 0))

        top_panel = self._bar_panel(self.bar_tab, "▥  Top productos", "Ver todos", self._show_bar_ranking)
        top_panel.grid(row=0, column=1, sticky="nsew", padx=(5, 14), pady=(9, 6))
        self.bar_top_rows = tk.Frame(top_panel, bg=self.SURFACE)
        self.bar_top_rows.pack(fill="both", expand=True, padx=13, pady=(1, 10))

        toolbar = tk.Frame(
            self.bar_tab, bg=self.SURFACE, highlightbackground=self.BORDER, highlightthickness=1,
        )
        toolbar.grid(row=1, column=0, sticky="ew", padx=(14, 5), pady=(0, 6))
        toolbar.grid_columnconfigure(0, weight=1)
        filters = tk.Frame(toolbar, bg=self.SURFACE)
        filters.grid(row=0, column=0, sticky="w", padx=12, pady=8)
        tk.Label(filters, text="Turno:", bg=self.SURFACE, fg=self.NAVY, font=("Segoe UI", 9, "bold")).pack(side="left", padx=(0, 7))
        period = ttk.Combobox(
            filters, textvariable=self.bar_period_var, state="readonly", width=17,
            values=("Hoy", "Ayer", "Últimos 7 días", "Mes actual", "Período personalizado"),
            font=("Segoe UI", 9),
        )
        period.pack(side="left", padx=(0, 16), ipady=5)
        period.bind("<<ComboboxSelected>>", lambda _event: self._apply_bar_period())
        tk.Frame(filters, bg=self.BORDER, width=1, height=28).pack(side="left", padx=(0, 14))
        tk.Label(filters, text="Categoría:", bg=self.SURFACE, fg=self.NAVY, font=("Segoe UI", 9, "bold")).pack(side="left", padx=(0, 7))
        self.bar_category_buttons: dict[str, tk.Button] = {}
        for category in ("Todos", "Bebidas", "Comidas", "Snacks"):
            button = tk.Button(
                filters, text=category, command=lambda value=category: self._set_bar_category(value),
                relief="flat", bd=0, padx=8, pady=7, cursor="hand2",
                font=("Segoe UI", 8, "bold" if category == "Todos" else "normal"),
            )
            button.pack(side="left", padx=2)
            self.bar_category_buttons[category] = button
        self._style_bar_categories()

        actions = tk.Frame(toolbar, bg=self.SURFACE)
        actions.grid(row=0, column=1, sticky="e", padx=(6, 10), pady=6)
        for text, command, color, hover, width in (
            ("⊕  Nuevo pedido", self._new_bar_order_dialog, self.BLUE, "#0F62E8", 112),
            ("▣  Cobrar pedido", self._choose_bar_payment, "#079455", "#067442", 120),
            ("▣  Registrar gasto", self._bar_expense_dialog, self.ORANGE, "#EA650C", 125),
        ):
            BarButton(actions, text, command, color=color, hover=hover, width=width, height=38).pack(side="left", padx=3)

        category_panel = self._bar_panel(self.bar_tab, "◔  Ventas por categoría", "Ver detalle", self._show_bar_categories)
        category_panel.grid(row=1, column=1, sticky="nsew", padx=(5, 14), pady=(0, 6))
        self.bar_category_rows = tk.Frame(category_panel, bg=self.SURFACE)
        self.bar_category_rows.pack(fill="both", expand=True, padx=13, pady=(1, 9))

        orders_panel = tk.Frame(self.bar_tab, bg=self.SURFACE, highlightbackground=self.BORDER, highlightthickness=1)
        orders_panel.grid(row=2, column=0, sticky="nsew", padx=(14, 5), pady=(0, 12))
        tk.Label(orders_panel, text="Pedidos del bar", bg=self.SURFACE, fg=self.NAVY, font=("Segoe UI", 12, "bold"), anchor="w").pack(fill="x", padx=14, pady=(9, 6))
        header = tk.Frame(orders_panel, bg="#F1F5F9", height=34)
        header.pack(fill="x", padx=12)
        header.pack_propagate(False)
        self.bar_table_weights = (9, 27, 19, 17, 13, 13, 7)
        for index, weight in enumerate(self.bar_table_weights):
            header.grid_columnconfigure(index, weight=weight, uniform="bar-table")
        for index, title in enumerate(("Hora", "Pedido", "Cliente / Mesa", "Estado", "Total", "Pago", "Acciones")):
            tk.Label(
                header, text=title, bg="#F1F5F9", fg=self.NAVY,
                font=("Segoe UI", 8, "bold"), anchor="w" if index not in {0, 4, 6} else "center",
            ).grid(row=0, column=index, sticky="nsew", padx=6)
        self.bar_rows_frame = tk.Frame(orders_panel, bg=self.SURFACE)
        self.bar_rows_frame.pack(fill="both", expand=True, padx=12)
        self.bar_rows_frame.bind("<MouseWheel>", self._bar_mousewheel)
        footer = tk.Frame(orders_panel, bg="#F5F8FE")
        footer.pack(fill="x", padx=12, pady=(3, 9))
        self.bar_pager = tk.Frame(footer, bg="#F5F8FE")
        self.bar_pager.pack(side="right", padx=8, pady=5)
        self.bar_page_var = tk.StringVar(value="Sin pedidos en el período")
        tk.Label(footer, textvariable=self.bar_page_var, bg="#F5F8FE", fg=self.MUTED, font=("Segoe UI", 8)).pack(side="left", padx=10, pady=7)

        inventory_panel = self._bar_panel(self.bar_tab, "▲  Stock crítico / Inventario", "Ver inventario", self._show_bar_inventory)
        inventory_panel.grid(row=2, column=1, sticky="nsew", padx=(5, 14), pady=(0, 12))
        stock_actions = tk.Frame(inventory_panel, bg=self.SURFACE)
        stock_actions.pack(fill="x", padx=10, pady=(0, 7))
        for text, operation, color, width in (("＋ Stock", "add", self.GREEN, 76), ("− Stock", "remove", self.ORANGE, 76)):
            BarButton(
                stock_actions, text, lambda op=operation: self._bar_stock_dialog(op),
                color=color, width=width, height=36, font=("Segoe UI", 8, "bold"),
            ).pack(side="left", padx=2)
        BarButton(
            stock_actions, "＋ Nuevo producto", self._bar_product_dialog,
            color=self.BLUE, width=116, height=36, font=("Segoe UI", 7, "bold"),
        ).pack(side="left", padx=2)
        self.bar_inventory_rows = tk.Frame(inventory_panel, bg=self.SURFACE)
        self.bar_inventory_rows.pack(fill="both", expand=True, padx=13, pady=(0, 9))

    def _bar_panel(self, parent: tk.Widget, title: str, link: str, command) -> tk.Frame:
        panel = tk.Frame(parent, bg=self.SURFACE, highlightbackground=self.BORDER, highlightthickness=1)
        heading = tk.Frame(panel, bg=self.SURFACE)
        heading.pack(fill="x", padx=12, pady=(8, 4))
        tk.Label(heading, text=title, bg=self.SURFACE, fg=self.NAVY, font=("Segoe UI", 10, "bold"), anchor="w").pack(side="left")
        tk.Button(
            heading, text=link, command=command, bg=self.SURFACE, fg=self.BLUE,
            activebackground=self.SURFACE, activeforeground="#0F62E8", relief="flat", bd=0,
            cursor="hand2", font=("Segoe UI", 8),
        ).pack(side="right")
        return panel

    def _apply_bar_period(self) -> None:
        today = dt.date.today()
        choice = self.bar_period_var.get()
        if choice == "Hoy":
            start = end = today
        elif choice == "Ayer":
            start = end = today - dt.timedelta(days=1)
        elif choice == "Últimos 7 días":
            start, end = today - dt.timedelta(days=6), today
        elif choice == "Mes actual":
            start, end = today.replace(day=1), today
        else:
            start_text = simpledialog.askstring("Período personalizado", "Fecha desde (AAAA-MM-DD):", initialvalue=self.bar_start_var.get(), parent=self)
            if not start_text:
                self.bar_period_var.set("Hoy")
                return
            end_text = simpledialog.askstring("Período personalizado", "Fecha hasta (AAAA-MM-DD):", initialvalue=self.bar_end_var.get(), parent=self)
            if not end_text:
                self.bar_period_var.set("Hoy")
                return
            try:
                start, end = dt.date.fromisoformat(start_text), dt.date.fromisoformat(end_text)
                if end < start:
                    raise ValueError
            except ValueError:
                messagebox.showerror("Bar", "Ingresá un período válido.", parent=self)
                self.bar_period_var.set("Hoy")
                return
        self.bar_start_var.set(start.isoformat())
        self.bar_end_var.set(end.isoformat())
        self._refresh_bar(reset_page=True)

    def _set_bar_category(self, value: str) -> None:
        self.bar_category_var.set(value)
        self._style_bar_categories()
        self._refresh_bar(reset_page=True)

    def _style_bar_categories(self) -> None:
        selected = self.bar_category_var.get()
        for value, button in getattr(self, "bar_category_buttons", {}).items():
            active = value == selected
            button.configure(
                bg=self.BLUE if active else "#F3F6FB", fg="white" if active else self.NAVY,
                activebackground=self.BLUE if active else "#DBEAFE",
                activeforeground="white" if active else self.BLUE,
            )

    def _refresh_bar(self, reset_page: bool = False) -> None:
        if not hasattr(self, "bar_rows_frame"):
            return
        method = getattr(self.service, "bar_snapshot", None)
        if not callable(method):
            return
        snapshot = method(
            start_date=self.bar_start_var.get(), end_date=self.bar_end_var.get(),
            category=self.bar_category_var.get(),
        )
        self._bar_snapshot = dict(snapshot)
        self.bar_summary_vars["sales"].set(self._money(snapshot.get("sales_today")))
        self.bar_summary_vars["active"].set(str(snapshot.get("active_orders", 0)))
        self.bar_summary_vars["low"].set(str(snapshot.get("low_products_count", 0)))
        if reset_page:
            self.bar_page = 0
        self._render_bar_orders(list(snapshot.get("orders") or []))
        self._render_bar_top(list(snapshot.get("top_products") or []))
        self._render_bar_categories(list(snapshot.get("category_sales") or []))
        self._render_bar_inventory(list(snapshot.get("critical_stock") or []))

    def _render_bar_top(self, rows: list[dict]) -> None:
        for child in self.bar_top_rows.winfo_children():
            child.destroy()
        if not rows:
            tk.Label(
                self.bar_top_rows, text="Sin ventas confirmadas en el período",
                bg=self.SURFACE, fg=self.MUTED, font=("Segoe UI", 8),
            ).pack(expand=True)
            return
        maximum = max(int(row.get("quantity") or 0) for row in rows[:5]) or 1
        for row in rows[:5]:
            line = tk.Frame(self.bar_top_rows, bg=self.SURFACE)
            line.pack(fill="x", pady=2)
            tk.Label(
                line, text=str(row.get("name") or "")[:18], bg=self.SURFACE,
                fg=self.NAVY, font=("Segoe UI", 8), width=15, anchor="w",
            ).pack(side="left")
            canvas = tk.Canvas(line, bg=self.SURFACE, height=12, highlightthickness=0)
            canvas.pack(side="left", fill="x", expand=True, padx=5)
            quantity = int(row.get("quantity") or 0)

            def draw(event, widget=canvas, value=quantity, top=maximum):
                widget.delete("all")
                width = max(10, event.width)
                widget.create_rectangle(0, 2, width, 10, fill="#E7ECF4", outline="")
                widget.create_rectangle(0, 2, width * value / top, 10, fill=self.BLUE, outline="")

            canvas.bind("<Configure>", draw)
            tk.Label(
                line, text=str(quantity), bg=self.SURFACE, fg=self.NAVY,
                font=("Segoe UI", 8), width=4, anchor="e",
            ).pack(side="right")

    def _render_bar_categories(self, rows: list[dict]) -> None:
        for child in self.bar_category_rows.winfo_children():
            child.destroy()
        if not rows:
            tk.Label(
                self.bar_category_rows, text="Sin cobros para calcular categorías",
                bg=self.SURFACE, fg=self.MUTED, font=("Segoe UI", 8),
            ).pack(expand=True)
            return
        for row in rows[:5]:
            line = tk.Frame(self.bar_category_rows, bg=self.SURFACE)
            line.pack(fill="x", pady=2)
            tk.Label(
                line, text=str(row.get("name") or "")[:16], bg=self.SURFACE,
                fg=self.NAVY, font=("Segoe UI", 8), width=13, anchor="w",
            ).pack(side="left")
            canvas = tk.Canvas(line, bg=self.SURFACE, height=12, highlightthickness=0)
            canvas.pack(side="left", fill="x", expand=True, padx=5)
            percent = float(row.get("percent") or 0)

            def draw(event, widget=canvas, value=percent):
                widget.delete("all")
                width = max(10, event.width)
                widget.create_rectangle(0, 2, width, 10, fill="#E7ECF4", outline="")
                widget.create_rectangle(0, 2, width * value / 100, 10, fill=self.BLUE, outline="")

            canvas.bind("<Configure>", draw)
            tk.Label(
                line, text=f"{percent:g}%", bg=self.SURFACE, fg=self.NAVY,
                font=("Segoe UI", 8), width=5, anchor="e",
            ).pack(side="right")

    def _render_bar_inventory(self, rows: list[dict]) -> None:
        for child in self.bar_inventory_rows.winfo_children():
            child.destroy()
        if not rows:
            tk.Label(
                self.bar_inventory_rows, text="No hay productos registrados",
                bg=self.SURFACE, fg=self.MUTED, font=("Segoe UI", 8),
            ).pack(expand=True)
            return
        visible = [row for row in rows if row.get("stock_level") != "ok"] or rows
        colors = {"critical": self.RED, "low": self.ORANGE, "ok": self.GREEN}
        for row in visible[:8 if not self._compact_height else 6]:
            line = tk.Frame(self.bar_inventory_rows, bg=self.SURFACE)
            line.pack(fill="x", pady=3)
            color = colors.get(str(row.get("stock_level")), self.GREEN)
            dot = tk.Canvas(line, width=12, height=12, bg=self.SURFACE, highlightthickness=0)
            dot.pack(side="left", padx=(1, 8))
            dot.create_oval(1, 1, 11, 11, fill=color, outline=color)
            tk.Label(
                line, text=str(row.get("name") or "")[:22], bg=self.SURFACE,
                fg=self.NAVY, font=("Segoe UI", 8), anchor="w",
            ).pack(side="left", fill="x", expand=True)
            tk.Label(
                line, text=f"{row.get('stock', 0)} {row.get('unit', 'unidades')}",
                bg=self.SURFACE, fg=color, font=("Segoe UI", 8, "bold"), anchor="e",
            ).pack(side="right")

    def _render_bar_orders(self, orders: list[dict]) -> None:
        for child in self.bar_rows_frame.winfo_children():
            child.destroy()
        for child in self.bar_pager.winfo_children():
            child.destroy()
        pages = max(1, (len(orders) + self.bar_page_size - 1) // self.bar_page_size)
        self.bar_page = min(self.bar_page, pages - 1)
        start = self.bar_page * self.bar_page_size
        visible = orders[start:start + self.bar_page_size]
        end = start + len(visible)
        period = f"{self.bar_start_var.get()} a {self.bar_end_var.get()}"
        self.bar_page_var.set(f"{period} · Mostrando {start + 1 if visible else 0} a {end} de {len(orders)} pedidos")
        self._bar_page_button("‹", self.bar_page - 1, self.bar_page > 0)
        for page in range(max(0, self.bar_page - 1), min(pages, max(0, self.bar_page - 1) + 3)):
            self._bar_page_button(str(page + 1), page, True, selected=page == self.bar_page)
        self._bar_page_button("›", self.bar_page + 1, self.bar_page < pages - 1)
        if not visible:
            tk.Label(
                self.bar_rows_frame, text="Todavía no hay pedidos del bar para este período.",
                bg=self.SURFACE, fg=self.MUTED, font=("Segoe UI", 9), pady=45,
            ).pack(fill="both", expand=True)
            return
        delivery_colors = {
            "open": ("#DBEAFE", "#0B68E8"), "preparing": ("#FFEDD5", "#C65100"),
            "delivered": ("#DCFCE7", "#07864C"), "cancelled": ("#FEE2E2", "#DC2626"),
        }
        payment_colors = {
            "pending": ("#F1F5F9", self.MUTED), "partial": ("#FEF3C7", "#B45309"),
            "paid": ("#DCFCE7", "#07864C"), "refunded": ("#FEE2E2", "#DC2626"),
        }
        for row in visible:
            line = tk.Frame(self.bar_rows_frame, bg=self.SURFACE, height=37)
            line.pack(fill="x")
            line.pack_propagate(False)
            for index, weight in enumerate(self.bar_table_weights):
                line.grid_columnconfigure(index, weight=weight, uniform="bar-table")
            try:
                hour = dt.datetime.fromisoformat(str(row.get("created_at"))).strftime("%H:%M")
            except ValueError:
                hour = "--:--"
            for column, value in enumerate((hour, str(row.get("summary") or "")[:36], str(row.get("display_location") or "")[:24])):
                tk.Label(
                    line, text=value, bg=self.SURFACE, fg=self.NAVY,
                    font=("Segoe UI", 8, "bold" if column == 0 else "normal"),
                    anchor="center" if column == 0 else "w",
                ).grid(row=0, column=column, sticky="nsew", padx=6)
            delivery_bg, delivery_fg = delivery_colors.get(row.get("delivery_status"), ("#F1F5F9", self.NAVY))
            holder = tk.Frame(line, bg=self.SURFACE)
            holder.grid(row=0, column=3, sticky="nsew", padx=4, pady=6)
            tk.Label(
                holder, text=row.get("delivery_label"), bg=delivery_bg, fg=delivery_fg,
                font=("Segoe UI", 7, "bold"), padx=7, pady=2,
            ).pack(expand=True, fill="x")
            tk.Label(
                line, text=self._money(row.get("total")), bg=self.SURFACE, fg=self.NAVY,
                font=("Segoe UI", 8, "bold"), anchor="e",
            ).grid(row=0, column=4, sticky="nsew", padx=6)
            pay_bg, pay_fg = payment_colors.get(row.get("payment_status"), ("#F1F5F9", self.MUTED))
            pay_holder = tk.Frame(line, bg=self.SURFACE)
            pay_holder.grid(row=0, column=5, sticky="nsew", padx=4, pady=6)
            tk.Label(
                pay_holder, text=row.get("payment_label"), bg=pay_bg, fg=pay_fg,
                font=("Segoe UI", 7, "bold"), padx=5, pady=2,
            ).pack(expand=True, fill="x")
            tk.Button(
                line, text="•••", command=lambda item=row: self._bar_order_menu(item),
                bg=self.SURFACE, fg=self.NAVY, activebackground="#DBEAFE", relief="flat",
                bd=0, cursor="hand2", font=("Segoe UI", 9, "bold"),
            ).grid(row=0, column=6, sticky="nsew", padx=4)
            tk.Frame(self.bar_rows_frame, bg="#E6EDF7", height=1).pack(fill="x")

    def _bar_page_button(self, text: str, page: int, enabled: bool, *, selected: bool = False) -> None:
        tk.Button(
            self.bar_pager, text=text, command=lambda target=page: self._bar_go_page(target),
            state="normal" if enabled else "disabled", width=3, pady=3, relief="flat", bd=0,
            bg=self.BLUE if selected else self.SURFACE, fg="white" if selected else self.NAVY,
            disabledforeground="#94A3B8", cursor="hand2", font=("Segoe UI", 8, "bold"),
        ).pack(side="left", padx=1)

    def _bar_go_page(self, page: int) -> None:
        total = len(self._bar_snapshot.get("orders") or [])
        pages = max(1, (total + self.bar_page_size - 1) // self.bar_page_size)
        self.bar_page = min(max(0, page), pages - 1)
        self._render_bar_orders(list(self._bar_snapshot.get("orders") or []))

    def _bar_mousewheel(self, event) -> str:
        self._bar_go_page(self.bar_page + (-1 if event.delta > 0 else 1))
        return "break"

    def _bar_product_dialog(self, product: dict | None = None) -> None:
        edit = product is not None
        dialog = tk.Toplevel(self)
        dialog.title("Editar producto" if edit else "Nuevo producto")
        dialog.configure(bg=self.SURFACE)
        dialog.resizable(False, False)
        dialog.transient(self)
        categories_method = getattr(self.service, "bar_categories", None)
        category_names = [row.get("name", "") for row in categories_method()] if callable(categories_method) else []
        product = dict(product or {})
        values = {
            "name": tk.StringVar(value=str(product.get("name") or "")),
            "category": tk.StringVar(value=str(product.get("category") or (category_names[0] if category_names else "Bebidas"))),
            "sale_price": tk.StringVar(value=str(product.get("sale_price") or "")),
            "cost_price": tk.StringVar(value="" if product.get("cost_price") is None else str(product.get("cost_price"))),
            "stock": tk.StringVar(value=str(product.get("stock") or 0)),
            "minimum_stock": tk.StringVar(value=str(product.get("minimum_stock") or 0)),
            "unit": tk.StringVar(value=str(product.get("unit") or "unidad")),
            "active": tk.BooleanVar(value=bool(product.get("active", True))),
        }
        tk.Label(
            dialog, text="Producto del Bar", bg=self.SURFACE, fg=self.NAVY,
            font=("Segoe UI", 15, "bold"),
        ).grid(row=0, column=0, columnspan=2, sticky="w", padx=18, pady=(16, 8))
        fields = (
            ("Nombre", "name"), ("Categoría", "category"),
            ("Precio de venta", "sale_price"), ("Precio de costo (opcional)", "cost_price"),
            ("Stock actual", "stock"), ("Stock mínimo", "minimum_stock"),
            ("Unidad de medida", "unit"),
        )
        for index, (label, key) in enumerate(fields, start=1):
            tk.Label(dialog, text=label, bg=self.SURFACE, fg=self.NAVY, font=("Segoe UI", 9, "bold")).grid(
                row=index, column=0, sticky="w", padx=18, pady=7
            )
            if key == "category":
                widget = ttk.Combobox(dialog, textvariable=values[key], values=category_names, width=31)
            else:
                widget = tk.Entry(dialog, textvariable=values[key], width=34)
            if edit and key == "stock":
                widget.configure(state="disabled")
            widget.grid(row=index, column=1, sticky="ew", padx=(4, 18), pady=7, ipady=3)
        tk.Checkbutton(
            dialog, text="Producto activo", variable=values["active"], bg=self.SURFACE,
            activebackground=self.SURFACE, fg=self.NAVY, font=("Segoe UI", 9),
        ).grid(row=8, column=0, columnspan=2, sticky="w", padx=16, pady=6)

        def save() -> None:
            try:
                payload = {
                    "name": values["name"].get(), "category": values["category"].get(),
                    "sale_price": values["sale_price"].get(), "cost_price": values["cost_price"].get(),
                    "minimum_stock": values["minimum_stock"].get(), "unit": values["unit"].get(),
                    "active": values["active"].get(),
                }
                if edit:
                    self.service.update_bar_product(product["product_id"], **payload)
                else:
                    self.service.create_bar_product(
                        **payload, stock=values["stock"].get(), responsible="Administrador"
                    )
                dialog.destroy()
                self._refresh_bar()
            except Exception as exc:
                messagebox.showerror("Producto", str(exc), parent=dialog)

        BarButton(
            dialog, "Guardar producto", save, color=self.BLUE, width=160, height=40,
        ).grid(row=9, column=0, columnspan=2, pady=(8, 16))

    def _bar_stock_dialog(self, operation: str, product: dict | None = None) -> None:
        products_method = getattr(self.service, "bar_products", None)
        products = products_method(include_inactive=True) if callable(products_method) else []
        if not products:
            messagebox.showinfo("Inventario", "Primero registrá un producto.", parent=self)
            self._bar_product_dialog()
            return
        dialog = tk.Toplevel(self)
        dialog.title("Agregar stock" if operation == "add" else "Descontar stock")
        dialog.configure(bg=self.SURFACE)
        dialog.resizable(False, False)
        dialog.transient(self)
        labels = {f"{row['name']} · actual {row['stock']} {row['unit']}": row for row in products}
        initial = next((label for label, row in labels.items() if product and row["product_id"] == product.get("product_id")), next(iter(labels)))
        selected = tk.StringVar(value=initial)
        quantity = tk.StringVar(value="1")
        reason = tk.StringVar(value="Recepción de mercadería" if operation == "add" else "Ajuste de inventario")
        responsible = tk.StringVar(value="Administrador")
        tk.Label(dialog, text="Movimiento de inventario", bg=self.SURFACE, fg=self.NAVY, font=("Segoe UI", 14, "bold")).grid(
            row=0, column=0, columnspan=2, sticky="w", padx=18, pady=(16, 10)
        )
        for index, (label, variable) in enumerate((
            ("Producto", selected), ("Cantidad", quantity), ("Motivo", reason), ("Responsable", responsible)
        ), start=1):
            tk.Label(dialog, text=label, bg=self.SURFACE, fg=self.NAVY, font=("Segoe UI", 9, "bold")).grid(
                row=index, column=0, sticky="w", padx=18, pady=8
            )
            widget = ttk.Combobox(dialog, textvariable=variable, values=tuple(labels), state="readonly", width=39) if label == "Producto" else tk.Entry(dialog, textvariable=variable, width=42)
            widget.grid(row=index, column=1, padx=(4, 18), pady=8, ipady=3)

        def save() -> None:
            try:
                target = labels[selected.get()]
                self.service.adjust_bar_stock(
                    product_id=target["product_id"], quantity=quantity.get(), operation=operation,
                    reason=reason.get(), responsible=responsible.get(),
                )
                dialog.destroy()
                self._refresh_bar()
            except Exception as exc:
                messagebox.showerror("Inventario", str(exc), parent=dialog)

        BarButton(
            dialog, "＋ Confirmar stock" if operation == "add" else "− Confirmar descuento",
            save, color=self.GREEN if operation == "add" else self.ORANGE, width=190, height=40,
        ).grid(row=5, column=0, columnspan=2, pady=(8, 16))

    def _new_bar_order_dialog(self, order: dict | None = None) -> None:
        edit = order is not None
        products_method = getattr(self.service, "bar_products", None)
        products = products_method() if callable(products_method) else []
        if not products:
            messagebox.showinfo("Nuevo pedido", "Registrá al menos un producto activo antes de crear pedidos.", parent=self)
            self._bar_product_dialog()
            return
        order = dict(order or {})
        dialog = tk.Toplevel(self)
        dialog.title("Editar pedido" if edit else "Nuevo pedido")
        dialog.configure(bg=self.SURFACE)
        dialog.geometry("720x650")
        dialog.minsize(650, 560)
        dialog.transient(self)
        dialog.grid_columnconfigure(0, weight=1)
        dialog.grid_rowconfigure(2, weight=1)
        tk.Label(
            dialog, text="Editar pedido" if edit else "Nuevo pedido del Bar",
            bg=self.SURFACE, fg=self.NAVY, font=("Segoe UI", 16, "bold"), anchor="w",
        ).grid(row=0, column=0, sticky="ew", padx=20, pady=(16, 8))

        details = tk.Frame(dialog, bg="#F8FAFC", highlightbackground=self.BORDER, highlightthickness=1)
        details.grid(row=1, column=0, sticky="ew", padx=20, pady=(0, 10))
        client = tk.StringVar(value=str(order.get("client") or ""))
        origin = tk.StringVar(value=str(order.get("origin") or "Mostrador"))
        location = tk.StringVar(value=str(order.get("location") or ""))
        notes = tk.StringVar(value=str(order.get("notes") or ""))
        for column in range(4):
            details.grid_columnconfigure(column, weight=1)
        for column, (label, variable) in enumerate((("Cliente", client), ("Origen", origin), ("Cancha / Mesa", location), ("Observaciones", notes))):
            tk.Label(details, text=label, bg="#F8FAFC", fg=self.NAVY, font=("Segoe UI", 8, "bold")).grid(
                row=0, column=column, sticky="w", padx=8, pady=(8, 3)
            )
            if label == "Origen":
                widget = ttk.Combobox(details, textvariable=variable, values=("Cancha", "Mesa", "Mostrador"), state="readonly", width=16)
            elif label == "Cancha / Mesa":
                widget = ttk.Combobox(details, textvariable=variable, width=17)
            else:
                widget = tk.Entry(details, textvariable=variable, width=20)
            widget.grid(row=1, column=column, sticky="ew", padx=8, pady=(0, 9), ipady=3)
            if label == "Cancha / Mesa":
                location_widget = widget

        def update_locations(*_args) -> None:
            if origin.get() == "Cancha":
                courts = tuple(getattr(self.service, "courts", lambda: [])())
                location_widget.configure(values=courts, state="readonly")
                if location.get() not in courts:
                    location.set(courts[0] if courts else "")
            else:
                location_widget.configure(values=(), state="normal")
                if origin.get() == "Mostrador" and not location.get():
                    location.set("Mostrador")

        origin.trace_add("write", update_locations)
        update_locations()

        product_box = tk.Frame(dialog, bg=self.SURFACE, highlightbackground=self.BORDER, highlightthickness=1)
        product_box.grid(row=2, column=0, sticky="nsew", padx=20)
        product_box.grid_columnconfigure(1, weight=1)
        tk.Label(product_box, text="Producto", bg="#F1F5F9", fg=self.NAVY, font=("Segoe UI", 9, "bold"), anchor="w").grid(row=0, column=0, columnspan=2, sticky="ew", padx=1, pady=1)
        tk.Label(product_box, text="Precio", bg="#F1F5F9", fg=self.NAVY, font=("Segoe UI", 9, "bold")).grid(row=0, column=2, sticky="ew")
        tk.Label(product_box, text="Cantidad", bg="#F1F5F9", fg=self.NAVY, font=("Segoe UI", 9, "bold")).grid(row=0, column=3, sticky="ew", padx=(0, 8))
        existing = {item["product_id"]: int(item["quantity"]) for item in order.get("items", [])}
        quantities: dict[str, tk.IntVar] = {}
        total_var = tk.StringVar(value="$ 0")

        def update_total(*_args) -> None:
            total = 0
            for product in products:
                try:
                    quantity = max(0, int(quantities[product["product_id"]].get()))
                except (tk.TclError, ValueError):
                    quantity = 0
                total += int(product.get("sale_price") or 0) * quantity
            total_var.set(self._money(total))

        for index, product in enumerate(products, start=1):
            variable = tk.IntVar(value=existing.get(product["product_id"], 0))
            quantities[product["product_id"]] = variable
            variable.trace_add("write", update_total)
            color = self.RED if product.get("stock_level") == "critical" else self.ORANGE if product.get("stock_level") == "low" else self.GREEN
            dot = tk.Canvas(product_box, width=12, height=12, bg=self.SURFACE, highlightthickness=0)
            dot.grid(row=index, column=0, padx=(9, 5), pady=6)
            dot.create_oval(1, 1, 11, 11, fill=color, outline=color)
            tk.Label(
                product_box, text=f"{product['name']}  · stock {product['stock']} {product['unit']}",
                bg=self.SURFACE, fg=self.NAVY, font=("Segoe UI", 9), anchor="w",
            ).grid(row=index, column=1, sticky="ew", pady=5)
            tk.Label(product_box, text=self._money(product["sale_price"]), bg=self.SURFACE, fg=self.NAVY, font=("Segoe UI", 9, "bold")).grid(row=index, column=2, padx=12)
            tk.Spinbox(product_box, from_=0, to=max(0, int(product["stock"])), textvariable=variable, width=6, command=update_total).grid(row=index, column=3, padx=(0, 10), pady=4, ipady=2)
        update_total()

        bottom = tk.Frame(dialog, bg=self.SURFACE)
        bottom.grid(row=3, column=0, sticky="ew", padx=20, pady=14)
        tk.Label(bottom, text="Total", bg=self.SURFACE, fg=self.MUTED, font=("Segoe UI", 10)).pack(side="left")
        tk.Label(bottom, textvariable=total_var, bg=self.SURFACE, fg=self.BLUE, font=("Segoe UI", 16, "bold")).pack(side="left", padx=9)

        def save() -> None:
            try:
                items = [{"product_id": product_id, "quantity": variable.get()} for product_id, variable in quantities.items() if variable.get() > 0]
                payload = {
                    "items": items, "client": client.get(), "origin": origin.get(),
                    "location": location.get(), "notes": notes.get(), "responsible": "Administrador",
                }
                if edit:
                    self.service.update_bar_order(order["order_id"], **payload)
                else:
                    self.service.create_bar_order(**payload)
                dialog.destroy()
                self._refresh_bar(reset_page=True)
            except Exception as exc:
                messagebox.showerror("Pedido", str(exc), parent=dialog)

        BarButton(bottom, "Guardar pedido", save, color=self.BLUE, width=150, height=42).pack(side="right")

    def _choose_bar_payment(self) -> None:
        orders = [
            row for row in self._bar_snapshot.get("orders", [])
            if row.get("balance_cents", 0) > 0 and row.get("delivery_status") != "cancelled"
        ]
        selected = next((row for row in orders if row["order_id"] == self._bar_selected_order_id), None)
        if selected is not None:
            self._bar_payment_dialog(selected)
            return
        if not orders:
            messagebox.showinfo("Cobrar pedido", "No hay pedidos pendientes de cobro en el período.", parent=self)
            return
        dialog = tk.Toplevel(self)
        dialog.title("Seleccionar pedido")
        dialog.configure(bg=self.SURFACE)
        dialog.geometry("520x360")
        dialog.transient(self)
        tk.Label(dialog, text="Seleccioná el pedido a cobrar", bg=self.SURFACE, fg=self.NAVY, font=("Segoe UI", 14, "bold")).pack(anchor="w", padx=18, pady=14)
        listbox = tk.Listbox(dialog, font=("Segoe UI", 10), relief="flat", highlightbackground=self.BORDER, highlightthickness=1)
        listbox.pack(fill="both", expand=True, padx=18, pady=(0, 12))
        for row in orders:
            listbox.insert("end", f"#{row['order_number']} · {row['display_location']} · saldo {self._money(row['balance'])}")

        def choose() -> None:
            selection = listbox.curselection()
            if not selection:
                return
            target = orders[selection[0]]
            dialog.destroy()
            self._bar_payment_dialog(target)

        BarButton(dialog, "Continuar", choose, color=self.GREEN, width=130, height=40).pack(pady=(0, 14))

    def _bar_payment_dialog(self, order: dict) -> None:
        dialog = tk.Toplevel(self)
        dialog.title(f"Cobrar pedido #{order['order_number']}")
        dialog.configure(bg=self.SURFACE)
        dialog.resizable(False, False)
        dialog.transient(self)
        amount = tk.StringVar(value=str(order.get("balance") or 0))
        method = tk.StringVar(value="Efectivo")
        responsible = tk.StringVar(value="Administrador")
        notes = tk.StringVar()
        tk.Label(
            dialog, text=f"Pedido #{order['order_number']} · Total {self._money(order['total'])}\nCobrado {self._money(order['paid'])} · Saldo {self._money(order['balance'])}",
            justify="left", bg="#ECFDF5", fg=self.NAVY, font=("Segoe UI", 10, "bold"), padx=16, pady=12,
        ).grid(row=0, column=0, columnspan=2, sticky="ew", padx=16, pady=14)
        for index, (label, variable) in enumerate((("Importe", amount), ("Método", method), ("Responsable", responsible), ("Observaciones", notes)), start=1):
            tk.Label(dialog, text=label, bg=self.SURFACE, fg=self.NAVY, font=("Segoe UI", 9, "bold")).grid(row=index, column=0, sticky="w", padx=16, pady=7)
            widget = ttk.Combobox(dialog, textvariable=variable, values=("Efectivo", "Transferencia", "Tarjeta", "Mercado Pago", "Otros"), state="readonly", width=29) if label == "Método" else tk.Entry(dialog, textvariable=variable, width=32)
            widget.grid(row=index, column=1, padx=16, pady=7, ipady=3)

        def save() -> None:
            try:
                self.service.record_bar_payment(
                    order["order_id"], amount=amount.get(), method=method.get(),
                    responsible=responsible.get(), notes=notes.get(),
                )
                dialog.destroy()
                self._refresh_bar()
                self._refresh_cash()
            except Exception as exc:
                messagebox.showerror("Cobrar pedido", str(exc), parent=dialog)

        BarButton(dialog, "Confirmar cobro", save, color=self.GREEN, width=160, height=42).grid(row=5, column=0, columnspan=2, pady=15)

    def _bar_expense_dialog(self) -> None:
        dialog = tk.Toplevel(self)
        dialog.title("Registrar gasto del Bar")
        dialog.configure(bg=self.SURFACE)
        dialog.resizable(False, False)
        dialog.transient(self)
        values = {
            "amount": tk.StringVar(), "category": tk.StringVar(value="Compra de mercadería"),
            "date": tk.StringVar(value=dt.datetime.now().isoformat(timespec="minutes")),
            "method": tk.StringVar(value="Efectivo"), "description": tk.StringVar(),
            "supplier": tk.StringVar(), "responsible": tk.StringVar(value="Administrador"),
        }
        tk.Label(dialog, text="Gasto relacionado con el Bar", bg=self.SURFACE, fg=self.NAVY, font=("Segoe UI", 14, "bold")).grid(row=0, column=0, columnspan=2, sticky="w", padx=18, pady=(16, 8))
        for index, (label, key) in enumerate((
            ("Importe", "amount"), ("Categoría", "category"), ("Fecha y hora", "date"),
            ("Método", "method"), ("Descripción", "description"), ("Proveedor (opcional)", "supplier"),
            ("Responsable", "responsible"),
        ), start=1):
            tk.Label(dialog, text=label, bg=self.SURFACE, fg=self.NAVY, font=("Segoe UI", 9, "bold")).grid(row=index, column=0, sticky="w", padx=18, pady=7)
            if key == "category":
                widget = ttk.Combobox(dialog, textvariable=values[key], values=("Compra de mercadería", "Proveedores", "Insumos", "Mantenimiento", "Otros"), state="readonly", width=31)
            elif key == "method":
                widget = ttk.Combobox(dialog, textvariable=values[key], values=("Efectivo", "Transferencia", "Tarjeta", "Mercado Pago", "Otros"), state="readonly", width=31)
            else:
                widget = tk.Entry(dialog, textvariable=values[key], width=34)
            widget.grid(row=index, column=1, padx=(4, 18), pady=7, ipady=3)

        def save() -> None:
            try:
                self.service.record_bar_expense(
                    amount=values["amount"].get(), category=values["category"].get(),
                    occurred_at=values["date"].get(), method=values["method"].get(),
                    description=values["description"].get(), supplier=values["supplier"].get(),
                    responsible=values["responsible"].get(),
                )
                dialog.destroy()
                self._refresh_cash()
                self._refresh_bar()
            except Exception as exc:
                messagebox.showerror("Gasto del Bar", str(exc), parent=dialog)

        BarButton(dialog, "Registrar gasto", save, color=self.ORANGE, width=160, height=42).grid(row=8, column=0, columnspan=2, pady=15)

    def _bar_order_menu(self, order: dict) -> None:
        self._bar_selected_order_id = str(order.get("order_id") or "")
        menu = tk.Menu(self, tearoff=0, font=("Segoe UI", 9))
        menu.add_command(label="Ver detalle", command=lambda: self._show_bar_order(order))
        if order.get("delivery_status") in {"open", "preparing"}:
            menu.add_command(label="Editar pedido", command=lambda: self._new_bar_order_dialog(self.service.bar_order(order["order_id"])))
        state_menu = tk.Menu(menu, tearoff=0, font=("Segoe UI", 9))
        for state, label in (("open", "Abierto"), ("preparing", "En preparación"), ("delivered", "Entregado")):
            state_menu.add_command(label=label, command=lambda value=state: self._bar_change_status(order, value))
        menu.add_cascade(label="Cambiar estado", menu=state_menu)
        if int(order.get("balance_cents") or 0) > 0 and order.get("delivery_status") != "cancelled":
            menu.add_command(label="Registrar cobro", command=lambda: self._bar_payment_dialog(order))
        if int(order.get("paid_cents") or 0) > 0:
            menu.add_command(label="Registrar reembolso", command=lambda: self._bar_refund_dialog(order))
        if order.get("delivery_status") != "cancelled":
            menu.add_separator()
            menu.add_command(label="Cancelar pedido", command=lambda: self._bar_cancel_order(order))
        menu.add_separator()
        menu.add_command(label="Consultar historial", command=lambda: self._bar_history_dialog(order))
        try:
            menu.tk_popup(self.winfo_pointerx(), self.winfo_pointery())
        finally:
            menu.grab_release()

    def _bar_change_status(self, order: dict, status: str) -> None:
        if status == order.get("delivery_status"):
            return
        if status == "delivered" and not messagebox.askyesno(
            "Confirmar entrega",
            "Al confirmar la entrega se descontará el stock exactamente una vez.\n\n¿Continuar?",
            parent=self,
        ):
            return
        try:
            self.service.set_bar_order_status(order["order_id"], status, responsible="Administrador")
            self._refresh_bar()
        except Exception as exc:
            messagebox.showerror("Estado del pedido", str(exc), parent=self)

    def _bar_cancel_order(self, order: dict) -> None:
        if not messagebox.askyesno("Cancelar pedido", f"¿Cancelar el pedido #{order['order_number']}?", parent=self):
            return
        restock = False
        if order.get("delivery_status") == "delivered" and order.get("stock_deducted_at") and not order.get("stock_restored_at"):
            restock = messagebox.askyesno(
                "Mercadería devuelta",
                "¿La mercadería regresó físicamente al inventario?\n\nElegí No si no fue devuelta.",
                parent=self,
            )
        try:
            self.service.set_bar_order_status(
                order["order_id"], "cancelled", responsible="Administrador", restock_returned=restock,
            )
            self._refresh_bar()
        except Exception as exc:
            messagebox.showerror("Cancelar pedido", str(exc), parent=self)

    def _bar_refund_dialog(self, order: dict) -> None:
        dialog = tk.Toplevel(self)
        dialog.title(f"Reembolsar pedido #{order['order_number']}")
        dialog.configure(bg=self.SURFACE)
        dialog.resizable(False, False)
        dialog.transient(self)
        amount = tk.StringVar(value=str(order.get("paid") or 0))
        method = tk.StringVar(value=str(order.get("payment_method") or "Efectivo"))
        notes = tk.StringVar(value="Reembolso confirmado")
        for index, (label, variable) in enumerate((("Importe", amount), ("Método", method), ("Motivo", notes))):
            tk.Label(dialog, text=label, bg=self.SURFACE, fg=self.NAVY, font=("Segoe UI", 9, "bold")).grid(row=index, column=0, sticky="w", padx=16, pady=9)
            widget = ttk.Combobox(dialog, textvariable=variable, values=("Efectivo", "Transferencia", "Tarjeta", "Mercado Pago", "Otros"), state="readonly", width=29) if label == "Método" else tk.Entry(dialog, textvariable=variable, width=32)
            widget.grid(row=index, column=1, padx=16, pady=9, ipady=3)

        def save() -> None:
            try:
                self.service.refund_bar_order(
                    order["order_id"], amount=amount.get(), method=method.get(),
                    responsible="Administrador", notes=notes.get(),
                )
                dialog.destroy()
                self._refresh_bar()
                self._refresh_cash()
            except Exception as exc:
                messagebox.showerror("Reembolso", str(exc), parent=dialog)

        BarButton(dialog, "Confirmar reembolso", save, color=self.RED, width=180, height=42).grid(row=3, column=0, columnspan=2, pady=15)

    def _show_bar_order(self, order: dict) -> None:
        order = self.service.bar_order(order["order_id"])
        dialog = tk.Toplevel(self)
        dialog.title(f"Pedido #{order['order_number']}")
        dialog.configure(bg=self.SURFACE)
        dialog.geometry("650x520")
        dialog.transient(self)
        tk.Label(dialog, text=f"Pedido #{order['order_number']}", bg=self.SURFACE, fg=self.NAVY, font=("Segoe UI", 16, "bold")).pack(anchor="w", padx=20, pady=(16, 4))
        tk.Label(
            dialog,
            text=(f"{order['origin']} · {order['display_location']} · {order.get('client') or 'Sin cliente'}\n"
                  f"Entrega: {order['delivery_label']} · Pago: {order['payment_label']}\n"
                  f"Total: {self._money(order['total'])} · Cobrado: {self._money(order['paid'])} · Saldo: {self._money(order['balance'])}"),
            bg="#EFF6FF", fg=self.NAVY, justify="left", anchor="w", font=("Segoe UI", 10), padx=14, pady=10,
        ).pack(fill="x", padx=20, pady=(0, 10))
        tree = ttk.Treeview(dialog, columns=("product", "qty", "price", "subtotal"), show="headings", style="Admin.Treeview")
        for key, title, width in (("product", "Producto", 250), ("qty", "Cantidad", 80), ("price", "Precio", 100), ("subtotal", "Subtotal", 110)):
            tree.heading(key, text=title)
            tree.column(key, width=width, anchor="w" if key == "product" else "center")
        for item in order["items"]:
            tree.insert("", "end", values=(item["product_name"], item["quantity"], self._money(item["unit_price_cents"] / 100), self._money(item["line_total_cents"] / 100)))
        tree.pack(fill="both", expand=True, padx=20, pady=(0, 10))
        tk.Label(dialog, text=f"Observaciones: {order.get('notes') or '-'}", bg=self.SURFACE, fg=self.MUTED, font=("Segoe UI", 9), anchor="w").pack(fill="x", padx=20, pady=(0, 14))

    def _bar_history_dialog(self, order: dict) -> None:
        order = self.service.bar_order(order["order_id"])
        dialog = tk.Toplevel(self)
        dialog.title(f"Historial pedido #{order['order_number']}")
        dialog.configure(bg=self.SURFACE)
        dialog.geometry("720x420")
        tree = ttk.Treeview(dialog, columns=("date", "event", "from", "to", "user", "notes"), show="headings", style="Admin.Treeview")
        for key, title, width in (("date", "Fecha", 135), ("event", "Evento", 110), ("from", "Anterior", 85), ("to", "Nuevo", 85), ("user", "Responsable", 100), ("notes", "Detalle", 170)):
            tree.heading(key, text=title)
            tree.column(key, width=width, anchor="w")
        for row in order["history"]:
            tree.insert("", "end", values=(row["occurred_at"].replace("T", " "), row["event_type"], row["previous_value"], row["new_value"], row["responsible"], row["notes"]))
        tree.pack(fill="both", expand=True, padx=16, pady=16)

    def _show_bar_inventory(self) -> None:
        dialog = tk.Toplevel(self)
        dialog.title("Inventario del Bar")
        dialog.configure(bg=self.BG)
        dialog.geometry("1040x620")
        dialog.transient(self)
        title = tk.Frame(dialog, bg=self.SURFACE, highlightbackground=self.BORDER, highlightthickness=1)
        title.pack(fill="x", padx=16, pady=(16, 8))
        tk.Label(title, text="Inventario y catálogo", bg=self.SURFACE, fg=self.NAVY, font=("Segoe UI", 17, "bold")).pack(side="left", padx=18, pady=13)
        actions = tk.Frame(title, bg=self.SURFACE)
        actions.pack(side="right", padx=12, pady=8)
        tree = ttk.Treeview(
            dialog, columns=("name", "category", "price", "cost", "stock", "minimum", "unit", "status"),
            show="headings", style="Admin.Treeview", selectmode="browse",
        )
        for key, label, width in (
            ("name", "Producto", 190), ("category", "Categoría", 110), ("price", "Precio", 95),
            ("cost", "Costo", 90), ("stock", "Stock", 70), ("minimum", "Mínimo", 70),
            ("unit", "Unidad", 90), ("status", "Estado", 90),
        ):
            tree.heading(key, text=label)
            tree.column(key, width=width, anchor="w" if key in {"name", "category", "unit"} else "center")
        tree.pack(fill="both", expand=True, padx=16, pady=(0, 16))

        def refresh() -> None:
            tree.delete(*tree.get_children())
            for row in self.service.bar_products(include_inactive=True):
                tree.insert("", "end", iid=row["product_id"], values=(
                    row["name"], row["category"], self._money(row["sale_price"]),
                    "-" if row["cost_price"] is None else self._money(row["cost_price"]),
                    row["stock"], row["minimum_stock"], row["unit"], "Activo" if row["active"] else "Inactivo",
                ))

        def selected() -> dict | None:
            choice = tree.selection()
            if not choice:
                messagebox.showinfo("Inventario", "Seleccioná un producto.", parent=dialog)
                return None
            return next((row for row in self.service.bar_products(include_inactive=True) if row["product_id"] == choice[0]), None)

        def edit() -> None:
            row = selected()
            if row:
                self._bar_product_dialog(row)
                dialog.after(300, refresh)

        def stock(operation: str) -> None:
            row = selected()
            if row:
                self._bar_stock_dialog(operation, row)
                dialog.after(300, refresh)

        def history() -> None:
            row = selected()
            if row:
                self._bar_inventory_history_dialog(row)

        for text, command, color, width in (
            ("Editar", edit, self.BLUE, 86), ("＋ Stock", lambda: stock("add"), self.GREEN, 92),
            ("− Stock", lambda: stock("remove"), self.ORANGE, 92), ("Historial", history, self.NAVY, 92),
            ("＋ Nuevo producto", self._bar_product_dialog, self.BLUE, 132),
        ):
            BarButton(actions, text, command, color=color, width=width, height=36, font=("Segoe UI", 8, "bold")).pack(side="left", padx=2)
        refresh()

    def _bar_inventory_history_dialog(self, product: dict) -> None:
        dialog = tk.Toplevel(self)
        dialog.title(f"Movimientos · {product['name']}")
        dialog.configure(bg=self.SURFACE)
        dialog.geometry("760x420")
        tree = ttk.Treeview(dialog, columns=("date", "operation", "quantity", "reason", "order", "user"), show="headings", style="Admin.Treeview")
        for key, title, width in (("date", "Fecha", 135), ("operation", "Operación", 90), ("quantity", "Cantidad", 75), ("reason", "Motivo", 190), ("order", "Pedido", 110), ("user", "Responsable", 110)):
            tree.heading(key, text=title)
            tree.column(key, width=width, anchor="w")
        for row in self.service.bar_inventory_history(product["product_id"]):
            tree.insert("", "end", values=(row["occurred_at"].replace("T", " "), row["operation"], row["delta"], row["reason"], row.get("order_id") or "-", row["responsible"]))
        tree.pack(fill="both", expand=True, padx=16, pady=16)

    def _show_bar_ranking(self) -> None:
        self._show_bar_report("Ranking completo de productos", self._bar_snapshot.get("top_products", []), ("name", "quantity"), ("Producto", "Unidades vendidas"))

    def _show_bar_categories(self) -> None:
        self._show_bar_report("Ventas por categoría", self._bar_snapshot.get("category_sales", []), ("name", "amount", "percent"), ("Categoría", "Venta neta", "Participación"))

    def _show_bar_report(self, title: str, rows: list[dict], keys: tuple[str, ...], labels: tuple[str, ...]) -> None:
        dialog = tk.Toplevel(self)
        dialog.title(title)
        dialog.configure(bg=self.SURFACE)
        dialog.geometry("600x430")
        tk.Label(dialog, text=title, bg=self.SURFACE, fg=self.NAVY, font=("Segoe UI", 15, "bold")).pack(anchor="w", padx=16, pady=(14, 8))
        tree = ttk.Treeview(dialog, columns=keys, show="headings", style="Admin.Treeview")
        for key, label in zip(keys, labels):
            tree.heading(key, text=label)
            tree.column(key, width=200 if key == "name" else 130, anchor="w" if key == "name" else "center")
        for row in rows:
            values = []
            for key in keys:
                value = row.get(key, "")
                if key == "amount":
                    value = self._money(value)
                elif key == "percent":
                    value = f"{value:g}%"
                values.append(value)
            tree.insert("", "end", values=values)
        tree.pack(fill="both", expand=True, padx=16, pady=(0, 16))

    def _on_tab_changed(self, _event=None) -> None:
        if self.notebook.select() == str(self.hours_tab):
            self._refresh_hours()
        elif self.notebook.select() == str(self.cash_tab):
            self._refresh_cash()
        elif self.notebook.select() == str(self.bar_tab):
            self._refresh_bar()
        elif self.notebook.select() == str(self.tournaments_tab):
            self._refresh_tournaments()
        elif self.notebook.select() == str(self.school_tab):
            self._refresh_school()
        elif self.notebook.select() == str(self.fixed_turns_tab):
            self._refresh_fixed_turns()
        elif self.notebook.select() == str(self.blacklist_tab):
            self._refresh_blacklist()

    def _on_notification_tab_clicked(self, _event=None) -> None:
        # Abrir Administración no significa haber revisado todas sus alertas.
        # Sólo la pestaña elegida explícitamente se considera leída, de modo
        # que el badge de Atención humana siga visible hasta abrir esa sección.
        selected = self.notebook.select()
        for tab, key in self._tab_notification_keys.items():
            if selected == str(tab):
                self.mark_notifications_read([key])
                break

    def _build_operation(self) -> None:
        form = tk.Frame(self.operation_tab, bg="white")
        form.pack(anchor="nw", padx=24, pady=24)
        tk.Label(form, text="Bloqueo de agenda", font=("Segoe UI", 14, "bold"), fg=self.NAVY, bg="white").grid(row=0, column=0, columnspan=3, sticky="w", pady=(0, 14))
        block_date_label = tk.Label(
            form,
            text="Fecha 📅",
            bg="white",
            fg=self.BLUE,
            font=("Segoe UI", 10, "bold"),
            cursor="hand2",
        )
        block_date_label.grid(row=1, column=0, sticky="w")
        self.block_day_var = tk.StringVar(value=dt_today())
        block_date_field = tk.Frame(form, bg="white")
        block_date_field.grid(
            row=2, column=0, sticky="w", padx=(0, 10), pady=(3, 12)
        )
        self.block_day_entry = tk.Entry(
            block_date_field,
            textvariable=self.block_day_var,
            width=19,
        )
        self.block_day_entry.pack(side="left")
        open_block_calendar = lambda _event=None: self._show_date_picker(
            self.block_day_var,
            self.block_day_entry,
            "Fecha del bloqueo de agenda",
        )
        block_date_label.bind("<Button-1>", open_block_calendar)
        self.block_day_entry.bind("<Double-Button-1>", open_block_calendar)
        tk.Button(
            block_date_field,
            text="📅",
            command=open_block_calendar,
            relief="flat",
            bg=self.BLUE,
            fg="white",
            cursor="hand2",
            padx=7,
            pady=2,
        ).pack(side="left", padx=(4, 0))
        tk.Label(form, text="Cancha (vacío = todas)", bg="white", fg=self.NAVY).grid(row=1, column=1, sticky="w")
        self.block_court_var = tk.StringVar(value="")
        ttk.Combobox(form, textvariable=self.block_court_var, values=["", *self.service.courts()], width=24, state="readonly").grid(row=2, column=1, sticky="w", padx=(0, 10), pady=(3, 12))
        self._action_button(form, "Bloquear", lambda: self._block_action(False), self.RED).grid(row=2, column=2, padx=4)
        self._action_button(form, "Desbloquear", lambda: self._block_action(True), self.GREEN).grid(row=2, column=3, padx=4)
        tk.Label(form, text="Los turnos existentes se conservan. Solo se crean o eliminan bloqueos administrativos.", bg="white", fg=self.MUTED).grid(row=3, column=0, columnspan=4, sticky="w", pady=(2, 20))

    def _build_cases(self) -> None:
        bar = tk.Frame(self.cases_tab, bg="white")
        bar.pack(fill="x", padx=10, pady=10)
        self._action_button(bar, "Resolver y reanudar", self._resolve_case, self.GREEN).pack(side="left")
        columns = ("id", "fecha", "cliente", "telefono", "mensaje", "motivo")
        body = tk.Frame(self.cases_tab, bg=self.SURFACE)
        body.pack(fill="both", expand=True, padx=10, pady=(0, 10))
        self.case_tree = ttk.Treeview(body, columns=columns, show="headings", selectmode="browse", style="Admin.Treeview")
        widths = (55, 140, 130, 125, 270, 360)
        labels = ("ID", "Creado", "Cliente", "Teléfono", "Mensaje", "Motivo")
        for key, label, width in zip(columns, labels, widths):
            self.case_tree.heading(key, text=label)
            self.case_tree.column(key, width=width, anchor="w")
        scrollbar = ttk.Scrollbar(body, orient="vertical", command=self.case_tree.yview, style="Admin.Vertical.TScrollbar")
        self.case_tree.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side="right", fill="y")
        self.case_tree.pack(side="left", fill="both", expand=True)

    def _build_tournaments(self) -> None:
        tournament_actions = tk.Frame(self.tournaments_tab, bg="white")
        tournament_actions.pack(fill="x", padx=10, pady=(10, 6))
        self._action_button(
            tournament_actions, "Nuevo torneo", self._new_tournament_dialog, self.BLUE
        ).pack(side="left", padx=3)
        self._action_button(
            tournament_actions, "Editar torneo", self._edit_tournament_dialog, self.ORANGE
        ).pack(side="left", padx=3)
        self._action_button(
            tournament_actions, "Borrar torneo", self._delete_tournament, self.RED
        ).pack(side="left", padx=3)
        self._action_button(
            tournament_actions, "Actualizar", self._refresh_tournaments, self.NAVY
        ).pack(side="left", padx=3)

        tournament_columns = (
            "id", "name", "date", "price", "prize", "confirmed", "holds", "available"
        )
        self.tournament_panes = tk.PanedWindow(
            self.tournaments_tab,
            orient="vertical",
            bg=self.BORDER,
            bd=0,
            sashwidth=7,
            sashrelief="flat",
            showhandle=False,
        )
        self.tournament_panes.pack(fill="both", expand=True, padx=10, pady=(0, 10))
        self.tournament_panes.bind("<Configure>", self._resize_tournament_panes)

        tournament_section = tk.Frame(self.tournament_panes, bg=self.SURFACE)
        registration_section = tk.Frame(self.tournament_panes, bg=self.SURFACE)
        self.tournament_panes.add(tournament_section, minsize=105, stretch="always")
        self.tournament_panes.add(registration_section, minsize=145, stretch="always")

        tournament_body = tk.Frame(tournament_section, bg=self.SURFACE)
        tournament_body.pack(fill="both", expand=True)
        self.tournament_tree = ttk.Treeview(
            tournament_body,
            columns=tournament_columns,
            show="headings",
            selectmode="browse",
            height=3,
            style="Admin.Treeview",
        )
        tournament_labels = (
            "ID", "Torneo", "Fecha", "Inscripción", "Premio",
            "Confirmados", "Holds", "Disponibles",
        )
        tournament_widths = (115, 220, 95, 105, 105, 90, 70, 90)
        for key, label, width in zip(tournament_columns, tournament_labels, tournament_widths):
            self.tournament_tree.heading(key, text=label)
            self.tournament_tree.column(
                key,
                width=width,
                anchor="w" if key == "name" else "center",
            )
        tournament_scroll = ttk.Scrollbar(
            tournament_body,
            orient="vertical",
            command=self.tournament_tree.yview,
            style="Admin.Vertical.TScrollbar",
        )
        self.tournament_tree.configure(yscrollcommand=tournament_scroll.set)
        tournament_scroll.pack(side="right", fill="y")
        self.tournament_tree.pack(side="left", fill="both", expand=True)
        self.tournament_tree.bind(
            "<<TreeviewSelect>>", lambda _event: self._refresh_tournament_registrations()
        )

        registrations_header = tk.Frame(registration_section, bg="white")
        registrations_header.pack(fill="x", pady=(5, 6))
        tk.Label(
            registrations_header,
            text="Inscripciones del torneo seleccionado",
            font=("Segoe UI", 11, "bold"),
            fg=self.NAVY,
            bg="white",
        ).pack(anchor="w", padx=3, pady=(0, 7))
        registration_actions = tk.Frame(registrations_header, bg=self.SURFACE)
        registration_actions.pack(fill="x")
        self._action_button(
            registration_actions,
            "Nueva inscripción",
            lambda: self._registration_dialog(edit=False),
            self.BLUE,
        ).pack(side="left", padx=3)
        self._action_button(
            registration_actions,
            "Editar datos",
            lambda: self._registration_dialog(edit=True),
            self.ORANGE,
        ).pack(side="left", padx=3)
        self._action_button(
            registration_actions,
            "Confirmar seña",
            lambda: self._registration_payment(total=False),
            self.GREEN,
        ).pack(side="left", padx=3)
        self._action_button(
            registration_actions,
            "Confirmar total",
            lambda: self._registration_payment(total=True),
            self.GREEN,
        ).pack(side="left", padx=3)
        self._action_button(
            registration_actions,
            "Liberar / cancelar",
            self._cancel_registration,
            self.RED,
        ).pack(side="left", padx=3)

        registration_columns = (
            "id", "team", "contact", "phone", "status", "paid", "pending", "method"
        )
        registration_body = tk.Frame(registration_section, bg=self.SURFACE)
        registration_body.pack(fill="both", expand=True)
        self.registration_tree = ttk.Treeview(
            registration_body,
            columns=registration_columns,
            show="headings",
            selectmode="browse",
            style="Admin.Treeview",
        )
        registration_labels = (
            "ID", "Equipo", "Responsable", "Teléfono", "Estado",
            "Pagado", "Pendiente", "Método",
        )
        registration_widths = (75, 165, 145, 125, 115, 90, 90, 125)
        for key, label, width in zip(
            registration_columns, registration_labels, registration_widths
        ):
            self.registration_tree.heading(key, text=label)
            self.registration_tree.column(
                key,
                width=width,
                anchor="w" if key in {"team", "contact", "phone"} else "center",
            )
        registration_scroll = ttk.Scrollbar(
            registration_body,
            orient="vertical",
            command=self.registration_tree.yview,
            style="Admin.Vertical.TScrollbar",
        )
        self.registration_tree.configure(yscrollcommand=registration_scroll.set)
        registration_scroll.pack(side="right", fill="y")
        self.registration_tree.pack(side="left", fill="both", expand=True)

    def _resize_tournament_panes(self, event) -> None:
        """Keep tournament and registration controls visible at every height."""
        if event.height < 260:
            return
        upper = max(105, min(event.height - 145, int(event.height * .43)))
        try:
            self.tournament_panes.sash_place(0, 0, upper)
        except tk.TclError:
            pass

    def _build_school(self) -> None:
        self._school_snapshot: dict = {}
        self._school_student_rows: dict[str, dict] = {}
        self._school_fee_rows: dict[str, dict] = {}
        stats = tk.Frame(self.school_tab, bg=self.SURFACE)
        stats.pack(fill="x", padx=14, pady=(14, 8))
        self.school_stat_vars = {
            key: tk.StringVar(value="0")
            for key in ("active_students", "active_groups", "classes_today", "pending_fees")
        }
        for column, (key, label, color) in enumerate((
            ("active_students", "Alumnos activos", self.BLUE),
            ("active_groups", "Grupos activos", "#7C3AED"),
            ("classes_today", "Clases de hoy", self.GREEN),
            ("pending_fees", "Cuotas pendientes", self.ORANGE),
        )):
            card = tk.Frame(stats, bg="white", highlightbackground=self.BORDER, highlightthickness=1)
            card.grid(row=0, column=column, sticky="nsew", padx=4)
            stats.grid_columnconfigure(column, weight=1)
            tk.Label(card, textvariable=self.school_stat_vars[key], bg="white", fg=color,
                     font=("Segoe UI", 20, "bold")).pack(anchor="w", padx=14, pady=(8, 0))
            tk.Label(card, text=label, bg="white", fg=self.MUTED,
                     font=("Segoe UI", 9)).pack(anchor="w", padx=14, pady=(0, 8))

        actions = tk.Frame(self.school_tab, bg=self.SURFACE)
        actions.pack(fill="x", padx=14, pady=(0, 8))
        self._action_button(actions, "+  Nuevo alumno", self._new_school_student_dialog, self.BLUE).pack(side="left", padx=3)
        self._action_button(actions, "+  Nuevo grupo", self._new_school_group_dialog, "#7C3AED").pack(side="left", padx=3)
        self._action_button(actions, "Registrar pago", self._school_payment_dialog, self.GREEN).pack(side="left", padx=3)
        self._action_button(actions, "Tomar asistencia", self._school_attendance_dialog, self.ORANGE).pack(side="left", padx=3)
        tk.Button(actions, text="Inscribir alumno", command=self._school_enroll_dialog,
                  bg="white", fg=self.NAVY, activebackground="#EFF6FF", relief="solid", bd=1,
                  font=("Segoe UI", 9, "bold"), padx=10, pady=8, cursor="hand2").pack(side="left", padx=3)
        tk.Button(actions, text="Aprobar preinscripción", command=self._school_approve_pre_enrollment,
                  bg="white", fg=self.NAVY, activebackground="#EFF6FF", relief="solid", bd=1,
                  font=("Segoe UI", 9, "bold"), padx=10, pady=8, cursor="hand2").pack(side="left", padx=3)

        filters = tk.Frame(self.school_tab, bg="white", highlightbackground=self.BORDER, highlightthickness=1)
        filters.pack(fill="x", padx=14, pady=(0, 8))
        self.school_category_filter = tk.StringVar(value="Todas")
        self.school_teacher_filter = tk.StringVar(value="Todos")
        self.school_status_filter = tk.StringVar(value="Activos")
        self.school_fee_filter = tk.StringVar(value="Todas")
        for index, (label, variable, values) in enumerate((
            ("Categoría", self.school_category_filter, ("Todas",)),
            ("Profesor", self.school_teacher_filter, ("Todos",)),
            ("Estado", self.school_status_filter, ("Activos", "Todos")),
            ("Cuota", self.school_fee_filter, ("Todas", "Al día", "Pendiente")),
        )):
            tk.Label(filters, text=label, bg="white", fg=self.NAVY,
                     font=("Segoe UI", 9, "bold")).grid(row=0, column=index * 2, padx=(12, 4), pady=9)
            combo = ttk.Combobox(filters, textvariable=variable, values=values, width=17, state="readonly")
            combo.grid(row=0, column=index * 2 + 1, padx=(0, 8), pady=9)
            combo.bind("<<ComboboxSelected>>", lambda _event: self._render_school_students())
            if index == 0:
                self.school_category_combo = combo
            elif index == 1:
                self.school_teacher_combo = combo

        panes = tk.PanedWindow(self.school_tab, orient="horizontal", bg=self.BORDER, bd=0, sashwidth=7)
        panes.pack(fill="both", expand=True, padx=14, pady=(0, 14))
        left = tk.Frame(panes, bg="white", highlightbackground=self.BORDER, highlightthickness=1)
        right_shell = tk.Frame(panes, bg=self.SURFACE)
        panes.add(left, minsize=650, stretch="always")
        panes.add(right_shell, minsize=340, stretch="always")
        self.school_side_canvas = tk.Canvas(
            right_shell,
            bg=self.SURFACE,
            bd=0,
            highlightthickness=0,
        )
        self.school_side_scroll = ttk.Scrollbar(
            right_shell,
            orient="vertical",
            command=self.school_side_canvas.yview,
            style="Admin.Vertical.TScrollbar",
        )
        self.school_side_canvas.configure(yscrollcommand=self.school_side_scroll.set)
        self.school_side_scroll.pack(side="right", fill="y")
        self.school_side_canvas.pack(side="left", fill="both", expand=True)
        right = tk.Frame(self.school_side_canvas, bg=self.SURFACE)
        self._school_side_window = self.school_side_canvas.create_window(
            (0, 0), window=right, anchor="nw"
        )
        right.bind(
            "<Configure>",
            lambda _event: self.school_side_canvas.configure(
                scrollregion=self.school_side_canvas.bbox("all")
            ),
        )
        self.school_side_canvas.bind(
            "<Configure>",
            lambda event: self.school_side_canvas.itemconfigure(
                self._school_side_window, width=event.width
            ),
        )
        tk.Label(left, text="Alumnos e inscripciones", bg="white", fg=self.NAVY,
                 font=("Segoe UI", 13, "bold")).pack(anchor="w", padx=12, pady=(10, 6))
        columns = ("student", "guardian", "phone", "group", "category", "teacher", "fee")
        self.school_student_tree = ttk.Treeview(
            left, columns=columns, show="headings", selectmode="browse", style="Admin.Treeview"
        )
        for key, label, width in zip(columns,
            ("Alumno", "Responsable", "Teléfono", "Grupo", "Categoría", "Profesor", "Cuota"),
            (150, 145, 120, 135, 95, 120, 90)):
            self.school_student_tree.heading(key, text=label)
            self.school_student_tree.column(key, width=width, anchor="w" if key != "fee" else "center")
        scroll = ttk.Scrollbar(left, orient="vertical", command=self.school_student_tree.yview,
                               style="Admin.Vertical.TScrollbar")
        self.school_student_tree.configure(yscrollcommand=scroll.set)
        scroll.pack(side="right", fill="y", pady=(0, 8))
        self.school_student_tree.pack(side="left", fill="both", expand=True, padx=(8, 0), pady=(0, 8))
        self.school_group_tree = self._school_side_panel(
            right, "Grupos y cupos", ("group", "schedule", "available"),
            ("Grupo", "Horario", "Cupos"), (120, 145, 55), 3
        )
        self.school_today_tree = self._school_side_panel(
            right, "Clases de hoy", ("time", "group", "court"), ("Hora", "Grupo", "Cancha"), (58, 150, 95), 3
        )
        self.school_fee_tree = self._school_side_panel(
            right, "Cuotas vencidas / pendientes", ("student", "period", "balance"),
            ("Alumno", "Período", "Saldo"), (145, 72, 90), 4
        )
        self.school_pre_tree = self._school_side_panel(
            right, "Preinscripciones por aprobar", ("child", "phone", "group"),
            ("Alumno", "Teléfono", "Grupo"), (125, 105, 105), 4
        )

    def _school_side_panel(self, parent, title, columns, labels, widths, height):
        panel = tk.Frame(parent, bg="white", highlightbackground=self.BORDER, highlightthickness=1)
        panel.pack(fill="x", pady=(0, 7))
        tk.Label(panel, text=title, bg="white", fg=self.NAVY,
                 font=("Segoe UI", 10, "bold")).pack(anchor="w", padx=10, pady=(7, 3))
        body = tk.Frame(panel, bg="white")
        body.pack(fill="both", expand=True, padx=7, pady=(0, 7))
        tree = ttk.Treeview(body, columns=columns, show="headings", height=height,
                            selectmode="browse", style="Admin.Treeview")
        for key, label, width in zip(columns, labels, widths):
            tree.heading(key, text=label)
            tree.column(key, width=width, anchor="w")
        scroll = ttk.Scrollbar(
            body,
            orient="vertical",
            command=tree.yview,
            style="Admin.Vertical.TScrollbar",
        )
        tree.configure(yscrollcommand=scroll.set)
        scroll.pack(side="right", fill="y")
        tree.pack(side="left", fill="both", expand=True)
        return tree

    def _build_fixed_turns(self) -> None:
        header = tk.Frame(self.fixed_turns_tab, bg="white")
        header.pack(fill="x", padx=16, pady=(16, 8))
        tk.Label(
            header,
            text="Turnos semanales recurrentes",
            font=("Segoe UI", 14, "bold"),
            fg=self.NAVY,
            bg="white",
        ).pack(anchor="w")
        tk.Label(
            header,
            text=(
                "Usa los mismos turnos fijos de WhatsApp. La próxima fecha se agrega a la agenda de Horas."
            ),
            fg=self.MUTED,
            bg="white",
        ).pack(anchor="w", pady=(3, 0))

        actions = tk.Frame(self.fixed_turns_tab, bg="white")
        actions.pack(fill="x", padx=16, pady=(4, 12))
        self._action_button(
            actions, "Nuevo turno fijo", self._new_fixed_turn_dialog, self.BLUE
        ).pack(side="left", padx=3)
        self._action_button(
            actions, "Quitar seleccionado", self._remove_fixed_turn, self.RED
        ).pack(side="left", padx=3)
        self._action_button(
            actions, "Actualizar", self._refresh_fixed_turns, self.NAVY
        ).pack(side="left", padx=3)

        body = tk.Frame(self.fixed_turns_tab, bg="white")
        body.pack(fill="both", expand=True, padx=16, pady=(0, 16))
        columns = ("name", "phone", "day", "time", "court", "next", "status")
        self.fixed_turn_tree = ttk.Treeview(
            body, columns=columns, show="headings", selectmode="browse", style="Admin.Treeview"
        )
        labels = (
            "Cliente", "Teléfono", "Día semanal", "Hora", "Cancha", "Próxima fecha", "Agenda Horas"
        )
        widths = (180, 145, 110, 75, 130, 105, 145)
        for key, label, width in zip(columns, labels, widths):
            self.fixed_turn_tree.heading(key, text=label)
            self.fixed_turn_tree.column(
                key,
                width=width,
                anchor="w" if key in {"name", "phone"} else "center",
            )
        scrollbar = ttk.Scrollbar(body, orient="vertical", command=self.fixed_turn_tree.yview, style="Admin.Vertical.TScrollbar")
        self.fixed_turn_tree.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side="right", fill="y")
        self.fixed_turn_tree.pack(side="left", fill="both", expand=True)

    def _build_blacklist(self) -> None:
        header = tk.Frame(self.blacklist_tab, bg="white")
        header.pack(fill="x", padx=16, pady=(16, 8))
        tk.Label(
            header,
            text="Gestión de contactos bloqueados",
            font=("Segoe UI", 14, "bold"),
            fg=self.NAVY,
            bg="white",
        ).pack(anchor="w")
        tk.Label(
            header,
            text=(
                "Ingresá un teléfono completo (por ejemplo +549351...) o un nombre. "
                "El agente ignorará sus mensajes sin responder."
            ),
            fg=self.MUTED,
            bg="white",
        ).pack(anchor="w", pady=(3, 0))

        actions = tk.Frame(self.blacklist_tab, bg="white")
        actions.pack(fill="x", padx=16, pady=(4, 12))
        tk.Label(actions, text="Número o nombre", fg=self.NAVY, bg="white").pack(
            side="left", padx=(0, 8)
        )
        self.blacklist_target_var = tk.StringVar()
        self.blacklist_target_entry = tk.Entry(
            actions,
            textvariable=self.blacklist_target_var,
            width=34,
            font=("Segoe UI", 10),
        )
        self.blacklist_target_entry.pack(side="left", padx=(0, 8), ipady=5)
        self.blacklist_target_entry.bind(
            "<Return>", lambda _event: self._blacklist_action(block=True)
        )
        self._action_button(
            actions, "Bloquear", lambda: self._blacklist_action(block=True), self.RED
        ).pack(side="left", padx=3)
        self._action_button(
            actions,
            "Desbloquear",
            lambda: self._blacklist_action(block=False),
            self.GREEN,
        ).pack(side="left", padx=3)
        self._action_button(
            actions, "Actualizar", self._refresh_blacklist, self.NAVY
        ).pack(side="left", padx=3)

        body = tk.Frame(self.blacklist_tab, bg="white")
        body.pack(fill="both", expand=True, padx=16, pady=(0, 16))
        columns = ("kind", "contact")
        self.blacklist_tree = ttk.Treeview(
            body, columns=columns, show="headings", selectmode="browse", style="Admin.Treeview"
        )
        self.blacklist_tree.heading("kind", text="Tipo")
        self.blacklist_tree.heading("contact", text="Número o nombre bloqueado")
        self.blacklist_tree.column("kind", width=130, anchor="center")
        self.blacklist_tree.column("contact", width=540, anchor="w")
        self.blacklist_tree.bind("<<TreeviewSelect>>", self._on_blacklist_selected)
        scrollbar = ttk.Scrollbar(body, orient="vertical", command=self.blacklist_tree.yview, style="Admin.Vertical.TScrollbar")
        self.blacklist_tree.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side="right", fill="y")
        self.blacklist_tree.pack(side="left", fill="both", expand=True)

    def _build_commands(self) -> None:
        bar = tk.Frame(self.commands_tab, bg="white")
        bar.pack(fill="x", padx=14, pady=12)
        self._action_button(bar, "Abrir configuración", self.open_configurator_callback, self.BLUE).pack(side="left", padx=(0, 8))
        self._action_button(
            bar,
            "🗑  Borrar comprobantes de pago",
            self._delete_used_payment_receipts,
            self.PAST_GRAY,
        ).pack(side="left")
        tk.Label(bar, text="Referencia de las mismas funciones disponibles por WhatsApp", bg="white", fg=self.MUTED).pack(side="left", padx=14)
        body = tk.Frame(self.commands_tab, bg="white")
        body.pack(fill="both", expand=True, padx=14, pady=(0, 14))
        text = tk.Text(
            body,
            wrap="word",
            font=("Segoe UI", 10),
            bg="#f8fafc",
            fg=self.NAVY,
            relief="flat",
            padx=16,
            pady=14,
        )
        scrollbar = ttk.Scrollbar(body, orient="vertical", command=text.yview, style="Admin.Vertical.TScrollbar")
        text.configure(yscrollcommand=scrollbar.set)
        text.tag_configure(
            "title", font=("Segoe UI", 14, "bold"), foreground=self.NAVY, spacing3=10
        )
        text.tag_configure(
            "heading", font=("Segoe UI", 11, "bold"), foreground=self.BLUE, spacing1=12, spacing3=4
        )
        text.tag_configure("command", font=("Consolas", 9), lmargin1=12, lmargin2=24, spacing1=2)
        reference_method = getattr(self.service, "command_reference", None)
        reference = reference_method() if callable(reference_method) else COMMAND_REFERENCE_FALLBACK
        for index, raw_line in enumerate(str(reference).splitlines()):
            line = raw_line.replace("*", "").replace("`", "")
            if index == 0:
                tag = "title"
            elif raw_line.strip().startswith("•"):
                tag = "command"
            elif raw_line.strip() and "*" in raw_line:
                tag = "heading"
            else:
                tag = None
            text.insert("end", line + "\n", tag)
        text.configure(state="disabled")
        scrollbar.pack(side="right", fill="y")
        text.pack(side="left", fill="both", expand=True)

    def _delete_used_payment_receipts(self) -> None:
        warning = (
            "¿Querés borrar el registro JSON de comprobantes de pago usados?\n\n"
            "Esta acción no elimina reservas ni movimientos de Caja, pero permite que "
            "comprobantes anteriores vuelvan a ser evaluados por el agente. No se puede deshacer."
        )
        if not messagebox.askyesno(
            "Borrar comprobantes de pago",
            warning,
            parent=self,
        ):
            return
        try:
            result = self.service.delete_used_payment_receipts()
            messagebox.showinfo("Comprobantes de pago", result, parent=self)
        except Exception as exc:
            messagebox.showerror(
                "Comprobantes de pago",
                str(exc),
                parent=self,
            )

    def refresh_all(self) -> None:
        try:
            stats = self.service.stats()
            for key, value in stats.items():
                if key in self.summary_vars:
                    self.summary_vars[key].set(str(value))
            self._apply_notification_counts(self._notification_counts_for_stats(stats))
            self._refresh_bookings()
            self._refresh_cases()
            self._refresh_tournaments()
            self._refresh_school()
            self._refresh_fixed_turns()
            self._refresh_blacklist()
            self._refresh_hours()
            self._refresh_cash()
            self._refresh_bar()
        except Exception as exc:
            messagebox.showerror("Administración", f"No pude actualizar el panel:\n{exc}", parent=self)

    def _refresh_and_mark_notifications_read(self) -> None:
        self.refresh_all()
        self.mark_notifications_read()

    def mark_notifications_read(self, keys: list[str] | None = None) -> None:
        method = getattr(self.service, "mark_notifications_read", None)
        if callable(method):
            counts = method(keys)
        else:
            counts = dict(self._last_notification_counts or {})
            selected = set(keys or self._tab_notification_keys.values())
            for key in selected:
                counts[key] = 0
            counts["total"] = sum(
                max(0, int(counts.get(key, 0) or 0))
                for key in self._tab_notification_keys.values()
            )
        self._apply_notification_counts(counts)

    def _apply_notification_counts(self, counts: dict[str, int]) -> None:
        normalized = {
            key: max(0, int(counts.get(key, 0) or 0))
            for key in (
                "bookings", "hours", "operation", "cases", "tournaments", "school", "fixed_turns",
                "cash", "bar", "blacklist", "commands"
            )
        }
        normalized["total"] = sum(normalized.values())
        self._last_notification_counts = normalized

        for tab, title in self._tab_titles.items():
            count = normalized[self._tab_notification_keys[tab]]
            if count:
                image = self._create_badge_image(count)
                self._tab_badge_images[tab] = image
                self.notebook.tab(tab, text=title, image=image, compound="right")
            else:
                self._tab_badge_images.pop(tab, None)
                self.notebook.tab(tab, text=title, image="")

        active_sources = [
            tab for tab in self._tab_titles
            if normalized[self._tab_notification_keys[tab]] > 0
        ]
        if not self._initial_notification_tab_selected:
            self._initial_notification_tab_selected = True
            if len(active_sources) == 1:
                self.notebook.select(active_sources[0])

        self.on_notifications_changed(dict(normalized))

    def _notification_counts_for_stats(self, stats: dict[str, int]) -> dict[str, int]:
        method = getattr(self.service, "unread_notification_counts", None)
        if callable(method):
            return method(stats)
        method = getattr(self.service, "notification_counts", None)
        if callable(method):
            return method(stats)
        bookings = max(0, int(stats.get("pending", 0) or 0))
        cases = max(0, int(stats.get("cases", 0) or 0))
        return {
            "bookings": bookings,
            "hours": 0,
            "cash": 0,
            "bar": 0,
            "operation": 0,
            "cases": cases,
            "tournaments": 0,
            "fixed_turns": 0,
            "blacklist": 0,
            "commands": 0,
            "total": bookings + cases,
        }

    def _create_badge_image(self, count: int) -> tk.PhotoImage:
        """Draw a dependency-free red numeric pill for a ttk notebook tab."""
        text = "99+" if count > 99 else str(count)
        glyphs = {
            "0": ("111", "101", "101", "101", "111"),
            "1": ("010", "110", "010", "010", "111"),
            "2": ("111", "001", "111", "100", "111"),
            "3": ("111", "001", "111", "001", "111"),
            "4": ("101", "101", "111", "001", "001"),
            "5": ("111", "100", "111", "001", "111"),
            "6": ("111", "100", "111", "101", "111"),
            "7": ("111", "001", "010", "010", "010"),
            "8": ("111", "101", "111", "101", "111"),
            "9": ("111", "101", "111", "001", "111"),
            "+": ("000", "010", "111", "010", "000"),
        }
        scale = 2
        glyph_width = 3 * scale
        gap = scale
        width = max(18, 8 + len(text) * glyph_width + max(0, len(text) - 1) * gap)
        height = 18
        image = tk.PhotoImage(master=self, width=width, height=height)
        for y in range(height):
            inset = 5 if y in {0, height - 1} else 3 if y in {1, height - 2} else 1
            image.put("#e31b23", to=(inset, y, width - inset, y + 1))
        text_width = len(text) * glyph_width + max(0, len(text) - 1) * gap
        start_x = (width - text_width) // 2
        start_y = 4
        for char_index, char in enumerate(text):
            glyph = glyphs[char]
            glyph_x = start_x + char_index * (glyph_width + gap)
            for row, bits in enumerate(glyph):
                for column, bit in enumerate(bits):
                    if bit == "1":
                        x = glyph_x + column * scale
                        y = start_y + row * scale
                        image.put("white", to=(x, y, x + scale, y + scale))
        return image

    def _schedule_notification_poll(self) -> None:
        if self.winfo_exists():
            self._notification_poll_id = self.after(3000, self._poll_notifications)

    def _poll_notifications(self) -> None:
        self._notification_poll_id = None
        if not self.winfo_exists():
            return
        try:
            stats = self.service.stats()
            for key, value in stats.items():
                if key in self.summary_vars:
                    self.summary_vars[key].set(str(value))
            previous = self._last_notification_counts
            current = self._notification_counts_for_stats(stats)
            self._apply_notification_counts(current)
            if previous != self._last_notification_counts:
                self._refresh_bookings()
                self._refresh_cases()
                self._refresh_tournaments()
            if self.notebook.select() == str(self.fixed_turns_tab):
                self._refresh_fixed_turns()
            if self.notebook.select() == str(self.blacklist_tab):
                self._refresh_blacklist()
            if self.notebook.select() == str(self.cash_tab):
                self._refresh_cash()
            if self.notebook.select() == str(self.bar_tab):
                self._refresh_bar()
        except Exception:
            # A transient file write must not interrupt the administrator.
            pass
        finally:
            self._schedule_notification_poll()

    def destroy(self) -> None:
        if self._notification_poll_id is not None:
            try:
                self.after_cancel(self._notification_poll_id)
            except tk.TclError:
                pass
            self._notification_poll_id = None
        super().destroy()

    def _refresh_bookings(self) -> None:
        self.booking_tree.delete(*self.booking_tree.get_children())
        show_past = bool(
            hasattr(self, "show_past_bookings_var") and self.show_past_bookings_var.get()
        )
        history_method = getattr(self.service, "bookings_with_history", None)
        rows = history_method() if show_past and callable(history_method) else self.service.bookings()
        sort_key = getattr(self.service, "booking_sort_key", None)
        if callable(sort_key):
            rows = sorted(
                rows,
                key=lambda row: sort_key(row, self._booking_sort_column),
                reverse=not self._booking_sort_ascending,
            )
        else:
            rows = sorted(
                rows,
                key=lambda row: (
                    str(row.get(self._booking_sort_column) or ""),
                    str(row.get("fecha") or ""),
                    str(row.get("hora") or ""),
                ),
                reverse=not self._booking_sort_ascending,
            )
        for index, row in enumerate(rows):
            payment_status = getattr(self.service, "booking_payment_status", None)
            payment_label = (
                payment_status(row)
                if callable(payment_status) else row.get("senia_estado", "")
            )
            source = "past" if row.get("_history") else "booking"
            self.booking_tree.insert("", "end", iid=f"{source}:{row.get('reservation_id')}:{index}", values=(
                row.get("reservation_id", ""), row.get("fecha", ""), row.get("hora", ""), row.get("cancha", ""),
                row.get("nombre", ""), row.get("telefono", ""), row.get("estado", ""), payment_label,
                row.get("monto_pendiente", ""),
            ))

    def _toggle_booking_sort(self, column: str) -> None:
        if column not in {"fecha", "hora"}:
            return
        if self._booking_sort_column == column:
            self._booking_sort_ascending = not self._booking_sort_ascending
        else:
            self._booking_sort_column = column
            self._booking_sort_ascending = True
        self._update_booking_sort_headings()
        self._refresh_bookings()

    def _update_booking_sort_headings(self) -> None:
        if not hasattr(self, "booking_tree"):
            return
        for column in ("fecha", "hora"):
            indicator = ""
            if self._booking_sort_column == column:
                indicator = "  ▲" if self._booking_sort_ascending else "  ▼"
            self.booking_tree.heading(
                column,
                text=f"{self._booking_headings[column]}{indicator}",
            )

    def _refresh_fixed_turns(self) -> None:
        if not hasattr(self, "fixed_turn_tree"):
            return
        method = getattr(self.service, "fixed_turns", None)
        if not callable(method):
            return
        selected_key = ""
        selection = self.fixed_turn_tree.selection()
        if selection:
            selected_key = str(
                getattr(self, "_fixed_turn_rows", {}).get(selection[0], {}).get("client_key") or ""
            )
        self.fixed_turn_tree.delete(*self.fixed_turn_tree.get_children())
        self._fixed_turn_rows = {}
        for index, row in enumerate(method()):
            iid = f"fixed-turn:{index}"
            normalized = dict(row)
            self._fixed_turn_rows[iid] = normalized
            next_date = str(normalized.get("next_date") or "")
            try:
                import datetime

                next_date = datetime.date.fromisoformat(next_date).strftime("%d/%m/%Y")
            except ValueError:
                pass
            self.fixed_turn_tree.insert(
                "",
                "end",
                iid=iid,
                values=(
                    normalized.get("name", ""),
                    normalized.get("phone", ""),
                    normalized.get("day_name", ""),
                    normalized.get("time", ""),
                    normalized.get("court", ""),
                    next_date,
                    normalized.get("calendar_status", ""),
                ),
            )
            if normalized.get("client_key") == selected_key:
                self.fixed_turn_tree.selection_set(iid)

    def _new_fixed_turn_dialog(self) -> None:
        dialog = tk.Toplevel(self)
        dialog.title("Nuevo turno fijo")
        dialog.resizable(False, False)
        dialog.transient(self)
        day_names = ("Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo")
        courts = self.service.courts()
        values = {
            "name": tk.StringVar(),
            "phone": tk.StringVar(),
            "day": tk.StringVar(value=day_names[0]),
            "time": tk.StringVar(value="20:00"),
            "court": tk.StringVar(value=courts[0]),
        }
        fields = (
            ("Nombre del cliente", "name"),
            ("Teléfono", "phone"),
            ("Día semanal", "day"),
            ("Hora (HH:MM)", "time"),
            ("Cancha", "court"),
        )
        for row_index, (label, key) in enumerate(fields):
            tk.Label(dialog, text=label).grid(
                row=row_index, column=0, sticky="w", padx=14, pady=8
            )
            if key == "day":
                ttk.Combobox(
                    dialog,
                    textvariable=values[key],
                    values=day_names,
                    state="readonly",
                    width=31,
                ).grid(row=row_index, column=1, padx=14, pady=8)
            elif key == "court":
                ttk.Combobox(
                    dialog,
                    textvariable=values[key],
                    values=courts,
                    state="readonly",
                    width=31,
                ).grid(row=row_index, column=1, padx=14, pady=8)
            else:
                tk.Entry(dialog, textvariable=values[key], width=34).grid(
                    row=row_index, column=1, padx=14, pady=8
                )

        tk.Label(
            dialog,
            text="Completá al menos el nombre o el teléfono.",
            fg=self.MUTED,
        ).grid(row=len(fields), column=0, columnspan=2, pady=(2, 6))

        def save() -> None:
            try:
                result = self.service.create_fixed_turn(
                    name=values["name"].get(),
                    phone=values["phone"].get(),
                    weekday=day_names.index(values["day"].get()),
                    time=values["time"].get(),
                    court=values["court"].get(),
                )
                messagebox.showinfo("Turnos Fijos", result, parent=dialog)
                dialog.destroy()
                self._refresh_fixed_turns()
                self._refresh_hours()
                self._refresh_bookings()
            except Exception as exc:
                messagebox.showerror("Turnos Fijos", str(exc), parent=dialog)

        self._action_button(dialog, "Crear turno fijo", save, self.BLUE).grid(
            row=len(fields) + 1, column=0, columnspan=2, pady=14
        )

    def _remove_fixed_turn(self) -> None:
        try:
            selection = self.fixed_turn_tree.selection()
            if not selection:
                raise ValueError("Seleccioná un turno fijo de la tabla.")
            row = getattr(self, "_fixed_turn_rows", {}).get(selection[0]) or {}
            label = str(row.get("name") or row.get("phone") or row.get("client_key") or "")
            if not messagebox.askyesno(
                "Turnos Fijos",
                f"¿Querés quitar el turno fijo de {label}?\n\n"
                "La reserva de la próxima fecha que ya fue generada se conservará en Horas.",
                parent=self,
            ):
                return
            result = self.service.remove_fixed_turn(
                client_key=str(row.get("client_key") or ""),
                name=str(row.get("name") or ""),
                phone=str(row.get("phone") or ""),
            )
            messagebox.showinfo("Turnos Fijos", result, parent=self)
            self._refresh_fixed_turns()
            self._refresh_hours()
            self._refresh_bookings()
        except Exception as exc:
            messagebox.showerror("Turnos Fijos", str(exc), parent=self)

    def _refresh_blacklist(self) -> None:
        if not hasattr(self, "blacklist_tree"):
            return
        method = getattr(self.service, "blacklist_entries", None)
        if not callable(method):
            return
        selected_entry = ""
        selection = self.blacklist_tree.selection()
        if selection:
            selected_entry = str(
                getattr(self, "_blacklist_rows", {}).get(selection[0], {}).get("entry") or ""
            )
        self.blacklist_tree.delete(*self.blacklist_tree.get_children())
        self._blacklist_rows = {}
        for index, row in enumerate(method()):
            iid = f"blacklist:{index}"
            normalized = dict(row)
            self._blacklist_rows[iid] = normalized
            self.blacklist_tree.insert(
                "",
                "end",
                iid=iid,
                values=(normalized.get("kind", ""), normalized.get("label", "")),
            )
            if normalized.get("entry") == selected_entry:
                self.blacklist_tree.selection_set(iid)

    def _on_blacklist_selected(self, _event=None) -> None:
        selection = self.blacklist_tree.selection()
        if not selection:
            return
        row = getattr(self, "_blacklist_rows", {}).get(selection[0]) or {}
        self.blacklist_target_var.set(str(row.get("label") or row.get("entry") or ""))

    def _blacklist_action(self, *, block: bool) -> None:
        try:
            target = self.blacklist_target_var.get().strip()
            if not block:
                selection = self.blacklist_tree.selection()
                if selection:
                    row = getattr(self, "_blacklist_rows", {}).get(selection[0]) or {}
                    target = str(row.get("entry") or target).strip()
            if not target:
                raise ValueError(
                    "Ingresá un número o nombre para bloquear, o seleccioná uno para desbloquear."
                )
            verb = "bloquear" if block else "desbloquear"
            if not messagebox.askyesno(
                "Blacklist",
                f"¿Querés {verb} a {self.blacklist_target_var.get().strip() or target}?",
                parent=self,
            ):
                return
            method_name = "block_blacklist" if block else "unblock_blacklist"
            method = getattr(self.service, method_name, None)
            if not callable(method):
                raise RuntimeError("La gestión de blacklist no está disponible.")
            result = method(target)
            messagebox.showinfo("Blacklist", result, parent=self)
            self.blacklist_target_var.set("")
            self._refresh_blacklist()
        except Exception as exc:
            messagebox.showerror("Blacklist", str(exc), parent=self)

    def _selected_booking_id(self, *, allow_history: bool = False) -> str:
        selection = self.booking_tree.selection()
        if not selection:
            raise ValueError("Seleccioná una reserva de la tabla.")
        if str(selection[0]).startswith("past:") and not allow_history:
            raise ValueError("Las reservas pasadas son de solo lectura.")
        return str(self.booking_tree.item(selection[0], "values")[0])

    def _booking_action(self, action: str) -> None:
        try:
            reservation_id = self._selected_booking_id(allow_history=action == "delete")
            labels = {"deposit": "confirmar la seña", "total": "confirmar el pago total", "release": "liberar el pendiente", "cancel": "cancelar la reserva", "delete": "borrar definitivamente la reserva"}
            warning = (
                f"¿Querés {labels[action]} ID {reservation_id}?\n\n"
                "Esta acción elimina la reserva de la lista y no se puede deshacer. "
                "Los movimientos de Caja se conservarán."
                if action == "delete"
                else f"¿Querés {labels[action]} de la reserva ID {reservation_id}?"
            )
            if not messagebox.askyesno("Borrar reserva" if action == "delete" else "Administración", warning, parent=self):
                return
            if action == "deposit":
                result = self.service.confirm_payment(reservation_id)
            elif action == "total":
                result = self.service.confirm_payment(reservation_id, total=True)
            elif action == "release":
                result = self.service.release_booking(reservation_id)
            elif action == "delete":
                result = self.service.delete_booking(reservation_id)
            else:
                result = self.service.cancel_booking(reservation_id)
            messagebox.showinfo("Administración", result, parent=self)
            self.refresh_all()
        except Exception as exc:
            messagebox.showerror("Administración", str(exc), parent=self)

    def _new_booking_dialog(self, day: str = "", time: str = "", court: str = "") -> None:
        dialog = tk.Toplevel(self)
        dialog.title("Nueva reserva manual")
        dialog.resizable(False, False)
        courts = self.service.courts()
        fields = [
            ("Fecha (AAAA-MM-DD)", tk.StringVar(value=day or dt_today())),
            ("Hora (HH:MM)", tk.StringVar(value=time or "20:00")),
            ("Cancha", tk.StringVar(value=court or courts[0])),
            ("Nombre", tk.StringVar()),
            ("Teléfono", tk.StringVar()),
        ]
        for index, (label, var) in enumerate(fields):
            tk.Label(dialog, text=label).grid(row=index, column=0, sticky="w", padx=12, pady=7)
            if label == "Cancha":
                ttk.Combobox(dialog, textvariable=var, values=courts, state="readonly", width=28).grid(row=index, column=1, padx=12, pady=7)
            else:
                tk.Entry(dialog, textvariable=var, width=31).grid(row=index, column=1, padx=12, pady=7)

        def save() -> None:
            try:
                result = self.service.add_booking(day=fields[0][1].get(), time=fields[1][1].get(), court=fields[2][1].get(), name=fields[3][1].get(), phone=fields[4][1].get())
                messagebox.showinfo("Administración", result, parent=dialog)
                dialog.destroy()
                self.refresh_all()
            except Exception as exc:
                messagebox.showerror("Administración", str(exc), parent=dialog)

        self._action_button(dialog, "Guardar reserva", save, self.BLUE).grid(row=len(fields), column=0, columnspan=2, pady=14)

    def _set_hours_today(self) -> None:
        self.hours_day_var.set(dt_today())
        self._refresh_hours()

    def _move_hours_date(self, delta: int) -> None:
        import datetime

        try:
            selected = datetime.date.fromisoformat(self.hours_day_var.get().strip())
        except ValueError:
            messagebox.showerror("Horas", "Ingresá la fecha con formato AAAA-MM-DD.", parent=self)
            return
        self.hours_day_var.set((selected + datetime.timedelta(days=delta)).isoformat())
        self._refresh_hours()

    def _refresh_hours(self) -> None:
        if not hasattr(self, "hours_grid"):
            return
        try:
            show_all = bool(
                hasattr(self, "hours_show_all_var") and self.hours_show_all_var.get()
            )
            schedule = (
                self.service.day_schedule(self.hours_day_var.get(), include_all=True)
                if show_all else self.service.day_schedule(self.hours_day_var.get())
            )
        except Exception as exc:
            messagebox.showerror("Horas", str(exc), parent=self)
            return

        self.hours_day_var.set(schedule["day"])
        for widget in self.hours_grid.winfo_children():
            widget.destroy()

        courts = schedule["courts"]
        slots = schedule["slots"]
        cell_map = {(cell["time"], cell["court"]): cell for cell in schedule["cells"]}
        self.hours_grid.grid_columnconfigure(0, weight=0, minsize=145)
        HoursTile(
            self.hours_grid,
            text="Hora",
            fill="#EDF3F9",
            foreground=self.NAVY,
            border="#E5ECF5",
            width=145,
            height=38,
            font=("Segoe UI", 10, "bold"),
        ).grid(row=0, column=0, sticky="nsew", padx=3, pady=1)
        catalog_method = getattr(self.service, "court_catalog", None)
        catalog = catalog_method() if callable(catalog_method) else []
        identities = {str(item.get("name")): item for item in catalog}
        for column, court in enumerate(courts, start=1):
            self.hours_grid.grid_columnconfigure(column, weight=1, minsize=215)
            identity = identities.get(court, {})
            icon = str(identity.get("icon") or "🏟️")
            court_type = str(identity.get("type") or "").strip()
            header = HoursTile(
                self.hours_grid,
                text=f"{icon} {court}" + (f" · {court_type}" if court_type else ""),
                fill="#EDF3F9",
                foreground=self.NAVY,
                border="#E5ECF5",
                width=215,
                height=38,
                font=("Segoe UI", 10, "bold"),
            )
            header.configure(cursor="hand2")
            header.grid(row=0, column=column, sticky="nsew", padx=3, pady=1)
            header.bind(
                "<Button-3>",
                lambda event, selected_court=court: self._show_court_sport_menu(
                    event, selected_court
                ),
            )

        for row_index, time in enumerate(slots, start=1):
            HoursTile(
                self.hours_grid,
                text=time,
                fill="#F7F9FC",
                foreground=self.NAVY,
                border="#F1F4F8",
                width=145,
                height=34,
                font=("Segoe UI", 11, "bold"),
            ).grid(row=row_index, column=0, sticky="nsew", padx=3, pady=1)
            for column, court in enumerate(courts, start=1):
                cell = cell_map[(time, court)]
                text, color = self._hour_cell_style(cell)
                hover = {
                    self.FREE_GREEN: "#067C4D",
                    self.RED: "#C71F27",
                    self.PAST_GRAY: "#55657B",
                }.get(color, color)
                HoursTile(
                    self.hours_grid,
                    text=text,
                    command=lambda selected=cell: self._open_hour_cell(selected),
                    fill=color,
                    foreground="white",
                    hover_fill=hover,
                    gradient=color == self.FREE_GREEN,
                    width=215,
                    height=34,
                    font=("Segoe UI", 9, "bold"),
                ).grid(row=row_index, column=column, sticky="nsew", padx=3, pady=1)

        if not slots:
            tk.Label(
                self.hours_grid,
                text=(
                    "No quedan horarios futuros para esta fecha."
                    if schedule.get("attention_day")
                    else "La fecha está fuera de los días de atención."
                ),
                bg="white",
                fg=self.MUTED,
                pady=30,
            ).grid(row=1, column=0, columnspan=max(1, len(courts) + 1), sticky="ew")
        summary = (
            f"{schedule['display_day']} · {len(slots)} horarios · {len(courts)} "
            f"{'cancha' if len(courts) == 1 else 'canchas'}"
        )
        self.hours_status_var.set(summary)
        self.hours_summary_pill.set_text(summary)
        self.hours_canvas.update_idletasks()
        self.hours_canvas.configure(scrollregion=self.hours_canvas.bbox("all"))
        self._bind_hours_wheel(self.hours_grid)

    def _show_court_sport_menu(self, event, court: str) -> None:
        menu = tk.Menu(self, tearoff=False)
        options_method = getattr(self.service, "court_sport_options", None)
        options = options_method() if callable(options_method) else []
        for option in options:
            court_type = str(option.get("type") or "").strip()
            menu.add_command(
                label=str(option.get("label") or court_type),
                command=lambda selected=court_type: self._change_court_sport(court, selected),
            )
        if options:
            menu.add_separator()
        menu.add_command(
            label="🏟️  Otro deporte...",
            command=lambda: self._custom_court_sport(court),
        )
        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()

    def _custom_court_sport(self, court: str) -> None:
        court_type = simpledialog.askstring(
            "Deporte de la cancha",
            f"Escribí el deporte correspondiente a {court}:",
            parent=self,
        )
        if court_type and court_type.strip():
            self._change_court_sport(court, court_type.strip())

    def _change_court_sport(self, court: str, court_type: str) -> None:
        try:
            result = self.service.update_court_sport(court, court_type)
            self._refresh_hours()
            messagebox.showinfo(
                "Deporte actualizado",
                result + "\n\nEl agente usará este mismo deporte e ícono en WhatsApp.",
                parent=self,
            )
        except Exception as exc:
            messagebox.showerror("Deporte de la cancha", str(exc), parent=self)

    def _hour_cell_style(self, cell: dict) -> tuple[str, str]:
        status = cell["status"]
        booking = cell.get("booking") or {}
        if status == "free":
            return "✓ DISPONIBLE", self.FREE_GREEN
        if status == "occupied":
            client = str(booking.get("nombre") or booking.get("telefono") or "Reserva").strip()
            return f"OCUPADO\n{client}", self.RED
        if status == "past_occupied":
            client = str(booking.get("nombre") or booking.get("telefono") or "Reserva").strip()
            return f"OCUPADO\n{client}", self.RED
        if status == "blocked":
            return "BLOQUEADO", self.RED
        if status == "past_blocked":
            return "BLOQUEADO", self.RED
        if status == "closed":
            return "FUERA DE ATENCIÓN", self.PAST_GRAY
        return "HORARIO PASADO", self.PAST_GRAY

    def _open_hour_cell(self, cell: dict) -> None:
        status = cell["status"]
        if status == "free":
            self._new_booking_dialog(cell["day"], cell["time"], cell["court"])
            return
        if status == "occupied":
            self._edit_booking_dialog(cell)
            return
        if status == "blocked":
            self._blocked_slot_dialog(cell)
            return
        if status in {"past_occupied", "past_blocked"}:
            self._past_booking_details_dialog(cell)
            return
        messagebox.showinfo(
            "Horas",
            "Ese horario ya pasó." if status == "past" else "La fecha está fuera de los días de atención configurados.",
            parent=self,
        )

    def _edit_booking_dialog(self, cell: dict) -> None:
        booking = cell.get("booking") or {}
        reservation_id = str(booking.get("reservation_id") or "").strip()
        try:
            details = self.service.booking_details(reservation_id, cell["day"])
        except Exception as exc:
            messagebox.showerror("Horas", str(exc), parent=self)
            self._refresh_hours()
            return

        dialog = tk.Toplevel(self)
        dialog.title(f"Editar reserva ID {reservation_id}")
        dialog.resizable(False, False)
        dialog.transient(self)
        fields = [
            ("Fecha (AAAA-MM-DD)", tk.StringVar(value=details.get("day") or cell["day"])),
            ("Hora inicial (HH:MM)", tk.StringVar(value=details.get("hora") or cell["time"])),
            ("Cancha", tk.StringVar(value=details.get("cancha") or cell["court"])),
            ("Nombre", tk.StringVar(value=details.get("nombre") or "")),
            ("Teléfono", tk.StringVar(value=details.get("telefono") or "")),
        ]
        tk.Label(
            dialog,
            text=f"Reserva ID {reservation_id} · Estado: {details.get('estado') or '-'}",
            font=("Segoe UI", 11, "bold"),
            fg=self.NAVY,
        ).grid(row=0, column=0, columnspan=2, sticky="w", padx=14, pady=(14, 8))
        for index, (label, var) in enumerate(fields, start=1):
            tk.Label(dialog, text=label).grid(row=index, column=0, sticky="w", padx=14, pady=7)
            if label == "Cancha":
                ttk.Combobox(dialog, textvariable=var, values=self.service.courts(), state="readonly", width=29).grid(row=index, column=1, padx=14, pady=7)
            else:
                tk.Entry(dialog, textvariable=var, width=32).grid(row=index, column=1, padx=14, pady=7)

        if int(details.get("slot_count") or 1) > 1:
            tk.Label(
                dialog,
                text=f"Este turno ocupa {details['slot_count']} bloques consecutivos.",
                fg=self.MUTED,
            ).grid(row=len(fields) + 1, column=0, columnspan=2, sticky="w", padx=14, pady=(4, 0))

        def save() -> None:
            try:
                result = self.service.update_booking(
                    reservation_id,
                    day=fields[0][1].get(),
                    time=fields[1][1].get(),
                    court=fields[2][1].get(),
                    name=fields[3][1].get(),
                    phone=fields[4][1].get(),
                )
                messagebox.showinfo("Administración", result, parent=dialog)
                dialog.destroy()
                self.refresh_all()
            except Exception as exc:
                messagebox.showerror("Administración", str(exc), parent=dialog)

        def cancel() -> None:
            if not messagebox.askyesno("Administración", f"¿Cancelar la reserva ID {reservation_id}?", parent=dialog):
                return
            try:
                result = self.service.cancel_booking(reservation_id)
                messagebox.showinfo("Administración", result, parent=dialog)
                dialog.destroy()
                self.refresh_all()
            except Exception as exc:
                messagebox.showerror("Administración", str(exc), parent=dialog)

        actions = tk.Frame(dialog)
        actions.grid(row=len(fields) + 2, column=0, columnspan=2, pady=14)
        self._action_button(actions, "Guardar cambios", save, self.BLUE).pack(side="left", padx=4)
        self._action_button(actions, "Cancelar reserva", cancel, self.RED).pack(side="left", padx=4)

    def _past_booking_details_dialog(self, cell: dict) -> None:
        booking = cell.get("booking") or {}
        reservation_id = str(booking.get("reservation_id") or "").strip()
        details_method = getattr(self.service, "past_booking_details", None)
        try:
            details = (
                details_method(reservation_id, cell.get("day") or "")
                if callable(details_method) else dict(booking)
            )
        except Exception as exc:
            messagebox.showerror("Horas", str(exc), parent=self)
            return

        payment_method = getattr(self.service, "booking_payment_status", None)
        payment_status = (
            payment_method(details)
            if callable(payment_method) else str(details.get("senia_estado") or "-")
        )
        display_date = str(details.get("fecha") or cell.get("day") or "-")
        time_range = str(details.get("time_range") or details.get("hora") or cell.get("time") or "-")
        fields = [
            ("ID", reservation_id or "-"),
            ("Fecha", display_date),
            ("Horario", time_range),
            ("Cancha", details.get("cancha") or cell.get("court") or "-"),
            ("Cliente", details.get("nombre") or "-"),
            ("Teléfono", details.get("telefono") or "-"),
            ("Estado", details.get("estado") or "finalizada"),
            ("Pago", payment_status or "-"),
            ("Total", self._money(details.get("precio_total"))),
            ("Saldo", self._money(details.get("monto_pendiente"))),
        ]

        dialog = tk.Toplevel(self)
        dialog.title(f"Detalle de reserva pasada ID {reservation_id or '-'}")
        dialog.configure(bg=self.BG)
        dialog.resizable(False, False)
        dialog.transient(self)

        card = tk.Frame(
            dialog,
            bg=self.SURFACE,
            highlightbackground=self.BORDER,
            highlightthickness=1,
            bd=0,
        )
        card.pack(fill="both", expand=True, padx=16, pady=16)
        tk.Label(
            card,
            text="Detalle del turno pasado",
            font=("Segoe UI", 15, "bold"),
            fg=self.NAVY,
            bg=self.SURFACE,
        ).grid(row=0, column=0, columnspan=2, sticky="w", padx=18, pady=(16, 2))
        tk.Label(
            card,
            text="Consulta de solo lectura · No modifica la reserva ni sus pagos",
            font=("Segoe UI", 9),
            fg=self.MUTED,
            bg=self.SURFACE,
        ).grid(row=1, column=0, columnspan=2, sticky="w", padx=18, pady=(0, 12))
        for row_index, (label, value) in enumerate(fields, start=2):
            tk.Label(
                card,
                text=label,
                font=("Segoe UI", 9, "bold"),
                fg=self.MUTED,
                bg=self.SURFACE,
                anchor="w",
                width=12,
            ).grid(row=row_index, column=0, sticky="w", padx=(18, 10), pady=5)
            tk.Label(
                card,
                text=str(value),
                font=("Segoe UI", 10, "bold" if label in {"Horario", "Estado", "Pago"} else "normal"),
                fg=self.NAVY,
                bg=self.SURFACE,
                anchor="w",
                width=32,
            ).grid(row=row_index, column=1, sticky="w", padx=(0, 18), pady=5)
        tk.Button(
            card,
            text="Cerrar",
            command=dialog.destroy,
            font=("Segoe UI", 10, "bold"),
            bg=self.BLUE,
            fg="white",
            activebackground="#0F62E8",
            activeforeground="white",
            relief="flat",
            bd=0,
            padx=24,
            pady=9,
            cursor="hand2",
        ).grid(row=len(fields) + 2, column=0, columnspan=2, pady=(14, 16))

    def _blocked_slot_dialog(self, cell: dict) -> None:
        if not messagebox.askyesno(
            "Horario bloqueado",
            f"{cell['day']} a las {cell['time']} · {cell['court']}\n\n¿Querés desbloquear este horario?",
            parent=self,
        ):
            return
        try:
            result = self.service.unblock_slot(cell["day"], cell["time"], cell["court"])
            messagebox.showinfo("Administración", result, parent=self)
            self.refresh_all()
        except Exception as exc:
            messagebox.showerror("Administración", str(exc), parent=self)

    def _block_action(self, unblock: bool) -> None:
        try:
            if unblock:
                result = self.service.unblock_day(self.block_day_var.get(), self.block_court_var.get())
            else:
                result = self.service.block_day(self.block_day_var.get(), self.block_court_var.get())
            messagebox.showinfo("Administración", result, parent=self)
            self.refresh_all()
        except Exception as exc:
            messagebox.showerror("Administración", str(exc), parent=self)

    @staticmethod
    def _money(value) -> str:
        try:
            amount = int(float(value or 0))
        except (TypeError, ValueError):
            amount = 0
        prefix = "-$" if amount < 0 else "$"
        return prefix + f"{abs(amount):,}".replace(",", ".")

    def _refresh_school(self) -> None:
        if not hasattr(self, "school_student_tree"):
            return
        method = getattr(self.service, "school_snapshot", None)
        if not callable(method):
            return
        self._school_snapshot = method()
        for key, variable in self.school_stat_vars.items():
            variable.set(str(self._school_snapshot.get(key, 0)))
        groups = self._school_snapshot.get("groups", [])
        categories = sorted({str(row.get("category") or "Sin categoría") for row in groups})
        teachers = sorted({str(row.get("teacher_name") or "Sin profesor") for row in groups})
        self.school_category_combo.configure(values=("Todas", *categories))
        self.school_teacher_combo.configure(values=("Todos", *teachers))
        self._render_school_students()
        for tree in (self.school_group_tree, self.school_today_tree, self.school_fee_tree, self.school_pre_tree):
            tree.delete(*tree.get_children())
        for row in groups:
            self.school_group_tree.insert("", "end", iid=str(row.get("group_id")), values=(
                row.get("name", ""), row.get("schedule_text", ""),
                f"{row.get('available', 0)}/{row.get('capacity', 0)}",
            ))
        for row in self._school_snapshot.get("today_classes", []):
            self.school_today_tree.insert("", "end", iid=str(row.get("schedule_id")), values=(
                row.get("start_time", ""), row.get("group_name", ""), row.get("court", "")
            ))
        self._school_fee_rows = {}
        for row in self._school_snapshot.get("fees", []):
            if int(row.get("balance") or 0) <= 0:
                continue
            fee_id = str(row.get("fee_id") or "")
            self._school_fee_rows[fee_id] = row
            self.school_fee_tree.insert("", "end", iid=fee_id, values=(
                row.get("student_name", ""), row.get("period", ""), self._money(row.get("balance"))
            ))
        for row in self._school_snapshot.get("pre_enrollments", []):
            pre_id = str(row.get("pre_enrollment_id") or "")
            self.school_pre_tree.insert("", "end", iid=pre_id, values=(
                row.get("child_name", ""), row.get("guardian_phone", ""),
                row.get("group_name") or "A definir",
            ))

    def _render_school_students(self) -> None:
        if not hasattr(self, "school_student_tree"):
            return
        self.school_student_tree.delete(*self.school_student_tree.get_children())
        groups = {str(row.get("group_id")): row for row in self._school_snapshot.get("groups", [])}
        fee_by_enrollment = {
            str(row.get("enrollment_id")): row for row in self._school_snapshot.get("fees", [])
        }
        self._school_student_rows = {}
        for index, row in enumerate(self._school_snapshot.get("students", [])):
            group = groups.get(str(row.get("group_id") or ""), {})
            fee = fee_by_enrollment.get(str(row.get("enrollment_id") or ""), {})
            balance = int(fee.get("balance") or 0)
            category = str(group.get("category") or "Sin categoría")
            teacher = str(group.get("teacher_name") or "Sin profesor")
            if self.school_category_filter.get() != "Todas" and category != self.school_category_filter.get():
                continue
            if self.school_teacher_filter.get() != "Todos" and teacher != self.school_teacher_filter.get():
                continue
            if self.school_status_filter.get() == "Activos" and str(row.get("status")) != "active":
                continue
            if self.school_fee_filter.get() == "Al día" and balance:
                continue
            if self.school_fee_filter.get() == "Pendiente" and not balance:
                continue
            item_id = f"{row.get('student_id')}:{row.get('enrollment_id') or index}"
            self._school_student_rows[item_id] = row
            self.school_student_tree.insert("", "end", iid=item_id, values=(
                row.get("name", ""), row.get("guardian_name", ""), row.get("guardian_phone", ""),
                row.get("group_name") or "Sin inscripción", category, teacher,
                self._money(balance) if balance else "Al día",
            ))

    def _selected_school_student(self) -> dict:
        selection = self.school_student_tree.selection()
        if not selection:
            raise ValueError("Seleccioná un alumno de la tabla.")
        return dict(self._school_student_rows.get(selection[0]) or {})

    def _school_modal(self, title: str, fields: list[tuple], submit, *, size="470x520") -> None:
        dialog = tk.Toplevel(self)
        dialog.title(title)
        dialog.configure(bg="white")
        dialog.geometry(size)
        dialog.transient(self)
        values: dict[str, tk.Variable] = {}
        form = tk.Frame(dialog, bg="white")
        form.pack(fill="both", expand=True, padx=20, pady=16)
        tk.Label(form, text=title, bg="white", fg=self.NAVY,
                 font=("Segoe UI", 15, "bold")).grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 12))
        for row_index, spec in enumerate(fields, start=1):
            key, label, kind, initial, options = spec
            tk.Label(form, text=label, bg="white", fg=self.NAVY).grid(
                row=row_index, column=0, sticky="w", padx=(0, 10), pady=5
            )
            variable = tk.StringVar(value=str(initial or ""))
            values[key] = variable
            if kind == "combo":
                widget = ttk.Combobox(form, textvariable=variable, values=options, state="readonly", width=29)
            else:
                widget = tk.Entry(form, textvariable=variable, width=32)
            widget.grid(row=row_index, column=1, sticky="ew", pady=5)
        form.grid_columnconfigure(1, weight=1)

        def save():
            try:
                submit({key: variable.get().strip() for key, variable in values.items()})
                dialog.destroy()
                self._refresh_school()
                self._refresh_hours()
                self._refresh_cash()
            except Exception as exc:
                messagebox.showerror(title, str(exc), parent=dialog)
        self._action_button(form, "Guardar", save, self.BLUE).grid(
            row=len(fields) + 1, column=0, columnspan=2, sticky="e", pady=(14, 0)
        )

    def _new_school_student_dialog(self) -> None:
        groups = self.service.school_groups()
        labels = ["Sin inscripción", *[str(row["name"]) for row in groups]]
        by_name = {str(row["name"]): str(row["group_id"]) for row in groups}
        fields = [
            ("name", "Alumno", "entry", "", ()),
            ("birth_date", "Nacimiento (AAAA-MM-DD)", "entry", "", ()),
            ("guardian_name", "Responsable", "entry", "", ()),
            ("guardian_phone", "Teléfono responsable", "entry", "", ()),
            ("emergency_phone", "Teléfono de emergencia", "entry", "", ()),
            ("medical_notes", "Observaciones médicas", "entry", "", ()),
            ("group", "Grupo inicial", "combo", "Sin inscripción", labels),
        ]
        def submit(data):
            group_name = data.pop("group")
            student = self.service.create_school_student(**data)
            if group_name != "Sin inscripción":
                self.service.enroll_school_student(student["student_id"], by_name[group_name])
        self._school_modal("Nuevo alumno", fields, submit)

    def _new_school_group_dialog(self) -> None:
        teachers = self.service.school_teachers()
        teacher_labels = ["Sin profesor", *[str(row["name"]) for row in teachers]]
        teacher_by_name = {str(row["name"]): str(row["teacher_id"]) for row in teachers}
        courts = self.service.courts()
        fields = [
            ("name", "Nombre del grupo", "entry", "", ()),
            ("sport", "Deporte", "entry", "Fútbol", ()),
            ("category", "Categoría", "entry", "", ()),
            ("age_min", "Edad mínima", "entry", "", ()),
            ("age_max", "Edad máxima", "entry", "", ()),
            ("court", "Cancha", "combo", courts[0] if courts else "", courts),
            ("teacher", "Profesor existente", "combo", "Sin profesor", teacher_labels),
            ("new_teacher", "Nuevo profesor (opcional)", "entry", "", ()),
            ("capacity", "Cupo", "entry", "12", ()),
            ("monthly_fee", "Cuota mensual", "entry", "", ()),
            ("weekday", "Día", "combo", "Lunes", ("Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo")),
            ("start_time", "Hora (HH:MM)", "entry", "18:00", ()),
            ("duration", "Duración (minutos)", "entry", "60", ()),
        ]
        day_index = {name: index for index, name in enumerate(("Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"))}
        def submit(data):
            teacher_name, new_teacher = data.pop("teacher"), data.pop("new_teacher")
            teacher_id = teacher_by_name.get(teacher_name, "")
            if new_teacher:
                teacher_id = self.service.create_school_teacher(name=new_teacher)["teacher_id"]
            schedule = [{"weekday": day_index[data.pop("weekday")],
                         "start_time": data.pop("start_time"),
                         "duration_minutes": int(data.pop("duration"))}]
            data["age_min"] = int(data["age_min"]) if data["age_min"] else None
            data["age_max"] = int(data["age_max"]) if data["age_max"] else None
            data["capacity"] = int(data["capacity"])
            self.service.create_school_group(**data, schedules=schedule, teacher_id=teacher_id)
        self._school_modal("Nuevo grupo", fields, submit, size="510x700")

    def _school_enroll_dialog(self) -> None:
        try:
            student = self._selected_school_student()
            groups = [row for row in self.service.school_groups() if int(row.get("available") or 0) > 0]
            if not groups:
                raise ValueError("No hay grupos activos con cupo disponible.")
            labels = [str(row["name"]) for row in groups]
            by_name = {str(row["name"]): str(row["group_id"]) for row in groups}
            self._school_modal("Inscribir alumno", [
                ("student", "Alumno", "entry", student.get("name"), ()),
                ("group", "Grupo", "combo", labels[0], labels),
                ("start_date", "Fecha de inicio", "entry", dt_today(), ()),
            ], lambda data: self.service.enroll_school_student(
                student["student_id"], by_name[data["group"]], start_date=data["start_date"]
            ), size="440x280")
        except Exception as exc:
            messagebox.showerror("Inscribir alumno", str(exc), parent=self)

    def _school_payment_dialog(self) -> None:
        fees = list(self._school_fee_rows.values())
        if not fees:
            messagebox.showinfo("Cuotas", "No hay cuotas con saldo pendiente.", parent=self)
            return
        selected = self.school_fee_tree.selection()
        initial = self._school_fee_rows.get(selected[0]) if selected else fees[0]
        labels = [f"{row['student_name']} · {row['period']} · {self._money(row['balance'])}" for row in fees]
        by_label = {label: row for label, row in zip(labels, fees)}
        initial_label = f"{initial['student_name']} · {initial['period']} · {self._money(initial['balance'])}"
        fields = [
            ("fee", "Cuota", "combo", initial_label, labels),
            ("amount", "Importe", "entry", initial["balance"], ()),
            ("method", "Método", "combo", "Efectivo", ("Efectivo", "Transferencia", "Tarjeta", "Mercado Pago", "Otros")),
        ]
        self._school_modal("Registrar pago de cuota", fields, lambda data: self.service.record_school_payment(
            by_label[data["fee"]]["fee_id"], amount=data["amount"], method=data["method"]
        ), size="590x300")

    def _school_attendance_dialog(self) -> None:
        try:
            student = self._selected_school_student()
            enrollment_id = str(student.get("enrollment_id") or "")
            if not enrollment_id:
                raise ValueError("El alumno seleccionado todavía no tiene una inscripción activa.")
            fields = [
                ("student", "Alumno", "entry", student.get("name"), ()),
                ("date", "Fecha", "entry", dt_today(), ()),
                ("status", "Asistencia", "combo", "Presente", ("Presente", "Ausente", "Justificada", "Recuperada", "Clase cancelada")),
                ("notes", "Observaciones", "entry", "", ()),
            ]
            states = {"Presente": "present", "Ausente": "absent", "Justificada": "excused",
                      "Recuperada": "recovered", "Clase cancelada": "cancelled"}
            self._school_modal("Tomar asistencia", fields, lambda data: self.service.record_school_attendance(
                enrollment_id, data["date"], states[data["status"]], notes=data["notes"]
            ), size="470x340")
        except Exception as exc:
            messagebox.showerror("Tomar asistencia", str(exc), parent=self)

    def _school_approve_pre_enrollment(self) -> None:
        try:
            selection = self.school_pre_tree.selection()
            if not selection:
                raise ValueError("Seleccioná una preinscripción pendiente.")
            pre_id = selection[0]
            pre = next(
                (row for row in self._school_snapshot.get("pre_enrollments", [])
                 if str(row.get("pre_enrollment_id")) == pre_id),
                None,
            )
            if not pre:
                raise ValueError("La preinscripción ya no está pendiente.")
            groups = [row for row in self.service.school_groups() if int(row.get("available") or 0) > 0]
            if not groups:
                raise ValueError("No hay grupos con cupo disponible.")
            labels = [str(row["name"]) for row in groups]
            by_name = {str(row["name"]): str(row["group_id"]) for row in groups}
            initial_group = str(pre.get("group_name") or "")
            if initial_group not in labels:
                initial_group = labels[0]

            def submit(data):
                student = self.service.create_school_student(
                    name=data["student"],
                    guardian_name=data["guardian_name"],
                    guardian_phone=pre.get("guardian_phone"),
                )
                self.service.enroll_school_student(
                    student["student_id"], by_name[data["group"]], start_date=data["start_date"]
                )
                self.service.resolve_school_pre_enrollment(pre_id, "approved")

            self._school_modal("Aprobar preinscripción", [
                ("student", "Alumno", "entry", pre.get("child_name"), ()),
                ("guardian_name", "Responsable", "entry", pre.get("guardian_name") or "Responsable", ()),
                ("group", "Grupo", "combo", initial_group, labels),
                ("start_date", "Fecha de inicio", "entry", dt_today(), ()),
            ], submit, size="500x350")
        except Exception as exc:
            messagebox.showerror("Preinscripción", str(exc), parent=self)

    def _refresh_tournaments(self) -> None:
        if not hasattr(self, "tournament_tree"):
            return
        method = getattr(self.service, "tournaments", None)
        if not callable(method):
            return
        previous = ""
        selection = self.tournament_tree.selection()
        if selection:
            previous = str(self.tournament_tree.item(selection[0], "values")[0])
        self.tournament_tree.delete(*self.tournament_tree.get_children())
        self._tournament_rows = {}
        for index, event in enumerate(method()):
            event_id = str(event.get("event_id") or "")
            self._tournament_rows[event_id] = dict(event)
            iid = f"tournament:{event_id}:{index}"
            self.tournament_tree.insert(
                "",
                "end",
                iid=iid,
                values=(
                    event_id,
                    event.get("name", ""),
                    event.get("date", ""),
                    self._money(event.get("registration_price")),
                    self._money(event.get("prize")),
                    f"{event.get('confirmed', 0)}/{event.get('capacity', 0)}",
                    event.get("active_holds", 0),
                    event.get("available", 0),
                ),
            )
            if event_id == previous:
                self.tournament_tree.selection_set(iid)
        if not self.tournament_tree.selection() and self.tournament_tree.get_children():
            first = self.tournament_tree.get_children()[0]
            self.tournament_tree.selection_set(first)
        self._refresh_tournament_registrations()

    def _selected_tournament_id(self) -> str:
        selection = self.tournament_tree.selection()
        if not selection:
            raise ValueError("Seleccioná un torneo de la tabla.")
        return str(self.tournament_tree.item(selection[0], "values")[0])

    def _selected_registration_id(self) -> str:
        selection = self.registration_tree.selection()
        if not selection:
            raise ValueError("Seleccioná una inscripción de la tabla.")
        iid = selection[0]
        row = getattr(self, "_registration_rows", {}).get(iid) or {}
        registration_id = str(row.get("registration_id") or "")
        if not registration_id:
            raise ValueError("La inscripción seleccionada ya no existe.")
        return registration_id

    def _refresh_tournament_registrations(self) -> None:
        if not hasattr(self, "registration_tree"):
            return
        self.registration_tree.delete(*self.registration_tree.get_children())
        self._registration_rows = {}
        method = getattr(self.service, "tournament_registrations", None)
        if not callable(method):
            return
        try:
            event_id = self._selected_tournament_id()
        except ValueError:
            return
        statuses = {
            "pending_payment": "Pendiente",
            "confirmed": "Confirmada",
            "expired": "Vencida",
            "cancelled": "Cancelada",
        }
        for index, row in enumerate(method(event_id)):
            iid = f"registration:{row.get('registration_id')}:{index}"
            self._registration_rows[iid] = dict(row)
            self.registration_tree.insert(
                "",
                "end",
                iid=iid,
                values=(
                    row.get("display_id") or row.get("registration_id", ""),
                    row.get("team_name", ""),
                    row.get("contact_name", ""),
                    row.get("phone", ""),
                    statuses.get(str(row.get("status") or ""), row.get("status", "")),
                    self._money(row.get("paid_amount")),
                    self._money(row.get("remaining_amount")),
                    row.get("payment_method", ""),
                ),
            )

    def _new_tournament_dialog(self) -> None:
        self._tournament_dialog(None)

    def _edit_tournament_dialog(self) -> None:
        try:
            event_id = self._selected_tournament_id()
            event = dict(getattr(self, "_tournament_rows", {}).get(event_id) or {})
            if not event:
                raise ValueError("El torneo seleccionado ya no existe.")
            self._tournament_dialog(event)
        except Exception as exc:
            messagebox.showerror("Torneos", str(exc), parent=self)

    def _tournament_dialog(self, event: dict | None) -> None:
        editing = bool(event)
        dialog = tk.Toplevel(self)
        dialog.title("Editar torneo" if editing else "Nuevo torneo")
        dialog.resizable(False, False)
        dialog.transient(self)
        values = {
            "name": tk.StringVar(value=str((event or {}).get("name") or "")),
            "date": tk.StringVar(value=str((event or {}).get("date") or dt_today())),
            "price": tk.StringVar(value=str((event or {}).get("registration_price") or "")),
            "prize": tk.StringVar(value=str((event or {}).get("prize") or "")),
            "capacity": tk.StringVar(value=str((event or {}).get("capacity") or "")),
            "alias": tk.StringVar(value=str((event or {}).get("payment_alias") or "")),
        }
        fields = (
            ("Nombre", "name"),
            ("Fecha (AAAA-MM-DD)", "date"),
            ("Precio de inscripción", "price"),
            ("Premio", "prize"),
            ("Máximo de equipos", "capacity"),
        )
        for row_index, (label, key) in enumerate(fields):
            field_label = tk.Label(
                dialog,
                text=("Fecha 📅" if key == "date" else label),
                fg=(self.BLUE if key == "date" else "black"),
                cursor=("hand2" if key == "date" else "arrow"),
            )
            field_label.grid(row=row_index, column=0, sticky="w", padx=14, pady=7)
            field_entry = tk.Entry(dialog, textvariable=values[key], width=34)
            field_entry.grid(
                row=row_index, column=1, padx=14, pady=7
            )
            if key == "date":
                open_calendar = lambda _event=None, entry=field_entry: self._show_date_picker(
                    values["date"], entry, "Fecha del torneo"
                )
                field_label.bind("<Button-1>", open_calendar)
                field_entry.bind("<Double-Button-1>", open_calendar)
                tk.Button(
                    dialog,
                    text="📅",
                    command=open_calendar,
                    relief="flat",
                    bg=self.BLUE,
                    fg="white",
                    cursor="hand2",
                    padx=7,
                    pady=3,
                ).grid(row=row_index, column=2, padx=(0, 12), pady=7)
        next_row = len(fields)
        if not editing:
            tk.Label(dialog, text="Alias de pago (opcional)").grid(
                row=next_row, column=0, sticky="w", padx=14, pady=7
            )
            tk.Entry(dialog, textvariable=values["alias"], width=34).grid(
                row=next_row, column=1, padx=14, pady=7
            )
            next_row += 1

        def save() -> None:
            try:
                if editing:
                    result = self.service.update_tournament(
                        str(event.get("event_id")),
                        name=values["name"].get(),
                        date=values["date"].get(),
                        price=values["price"].get(),
                        prize=values["prize"].get(),
                        capacity=values["capacity"].get(),
                    )
                else:
                    result = self.service.create_tournament(
                        name=values["name"].get(),
                        date=values["date"].get(),
                        price=values["price"].get(),
                        prize=values["prize"].get(),
                        capacity=values["capacity"].get(),
                        payment_alias=values["alias"].get(),
                    )
                messagebox.showinfo("Torneos", result, parent=dialog)
                dialog.destroy()
                self.refresh_all()
            except Exception as exc:
                messagebox.showerror("Torneos", str(exc), parent=dialog)

        self._action_button(
            dialog, "Guardar cambios" if editing else "Crear torneo", save, self.BLUE
        ).grid(row=next_row, column=0, columnspan=3, pady=14)

    def _delete_tournament(self) -> None:
        try:
            event_id = self._selected_tournament_id()
            event = getattr(self, "_tournament_rows", {}).get(event_id) or {}
            if not messagebox.askyesno(
                "Borrar torneo",
                f"¿Borrar {event.get('name') or event_id}?\n\n"
                "También se eliminará su archivo de inscripciones. Esta acción no se puede deshacer.",
                parent=self,
            ):
                return
            result = self.service.delete_tournament(event_id)
            messagebox.showinfo("Torneos", result, parent=self)
            self.refresh_all()
        except Exception as exc:
            messagebox.showerror("Torneos", str(exc), parent=self)

    def _registration_dialog(self, *, edit: bool) -> None:
        try:
            event_id = self._selected_tournament_id()
            current = {}
            registration_id = ""
            if edit:
                registration_id = self._selected_registration_id()
                selection = self.registration_tree.selection()[0]
                current = dict(self._registration_rows.get(selection) or {})
        except Exception as exc:
            messagebox.showerror("Inscripciones", str(exc), parent=self)
            return

        dialog = tk.Toplevel(self)
        dialog.title("Editar inscripción" if edit else "Nueva inscripción")
        dialog.resizable(False, False)
        dialog.transient(self)
        fields = (
            ("Equipo", tk.StringVar(value=str(current.get("team_name") or ""))),
            ("Responsable", tk.StringVar(value=str(current.get("contact_name") or ""))),
            ("Teléfono", tk.StringVar(value=str(current.get("phone") or ""))),
        )
        for row_index, (label, variable) in enumerate(fields):
            tk.Label(dialog, text=label).grid(row=row_index, column=0, sticky="w", padx=14, pady=8)
            tk.Entry(dialog, textvariable=variable, width=34).grid(
                row=row_index, column=1, padx=14, pady=8
            )

        def save() -> None:
            try:
                if edit:
                    result = self.service.update_tournament_registration(
                        event_id,
                        registration_id,
                        team_name=fields[0][1].get(),
                        contact_name=fields[1][1].get(),
                        phone=fields[2][1].get(),
                    )
                else:
                    result = self.service.create_tournament_registration(
                        event_id,
                        team_name=fields[0][1].get(),
                        contact_name=fields[1][1].get(),
                        phone=fields[2][1].get(),
                    )
                messagebox.showinfo("Inscripciones", result, parent=dialog)
                dialog.destroy()
                self.refresh_all()
            except Exception as exc:
                messagebox.showerror("Inscripciones", str(exc), parent=dialog)

        self._action_button(
            dialog, "Guardar cambios" if edit else "Crear inscripción", save, self.BLUE
        ).grid(row=len(fields), column=0, columnspan=2, pady=14)

    def _registration_payment(self, *, total: bool) -> None:
        try:
            registration_id = self._selected_registration_id()
            label = "el pago total" if total else "la seña"
            if not messagebox.askyesno(
                "Inscripciones",
                f"¿Confirmar {label} de la inscripción seleccionada?",
                parent=self,
            ):
                return
            result = self.service.confirm_tournament_registration(
                registration_id, total=total
            )
            messagebox.showinfo("Inscripciones", result, parent=self)
            self.refresh_all()
        except Exception as exc:
            messagebox.showerror("Inscripciones", str(exc), parent=self)

    def _cancel_registration(self) -> None:
        try:
            registration_id = self._selected_registration_id()
            if not messagebox.askyesno(
                "Liberar inscripción",
                "¿Cancelar esta inscripción y liberar el cupo?\n\n"
                "Los pagos registrados se conservarán como historial.",
                parent=self,
            ):
                return
            result = self.service.cancel_tournament_registration(registration_id)
            messagebox.showinfo("Inscripciones", result, parent=self)
            self.refresh_all()
        except Exception as exc:
            messagebox.showerror("Inscripciones", str(exc), parent=self)

    def _refresh_cases(self) -> None:
        self.case_tree.delete(*self.case_tree.get_children())
        for item in self.service.human_cases():
            self.case_tree.insert("", "end", iid=f"case:{item.get('case_id')}", values=(
                item.get("case_id", ""), str(item.get("created_at") or "")[:19], item.get("nombre", ""),
                item.get("telefono", ""), item.get("mensaje_usuario", ""), item.get("reason", ""),
            ))

    def _resolve_case(self) -> None:
        try:
            selection = self.case_tree.selection()
            if not selection:
                raise ValueError("Seleccioná un caso pendiente.")
            case_id = int(self.case_tree.item(selection[0], "values")[0])
            if not messagebox.askyesno("Administración", f"¿Resolver el caso ID {case_id} y reanudar al contacto?", parent=self):
                return
            result = self.service.resolve_case(case_id)
            messagebox.showinfo("Administración", result, parent=self)
            self.refresh_all()
        except Exception as exc:
            messagebox.showerror("Administración", str(exc), parent=self)


def dt_today() -> str:
    import datetime

    return datetime.date.today().isoformat()

