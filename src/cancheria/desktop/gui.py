from __future__ import annotations

import os
import queue
import re
import signal
import subprocess
import sys
import threading
import time
import webbrowser
from datetime import datetime
from pathlib import Path
import tkinter as tk
from tkinter import messagebox, ttk

from cancheria import __version__
from cancheria.desktop.ai_control import ensure_ai_control, read_ai_control, write_ai_paused
from cancheria.desktop.session_manager import ensure_profile, reset_profile, SessionResetError
from cancheria.config.openai_credentials import CredentialStatus, verify_openai_api_key
from cancheria.config.settings import AppSettings
from cancheria.desktop.update_service import (
    ReleaseInfo,
    UpdateError,
    check_for_update,
    launch_update_helper,
    prepare_update,
)


def _rounded_rectangle(
    canvas: tk.Canvas,
    x1: float,
    y1: float,
    x2: float,
    y2: float,
    radius: float,
    **kwargs,
):
    """Draw a dependency-free rounded rectangle on a Tk canvas."""
    radius = max(0, min(radius, (x2 - x1) / 2, (y2 - y1) / 2))
    fill = kwargs.pop("fill", "")
    outline = kwargs.pop("outline", "")
    width = float(kwargs.pop("width", 1))
    tags = kwargs.pop("tags", None)

    def draw_layer(ax1, ay1, ax2, ay2, aradius, color):
        options = {"fill": color, "outline": color}
        if tags is not None:
            options["tags"] = tags
        items = [
            canvas.create_rectangle(ax1 + aradius, ay1, ax2 - aradius, ay2, **options),
            canvas.create_rectangle(ax1, ay1 + aradius, ax2, ay2 - aradius, **options),
            canvas.create_oval(ax1, ay1, ax1 + 2 * aradius, ay1 + 2 * aradius, **options),
            canvas.create_oval(ax2 - 2 * aradius, ay1, ax2, ay1 + 2 * aradius, **options),
            canvas.create_oval(ax1, ay2 - 2 * aradius, ax1 + 2 * aradius, ay2, **options),
            canvas.create_oval(ax2 - 2 * aradius, ay2 - 2 * aradius, ax2, ay2, **options),
        ]
        return items

    items = draw_layer(x1, y1, x2, y2, radius, outline or fill)
    if fill and outline and width > 0:
        inset = max(1.0, width)
        inner_radius = max(0.0, radius - inset)
        items.extend(
            draw_layer(
                x1 + inset,
                y1 + inset,
                x2 - inset,
                y2 - inset,
                inner_radius,
                fill,
            )
        )
    elif fill and not outline:
        items = draw_layer(x1, y1, x2, y2, radius, fill)
    return items


def _draw_icon(canvas: tk.Canvas, name: str, x: float, y: float, color: str) -> None:
    """Draw compact, offline-safe line icons used by the desktop shell."""
    line = {"fill": color, "width": 2.6, "capstyle": tk.ROUND, "joinstyle": tk.ROUND}
    if name == "play":
        canvas.create_polygon(x - 6, y - 9, x + 9, y, x - 6, y + 9, fill=color, outline=color)
    elif name == "stop":
        canvas.create_rectangle(x - 7, y - 7, x + 7, y + 7, fill=color, outline=color)
    elif name == "pause":
        canvas.create_rectangle(x - 7, y - 9, x - 2, y + 9, fill=color, outline=color)
        canvas.create_rectangle(x + 2, y - 9, x + 7, y + 9, fill=color, outline=color)
    elif name == "logout":
        canvas.create_line(x - 9, y - 9, x - 9, y + 9, x, y + 9, **line)
        canvas.create_line(x - 9, y - 9, x, y - 9, **line)
        canvas.create_line(x - 3, y, x + 10, y, **line)
        canvas.create_line(x + 5, y - 5, x + 10, y, x + 5, y + 5, **line)
    elif name == "plus":
        canvas.create_line(x - 9, y, x + 9, y, **line)
        canvas.create_line(x, y - 9, x, y + 9, **line)
    elif name == "gear":
        canvas.create_oval(x - 8, y - 8, x + 8, y + 8, outline=color, width=2.6)
        canvas.create_oval(x - 3, y - 3, x + 3, y + 3, fill=color, outline=color)
        for dx, dy in ((0, -12), (0, 12), (-12, 0), (12, 0)):
            canvas.create_line(x + dx * .55, y + dy * .55, x + dx, y + dy, **line)
    elif name == "users":
        canvas.create_oval(x - 5, y - 9, x + 5, y + 1, outline=color, width=2.4)
        canvas.create_arc(x - 10, y - 1, x + 10, y + 15, start=0, extent=180, style="arc", outline=color, width=2.4)
        canvas.create_oval(x - 12, y - 6, x - 6, y, outline=color, width=2)
        canvas.create_oval(x + 6, y - 6, x + 12, y, outline=color, width=2)
    elif name == "book":
        canvas.create_line(x, y - 9, x, y + 10, **line)
        canvas.create_line(x, y - 8, x - 4, y - 10, x - 11, y - 9, x - 11, y + 8, x - 4, y + 7, x, y + 9, **line)
        canvas.create_line(x, y - 8, x + 4, y - 10, x + 11, y - 9, x + 11, y + 8, x + 4, y + 7, x, y + 9, **line)
    elif name == "refresh":
        canvas.create_arc(x - 9, y - 9, x + 9, y + 9, start=35, extent=245, style="arc", outline=color, width=2.5)
        canvas.create_polygon(x + 8, y - 7, x + 10, y + 1, x + 2, y - 1, fill=color, outline=color)
    elif name == "terminal":
        canvas.create_line(x - 9, y - 6, x - 3, y, x - 9, y + 6, **line)
        canvas.create_line(x, y + 6, x + 9, y + 6, **line)
    elif name == "profile":
        canvas.create_oval(x - 5, y - 9, x + 5, y + 1, fill=color, outline=color)
        canvas.create_arc(x - 10, y - 1, x + 10, y + 15, start=0, extent=180, style="chord", fill=color, outline=color)
    elif name == "info":
        canvas.create_oval(x - 9, y - 9, x + 9, y + 9, outline=color, width=2)
        canvas.create_text(x, y + 1, text="i", fill=color, font=("Segoe UI", 11, "bold"))


