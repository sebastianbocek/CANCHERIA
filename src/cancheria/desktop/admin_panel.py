from __future__ import annotations

import tkinter as tk
from tkinter import messagebox, ttk
from typing import Callable

from cancheria.admin.desktop_service import DesktopAdminService


COMMAND_REFERENCE = """CONTROL DEL AGENTE
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
    ) -> None:
        super().__init__(parent)
        self.service = service
        self.open_configurator_callback = open_configurator
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
        self.commands_tab = tk.Frame(self.notebook, bg="white")
        self.notebook.add(self.bookings_tab, text="Reservas y pagos")
        self.notebook.add(self.hours_tab, text="Horas")
        self.notebook.add(self.operation_tab, text="Operación")
        self.notebook.add(self.cases_tab, text="Atención humana")
        self.notebook.add(self.commands_tab, text="Comandos y configuración")
        self._build_bookings()
        self._build_hours()
        self._build_operation()
        self._build_cases()
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
        tk.Label(toolbar, text="Fecha", font=("Segoe UI", 10, "bold"), fg=self.NAVY, bg="white").pack(side="left")
        self.hours_day_var = tk.StringVar(value=dt_today())
        date_entry = tk.Entry(toolbar, textvariable=self.hours_day_var, width=13, font=("Segoe UI", 10))
        date_entry.pack(side="left", padx=(8, 5), ipady=5)
        date_entry.bind("<Return>", lambda _event: self._refresh_hours())
        self._action_button(toolbar, "◀", lambda: self._move_hours_date(-1), self.NAVY).pack(side="left", padx=2)
        self._action_button(toolbar, "Hoy", self._set_hours_today, self.BLUE).pack(side="left", padx=2)
        self._action_button(toolbar, "▶", lambda: self._move_hours_date(1), self.NAVY).pack(side="left", padx=2)
        self._action_button(toolbar, "Ver horarios", self._refresh_hours, self.BLUE).pack(side="left", padx=(8, 2))

        legend = tk.Frame(self.hours_tab, bg="white")
        legend.pack(fill="x", padx=14, pady=(0, 8))
        self._legend_item(legend, self.FREE_GREEN, "Disponible")
        self._legend_item(legend, self.RED, "Ocupado / bloqueado")
        self._legend_item(legend, self.PAST_GRAY, "Horario pasado / fuera de atención")
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

    def _resize_hours_grid(self, event) -> None:
        requested = self.hours_grid.winfo_reqwidth()
        self.hours_canvas.itemconfigure(self.hours_grid_window, width=max(event.width, requested))

    def _on_tab_changed(self, _event=None) -> None:
        if self.notebook.select() == str(self.hours_tab):
            self._refresh_hours()

    def _build_operation(self) -> None:
        form = tk.Frame(self.operation_tab, bg="white")
        form.pack(anchor="nw", padx=24, pady=24)
        tk.Label(form, text="Bloqueo de agenda", font=("Segoe UI", 14, "bold"), fg=self.NAVY, bg="white").grid(row=0, column=0, columnspan=3, sticky="w", pady=(0, 14))
        tk.Label(form, text="Fecha (AAAA-MM-DD o ‘mañana’)", bg="white", fg=self.NAVY).grid(row=1, column=0, sticky="w")
        self.block_day_var = tk.StringVar(value=dt_today())
        tk.Entry(form, textvariable=self.block_day_var, width=24).grid(row=2, column=0, sticky="w", padx=(0, 10), pady=(3, 12))
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

    def _build_commands(self) -> None:
        bar = tk.Frame(self.commands_tab, bg="white")
        bar.pack(fill="x", padx=14, pady=12)
        self._action_button(bar, "Abrir configuración", self.open_configurator_callback, self.BLUE).pack(side="left")
        tk.Label(bar, text="Referencia de las mismas funciones disponibles por WhatsApp", bg="white", fg=self.MUTED).pack(side="left", padx=14)
        text = tk.Text(self.commands_tab, wrap="word", font=("Consolas", 10), bg="#f8fafc", fg=self.NAVY, relief="flat", padx=14, pady=14)
        text.insert("1.0", COMMAND_REFERENCE)
        text.configure(state="disabled")
        text.pack(fill="both", expand=True, padx=14, pady=(0, 14))

    def refresh_all(self) -> None:
        try:
            for key, value in self.service.stats().items():
                if key in self.summary_vars:
                    self.summary_vars[key].set(str(value))
            self._refresh_bookings()
            self._refresh_cases()
            self._refresh_hours()
        except Exception as exc:
            messagebox.showerror("Administración", f"No pude actualizar el panel:\n{exc}", parent=self)

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
        for column, court in enumerate(courts, start=1):
            self.hours_grid.grid_columnconfigure(column, weight=1, minsize=180)
            tk.Label(
                self.hours_grid,
                text=court,
                font=("Segoe UI", 10, "bold"),
                fg=self.NAVY,
                bg="#eef2f6",
                pady=10,
            ).grid(row=0, column=column, sticky="nsew", padx=2, pady=2)

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
                text="No hay franjas horarias configuradas.",
                bg="white",
                fg=self.MUTED,
                pady=30,
            ).grid(row=1, column=0, columnspan=max(1, len(courts) + 1), sticky="ew")
        self.hours_status_var.set(f"{schedule['display_day']} · {len(slots)} horarios")
        self.hours_canvas.update_idletasks()
        self.hours_canvas.configure(scrollregion=self.hours_canvas.bbox("all"))

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

