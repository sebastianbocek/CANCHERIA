from __future__ import annotations

import tkinter as tk
from tkinter import messagebox, simpledialog, ttk
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


class AdminPanel(tk.Toplevel):
    NAVY = "#061632"
    BLUE = "#1677ff"
    GREEN = "#14804a"
    ORANGE = "#b45309"
    RED = "#b42318"
    FREE_GREEN = "#079455"
    PAST_GRAY = "#667085"
    MUTED = "#6b7280"
    BG = "#f7f9fc"

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
        self.geometry("1180x740")
        self.minsize(980, 620)
        self.configure(bg=self.BG)
        self.transient(parent)

        self.summary_vars = {
            key: tk.StringVar(value="0") for key in ("active", "pending", "today", "cases")
        }
        self._build()
        self.refresh_all()
        self._schedule_notification_poll()

    def _build(self) -> None:
        header = tk.Frame(self, bg="white")
        header.pack(fill="x", padx=16, pady=(16, 8))
        tk.Label(header, text="Panel de administración", font=("Segoe UI", 20, "bold"), fg=self.NAVY, bg="white").pack(side="left", padx=16, pady=14)
        tk.Button(header, text="Actualizar", command=self.refresh_all, bg=self.BLUE, fg="white", relief="flat", padx=16, pady=8).pack(side="right", padx=16)

        cards = tk.Frame(self, bg=self.BG)
        cards.pack(fill="x", padx=18, pady=(0, 10))
        labels = (("active", "Reservas activas"), ("pending", "Pagos pendientes"), ("today", "Turnos de hoy"), ("cases", "Casos humanos"))
        for index, (key, label) in enumerate(labels):
            cards.grid_columnconfigure(index, weight=1)
            card = tk.Frame(cards, bg="white", bd=1, relief="solid")
            card.grid(row=0, column=index, sticky="ew", padx=5)
            tk.Label(card, textvariable=self.summary_vars[key], font=("Segoe UI", 23, "bold"), fg=self.BLUE, bg="white").pack(pady=(10, 0))
            tk.Label(card, text=label, font=("Segoe UI", 9), fg=self.MUTED, bg="white").pack(pady=(0, 10))

        self.notebook = ttk.Notebook(self)
        self.notebook.pack(fill="both", expand=True, padx=22, pady=(0, 18))
        self.bookings_tab = tk.Frame(self.notebook, bg="white")
        self.hours_tab = tk.Frame(self.notebook, bg="white")
        self.operation_tab = tk.Frame(self.notebook, bg="white")
        self.cases_tab = tk.Frame(self.notebook, bg="white")
        self.tournaments_tab = tk.Frame(self.notebook, bg="white")
        self.commands_tab = tk.Frame(self.notebook, bg="white")
        self.notebook.add(self.bookings_tab, text="Reservas y pagos")
        self.notebook.add(self.hours_tab, text="Horas")
        self.notebook.add(self.operation_tab, text="Operación")
        self.notebook.add(self.cases_tab, text="Atención humana")
        self.notebook.add(self.tournaments_tab, text="Torneos")
        self.notebook.add(self.commands_tab, text="Comandos y configuración")
        self._tab_titles = {
            self.bookings_tab: "Reservas y pagos",
            self.hours_tab: "Horas",
            self.operation_tab: "Operación",
            self.cases_tab: "Atención humana",
            self.tournaments_tab: "Torneos",
            self.commands_tab: "Comandos y configuración",
        }
        self._tab_notification_keys = {
            self.bookings_tab: "bookings",
            self.hours_tab: "hours",
            self.operation_tab: "operation",
            self.cases_tab: "cases",
            self.tournaments_tab: "tournaments",
            self.commands_tab: "commands",
        }
        self._tab_badge_images: dict[tk.Widget, tk.PhotoImage] = {}
        self._build_bookings()
        self._build_hours()
        self._build_operation()
        self._build_cases()
        self._build_tournaments()
        self._build_commands()
        self.notebook.bind("<<NotebookTabChanged>>", self._on_tab_changed)

    def _action_button(self, parent: tk.Widget, text: str, command, color: str) -> tk.Button:
        return tk.Button(parent, text=text, command=command, bg=color, fg="white", activebackground=color, activeforeground="white", relief="flat", padx=12, pady=7, cursor="hand2")

    def _build_bookings(self) -> None:
        actions = tk.Frame(self.bookings_tab, bg="white")
        actions.pack(fill="x", padx=10, pady=10)
        self._action_button(actions, "Nueva reserva", self._new_booking_dialog, self.BLUE).pack(side="left", padx=3)
        self._action_button(actions, "Confirmar seña", lambda: self._booking_action("deposit"), self.GREEN).pack(side="left", padx=3)
        self._action_button(actions, "Confirmar total", lambda: self._booking_action("total"), self.GREEN).pack(side="left", padx=3)
        self._action_button(actions, "Liberar pendiente", lambda: self._booking_action("release"), self.ORANGE).pack(side="left", padx=3)
        self._action_button(actions, "Cancelar", lambda: self._booking_action("cancel"), self.RED).pack(side="left", padx=3)

        columns = ("id", "fecha", "hora", "cancha", "nombre", "telefono", "estado", "senia", "saldo")
        self.booking_tree = ttk.Treeview(self.bookings_tab, columns=columns, show="headings", selectmode="browse")
        headings = {"id": "ID", "fecha": "Fecha", "hora": "Hora", "cancha": "Cancha", "nombre": "Cliente", "telefono": "Teléfono", "estado": "Estado", "senia": "Seña", "saldo": "Saldo"}
        widths = {"id": 55, "fecha": 105, "hora": 65, "cancha": 105, "nombre": 155, "telefono": 125, "estado": 90, "senia": 105, "saldo": 90}
        for key in columns:
            self.booking_tree.heading(key, text=headings[key])
            self.booking_tree.column(key, width=widths[key], anchor="center" if key not in {"nombre", "telefono"} else "w")
        scrollbar = ttk.Scrollbar(self.bookings_tab, orient="vertical", command=self.booking_tree.yview)
        self.booking_tree.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side="right", fill="y", pady=(0, 10))
        self.booking_tree.pack(fill="both", expand=True, padx=(10, 0), pady=(0, 10))

    def _build_hours(self) -> None:
        toolbar = tk.Frame(self.hours_tab, bg="white")
        toolbar.pack(fill="x", padx=14, pady=(12, 6))
        date_label = tk.Label(
            toolbar,
            text="Fecha 📅",
            font=("Segoe UI", 10, "bold"),
            fg=self.BLUE,
            bg="white",
            cursor="hand2",
        )
        date_label.pack(side="left")
        self.hours_day_var = tk.StringVar(value=dt_today())
        date_entry = tk.Entry(toolbar, textvariable=self.hours_day_var, width=13, font=("Segoe UI", 10))
        date_entry.pack(side="left", padx=(8, 5), ipady=5)
        date_entry.bind("<Return>", lambda _event: self._refresh_hours())
        date_entry.bind(
            "<Double-Button-1>",
            lambda _event: self._show_date_picker(
                self.hours_day_var, date_entry, "Fecha de horarios", self._refresh_hours
            ),
        )
        date_label.bind(
            "<Button-1>",
            lambda _event: self._show_date_picker(
                self.hours_day_var, date_entry, "Fecha de horarios", self._refresh_hours
            ),
        )
        self._action_button(toolbar, "◀", lambda: self._move_hours_date(-1), self.NAVY).pack(side="left", padx=2)
        self._action_button(toolbar, "Hoy", self._set_hours_today, self.BLUE).pack(side="left", padx=2)
        self._action_button(toolbar, "▶", lambda: self._move_hours_date(1), self.NAVY).pack(side="left", padx=2)
        self._action_button(toolbar, "Ver horarios", self._refresh_hours, self.BLUE).pack(side="left", padx=(8, 2))

        legend = tk.Frame(self.hours_tab, bg="white")
        legend.pack(fill="x", padx=14, pady=(0, 8))
        self._legend_item(legend, self.FREE_GREEN, "Disponible")
        self._legend_item(legend, self.RED, "Ocupado / bloqueado")
        self._legend_item(legend, self.PAST_GRAY, "Fuera de atención")
        self.hours_status_var = tk.StringVar(value="")
        tk.Label(legend, textvariable=self.hours_status_var, bg="white", fg=self.MUTED).pack(side="right")

        body = tk.Frame(self.hours_tab, bg="white")
        body.pack(fill="both", expand=True, padx=14, pady=(0, 12))
        self.hours_canvas = tk.Canvas(body, bg="white", highlightthickness=0)
        vertical = ttk.Scrollbar(body, orient="vertical", command=self.hours_canvas.yview)
        horizontal = ttk.Scrollbar(body, orient="horizontal", command=self.hours_canvas.xview)
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

    def _legend_item(self, parent: tk.Widget, color: str, label: str) -> None:
        item = tk.Frame(parent, bg="white")
        item.pack(side="left", padx=(0, 16))
        tk.Label(item, text="  ", bg=color, width=2).pack(side="left", padx=(0, 5))
        tk.Label(item, text=label, bg="white", fg=self.NAVY).pack(side="left")

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

    def _on_tab_changed(self, _event=None) -> None:
        if self.notebook.select() == str(self.hours_tab):
            self._refresh_hours()
        elif self.notebook.select() == str(self.tournaments_tab):
            self._refresh_tournaments()

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
        self.case_tree = ttk.Treeview(self.cases_tab, columns=columns, show="headings", selectmode="browse")
        widths = (55, 140, 130, 125, 270, 360)
        labels = ("ID", "Creado", "Cliente", "Teléfono", "Mensaje", "Motivo")
        for key, label, width in zip(columns, labels, widths):
            self.case_tree.heading(key, text=label)
            self.case_tree.column(key, width=width, anchor="w")
        self.case_tree.pack(fill="both", expand=True, padx=10, pady=(0, 10))

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
        self.tournament_tree = ttk.Treeview(
            self.tournaments_tab,
            columns=tournament_columns,
            show="headings",
            selectmode="browse",
            height=7,
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
        self.tournament_tree.pack(fill="x", padx=10, pady=(0, 8))
        self.tournament_tree.bind(
            "<<TreeviewSelect>>", lambda _event: self._refresh_tournament_registrations()
        )

        separator = ttk.Separator(self.tournaments_tab, orient="horizontal")
        separator.pack(fill="x", padx=10, pady=(0, 7))
        registrations_header = tk.Frame(self.tournaments_tab, bg="white")
        registrations_header.pack(fill="x", padx=10, pady=(0, 6))
        tk.Label(
            registrations_header,
            text="Inscripciones del torneo seleccionado",
            font=("Segoe UI", 11, "bold"),
            fg=self.NAVY,
            bg="white",
        ).pack(side="left", padx=(3, 14))
        self._action_button(
            registrations_header,
            "Nueva inscripción",
            lambda: self._registration_dialog(edit=False),
            self.BLUE,
        ).pack(side="left", padx=3)
        self._action_button(
            registrations_header,
            "Editar datos",
            lambda: self._registration_dialog(edit=True),
            self.ORANGE,
        ).pack(side="left", padx=3)
        self._action_button(
            registrations_header,
            "Confirmar seña",
            lambda: self._registration_payment(total=False),
            self.GREEN,
        ).pack(side="left", padx=3)
        self._action_button(
            registrations_header,
            "Confirmar total",
            lambda: self._registration_payment(total=True),
            self.GREEN,
        ).pack(side="left", padx=3)
        self._action_button(
            registrations_header,
            "Liberar / cancelar",
            self._cancel_registration,
            self.RED,
        ).pack(side="left", padx=3)

        registration_columns = (
            "id", "team", "contact", "phone", "status", "paid", "pending", "method"
        )
        self.registration_tree = ttk.Treeview(
            self.tournaments_tab,
            columns=registration_columns,
            show="headings",
            selectmode="browse",
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
            self.tournaments_tab,
            orient="vertical",
            command=self.registration_tree.yview,
        )
        self.registration_tree.configure(yscrollcommand=registration_scroll.set)
        registration_scroll.pack(side="right", fill="y", pady=(0, 10))
        self.registration_tree.pack(fill="both", expand=True, padx=(10, 0), pady=(0, 10))

    def _build_commands(self) -> None:
        bar = tk.Frame(self.commands_tab, bg="white")
        bar.pack(fill="x", padx=14, pady=12)
        self._action_button(bar, "Abrir configuración", self.open_configurator_callback, self.BLUE).pack(side="left")
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
        scrollbar = ttk.Scrollbar(body, orient="vertical", command=text.yview)
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
            self._refresh_hours()
        except Exception as exc:
            messagebox.showerror("Administración", f"No pude actualizar el panel:\n{exc}", parent=self)

    def _apply_notification_counts(self, counts: dict[str, int]) -> None:
        normalized = {
            key: max(0, int(counts.get(key, 0) or 0))
            for key in ("bookings", "hours", "operation", "cases", "tournaments", "commands")
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
        method = getattr(self.service, "notification_counts", None)
        if callable(method):
            return method(stats)
        bookings = max(0, int(stats.get("pending", 0) or 0))
        cases = max(0, int(stats.get("cases", 0) or 0))
        return {
            "bookings": bookings,
            "hours": 0,
            "operation": 0,
            "cases": cases,
            "tournaments": 0,
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
        for index, row in enumerate(self.service.bookings()):
            self.booking_tree.insert("", "end", iid=f"booking:{row.get('reservation_id')}:{index}", values=(
                row.get("reservation_id", ""), row.get("fecha", ""), row.get("hora", ""), row.get("cancha", ""),
                row.get("nombre", ""), row.get("telefono", ""), row.get("estado", ""), row.get("senia_estado", ""),
                row.get("monto_pendiente", ""),
            ))

    def _selected_booking_id(self) -> str:
        selection = self.booking_tree.selection()
        if not selection:
            raise ValueError("Seleccioná una reserva de la tabla.")
        return str(self.booking_tree.item(selection[0], "values")[0])

    def _booking_action(self, action: str) -> None:
        try:
            reservation_id = self._selected_booking_id()
            labels = {"deposit": "confirmar la seña", "total": "confirmar el pago total", "release": "liberar el pendiente", "cancel": "cancelar la reserva"}
            if not messagebox.askyesno("Administración", f"¿Querés {labels[action]} de la reserva ID {reservation_id}?", parent=self):
                return
            if action == "deposit":
                result = self.service.confirm_payment(reservation_id)
            elif action == "total":
                result = self.service.confirm_payment(reservation_id, total=True)
            elif action == "release":
                result = self.service.release_booking(reservation_id)
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
            schedule = self.service.day_schedule(self.hours_day_var.get())
        except Exception as exc:
            messagebox.showerror("Horas", str(exc), parent=self)
            return

        self.hours_day_var.set(schedule["day"])
        for widget in self.hours_grid.winfo_children():
            widget.destroy()

        courts = schedule["courts"]
        slots = schedule["slots"]
        cell_map = {(cell["time"], cell["court"]): cell for cell in schedule["cells"]}
        tk.Label(
            self.hours_grid,
            text="Hora",
            font=("Segoe UI", 10, "bold"),
            fg=self.NAVY,
            bg="#eef2f6",
            width=9,
            pady=10,
        ).grid(row=0, column=0, sticky="nsew", padx=2, pady=2)
        catalog_method = getattr(self.service, "court_catalog", None)
        catalog = catalog_method() if callable(catalog_method) else []
        identities = {str(item.get("name")): item for item in catalog}
        for column, court in enumerate(courts, start=1):
            self.hours_grid.grid_columnconfigure(column, weight=1, minsize=180)
            identity = identities.get(court, {})
            icon = str(identity.get("icon") or "🏟️")
            court_type = str(identity.get("type") or "").strip()
            header = tk.Label(
                self.hours_grid,
                text=f"{icon} {court}" + (f" · {court_type}" if court_type else ""),
                font=("Segoe UI", 10, "bold"),
                fg=self.NAVY,
                bg="#eef2f6",
                pady=10,
                cursor="hand2",
            )
            header.grid(row=0, column=column, sticky="nsew", padx=2, pady=2)
            header.bind(
                "<Button-3>",
                lambda event, selected_court=court: self._show_court_sport_menu(
                    event, selected_court
                ),
            )

        for row_index, time in enumerate(slots, start=1):
            tk.Label(
                self.hours_grid,
                text=time,
                font=("Segoe UI", 11, "bold"),
                fg=self.NAVY,
                bg="#f8fafc",
                width=9,
            ).grid(row=row_index, column=0, sticky="nsew", padx=2, pady=2)
            for column, court in enumerate(courts, start=1):
                cell = cell_map[(time, court)]
                text, color = self._hour_cell_style(cell)
                tk.Button(
                    self.hours_grid,
                    text=text,
                    command=lambda selected=cell: self._open_hour_cell(selected),
                    bg=color,
                    fg="white",
                    activebackground=color,
                    activeforeground="white",
                    relief="flat",
                    cursor="hand2",
                    font=("Segoe UI", 9, "bold"),
                    padx=8,
                    pady=8,
                ).grid(row=row_index, column=column, sticky="nsew", padx=2, pady=2)

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
        self.hours_status_var.set(f"{schedule['display_day']} · {len(slots)} horarios")
        self.hours_canvas.update_idletasks()
        self.hours_canvas.configure(scrollregion=self.hours_canvas.bbox("all"))

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
        if status == "blocked":
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
        return "$" + f"{amount:,}".replace(",", ".")

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