class ModernButton(tk.Canvas):
    """Rounded Canvas button that keeps the small API used by the old GUI."""

    def __init__(
        self,
        parent: tk.Widget,
        *,
        text: str,
        command,
        background: str,
        foreground: str,
        icon: str,
        border: str | None = None,
        active_background: str | None = None,
        height: int = 58,
        font=("Segoe UI", 10, "bold"),
    ) -> None:
        super().__init__(
            parent,
            width=150,
            height=height,
            bg=parent.cget("bg"),
            bd=0,
            highlightthickness=0,
            cursor="hand2",
            takefocus=True,
        )
        self._text = text
        self._command = command
        self._background = background
        self._foreground = foreground
        self._border = border or background
        self._active_background = active_background or background
        self._icon = icon
        self._font = font
        self._hovered = False
        self.bind("<Configure>", self._redraw)
        self.bind("<Enter>", self._enter)
        self.bind("<Leave>", self._leave)
        self.bind("<ButtonRelease-1>", self._invoke)
        self.bind("<Return>", self._invoke)
        self.bind("<space>", self._invoke)

    def configure(self, cnf=None, **kwargs):  # type: ignore[override]
        if cnf:
            kwargs.update(cnf)
        if "text" in kwargs:
            self._text = str(kwargs.pop("text"))
            self._redraw()
        if kwargs:
            return super().configure(**kwargs)
        return None

    config = configure

    def _enter(self, _event=None) -> None:
        self._hovered = True
        self._redraw()

    def _leave(self, _event=None) -> None:
        self._hovered = False
        self._redraw()

    def _invoke(self, _event=None) -> None:
        if callable(self._command):
            self._command()

    def _redraw(self, _event=None) -> None:
        self.delete("all")
        width = max(4, self.winfo_width())
        height = max(4, self.winfo_height())
        fill = self._active_background if self._hovered else self._background
        _rounded_rectangle(
            self,
            1.5,
            1.5,
            width - 1.5,
            height - 1.5,
            10,
            fill=fill,
            outline=self._border,
            width=1.3,
        )
        label_width = self.create_text(
            0,
            0,
            text=self._text,
            font=self._font,
        )
        bbox = self.bbox(label_width) or (0, 0, 0, 0)
        self.delete(label_width)
        text_width = bbox[2] - bbox[0]
        group_width = text_width + 34
        icon_x = max(22, (width - group_width) / 2 + 11)
        _draw_icon(self, self._icon, icon_x, height / 2, self._foreground)
        self.create_text(
            icon_x + 22,
            height / 2,
            text=self._text,
            fill=self._foreground,
            font=self._font,
            anchor="w",
        )


def _is_install_root(path: Path) -> bool:
    """Return True when *path* looks like a complete CANCHERIA installation."""
    path = Path(path)
    return (
        (path / "WPSetter.py").is_file()
        and (path / "src" / "cancheria").is_dir()
        and (path / "legacy").is_dir()
    )


def install_root() -> Path:
    """Locate the real CANCHERIA installation directory.

    Release builds place the EXEs in the project/distribution root.  The parent
    fallback intentionally supports older builds that were accidentally run from
    ``dist/`` so buttons keep finding WPSetter, docs and legacy modules.
    """
    candidates: list[Path] = []

    configured = os.environ.get("CANCHERIA_INSTALL_ROOT", "").strip()
    if configured:
        candidates.append(Path(configured).expanduser().resolve())

    if getattr(sys, "frozen", False):
        exe_dir = Path(sys.executable).resolve().parent
        candidates.extend([exe_dir, exe_dir.parent])
    else:
        candidates.append(Path(__file__).resolve().parents[3])

    candidates.append(Path.cwd().resolve())

    seen: set[Path] = set()
    for candidate in candidates:
        if candidate in seen:
            continue
        seen.add(candidate)
        if _is_install_root(candidate):
            return candidate

    # Keep deterministic diagnostics even for an incomplete installation.
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[3]


