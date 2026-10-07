#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
CONFIGURADOR VISUAL DE CANCHERIA
================================

Poner este archivo al lado de config.py y ejecutar:

    python configurador_cancheria.py

No requiere dependencias externas: usa Tkinter de Python.

Protecciones:
- Lee el config.py existente.
- Sólo modifica variables conocidas.
- Crea un backup automático antes de guardar.
- Valida sintaxis antes de reemplazar config.py.
- Conserva funciones, prompts y comentarios del archivo original.
"""

from __future__ import annotations

import ast
import json
import os
import pprint
import re
import shutil
import sys
from datetime import datetime
from pathlib import Path
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

from cancheria.config.openai_credentials import (
    CredentialStatus,
    normalize_openai_api_key,
    read_openai_api_key_assignment,
    validate_openai_api_key_format,
    verify_openai_api_key,
)

APP_TITLE = "CANCHERIA - Configurador de Cliente"
SCRIPT_DIR = Path(__file__).resolve().parent
_INSTALL_ROOT = os.getenv("CANCHERIA_INSTALL_ROOT", "").strip()
if _INSTALL_ROOT:
    PROJECT_ROOT = Path(_INSTALL_ROOT).resolve()
elif getattr(sys, "frozen", False):
    PROJECT_ROOT = Path(sys.executable).resolve().parent
else:
    PROJECT_ROOT = SCRIPT_DIR.parent
DEFAULT_CONFIG = PROJECT_ROOT / "src" / "cancheria" / "config" / "legacy_config.py"
ROOT_CONFIG = PROJECT_ROOT / "config.py"

DAY_NAMES = [
    ("Lunes", 0),
    ("Martes", 1),
    ("Miércoles", 2),
    ("Jueves", 3),
    ("Viernes", 4),
    ("Sábado", 5),
    ("Domingo", 6),
]


class ConfigSource:
    """Editor de asignaciones top-level preservando el resto del archivo."""

    def __init__(self, path: Path):
        self.path = Path(path)
        self.text = ""
        self.tree = None
        self.assignments = {}
        self.load()

    def load(self):
        self.text = self.path.read_text(encoding="utf-8-sig")
        self.tree = ast.parse(self.text, filename=str(self.path))
        self.assignments = {}

        for node in self.tree.body:
            if isinstance(node, ast.Assign) and len(node.targets) == 1:
                target = node.targets[0]
                if isinstance(target, ast.Name):
                    self.assignments[target.id] = node
            elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
                self.assignments[node.target.id] = node

    def literal(self, name, default=None):
        node = self.assignments.get(name)
        if node is None:
            return default
        value_node = getattr(node, "value", None)
        if value_node is None:
            return default
        try:
            return ast.literal_eval(value_node)
        except Exception:
            return default

    @staticmethod
    def _format_value(value):
        if isinstance(value, str):
            return repr(value)
        return pprint.pformat(value, width=100, sort_dicts=False, compact=False)

    def render_with_updates(self, updates: dict) -> str:
        lines = self.text.splitlines(keepends=True)
        replacements = []

        for name, value in updates.items():
            node = self.assignments.get(name)
            if node is None:
                raise KeyError(
                    f"No encontré la variable {name!r} en {self.path.name}. "
                    "Se canceló el guardado para no romper el config."
                )
            start = int(node.lineno) - 1
            end = int(getattr(node, "end_lineno", node.lineno))
            replacements.append((start, end, f"{name} = {self._format_value(value)}\n"))

        for start, end, assignment in sorted(replacements, reverse=True):
            lines[start:end] = [assignment]

        rendered = "".join(lines)
        ast.parse(rendered, filename=str(self.path))
        compile(rendered, str(self.path), "exec")
        return rendered

    def create_backup(self) -> Path:
        folder = self.path.parent / "config_backups"
        folder.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        dst = folder / f"config_{stamp}.py"
        shutil.copy2(self.path, dst)
        return dst

    def save_updates(self, updates: dict) -> Path:
        rendered = self.render_with_updates(updates)
        backup = self.create_backup()
        temp = self.path.with_name(self.path.name + ".tmp")
        temp.write_text(rendered, encoding="utf-8")

        check = temp.read_text(encoding="utf-8")
        ast.parse(check, filename=str(temp))
        compile(check, str(temp), "exec")

        os.replace(temp, self.path)
        self.load()
        return backup


def render_root_api_key(path: Path, api_key: str) -> str:
    """Render the historical root config.py with an explicit API key."""
    source = ConfigSource(path)
    if "OPENAI_API_KEY" in source.assignments:
        return source.render_with_updates({"OPENAI_API_KEY": api_key})
    rendered = source.text.rstrip() + (
        "\n\n# Credencial operativa guardada por el configurador de CANCHERIA.\n"
        f"OPENAI_API_KEY = {api_key!r}\n"
    )
    ast.parse(rendered, filename=str(path))
    compile(rendered, str(path), "exec")
    return rendered


def save_config_and_root_key(source: ConfigSource, updates: dict, api_key: str) -> tuple[Path, Path]:
    """Save business settings and config.py credential with rollback protection."""
    nested_updates = dict(updates)
    nested_updates["OPENAI_API_KEY"] = ""
    nested_rendered = source.render_with_updates(nested_updates)
    root_rendered = render_root_api_key(ROOT_CONFIG, api_key)

    nested_backup = source.create_backup()
    root_source = ConfigSource(ROOT_CONFIG)
    root_backup = root_source.create_backup()
    nested_temp = source.path.with_name(source.path.name + ".tmp")
    root_temp = ROOT_CONFIG.with_name(ROOT_CONFIG.name + ".tmp")
    try:
        nested_temp.write_text(nested_rendered, encoding="utf-8")
        root_temp.write_text(root_rendered, encoding="utf-8")
        for temp in (nested_temp, root_temp):
            checked = temp.read_text(encoding="utf-8")
            ast.parse(checked, filename=str(temp))
            compile(checked, str(temp), "exec")
        os.replace(root_temp, ROOT_CONFIG)
        os.replace(nested_temp, source.path)
    except Exception:
        nested_temp.unlink(missing_ok=True)
        root_temp.unlink(missing_ok=True)
        shutil.copy2(root_backup, ROOT_CONFIG)
        shutil.copy2(nested_backup, source.path)
        raise
    source.load()
    return nested_backup, root_backup


class ScrollableFrame(ttk.Frame):
    def __init__(self, parent):
        super().__init__(parent)
        canvas = tk.Canvas(self, highlightthickness=0)
        bar = ttk.Scrollbar(self, orient="vertical", command=canvas.yview)
        self.inner = ttk.Frame(canvas)
        window = canvas.create_window((0, 0), window=self.inner, anchor="nw")

        self.inner.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all")),
        )
        canvas.bind(
            "<Configure>",
            lambda e: canvas.itemconfigure(window, width=e.width),
        )
        canvas.configure(yscrollcommand=bar.set)
        canvas.pack(side="left", fill="both", expand=True)
        bar.pack(side="right", fill="y")

        def on_wheel(event):
            if sys.platform.startswith("win"):
                canvas.yview_scroll(int(-event.delta / 120), "units")
            elif getattr(event, "num", None) == 4:
                canvas.yview_scroll(-1, "units")
            elif getattr(event, "num", None) == 5:
                canvas.yview_scroll(1, "units")

        canvas.bind_all("<MouseWheel>", on_wheel)
        canvas.bind_all("<Button-4>", on_wheel)
        canvas.bind_all("<Button-5>", on_wheel)


class SimpleTable(ttk.Frame):
    def __init__(self, parent, columns, headings, widths=None):
        super().__init__(parent)
        self.columns = list(columns)
        widths = widths or {}

        self.tree = ttk.Treeview(
            self,
            columns=self.columns,
            show="headings",
            height=7,
            selectmode="browse",
        )
        for col, heading in zip(self.columns, headings):
            self.tree.heading(col, text=heading)
            self.tree.column(col, width=widths.get(col, 180), anchor="w")

        scroll = ttk.Scrollbar(self, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=scroll.set)
        self.tree.grid(row=0, column=0, columnspan=len(self.columns), sticky="nsew")
        scroll.grid(row=0, column=len(self.columns), sticky="ns")

        self.vars = {col: tk.StringVar() for col in self.columns}
        for idx, col in enumerate(self.columns):
            ttk.Entry(self, textvariable=self.vars[col]).grid(
                row=1, column=idx, padx=(0, 5), pady=6, sticky="ew"
            )
            self.columnconfigure(idx, weight=1)

        buttons = ttk.Frame(self)
        buttons.grid(row=2, column=0, columnspan=len(self.columns), sticky="w")
        ttk.Button(buttons, text="Agregar", command=self.add).pack(side="left", padx=(0, 5))
        ttk.Button(buttons, text="Actualizar", command=self.update).pack(side="left", padx=(0, 5))
        ttk.Button(buttons, text="Eliminar", command=self.delete).pack(side="left", padx=(0, 5))
        ttk.Button(buttons, text="Limpiar", command=self.clear).pack(side="left")

        self.tree.bind("<<TreeviewSelect>>", self.on_select)
        self.rowconfigure(0, weight=1)

    def set_rows(self, rows):
        self.tree.delete(*self.tree.get_children())
        for row in rows:
            self.tree.insert("", "end", values=[row.get(c, "") for c in self.columns])

    def get_rows(self):
        out = []
        for item in self.tree.get_children():
            values = self.tree.item(item, "values")
            out.append({c: values[i] for i, c in enumerate(self.columns)})
        return out

    def add(self):
        values = [self.vars[c].get().strip() for c in self.columns]
        if any(values):
            self.tree.insert("", "end", values=values)
            self.clear()

    def update(self):
        selected = self.tree.selection()
        if not selected:
            messagebox.showinfo(APP_TITLE, "Seleccioná una fila primero.")
            return
        self.tree.item(selected[0], values=[self.vars[c].get().strip() for c in self.columns])

    def delete(self):
        selected = self.tree.selection()
        if selected:
            self.tree.delete(selected[0])
            self.clear()

    def clear(self):
        for var in self.vars.values():
            var.set("")

    def on_select(self, _event=None):
        selected = self.tree.selection()
        if not selected:
            return
        values = self.tree.item(selected[0], "values")
        for i, col in enumerate(self.columns):
            self.vars[col].set(values[i] if i < len(values) else "")


class CancheriaConfigurator(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(APP_TITLE)
        self.geometry("1180x820")
        self.minsize(980, 700)

        try:
            ttk.Style().theme_use("vista" if sys.platform.startswith("win") else "clam")
        except Exception:
            pass

        self.source = None
        self.config_path = tk.StringVar(value=str(DEFAULT_CONFIG))
        self.status = tk.StringVar(value="Listo")

        self.build_header()
        self.build_tabs()
        self.build_footer()

        if DEFAULT_CONFIG.exists():
            self.load_config(DEFAULT_CONFIG)
        else:
            self.status.set("Elegí un config.py con Examinar")

    # ========================================================
    # UI helpers
    # ========================================================

    def build_header(self):
        bar = ttk.Frame(self, padding=10)
        bar.pack(fill="x")
        ttk.Label(bar, text="Archivo:").pack(side="left")
        ttk.Entry(bar, textvariable=self.config_path).pack(
            side="left", fill="x", expand=True, padx=8
        )
        ttk.Button(bar, text="Examinar", command=self.choose_config).pack(side="left", padx=3)
        ttk.Button(bar, text="Recargar", command=self.reload).pack(side="left", padx=3)

    def build_footer(self):
        bar = ttk.Frame(self, padding=(10, 0, 10, 10))
        bar.pack(fill="x")
        ttk.Label(bar, textvariable=self.status).pack(side="left", fill="x", expand=True)
        ttk.Button(bar, text="Validar", command=self.validate_only).pack(side="right", padx=4)
        ttk.Button(bar, text="💾 Guardar config.py", command=self.save).pack(side="right", padx=4)

    def section(self, p, title, row):
        ttk.Label(p, text=title, font=("Segoe UI", 11, "bold")).grid(
            row=row, column=0, columnspan=4, sticky="w", pady=(14, 6)
        )
        return row + 1

    def entry(self, p, row, label, var, help_text="", show=None):
        ttk.Label(p, text=label).grid(row=row, column=0, sticky="w", padx=(0, 8), pady=4)
        widget = ttk.Entry(p, textvariable=var, show=show)
        widget.grid(row=row, column=1, sticky="ew", pady=4)
        if help_text:
            ttk.Label(p, text=help_text, foreground="#666").grid(
                row=row, column=2, columnspan=2, sticky="w", padx=8
            )
        p.columnconfigure(1, weight=1)
        return widget

    def spin(self, p, row, label, var, from_, to, increment=1, help_text=""):
        ttk.Label(p, text=label).grid(row=row, column=0, sticky="w", padx=(0, 8), pady=4)
        ttk.Spinbox(
            p, textvariable=var, from_=from_, to=to, increment=increment, width=18
        ).grid(row=row, column=1, sticky="w", pady=4)
        if help_text:
            ttk.Label(p, text=help_text, foreground="#666").grid(
                row=row, column=2, columnspan=2, sticky="w", padx=8
            )

    def multiline(self, p, row, label, height=6, help_text=""):
        ttk.Label(p, text=label).grid(row=row, column=0, sticky="nw", padx=(0, 8), pady=4)
        text = tk.Text(p, height=height, wrap="word")
        text.grid(row=row, column=1, sticky="nsew", pady=4)
        if help_text:
            ttk.Label(p, text=help_text, foreground="#666", wraplength=330).grid(
                row=row, column=2, sticky="nw", padx=8
            )
        p.columnconfigure(1, weight=1)
        return text

    @staticmethod
    def set_text(widget, value):
        widget.delete("1.0", "end")
        widget.insert("1.0", value)

    @staticmethod
    def get_text(widget):
        return widget.get("1.0", "end").strip()

    # ========================================================
    # Tabs
    # ========================================================

    def build_tabs(self):
        notebook = ttk.Notebook(self)
        notebook.pack(fill="both", expand=True, padx=10, pady=(0, 10))
        self.pages = {}

        definitions = [
            ("negocio", "1. Negocio"),
            ("recursos", "2. Canchas y Quincho"),
            ("precios", "3. Precios y Seña"),
            ("horarios", "4. Horarios"),
            ("alertas", "5. Alertas"),
            ("admins", "6. Admins"),
            ("servicios", "7. Servicios"),
            ("tecnico", "8. Técnico"),
            ("credenciales", "9. Credenciales"),
        ]

        for key, title in definitions:
            scroll = ScrollableFrame(notebook)
            notebook.add(scroll, text=title)
            self.pages[key] = scroll.inner

        self.tab_negocio()
        self.tab_recursos()
        self.tab_precios()
        self.tab_horarios()
        self.tab_alertas()
        self.tab_admins()
        self.tab_servicios()
        self.tab_tecnico()
        self.tab_credenciales()

    def tab_negocio(self):
        p = self.pages["negocio"]
        row = 0
        self.business_name = tk.StringVar()
        self.agent_name = tk.StringVar()
        self.business_address = tk.StringVar()
        self.payment_alias = tk.StringVar()
        self.arrival_tolerance = tk.StringVar()
        self.min_booking_notice = tk.StringVar()
        self.min_cancel_notice = tk.StringVar()
        self.cancellation_policy = tk.StringVar()

        row = self.section(p, "Identidad", row)
        self.entry(p, row, "Nombre del negocio", self.business_name); row += 1
        self.entry(p, row, "Nombre del agente IA", self.agent_name); row += 1
        self.entry(p, row, "Dirección", self.business_address); row += 1
        self.entry(p, row, "Alias de pago", self.payment_alias); row += 1

        row = self.section(p, "Reglas", row)
        self.spin(p, row, "Tolerancia llegada (min)", self.arrival_tolerance, 0, 180); row += 1
        self.spin(p, row, "Anticipación mínima reserva (min)", self.min_booking_notice, 0, 10080); row += 1
        self.spin(p, row, "Anticipación mínima cancelación (min)", self.min_cancel_notice, 0, 10080); row += 1
        self.entry(p, row, "Política de cancelación", self.cancellation_policy); row += 1

    def tab_recursos(self):
        p = self.pages["recursos"]
        row = 0
        row = self.section(p, "Canchas", row)
        self.courts = SimpleTable(
            p,
            ("name", "type"),
            ("Nombre", "Tipo"),
            {"name": 240, "type": 240},
        )
        self.courts.grid(row=row, column=0, columnspan=4, sticky="nsew", pady=5)
        row += 1

        row = self.section(p, "Quincho / parrilla", row)
        self.con_quincho = tk.BooleanVar()
        ttk.Checkbutton(p, text="El negocio ofrece quincho/parrilla", variable=self.con_quincho).grid(
            row=row, column=0, columnspan=3, sticky="w", pady=5
        )
        row += 1
        self.quinchos = SimpleTable(
            p,
            ("name", "type", "price"),
            ("Nombre", "Tipo", "Precio/hora"),
            {"name": 220, "type": 220, "price": 160},
        )
        self.quinchos.grid(row=row, column=0, columnspan=4, sticky="nsew", pady=5)

    def tab_precios(self):
        p = self.pages["precios"]
        row = 0
        self.price_per_hour = tk.StringVar()
        self.turn_duration = tk.StringVar()
        self.allowed_durations = tk.StringVar()
        self.default_duration = tk.StringVar()
        self.requires_deposit = tk.BooleanVar()
        self.deposit_mode = tk.StringVar(value="percentage")
        self.deposit_percentage = tk.StringVar()
        self.deposit_amount = tk.StringVar()

        row = self.section(p, "Precio y duración", row)
        self.entry(
            p, row, "Precio por hora (ARS)", self.price_per_hour,
            "Se sincroniza con PRICES para todas las canchas."
        ); row += 1
        self.spin(p, row, "Duración base (min)", self.turn_duration, 15, 480, 15); row += 1
        self.entry(p, row, "Duraciones permitidas", self.allowed_durations, "Ej: 1, 1.5, 2"); row += 1
        self.entry(p, row, "Duración por defecto", self.default_duration, "Ej: 1"); row += 1

        row = self.section(p, "Seña", row)
        ttk.Checkbutton(p, text="Requiere seña", variable=self.requires_deposit).grid(
            row=row, column=0, columnspan=2, sticky="w", pady=5
        )
        row += 1
        ttk.Label(p, text="Modalidad").grid(row=row, column=0, sticky="w")
        ttk.Combobox(
            p,
            textvariable=self.deposit_mode,
            values=("percentage", "fixed"),
            state="readonly",
            width=20,
        ).grid(row=row, column=1, sticky="w")
        row += 1
        self.spin(p, row, "Porcentaje", self.deposit_percentage, 0, 100, 1, "Si modalidad = percentage"); row += 1
        self.entry(p, row, "Monto fijo (ARS)", self.deposit_amount, "Si modalidad = fixed"); row += 1

    def tab_horarios(self):
        p = self.pages["horarios"]
        row = 0
        self.day_vars = {idx: tk.BooleanVar() for _, idx in DAY_NAMES}
        self.call_default_time = tk.StringVar()
        self.local_timezone = tk.StringVar()

        row = self.section(p, "Días de atención", row)
        frame = ttk.Frame(p)
        frame.grid(row=row, column=0, columnspan=4, sticky="w")
        for i, (name, idx) in enumerate(DAY_NAMES):
            ttk.Checkbutton(frame, text=name, variable=self.day_vars[idx]).grid(
                row=i // 4, column=i % 4, sticky="w", padx=(0, 15), pady=3
            )
        row += 1

        row = self.section(p, "Franjas", row)
        self.call_windows = self.multiline(
            p, row, "Una franja por línea", 6,
            "Formato 10:00-00:00. Horario cortado: una franja por línea."
        ); row += 1
        self.entry(p, row, "Hora por defecto", self.call_default_time); row += 1
        self.entry(p, row, "Zona horaria", self.local_timezone, "Ej: America/Argentina/Cordoba"); row += 1

    def tab_alertas(self):
        p = self.pages["alertas"]
        row = 0
        self.owner_reminder = tk.StringVar()
        self.client_reminder = tk.StringVar()
        self.final_owner_reminder = tk.StringVar()
        self.daily_summary = tk.StringVar()
        self.post_followup = tk.StringVar()
        self.post_followup_ttl = tk.StringVar()

        row = self.section(p, "Alertas y recordatorios", row)
        self.spin(p, row, "Aviso admin previo (min)", self.owner_reminder, 0, 1440); row += 1
        self.spin(p, row, "Recordatorio cliente (min)", self.client_reminder, 0, 10080, 1, "120 = 2 horas antes"); row += 1
        self.spin(p, row, "Último aviso admin (min)", self.final_owner_reminder, 0, 1440); row += 1
        self.entry(p, row, "Agenda diaria HH:MM", self.daily_summary, "Ej: 08:00"); row += 1
        self.spin(p, row, "Follow-up post turno (min)", self.post_followup, 0, 1440); row += 1
        self.spin(p, row, "TTL follow-up (horas)", self.post_followup_ttl, 1, 720); row += 1

    def tab_admins(self):
        p = self.pages["admins"]
        row = 0
        self.authorized_number = tk.StringVar()
        self.human_contact_name = tk.StringVar()
        self.human_available_hours = tk.StringVar()

        row = self.section(p, "Principal", row)
        self.entry(p, row, "WhatsApp principal", self.authorized_number, "Formato recomendado +549..."); row += 1
        self.entry(p, row, "Nombre del encargado", self.human_contact_name); row += 1
        self.entry(p, row, "Horario del encargado", self.human_available_hours); row += 1

        row = self.section(p, "Teléfonos administradores", row)
        self.authorized_numbers = self.multiline(p, row, "Uno por línea", 6, "Todos reciben alertas administrativas."); row += 1
        row = self.section(p, "Nombres autorizados", row)
        self.authorized_names = self.multiline(p, row, "Uno por línea", 6); row += 1

    def tab_servicios(self):
        p = self.pages["servicios"]
        ttk.Label(
            p,
            text="Servicios del negocio en JSON. Podés configurar pelota, estacionamiento, duchas, etc.",
            foreground="#666",
        ).grid(row=0, column=0, sticky="w", pady=(10, 5))
        self.services = tk.Text(p, height=28, wrap="none", font=("Consolas", 10))
        self.services.grid(row=1, column=0, sticky="nsew")
        p.columnconfigure(0, weight=1)
        p.rowconfigure(1, weight=1)

    def tab_tecnico(self):
        p = self.pages["tecnico"]
        row = 0
        self.openai_model = tk.StringVar()
        self.scheduler_interval = tk.StringVar()
        self.pause_recheck = tk.StringVar()
        self.max_search_days = tk.StringVar()
        self.qr_refresh = tk.StringVar()
        self.qr_check = tk.StringVar()
        self.bot_threshold = tk.StringVar()
        self.bot_quarantine = tk.StringVar()

        row = self.section(p, "Motor", row)
        self.entry(p, row, "Modelo OpenAI", self.openai_model); row += 1
        self.spin(p, row, "Scheduler check (seg)", self.scheduler_interval, 1, 3600); row += 1
        self.spin(p, row, "Recheck pausa admin (seg)", self.pause_recheck, 1, 86400); row += 1
        self.spin(p, row, "Máx. días búsqueda", self.max_search_days, 1, 365); row += 1

        row = self.section(p, "WhatsApp / QR", row)
        self.spin(p, row, "Refresh preventivo QR (seg)", self.qr_refresh, 1, 86400); row += 1
        self.spin(p, row, "Chequeo QR (seg)", self.qr_check, 1, 3600); row += 1

        row = self.section(p, "Detección de bots", row)
        self.spin(p, row, "Umbral", self.bot_threshold, 1, 100); row += 1
        self.spin(p, row, "Cuarentena (seg)", self.bot_quarantine, 0, 604800, 60); row += 1

    def tab_credenciales(self):
        p = self.pages["credenciales"]
        row = 0
        self.openai_key = tk.StringVar()
        self.email_sender = tk.StringVar()
        self.email_password = tk.StringVar()
        self.email_receiver = tk.StringVar()
        self.show_secrets = tk.BooleanVar(value=False)

        ttk.Label(
            p,
            text="⚠ Los secretos se gestionan con .env. Esta herramienta legacy no debe guardar credenciales en el código.",
            foreground="#a06000",
            wraplength=900,
        ).grid(row=row, column=0, columnspan=4, sticky="w", pady=(10, 8))
        row += 1
        self.openai_key_entry = self.entry(p, row, "OpenAI API Key", self.openai_key, show="*"); row += 1
        self.entry(p, row, "Email emisor", self.email_sender); row += 1
        self.email_password_entry = self.entry(p, row, "Password de aplicación", self.email_password, show="*"); row += 1
        self.entry(p, row, "Email receptor", self.email_receiver); row += 1
        ttk.Checkbutton(
            p,
            text="Mostrar secretos",
            variable=self.show_secrets,
            command=self.toggle_secrets,
        ).grid(row=row, column=0, columnspan=2, sticky="w", pady=8)

    # ========================================================
    # Load
    # ========================================================

    def choose_config(self):
        selected = filedialog.askopenfilename(
            title="Elegir config.py",
            filetypes=[("Python", "*.py"), ("Todos", "*.*")],
        )
        if selected:
            self.config_path.set(selected)
            self.load_config(Path(selected))

    def reload(self):
        self.load_config(Path(self.config_path.get().strip()))

    def toggle_secrets(self):
        show = "" if self.show_secrets.get() else "*"
        self.openai_key_entry.configure(show=show)
        self.email_password_entry.configure(show=show)

    def load_config(self, path: Path):
        try:
            if not path.exists():
                raise FileNotFoundError(path)
            self.source = ConfigSource(path)
            self.config_path.set(str(path))
            lit = self.source.literal

            self.business_name.set(str(lit("BUSINESS_NAME", "")))
            self.agent_name.set(str(lit("AGENT_NAME", "")))
            self.business_address.set(str(lit("BUSINESS_ADDRESS", "")))
            self.payment_alias.set(str(lit("PAYMENT_ALIAS", "")))
            self.arrival_tolerance.set(str(lit("ARRIVAL_TOLERANCE_MINUTES", 10)))
            self.min_booking_notice.set(str(lit("MIN_BOOKING_NOTICE_MINUTES", 0)))
            self.min_cancel_notice.set(str(lit("MIN_CANCELLATION_NOTICE_MINUTES", 0)))
            self.cancellation_policy.set(str(lit("CANCELLATION_POLICY", "")))

            self.courts.set_rows([
                {"name": c.get("name", ""), "type": c.get("type", "")}
                for c in (lit("COURTS", []) or []) if isinstance(c, dict)
            ])
            self.con_quincho.set(bool(lit("CON_QUINCHO", False)))
            q_prices = {
                str(q.get("description", "")): str(q.get("amount", ""))
                for q in (lit("QUINCHOS_PRICES", []) or []) if isinstance(q, dict)
            }
            self.quinchos.set_rows([
                {
                    "name": q.get("name", ""),
                    "type": q.get("type", ""),
                    "price": q_prices.get(str(q.get("name", "")), ""),
                }
                for q in (lit("QUINCHOS", []) or []) if isinstance(q, dict)
            ])

            self.price_per_hour.set(str(lit("PRICE_PER_HOUR", 0)))
            self.turn_duration.set(str(lit("TURN_DURATION_MINUTES", 60)))
            self.allowed_durations.set(", ".join(str(x) for x in (lit("ALLOWED_TURN_DURATIONS", []) or [])))
            self.default_duration.set(str(lit("DEFAULT_TURN_DURATION_HOURS", 1.0)))
            self.requires_deposit.set(bool(lit("REQUIRES_DEPOSIT", True)))
            self.deposit_mode.set(str(lit("DEPOSIT_MODE", "percentage")))
            self.deposit_percentage.set(str(lit("DEPOSIT_PERCENTAGE", 50)))
            self.deposit_amount.set(re.sub(r"[^\d]", "", str(lit("DEPOSIT_AMOUNT", "") or "")))

            attention = set(lit("ATTENTION_DAYS", []) or [])
            for idx, var in self.day_vars.items():
                var.set(idx in attention)
            self.set_text(
                self.call_windows,
                "\n".join(f"{a}-{b}" for a, b in (lit("CALL_TIME_WINDOWS", []) or [])),
            )
            self.call_default_time.set(str(lit("CALL_DEFAULT_TIME", "20:00")))
            self.local_timezone.set(str(lit("LOCAL_TIMEZONE", "America/Argentina/Cordoba")))

            self.owner_reminder.set(str(lit("OWNER_REMINDER_MINUTES_BEFORE", 15)))
            self.client_reminder.set(str(lit("CLIENT_REMINDER_MINUTES_BEFORE", 120)))
            self.final_owner_reminder.set(str(lit("FINAL_OWNER_REMINDER_MINUTES_BEFORE", 5)))
            self.daily_summary.set(str(lit("DAILY_AGENDA_SUMMARY_TIME", "08:00")))
            self.post_followup.set(str(lit("POST_TURNO_FOLLOWUP_MINUTES", 5)))
            self.post_followup_ttl.set(str(lit("POST_TURNO_FOLLOWUP_TTL_HOURS", 24)))

            self.authorized_number.set(str(lit("AUTHORIZED_NUMBER", "")))
            self.human_contact_name.set(str(lit("HUMAN_CONTACT_NAME", "")))
            self.human_available_hours.set(str(lit("HUMAN_AVAILABLE_HOURS", "")))
            self.set_text(self.authorized_numbers, "\n".join(str(x) for x in (lit("AUTHORIZED_NUMBERS", []) or [])))
            self.set_text(self.authorized_names, "\n".join(str(x) for x in (lit("AUTHORIZED_NAMES", []) or [])))

            self.set_text(
                self.services,
                json.dumps(lit("BUSINESS_SERVICES", []) or [], ensure_ascii=False, indent=2),
            )

            self.openai_model.set(str(lit("OPENAI_MODEL", "") or "gpt-4o-mini"))
            self.scheduler_interval.set(str(lit("SCHEDULER_CHECK_INTERVAL_SECONDS", 3)))
            self.pause_recheck.set(str(lit("PAUSE_CONTROL_RECHECK_SECONDS", 120)))
            self.max_search_days.set(str(lit("MAX_BOOKING_SEARCH_DAYS", 14)))
            self.qr_refresh.set(str(lit("QR_PREVENTIVE_REFRESH_INTERVAL_SECONDS", 900)))
            self.qr_check.set(str(lit("QR_CHECK_INTERVAL_SECONDS", 10)))
            self.bot_threshold.set(str(lit("BOT_DETECTION_THRESHOLD", 3)))
            self.bot_quarantine.set(str(lit("BOT_QUARANTINE_SECONDS", 3600)))

            root_key_found, root_key = read_openai_api_key_assignment(ROOT_CONFIG)
            self.openai_key.set(root_key if root_key_found else str(lit("OPENAI_API_KEY", "")))
            self.email_sender.set(str(lit("EMAIL_SENDER", "")))
            self.email_password.set(str(lit("EMAIL_PASSWORD", "")))
            self.email_receiver.set(str(lit("EMAIL_RECEIVER", "")))

            self.status.set(f"Cargado: {path}")
        except Exception as exc:
            self.status.set("Error cargando config.py")
            messagebox.showerror(APP_TITLE, f"No pude cargar config.py:\n\n{exc}")

    # ========================================================
    # Validation / conversion
    # ========================================================

    @staticmethod
    def int_value(value, label, minimum=None, maximum=None):
        try:
            result = int(str(value).strip())
        except Exception:
            raise ValueError(f"{label}: debe ser entero")
        if minimum is not None and result < minimum:
            raise ValueError(f"{label}: mínimo {minimum}")
        if maximum is not None and result > maximum:
            raise ValueError(f"{label}: máximo {maximum}")
        return result

    @staticmethod
    def float_value(value, label, minimum=None, maximum=None):
        try:
            result = float(str(value).strip().replace(",", "."))
        except Exception:
            raise ValueError(f"{label}: debe ser numérico")
        if minimum is not None and result < minimum:
            raise ValueError(f"{label}: mínimo {minimum}")
        if maximum is not None and result > maximum:
            raise ValueError(f"{label}: máximo {maximum}")
        return result

    @staticmethod
    def valid_time(value, label):
        value = str(value).strip()
        if not re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", value):
            raise ValueError(f"{label}: usá HH:MM, por ejemplo 08:00")
        return value

    def parse_windows(self):
        raw = self.get_text(self.call_windows)
        if not raw:
            raise ValueError("Configurá al menos una franja horaria")
        result = []
        for line in raw.splitlines():
            line = line.strip()
            if not line:
                continue
            m = re.fullmatch(r"\s*(\d{1,2}:\d{2})\s*-\s*(\d{1,2}:\d{2})\s*", line)
            if not m:
                raise ValueError(f"Franja inválida: {line}. Ejemplo: 10:00-00:00")
            start, end = m.groups()
            self.valid_time(start, "Inicio de franja")
            self.valid_time(end, "Fin de franja")
            result.append((start, end))
        if not result:
            raise ValueError("Configurá al menos una franja horaria")
        return result

    def collect_updates(self):
        if self.source is None:
            raise RuntimeError("Primero cargá un config.py")

        business_name = self.business_name.get().strip()
        agent_name = self.agent_name.get().strip()
        business_address = self.business_address.get().strip()
        payment_alias = self.payment_alias.get().strip()

        if not business_name:
            raise ValueError("Nombre del negocio obligatorio")
        if not agent_name:
            raise ValueError("Nombre del agente obligatorio")
        if not business_address:
            raise ValueError("Dirección obligatoria")
        if not payment_alias:
            raise ValueError("Alias de pago obligatorio")

        court_rows = self.courts.get_rows()
        courts = []
        seen = set()
        for row in court_rows:
            name = row["name"].strip()
            if not name:
                continue
            if name.casefold() in seen:
                raise ValueError(f"Cancha duplicada: {name}")
            seen.add(name.casefold())
            courts.append({"name": name, "type": row["type"].strip() or "futbol 5"})
        if not courts:
            raise ValueError("Debe existir al menos una cancha")

        price = self.int_value(self.price_per_hour.get(), "Precio por hora", 0)
        prices = [{"description": c["name"], "amount": str(price)} for c in courts]

        quinchos = []
        quincho_prices = []
        seen_q = set()
        for row in self.quinchos.get_rows():
            name = row["name"].strip()
            if not name:
                continue
            if name.casefold() in seen_q:
                raise ValueError(f"Quincho duplicado: {name}")
            seen_q.add(name.casefold())
            qprice = self.int_value(row["price"].strip() or 0, f"Precio de {name}", 0)
            quinchos.append({"name": name, "type": row["type"].strip() or "quincho/parrilla"})
            quincho_prices.append({"description": name, "amount": str(qprice)})
        if self.con_quincho.get() and not quinchos:
            raise ValueError("Quincho está habilitado pero no agregaste ninguno")

        durations = []
        for raw in self.allowed_durations.get().split(","):
            raw = raw.strip()
            if raw:
                durations.append(self.float_value(raw, "Duraciones permitidas", 0.25, 24))
        if not durations:
            raise ValueError("Configurá al menos una duración permitida")
        default_duration = self.float_value(self.default_duration.get(), "Duración por defecto", 0.25, 24)
        if default_duration not in durations:
            raise ValueError("La duración por defecto debe estar incluida en las permitidas")

        days = [idx for idx, var in self.day_vars.items() if var.get()]
        if not days:
            raise ValueError("Seleccioná al menos un día de atención")

        try:
            services = json.loads(self.get_text(self.services) or "[]")
        except Exception as exc:
            raise ValueError(f"Servicios: JSON inválido: {exc}")
        if not isinstance(services, list):
            raise ValueError("Servicios debe ser una lista JSON")

        auth_number = self.authorized_number.get().strip()
        if not auth_number:
            raise ValueError("WhatsApp principal obligatorio")
        auth_numbers = [x.strip() for x in self.get_text(self.authorized_numbers).splitlines() if x.strip()]
        if auth_number not in auth_numbers:
            auth_numbers.insert(0, auth_number)
        auth_names = [x.strip() for x in self.get_text(self.authorized_names).splitlines() if x.strip()]

        fixed_deposit = self.int_value(self.deposit_amount.get() or 0, "Seña fija", 0)
        deposit_pct = self.int_value(self.deposit_percentage.get() or 0, "Porcentaje seña", 0, 100)
        deposit_mode = self.deposit_mode.get().strip()
        if deposit_mode not in {"percentage", "fixed"}:
            raise ValueError("Modalidad de seña inválida")

        openai_model = self.openai_model.get().strip()
        if not openai_model:
            raise ValueError("Modelo OpenAI obligatorio (por ejemplo: gpt-4o-mini)")

        openai_key = validate_openai_api_key_format(self.openai_key.get())

        updates = {
            "OPENAI_API_KEY": openai_key,
            "EMAIL_SENDER": self.email_sender.get().strip(),
            "EMAIL_PASSWORD": self.email_password.get().strip(),
            "EMAIL_RECEIVER": self.email_receiver.get().strip(),
            "AUTHORIZED_NUMBER": auth_number,
            "AUTHORIZED_NUMBERS": auth_numbers,
            "AUTHORIZED_NAMES": auth_names,
            "BUSINESS_NAME": business_name,
            "AGENT_NAME": agent_name,
            "HUMAN_CONTACT_NAME": self.human_contact_name.get().strip(),
            "HUMAN_AVAILABLE_HOURS": self.human_available_hours.get().strip(),
            "BUSINESS_ADDRESS": business_address,
            "PAYMENT_ALIAS": payment_alias,
            "COURTS": courts,
            "BUSINESS_SERVICES": services,
            "CON_QUINCHO": bool(self.con_quincho.get()),
            "QUINCHOS": quinchos,
            "QUINCHOS_PRICES": quincho_prices,
            "TURN_DURATION_MINUTES": self.int_value(self.turn_duration.get(), "Duración base", 1, 1440),
            "ARRIVAL_TOLERANCE_MINUTES": self.int_value(self.arrival_tolerance.get(), "Tolerancia llegada", 0, 1440),
            "REQUIRES_DEPOSIT": bool(self.requires_deposit.get()),
            "DEPOSIT_MODE": deposit_mode,
            "DEPOSIT_AMOUNT": f"${fixed_deposit}",
            "DEPOSIT_PERCENTAGE": deposit_pct,
            "MIN_BOOKING_NOTICE_MINUTES": self.int_value(self.min_booking_notice.get(), "Anticipación reserva", 0),
            "MIN_CANCELLATION_NOTICE_MINUTES": self.int_value(self.min_cancel_notice.get(), "Anticipación cancelación", 0),
            "CANCELLATION_POLICY": self.cancellation_policy.get().strip(),
            "OWNER_REMINDER_MINUTES_BEFORE": self.int_value(self.owner_reminder.get(), "Aviso admin", 0),
            "CLIENT_REMINDER_MINUTES_BEFORE": self.int_value(self.client_reminder.get(), "Recordatorio cliente", 0),
            "FINAL_OWNER_REMINDER_MINUTES_BEFORE": self.int_value(self.final_owner_reminder.get(), "Último aviso admin", 0),
            "DAILY_AGENDA_SUMMARY_TIME": self.valid_time(self.daily_summary.get(), "Agenda diaria"),
            "POST_TURNO_FOLLOWUP_MINUTES": self.int_value(self.post_followup.get(), "Follow-up", 0),
            "POST_TURNO_FOLLOWUP_TTL_HOURS": self.int_value(self.post_followup_ttl.get(), "TTL follow-up", 1),
            "PRICES": prices,
            "ALLOWED_TURN_DURATIONS": durations,
            "DEFAULT_TURN_DURATION_HOURS": default_duration,
            "PRICE_PER_HOUR": price,
            "MAX_BOOKING_SEARCH_DAYS": self.int_value(self.max_search_days.get(), "Máx. días búsqueda", 1),
            "LOCAL_TIMEZONE": self.local_timezone.get().strip(),
            "OPENAI_MODEL": openai_model,
            "SCHEDULER_CHECK_INTERVAL_SECONDS": self.int_value(self.scheduler_interval.get(), "Scheduler", 1),
            "PAUSE_CONTROL_RECHECK_SECONDS": self.int_value(self.pause_recheck.get(), "Recheck pausa", 1),
            "QR_PREVENTIVE_REFRESH_INTERVAL_SECONDS": self.int_value(self.qr_refresh.get(), "Refresh QR", 1),
            "QR_CHECK_INTERVAL_SECONDS": self.int_value(self.qr_check.get(), "Chequeo QR", 1),
            "BOT_DETECTION_THRESHOLD": self.int_value(self.bot_threshold.get(), "Umbral bot", 1),
            "BOT_QUARANTINE_SECONDS": self.int_value(self.bot_quarantine.get(), "Cuarentena bot", 0),
            "ATTENTION_DAYS": days,
            "CALL_TIME_WINDOWS": self.parse_windows(),
            "CALL_DEFAULT_TIME": self.valid_time(self.call_default_time.get(), "Hora por defecto"),
        }

        missing = [name for name in updates if name not in self.source.assignments]
        if missing:
            raise KeyError(
                "El config seleccionado no contiene estas variables:\n\n"
                + "\n".join(missing)
                + "\n\nNo se guardó nada."
            )
        return updates

    # ========================================================
    # Save
    # ========================================================

    def validate_only(self):
        try:
            updates = self.collect_updates()
            nested_updates = dict(updates)
            nested_updates["OPENAI_API_KEY"] = ""
            rendered = self.source.render_with_updates(nested_updates)
            ast.parse(rendered)
            compile(rendered, str(self.source.path), "exec")
            render_root_api_key(ROOT_CONFIG, updates["OPENAI_API_KEY"])
            self.status.set("Validación OK")
            messagebox.showinfo(
                APP_TITLE,
                "✅ Configuración válida.\n\nNo se modificó todavía el archivo."
            )
        except Exception as exc:
            self.status.set("Error de validación")
            messagebox.showerror(APP_TITLE, f"❌ Configuración inválida:\n\n{exc}")

    def save(self):
        try:
            updates = self.collect_updates()
            self.status.set("Verificando API key con OpenAI...")
            self.update_idletasks()
            credential_check = verify_openai_api_key(updates["OPENAI_API_KEY"])
            if credential_check.status != CredentialStatus.VALID:
                self.status.set("API key rechazada")
                messagebox.showerror(
                    APP_TITLE,
                    "❌ No se guardó la configuración.\n\n"
                    f"{credential_check.message}\n\n"
                    "Creá o revisá la clave en:\n"
                    "https://platform.openai.com/api-keys",
                )
                return
            self.openai_key.set(normalize_openai_api_key(updates["OPENAI_API_KEY"]))
            if not messagebox.askyesno(
                APP_TITLE,
                f"Se modificará:\n\n{self.source.path}\n\n"
                "Se creará un backup antes de escribir.\n\n¿Continuar?"
            ):
                return

            backup, root_backup = save_config_and_root_key(
                self.source,
                updates,
                updates["OPENAI_API_KEY"],
            )
            self.status.set(f"Guardado OK · API en config.py · backup {backup.name}")
            messagebox.showinfo(
                APP_TITLE,
                "✅ Configuración actualizada correctamente.\n\n"
                f"API key guardada en:\n{ROOT_CONFIG}\n\n"
                f"Backups:\n{backup}\n{root_backup}\n\n"
                "Reiniciá WPSetter para aplicar todos los cambios."
            )
        except Exception as exc:
            self.status.set("Guardado cancelado por error")
            messagebox.showerror(
                APP_TITLE,
                f"❌ No se modificó config.py.\n\n{exc}"
            )


def main():
    app = CancheriaConfigurator()
    app.mainloop()


if __name__ == "__main__":
    main()