class CancheriaDesktop(tk.Tk):
    BG = "#F4F8FF"
    PANEL = "#FFFFFF"
    NAVY = "#0B1930"
    BLUE = "#1673FF"
    MUTED = "#64748B"
    BORDER = "#DCE7F5"
    GREEN = "#139B51"
    ORANGE = "#F59E0B"
    RED = "#DC2626"
    DARK_RED = "#B91C1C"
    # Las consultas silenciosas se originan sólo en una interacción real del
    # operador. El intervalo agrupa clics consecutivos para respetar el límite
    # anónimo de GitHub; BUSCAR ACTUALIZACIONES conserva la consulta manual.
    UPDATE_INTERACTION_COOLDOWN_SECONDS = 15 * 60.0

    def __init__(self) -> None:
        super().__init__()
        self.root_dir = install_root()
        self.profile_dir = self.root_dir / "wa_profile"
        self.manual_path = self.root_dir / "docs" / "MANUAL_DE_USO_CANCHERIA_DUENOS_ENCARGADOS.pdf"
        self.process: subprocess.Popen[str] | None = None
        self.admin_window: tk.Toplevel | None = None
        self.settings_window: tk.Toplevel | None = None
        self.available_update: ReleaseInfo | None = None
        self.admin_service = None
        self._admin_notification_poll_id: str | None = None
        self._update_check_in_progress = False
        self._last_interaction_update_check = 0.0
        self._announced_update_version = ""
        self.log_queue: queue.Queue[str] = queue.Queue()
        self._closing = False
        self.ai_paused = bool(
            ensure_ai_control(self.root_dir, default_paused=False).get("paused", False)
        )

        ensure_profile(self.profile_dir)

        self.title("CANCHERIA")
        self.geometry("1080x800")
        self.minsize(900, 680)
        self.configure(bg=self.BG)
        try:
            self.iconbitmap(str(self.root_dir / "assets" / "cancheria.ico"))
        except Exception:
            pass

        self._build_ui()
        # Un solo enlace a nivel de aplicación cubre la ventana principal y
        # todos sus Toplevel, incluido Administración. Cualquier clic del
        # operador puede refrescar silenciosamente la insignia sin obligarlo a
        # abrir primero el apartado Actualización.
        self.bind_all(
            "<ButtonRelease-1>",
            self._on_user_interaction_for_update,
            add="+",
        )
        self.after(120, self._drain_log_queue)
        self.after(700, self._poll_process)
        self.after(450, self._show_update_result)
        self.after(800, self._poll_admin_notifications)
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    def _build_ui(self) -> None:
        header = tk.Canvas(
            self,
            height=270,
            bg=self.BG,
            bd=0,
            highlightthickness=0,
        )
        header.pack(fill="x", padx=20, pady=(16, 10))
        header.bind("<Configure>", self._draw_header_background)

        logo_path = self.root_dir / "assets" / "cancheria-logo-cropped.png"
        if not logo_path.exists():
            logo_path = self.root_dir / "assets" / "cancheria-logo.png"
        self._logo = None
        if logo_path.exists():
            try:
                img = tk.PhotoImage(file=str(logo_path))
                factor = max(1, int(max(img.width() / 390, img.height() / 250)))
                if factor > 1:
                    img = img.subsample(factor, factor)
                self._logo = img
                self.logo_label = tk.Label(header, image=img, bg=self.PANEL, bd=0)
                self.logo_label.place(relx=.5, y=12, anchor="n")
            except Exception:
                pass

        if self._logo is None:
            self.logo_label = tk.Label(
                header,
                text="CANCHERIA",
                font=("Segoe UI", 30, "bold"),
                fg=self.NAVY,
                bg=self.PANEL,
                bd=0,
            )
            self.logo_label.place(relx=.5, rely=.47, anchor="center")

        self.header_subtitle = tk.Label(
            header,
            text="Agente de reservas · Panel de escritorio",
            font=("Segoe UI", 13, "bold"),
            fg="#294A78",
            bg=self.PANEL,
            bd=0,
        )
        self.header_subtitle.place(relx=.5, rely=1.0, y=-23, anchor="s")

        status_row = tk.Frame(
            self,
            bg=self.PANEL,
            highlightbackground=self.BORDER,
            highlightthickness=1,
            bd=0,
        )
        status_row.pack(fill="x", padx=20, pady=(0, 10), ipady=12)
        left_status = tk.Frame(status_row, bg=self.PANEL)
        left_status.pack(side="left", padx=18)
        self.status_dot = tk.Canvas(
            left_status,
            width=18,
            height=18,
            bg=self.PANEL,
            highlightthickness=0,
        )
        self.status_dot.pack(side="left", padx=(0, 10))
        self._draw_status_dot("#94A3B8")
        tk.Label(
            left_status,
            text="Estado:",
            font=("Segoe UI", 11, "bold"),
            bg=self.PANEL,
            fg=self.NAVY,
        ).pack(side="left")
        self.status_var = tk.StringVar(value="Apagado")
        self.status_label = tk.Label(
            left_status,
            textvariable=self.status_var,
            font=("Segoe UI", 11, "bold"),
            bg="#E8EEF6",
            fg=self.MUTED,
            padx=12,
            pady=3,
        )
        self.status_label.pack(side="left", padx=(9, 0))
        profile = tk.Frame(status_row, bg=self.PANEL)
        profile.pack(side="right", padx=18)
        profile_icon = tk.Canvas(profile, width=26, height=26, bg=self.PANEL, highlightthickness=0)
        profile_icon.pack(side="left", padx=(0, 8))
        _draw_icon(profile_icon, "profile", 13, 13, "#7890B2")
        tk.Label(
            profile,
            text=f"Perfil: {self.profile_dir.name}",
            font=("Segoe UI", 10),
            bg=self.PANEL,
            fg="#486487",
        ).pack(side="left")

        actions = tk.Frame(self, bg=self.BG)
        actions.pack(fill="x", padx=16, pady=(0, 10))
        for col in range(5):
            actions.grid_columnconfigure(col, weight=1)

        self.btn_on = self._button(actions, "ENCENDER", self.start_agent, self.GREEN, "play")
        self.btn_off = self._button(actions, "APAGAR", self.stop_agent, self.RED, "stop")
        self.btn_ai_pause = self._button(
            actions,
            "REANUDAR IA" if self.ai_paused else "PAUSAR IA",
            self.toggle_ai_pause,
            self.ORANGE,
            "pause",
        )
        self.btn_logout = self._button(actions, "CERRAR SESIÓN", self.close_session, self.DARK_RED, "logout")
        self.btn_new = self._button(actions, "NUEVA SESIÓN", self.new_session, self.BLUE, "plus")
        self.btn_on.grid(row=0, column=0, sticky="ew", padx=4)
        self.btn_off.grid(row=0, column=1, sticky="ew", padx=4)
        self.btn_ai_pause.grid(row=0, column=2, sticky="ew", padx=4)
        self.btn_logout.grid(row=0, column=3, sticky="ew", padx=4)
        self.btn_new.grid(row=0, column=4, sticky="ew", padx=4)

        secondary = tk.Frame(self, bg=self.BG)
        secondary.pack(fill="x", padx=16, pady=(0, 10))
        for col, weight in enumerate((1, 1, 1, 1, 1)):
            secondary.grid_columnconfigure(col, weight=weight)
        self.btn_config = ModernButton(
            secondary,
            text="CONFIGURACIÓN",
            command=self.open_configurator,
            background="#EAF3FF",
            foreground="#1263D8",
            border="#BBD8FF",
            active_background="#DCEBFF",
            icon="gear",
            height=54,
        )
        self.btn_config.grid(row=0, column=0, sticky="ew", padx=4)
        admin_button_holder = tk.Frame(secondary, bg=self.BG)
        admin_button_holder.grid(row=0, column=1, sticky="nsew", padx=4)
        self.btn_admin = ModernButton(
            admin_button_holder,
            text="ADMINISTRACIÓN",
            command=self.open_admin_panel,
            background=self.NAVY,
            foreground="white",
            active_background="#142B50",
            icon="users",
            height=54,
        )
        self.btn_admin.pack(fill="both", expand=True)
        self.admin_notification_badge = tk.Label(
            admin_button_holder,
            text="",
            bg="#e31b23",
            fg="white",
            font=("Segoe UI", 8, "bold"),
            padx=5,
            pady=1,
            cursor="hand2",
        )
        self.admin_notification_badge.bind("<Button-1>", lambda _event: self.open_admin_panel())
        self.btn_manual = ModernButton(
            secondary,
            text="Abrir manual",
            command=self.open_manual,
            background=self.PANEL,
            foreground=self.NAVY,
            border="#C7D5E8",
            active_background="#EEF4FF",
            icon="book",
            height=54,
        )
        self.btn_manual.grid(row=0, column=2, sticky="ew", padx=4)
        update_button_holder = tk.Frame(secondary, bg=self.BG)
        update_button_holder.grid(row=0, column=3, sticky="nsew", padx=4)
        self.btn_settings = ModernButton(
            update_button_holder,
            text="ACTUALIZACIÓN",
            command=self.open_settings,
            background=self.PANEL,
            foreground="#1263D8",
            border="#BBD8FF",
            active_background="#EEF4FF",
            icon="refresh",
            height=54,
        )
        self.btn_settings.pack(fill="both", expand=True)
        self.update_notification_badge = tk.Label(
            update_button_holder,
            text="",
            bg="#e31b23",
            fg="white",
            font=("Segoe UI", 8, "bold"),
            padx=5,
            pady=1,
            cursor="hand2",
        )
        self.update_notification_badge.bind(
            "<Button-1>", lambda _event: self.open_settings()
        )
        info_holder = tk.Frame(secondary, bg=self.BG)
        info_holder.grid(row=0, column=4, sticky="ew", padx=(10, 0))
        info_icon = tk.Canvas(info_holder, width=24, height=24, bg=self.BG, highlightthickness=0)
        info_icon.pack(side="left")
        _draw_icon(info_icon, "info", 12, 12, "#7890B2")
        tk.Label(
            info_holder,
            text="Reservas, agenda y versión\ndel sistema.",
            justify="left",
            font=("Segoe UI", 8),
            bg=self.BG,
            fg=self.MUTED,
        ).pack(side="left", padx=(4, 0))

        log_panel = tk.Frame(
            self,
            bg=self.PANEL,
            highlightbackground=self.BORDER,
            highlightthickness=1,
            bd=0,
        )
        log_panel.pack(fill="both", expand=True, padx=20, pady=(0, 16))
        log_header = tk.Frame(log_panel, bg=self.PANEL)
        log_header.pack(fill="x", padx=14, pady=(10, 7))
        terminal_box = tk.Canvas(log_header, width=32, height=32, bg=self.PANEL, highlightthickness=0)
        terminal_box.pack(side="left")
        _rounded_rectangle(terminal_box, 1, 1, 31, 31, 7, fill=self.NAVY, outline=self.NAVY)
        _draw_icon(terminal_box, "terminal", 16, 16, "white")
        tk.Label(
            log_header,
            text="Actividad",
            font=("Segoe UI", 12, "bold"),
            fg=self.NAVY,
            bg=self.PANEL,
        ).pack(side="left", padx=(9, 0))
        event_hint = tk.Frame(log_header, bg=self.PANEL)
        event_hint.pack(side="right")
        tk.Label(event_hint, text="●", font=("Segoe UI", 10), fg=self.BLUE, bg=self.PANEL).pack(side="left")
        tk.Label(
            event_hint,
            text="Panel de eventos del sistema",
            font=("Segoe UI", 9),
            fg="#6681A5",
            bg=self.PANEL,
        ).pack(side="left", padx=(5, 0))

        console = tk.Frame(log_panel, bg=self.NAVY)
        console.pack(fill="both", expand=True, padx=12, pady=(0, 12))
        self.log = tk.Text(
            console,
            height=16,
            wrap="word",
            bg=self.NAVY,
            fg="#E2E8F0",
            insertbackground="white",
            selectbackground="#214777",
            font=("Cascadia Mono", 9),
            relief="flat",
            bd=0,
            padx=12,
            pady=10,
        )
        log_scroll = ttk.Scrollbar(console, orient="vertical", command=self.log.yview)
        self.log.configure(yscrollcommand=log_scroll.set)
        log_scroll.pack(side="right", fill="y")
        self.log.pack(side="left", fill="both", expand=True)
        self.log.tag_configure("timestamp", foreground="#8FB8E8")
        self.log.tag_configure("info", foreground="#7CC4FF")
        self.log.tag_configure("success", foreground="#4ADE80")
        self.log.tag_configure("warning", foreground="#FBBF24")
        self.log.tag_configure("error", foreground="#F87171")
        self.log.tag_configure("normal", foreground="#E2E8F0")
        self.log.configure(state="disabled")
        self._append_log("CANCHERIA listo. Presioná ENCENDER para usar la sesión guardada o NUEVA SESIÓN para escanear un QR nuevo.")

    def _draw_header_background(self, event=None) -> None:
        canvas = event.widget if event is not None else None
        if not isinstance(canvas, tk.Canvas):
            return
        width = max(10, canvas.winfo_width())
        height = max(10, canvas.winfo_height())
        canvas.delete("header_decor")
        _rounded_rectangle(
            canvas,
            1,
            1,
            width - 1,
            height - 1,
            18,
            fill=self.PANEL,
            outline=self.BORDER,
            width=1,
            tags="header_decor",
        )
        canvas.create_polygon(2, 2, width * .18, 2, width * .08, height * .46, 2, height * .72, fill="#D8ECFF", outline="", tags="header_decor")
        canvas.create_polygon(width - 2, height - 2, width * .78, height - 2, width - 2, height * .42, fill="#D7EBFF", outline="", tags="header_decor")
        canvas.create_polygon(width - 2, height * .2, width - 2, height * .72, width * .88, height - 2, width * .94, height * .35, fill="#EAF4FF", outline="", tags="header_decor")
        for offset in (0, 15, 30):
            canvas.create_arc(width * .04 + offset, height * .38, width * .30 + offset, height * 1.18, start=52, extent=94, style="arc", outline="#E8F3FF", width=2, tags="header_decor")
        canvas.tag_lower("header_decor")

    def _button(self, parent: tk.Widget, label: str, command, color: str, icon: str) -> ModernButton:
        return ModernButton(
            parent,
            text=label,
            command=command,
            background=color,
            foreground="white",
            active_background=color,
            icon=icon,
            height=62,
            font=("Segoe UI", 10, "bold"),
        )

    def _append_log(self, text: str) -> None:
        if not text:
            return
        clean = text.rstrip()
        lowered = clean.casefold()
        if any(token in lowered for token in ("error", "falló", "fallo", "excepción", "exception", "❌")):
            tag = "error"
        elif any(token in lowered for token in ("advertencia", "atención", "⚠", "cancelada")):
            tag = "warning"
        elif any(token in lowered for token in ("correctamente", "iniciado", "reanudada", "abierto", "✓", "✅")):
            tag = "success"
        elif any(token in lowered for token in ("listo", "perfil", "preparando", "▶", "[gui]")):
            tag = "info"
        else:
            tag = "normal"
        self.log.configure(state="normal")
        if not re.match(r"^\s*\[\d{1,2}:\d{2}(?::\d{2})?\]", clean):
            self.log.insert("end", f"[{datetime.now():%H:%M:%S}] ", "timestamp")
        self.log.insert("end", clean + "\n", tag)
        self.log.see("end")
        self.log.configure(state="disabled")

    def _set_status(self, text: str, color: str) -> None:
        self.status_var.set(text)
        self.status_label.configure(fg=color)
        self._draw_status_dot(color)

    def _draw_status_dot(self, color: str) -> None:
        if not hasattr(self, "status_dot"):
            return
        self.status_dot.delete("all")
        self.status_dot.create_oval(2, 2, 16, 16, fill=color, outline=color)

    def _worker_command(self) -> list[str]:
        profile = str(self.profile_dir.resolve())
        if getattr(sys, "frozen", False):
            return [sys.executable, "--worker", "--profile", profile]
        launcher = self.root_dir / "cancheria_desktop.py"
        return [sys.executable, str(launcher), "--worker", "--profile", profile]

    def start_agent(self) -> None:
        if self.process and self.process.poll() is None:
            self._append_log("El agente ya está encendido.")
            return

        wp = self.root_dir / "WPSetter.py"
        if not wp.exists():
            messagebox.showerror("CANCHERIA", f"No encontré WPSetter.py en:\n{self.root_dir}")
            return

        ensure_profile(self.profile_dir)
        env = os.environ.copy()
        env["PYTHONIOENCODING"] = "utf-8"
        env["PYTHONUTF8"] = "1"
        env["CANCHERIA_DESKTOP"] = "1"

        kwargs: dict = {
            "cwd": str(self.root_dir),
            "stdout": subprocess.PIPE,
            "stderr": subprocess.STDOUT,
            "text": True,
            "encoding": "utf-8",
            "errors": "replace",
            "bufsize": 1,
            "env": env,
        }
        if os.name == "nt":
            kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_NO_WINDOW
        else:
            kwargs["start_new_session"] = True

        try:
            self.process = subprocess.Popen(self._worker_command(), **kwargs)
        except Exception as exc:
            self.process = None
            self._set_status("Error", self.RED)
            messagebox.showerror("CANCHERIA", f"No pude iniciar WPSetter:\n{exc}")
            return

        self._refresh_ai_pause_state()
        self._set_running_status()
        self._append_log(f"▶ CANCHERIA iniciado con profile: {self.profile_dir.name}")
        threading.Thread(target=self._read_worker_output, args=(self.process,), daemon=True).start()
        threading.Thread(target=self._verify_api_in_background, daemon=True).start()

    def _verify_api_in_background(self) -> None:
        """Report credential health without ever blocking WhatsApp startup."""
        try:
            credential_check = verify_openai_api_key(AppSettings.from_env().openai_api_key)
        except Exception as exc:
            self.log_queue.put(
                "⚠ No pude verificar la API de OpenAI, pero WhatsApp y las alertas "
                f"siguen encendidos. Detalle: {exc}"
            )
            return
        if credential_check.status == CredentialStatus.VALID:
            self.log_queue.put("✓ API de OpenAI verificada correctamente.")
            return
        self.log_queue.put(
            f"⚠ {credential_check.message} WhatsApp y las alertas siguen encendidos; "
            "la IA no podrá responder hasta guardar una clave válida en CONFIGURACIÓN."
        )

    def _read_worker_output(self, process: subprocess.Popen[str]) -> None:
        stream = process.stdout
        if stream is None:
            return
        try:
            for line in iter(stream.readline, ""):
                if line:
                    self.log_queue.put(line.rstrip("\r\n"))
                if process.poll() is not None:
                    break
        except Exception as exc:
            self.log_queue.put(f"[GUI] Error leyendo salida: {exc}")

    def _drain_log_queue(self) -> None:
        try:
            while True:
                self._append_log(self.log_queue.get_nowait())
        except queue.Empty:
            pass
        if not self._closing:
            self.after(120, self._drain_log_queue)

    def _poll_process(self) -> None:
        if self.process and self.process.poll() is not None:
            code = self.process.returncode
            self._append_log(f"■ Proceso finalizado (código {code}).")
            self._set_status("Apagado", self.MUTED if code == 0 else self.RED)
            self.process = None
        elif self.process and self.process.poll() is None:
            self._refresh_ai_pause_state()
            self._set_running_status()
        if not self._closing:
            self.after(700, self._poll_process)

    def _stop_process(self) -> None:
        process = self.process
        if not process or process.poll() is not None:
            self.process = None
            return

        pid = process.pid
        self._append_log("⏹ Deteniendo automatización y Chrome...")
        try:
            if os.name == "nt":
                subprocess.run(
                    ["taskkill", "/PID", str(pid), "/T", "/F"],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    timeout=12,
                )
            else:
                try:
                    os.killpg(os.getpgid(pid), signal.SIGTERM)
                except Exception:
                    process.terminate()
                try:
                    process.wait(timeout=8)
                except subprocess.TimeoutExpired:
                    try:
                        os.killpg(os.getpgid(pid), signal.SIGKILL)
                    except Exception:
                        process.kill()
        finally:
            try:
                process.wait(timeout=3)
            except Exception:
                pass
            self.process = None
            time.sleep(0.5)

    def _refresh_ai_pause_state(self) -> None:
        self.ai_paused = bool(
            read_ai_control(
                self.root_dir,
                default_paused=getattr(self, "ai_paused", False),
            ).get("paused", False)
        )
        if hasattr(self, "btn_ai_pause"):
            self.btn_ai_pause.configure(
                text="REANUDAR IA" if self.ai_paused else "PAUSAR IA"
            )

    def _set_running_status(self) -> None:
        if self.ai_paused:
            self._set_status("Encendido · IA pausada", self.ORANGE)
        else:
            self._set_status("Encendido", self.GREEN)

    def stop_agent(self) -> None:
        if not self.process or self.process.poll() is not None:
            self._set_status("Apagado", self.MUTED)
            self._append_log("CANCHERIA ya estaba detenido. La sesión de WhatsApp sigue guardada.")
            return
        self._stop_process()
        self._set_status("Apagado", self.MUTED)
        self._append_log("⏹ Apagado. El perfil wa_profile se conserva; ENCENDER retoma la misma sesión.")

    def toggle_ai_pause(self) -> None:
        if not self.process or self.process.poll() is not None:
            self._set_status("Apagado", self.MUTED)
            self._append_log("Encendé CANCHERIA antes de pausar o reanudar la IA.")
            return
        paused = not self.ai_paused
        try:
            write_ai_paused(paused, self.root_dir, source="desktop_gui")
        except OSError as exc:
            messagebox.showerror(
                "CANCHERIA · Pausa IA",
                f"No pude cambiar el estado de la IA:\n{exc}",
            )
            return
        self.ai_paused = paused
        self._refresh_ai_pause_state()
        self._set_running_status()
        if paused:
            self._append_log(
                "⏸ IA pausada. WhatsApp permanece abierto; CANCHERIA no responderá "
                "automáticamente a los clientes."
            )
        else:
            self._append_log("▶ IA reanudada. CANCHERIA vuelve a responder a los clientes.")

    def close_session(self) -> None:
        ok = messagebox.askyesno(
            "Cerrar sesión",
            "Esto detendrá CANCHERIA y borrará el perfil local wa_profile.\n\n"
            "La próxima vez tendrás que escanear el QR de WhatsApp nuevamente.\n\n¿Continuar?",
        )
        if not ok:
            return
        self._stop_process()
        try:
            reset_profile(self.profile_dir)
        except SessionResetError as exc:
            self._set_status("Error", self.RED)
            messagebox.showerror("CANCHERIA", str(exc))
            return
        self._set_status("Sesión cerrada", self.MUTED)
        self._append_log("🔒 Sesión local cerrada. wa_profile quedó limpio.")

    def new_session(self) -> None:
        ok = messagebox.askyesno(
            "Nueva sesión",
            "Se eliminará la sesión local actual y se abrirá WhatsApp con un perfil limpio para escanear un nuevo QR.\n\n"
            "Los datos de reservas y configuración NO se borran.\n\n¿Crear nueva sesión?",
        )
        if not ok:
            return
        self._stop_process()
        try:
            reset_profile(self.profile_dir)
        except SessionResetError as exc:
            self._set_status("Error", self.RED)
            messagebox.showerror("CANCHERIA", str(exc))
            return
        self._set_status("Preparando nueva sesión", self.BLUE)
        self._append_log("🆕 Perfil wa_profile recreado. Abriendo WhatsApp para un QR nuevo...")
        self.after(350, self.start_agent)

    def open_configurator(self) -> None:
        """Open the standalone business configurator.

        In the Windows distribution we prefer ``configurador_cancheria.exe``.
        Source checkouts fall back to the Python launcher. Configuration writes
        are persistent, but an already-running agent must be restarted to load
        changed Python configuration values.
        """
        if self.process and self.process.poll() is None:
            ok = messagebox.askyesno(
                "Configuración",
                "CANCHERIA está encendido. Podés editar la configuración ahora, "
                "pero los cambios se aplicarán completamente al reiniciar el agente.\n\n"
                "¿Abrir el configurador igualmente?",
            )
            if not ok:
                return

        if getattr(sys, "frozen", False):
            configurator = self.root_dir / "configurador_cancheria.exe"
            if not configurator.exists():
                messagebox.showerror(
                    "CANCHERIA",
                    "No encontré configurador_cancheria.exe junto a cancheria.exe.\n\n"
                    "Volvé a extraer la distribución completa de CANCHERIA.",
                )
                return
            command = [str(configurator)]
        else:
            configurator = self.root_dir / "configurador_cancheria.py"
            if not configurator.exists():
                messagebox.showerror("CANCHERIA", f"No encontré el configurador en:\n{configurator}")
                return
            command = [sys.executable, str(configurator)]

        env = os.environ.copy()
        env["CANCHERIA_INSTALL_ROOT"] = str(self.root_dir)
        kwargs: dict = {"cwd": str(self.root_dir), "env": env}
        if os.name == "nt":
            kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
        try:
            subprocess.Popen(command, **kwargs)
            self._append_log("⚙ Configurador de CANCHERIA abierto.")
        except Exception as exc:
            messagebox.showerror("CANCHERIA", f"No pude abrir el configurador:\n{exc}")

    def open_admin_panel(self) -> None:
        """Open the visual counterpart of the WhatsApp admin commands."""
        if self.admin_window is not None and self.admin_window.winfo_exists():
            self.admin_window.deiconify()
            self.admin_window.lift()
            self.admin_window.focus_force()
            return
        try:
            from cancheria.admin.desktop_service import DesktopAdminService
            from cancheria.desktop.admin_panel import AdminPanel

            service = self._get_admin_service()
            self.admin_window = AdminPanel(
                self,
                service,
                self.open_configurator,
                self._update_admin_notification_badge,
            )
            self.admin_window.protocol(
                "WM_DELETE_WINDOW",
                lambda: (self.admin_window.destroy(), setattr(self, "admin_window", None)),
            )
            self._append_log("🛠 Panel de administración abierto.")
        except Exception as exc:
            self.admin_window = None
            messagebox.showerror("CANCHERIA", f"No pude abrir Administración:\n{exc}")

    def _get_admin_service(self):
        if self.admin_service is None:
            from cancheria.admin.desktop_service import DesktopAdminService

            self.admin_service = DesktopAdminService(self.root_dir)
        return self.admin_service

    def _update_admin_notification_badge(self, counts: dict[str, int]) -> None:
        total = max(0, int(counts.get("total", 0) or 0))
        if total:
            self.admin_notification_badge.configure(text="99+" if total > 99 else str(total))
            self.admin_notification_badge.place(relx=1.0, rely=0.0, x=-2, y=2, anchor="ne")
            self.admin_notification_badge.lift()
        else:
            self.admin_notification_badge.place_forget()

    def _poll_admin_notifications(self) -> None:
        self._admin_notification_poll_id = None
        if self._closing:
            return
        try:
            counts = self._get_admin_service().notification_counts()
            self._update_admin_notification_badge(counts)
        except Exception:
            # Runtime files can be replaced atomically by the agent. Retry on
            # the next cycle without distracting the operator with a popup.
            pass
        if not self._closing:
            self._admin_notification_poll_id = self.after(3000, self._poll_admin_notifications)

    def _update_update_notification_badge(self, release: ReleaseInfo | None) -> None:
        if release is not None:
            self.update_notification_badge.configure(text="1")
            self.update_notification_badge.place(
                relx=1.0, rely=0.0, x=-2, y=2, anchor="ne"
            )
            self.update_notification_badge.lift()
        else:
            self.update_notification_badge.place_forget()

    def _on_user_interaction_for_update(self, _event=None) -> None:
        """Refresh the update badge from normal GUI activity.

        Tk's application-wide binding includes buttons, tabs and controls in
        the administration Toplevel. There is intentionally no startup or
        periodic timer: a monotonic cooldown groups normal click bursts into a
        single GitHub request.
        """
        if self._closing:
            return
        if self.available_update is not None:
            self._update_update_notification_badge(self.available_update)
            return

        now = time.monotonic()
        if (
            self._last_interaction_update_check > 0
            and now - self._last_interaction_update_check
            < self.UPDATE_INTERACTION_COOLDOWN_SECONDS
        ):
            return
        self._last_interaction_update_check = now

        if self._update_check_in_progress:
            return
        self._start_update_check(show_status=False)

    def _show_update_result(self) -> None:
        if "CANCHERIA_UPDATE_FINISHED" not in os.environ:
            return
        status_path = self.root_dir / "Backups" / "ultima_actualizacion.json"
        try:
            import json

            status = json.loads(status_path.read_text(encoding="utf-8"))
        except Exception:
            messagebox.showwarning(
                "CANCHERIA · Actualización",
                "CANCHERIA volvió a iniciarse, pero no se pudo leer el resultado de la actualización.",
            )
            return
        if status.get("success"):
            version = status.get("version") or os.environ.get("CANCHERIA_UPDATE_FINISHED", "")
            self._append_log(f"✓ CANCHERIA se actualizó correctamente a la versión {version}.")
            messagebox.showinfo(
                "CANCHERIA actualizado",
                f"La versión {version} quedó instalada correctamente.\n\n"
                f"Respaldo creado en:\n{status.get('backup', '')}",
            )
        else:
            detail = status.get("detail") or "Error desconocido."
            self._append_log(f"⚠ La actualización no pudo completarse: {detail}")
            messagebox.showerror(
                "CANCHERIA · Actualización",
                "La actualización no pudo completarse y se restauró la versión anterior.\n\n"
                f"Detalle: {detail}",
            )

    def open_settings(self) -> None:
        if self.settings_window is not None and self.settings_window.winfo_exists():
            self.settings_window.deiconify()
            self.settings_window.lift()
            self.settings_window.focus_force()
            return

        window = tk.Toplevel(self)
        self.settings_window = window
        window.title("CANCHERIA · Actualización")
        window.geometry("680x570")
        window.minsize(600, 520)
        window.configure(bg=self.BG)
        window.transient(self)
        window.protocol("WM_DELETE_WINDOW", lambda: (window.destroy(), setattr(self, "settings_window", None)))

        panel = tk.Frame(window, bg=self.PANEL, bd=1, relief="solid")
        panel.pack(fill="both", expand=True, padx=20, pady=20)
        tk.Label(
            panel,
            text="⬆ Actualización de CANCHERIA",
            font=("Segoe UI", 18, "bold"),
            fg=self.NAVY,
            bg=self.PANEL,
        ).pack(anchor="w", padx=20, pady=(18, 4))
        tk.Label(
            panel,
            text=f"Versión instalada: {__version__}",
            font=("Segoe UI", 10, "bold"),
            fg=self.MUTED,
            bg=self.PANEL,
        ).pack(anchor="w", padx=20)

        self.update_status_var = tk.StringVar(value="Comprobando la última versión publicada...")
        tk.Label(
            panel,
            textvariable=self.update_status_var,
            wraplength=580,
            justify="left",
            font=("Segoe UI", 10),
            fg=self.NAVY,
            bg=self.PANEL,
        ).pack(fill="x", padx=20, pady=(18, 8))

        self.update_progress = ttk.Progressbar(panel, mode="determinate", maximum=100)
        self.update_progress.pack(fill="x", padx=20, pady=(0, 12))

        tk.Label(
            panel,
            text="Novedades de la versión",
            font=("Segoe UI", 10, "bold"),
            fg=self.NAVY,
            bg=self.PANEL,
        ).pack(anchor="w", padx=20)
        self.update_notes = tk.Text(
            panel,
            height=9,
            wrap="word",
            font=("Segoe UI", 9),
            bg="#f8fafc",
            fg=self.NAVY,
            relief="solid",
            bd=1,
            padx=8,
            pady=8,
        )
        self.update_notes.pack(fill="both", expand=True, padx=20, pady=(5, 12))
        self.update_notes.insert("1.0", "Todavía no se consultó una nueva versión.")
        self.update_notes.configure(state="disabled")

        buttons = tk.Frame(panel, bg=self.PANEL)
        buttons.pack(fill="x", padx=20, pady=(0, 18))
        self.btn_check_update = tk.Button(
            buttons,
            text="BUSCAR ACTUALIZACIONES",
            command=self._check_updates,
            font=("Segoe UI", 10, "bold"),
            bg=self.NAVY,
            fg="white",
            activebackground=self.NAVY,
            activeforeground="white",
            relief="flat",
            padx=14,
            pady=9,
            cursor="hand2",
        )
        self.btn_check_update.pack(side="left")
        self.btn_install_update = tk.Button(
            buttons,
            text="ACTUALIZAR VERSIÓN",
            command=self._install_available_update,
            state="disabled",
            font=("Segoe UI", 10, "bold"),
            bg=self.GREEN,
            fg="white",
            activebackground=self.GREEN,
            activeforeground="white",
            disabledforeground="#cbd5e1",
            relief="flat",
            padx=14,
            pady=9,
            cursor="hand2",
        )
        self.btn_install_update.pack(side="left", padx=(8, 0))

        creator_panel = tk.Frame(
            panel,
            bg="#eef4ff",
            highlightbackground="#c9dcff",
            highlightthickness=1,
        )
        creator_panel.pack(fill="x", padx=20, pady=(0, 18))
        tk.Label(
            creator_panel,
            text="Software creado por Sebastián Bocek de AIBROTHERS",
            font=("Segoe UI", 10, "bold"),
            fg=self.NAVY,
            bg="#eef4ff",
        ).pack(anchor="w", padx=12, pady=(9, 2))
        contacts = tk.Frame(creator_panel, bg="#eef4ff")
        contacts.pack(anchor="w", padx=12, pady=(0, 9))

        def contact_link(label: str, url: str) -> None:
            link = tk.Label(
                contacts,
                text=label,
                font=("Segoe UI", 9, "underline"),
                fg="#0b63ce",
                bg="#eef4ff",
                cursor="hand2",
            )
            link.pack(side="left", padx=(0, 16))
            link.bind("<Button-1>", lambda _event, target=url: webbrowser.open_new_tab(target))

        contact_link("GitHub: @sebastianbocek", "https://github.com/sebastianbocek")
        contact_link(
            "Email: sebastianbocek.marketing@gmail.com",
            "mailto:sebastianbocek.marketing@gmail.com",
        )
        contact_link("WhatsApp", "https://wa.me/5493513441882")

        if self.available_update is not None:
            self._render_update_check_result(self.available_update, "")
        self.after(120, self._check_updates)

    def _set_update_notes(self, text: str) -> None:
        if self.settings_window is None or not self.settings_window.winfo_exists():
            return
        self.update_notes.configure(state="normal")
        self.update_notes.delete("1.0", "end")
        self.update_notes.insert("1.0", text.strip() or "Sin notas de versión.")
        self.update_notes.configure(state="disabled")

    def _check_updates(self) -> None:
        self._start_update_check(show_status=True)

    def _start_update_check(self, *, show_status: bool) -> None:
        settings_open = self.settings_window is not None and self.settings_window.winfo_exists()
        if self._update_check_in_progress:
            if show_status and settings_open:
                self.update_status_var.set("Ya se está comprobando la última versión...")
            return
        self._update_check_in_progress = True
        if show_status and settings_open:
            self.btn_check_update.configure(state="disabled")
            self.btn_install_update.configure(state="disabled")
            self.update_progress.configure(value=0)
            self.update_status_var.set("Consultando la última versión publicada en GitHub...")

        def worker() -> None:
            try:
                release = check_for_update(__version__)
            except Exception as exc:
                message = str(exc)
                self.after(0, lambda: self._finish_update_check(None, message))
                return
            self.after(0, lambda: self._finish_update_check(release, ""))

        threading.Thread(target=worker, daemon=True).start()

    def _render_update_check_result(self, release: ReleaseInfo | None, error: str) -> None:
        if self.settings_window is None or not self.settings_window.winfo_exists():
            return
        self.btn_check_update.configure(state="normal")
        if error:
            self.update_status_var.set(f"No se pudo buscar la actualización: {error}")
            self._set_update_notes("Volvé a intentarlo cuando tengas conexión a Internet.")
            self.btn_install_update.configure(
                state="normal" if self.available_update is not None else "disabled"
            )
            return
        if release is None:
            self.update_status_var.set(f"CANCHERIA {__version__} ya es la versión más reciente.")
            self._set_update_notes("No hay actualizaciones pendientes.")
            self.btn_install_update.configure(state="disabled")
            return
        self.update_status_var.set(
            f"Nueva versión disponible: {release.version} · {release.asset.size / (1024 * 1024):.1f} MB"
        )
        self._set_update_notes(release.notes)
        self.btn_install_update.configure(state="normal")

    def _finish_update_check(self, release: ReleaseInfo | None, error: str) -> None:
        self._update_check_in_progress = False
        if not error:
            self.available_update = release
            self._update_update_notification_badge(release)
            if (
                release is not None
                and release.version != self._announced_update_version
            ):
                self._announced_update_version = release.version
                self._append_log(
                    f"🔴 Nueva versión disponible: CANCHERIA {release.version}. "
                    "Abrí ACTUALIZACIÓN para instalarla."
                )
        self._render_update_check_result(release, error)

    def _install_available_update(self) -> None:
        release = self.available_update
        if release is None:
            return
        if not messagebox.askyesno(
            "Actualizar CANCHERIA",
            f"Se instalará CANCHERIA {release.version}.\n\n"
            "Antes de actualizar se creará un respaldo automático. "
            "La aplicación se cerrará y volverá a abrir al terminar.\n\n"
            "¿Continuar?",
            parent=self.settings_window,
        ):
            return

        self._stop_process()
        self.btn_check_update.configure(state="disabled")
        self.btn_install_update.configure(state="disabled")
        self.update_status_var.set("Descargando y verificando la actualización...")
        self.update_progress.configure(value=0)

        def progress(downloaded: int, total: int) -> None:
            percent = min(100, int(downloaded * 100 / max(total, 1)))
            self.after(0, lambda value=percent: self.update_progress.configure(value=value))

        def worker() -> None:
            try:
                prepared = prepare_update(release, self.root_dir, progress)
            except Exception as exc:
                message = str(exc)
                self.after(0, lambda: self._update_install_failed(message))
                return
            self.after(0, lambda: self._launch_prepared_update(release, prepared))

        threading.Thread(target=worker, daemon=True).start()

    def _update_install_failed(self, message: str) -> None:
        if self.settings_window is not None and self.settings_window.winfo_exists():
            self.btn_check_update.configure(state="normal")
            self.btn_install_update.configure(state="normal")
            self.update_status_var.set(f"La actualización fue cancelada: {message}")
        self._append_log(f"⚠ Actualización cancelada: {message}")
        messagebox.showerror("CANCHERIA · Actualización", message, parent=self.settings_window)

    def _launch_prepared_update(
        self,
        release: ReleaseInfo,
        prepared: tuple[Path, Path, Path],
    ) -> None:
        work_dir, staged_dir, backup_zip = prepared
        try:
            launch_update_helper(
                self.root_dir,
                work_dir,
                staged_dir,
                release.version,
                backup_zip,
            )
        except UpdateError as exc:
            self._update_install_failed(str(exc))
            return
        self._append_log(
            f"⬆ Actualización {release.version} verificada. Cerrando CANCHERIA para instalarla..."
        )
        self.update_status_var.set("Paquete verificado. CANCHERIA se reiniciará automáticamente...")
        self._closing = True
        self.after(350, self.destroy)

    def open_manual(self) -> None:
        if not self.manual_path.exists():
            messagebox.showwarning("CANCHERIA", "No encontré el manual PDF dentro de docs/.")
            return
        try:
            if os.name == "nt":
                os.startfile(str(self.manual_path))  # type: ignore[attr-defined]
            else:
                webbrowser.open(self.manual_path.as_uri())
        except Exception as exc:
            messagebox.showerror("CANCHERIA", f"No pude abrir el manual:\n{exc}")

    def _on_close(self) -> None:
        if self.process and self.process.poll() is None:
            ok = messagebox.askyesno(
                "Salir de CANCHERIA",
                "El agente está encendido. ¿Querés detenerlo y cerrar el panel?",
            )
            if not ok:
                return
        self._closing = True
        self._stop_process()
        self.destroy()


def main() -> int:
    app = CancheriaDesktop()
    app.mainloop()
    return 0
