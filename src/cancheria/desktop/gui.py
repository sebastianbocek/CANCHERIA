from __future__ import annotations

import os
import queue
import signal
import subprocess
import sys
import threading
import time
import webbrowser
from pathlib import Path
import tkinter as tk
from tkinter import messagebox, ttk

from cancheria import __version__
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
    BG = "#f7f9fc"
    PANEL = "#ffffff"
    NAVY = "#061632"
    BLUE = "#1677ff"
    MUTED = "#6b7280"
    GREEN = "#14804a"
    ORANGE = "#b45309"
    RED = "#b42318"
    UPDATE_POLL_INTERVAL_MS = 6 * 60 * 60 * 1000
    UPDATE_STARTUP_DELAY_MS = 350
    UPDATE_STARTUP_RETRY_MS = 30_000
    UPDATE_STARTUP_CHECKS = 3

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
        self._update_notification_poll_id: str | None = None
        self._update_check_in_progress = False
        self._startup_update_checks_remaining = self.UPDATE_STARTUP_CHECKS
        self._announced_update_version = ""
        self.log_queue: queue.Queue[str] = queue.Queue()
        self._closing = False

        ensure_profile(self.profile_dir)

        self.title("CANCHERIA")
        self.geometry("920x720")
        self.minsize(820, 620)
        self.configure(bg=self.BG)
        try:
            self.iconbitmap(str(self.root_dir / "assets" / "cancheria.ico"))
        except Exception:
            pass

        self._build_ui()
        self.after(120, self._drain_log_queue)
        self.after(700, self._poll_process)
        self.after(450, self._show_update_result)
        self.after(800, self._poll_admin_notifications)
        self._update_notification_poll_id = self.after(
            self.UPDATE_STARTUP_DELAY_MS,
            self._poll_update_notifications,
        )
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    def _build_ui(self) -> None:
        header = tk.Frame(self, bg=self.PANEL, bd=0, highlightthickness=0)
        header.pack(fill="x", padx=18, pady=(18, 10))

        logo_path = self.root_dir / "assets" / "cancheria-logo.png"
        self._logo = None
        if logo_path.exists():
            try:
                img = tk.PhotoImage(file=str(logo_path))
                # Original is large. Tk's integer subsampling keeps the app dependency-free.
                factor = max(1, int(max(img.width() / 470, img.height() / 250)))
                if factor > 1:
                    img = img.subsample(factor, factor)
                self._logo = img
                tk.Label(header, image=img, bg=self.PANEL).pack(pady=(12, 0))
            except Exception:
                pass

        if self._logo is None:
            tk.Label(
                header,
                text="CANCHERIA",
                font=("Segoe UI", 28, "bold"),
                fg=self.NAVY,
                bg=self.PANEL,
            ).pack(pady=(22, 4))

        tk.Label(
            header,
            text="Agente de reservas · Panel de escritorio",
            font=("Segoe UI", 11),
            fg=self.MUTED,
            bg=self.PANEL,
        ).pack(pady=(0, 12))

        status_row = tk.Frame(self, bg=self.BG)
        status_row.pack(fill="x", padx=24, pady=(2, 8))
        tk.Label(status_row, text="Estado:", font=("Segoe UI", 11, "bold"), bg=self.BG, fg=self.NAVY).pack(side="left")
        self.status_var = tk.StringVar(value="Apagado")
        self.status_label = tk.Label(status_row, textvariable=self.status_var, font=("Segoe UI", 11, "bold"), bg=self.BG, fg=self.MUTED)
        self.status_label.pack(side="left", padx=(8, 0))
        tk.Label(status_row, text="Perfil: wa_profile", font=("Segoe UI", 10), bg=self.BG, fg=self.MUTED).pack(side="right")

        actions = tk.Frame(self, bg=self.BG)
        actions.pack(fill="x", padx=20, pady=(4, 12))
        for col in range(4):
            actions.grid_columnconfigure(col, weight=1)

        self.btn_on = self._button(actions, "ENCENDER", self.start_agent, self.GREEN)
        self.btn_pause = self._button(actions, "PAUSA", self.pause_agent, self.ORANGE)
        self.btn_logout = self._button(actions, "CERRAR SESIÓN", self.close_session, self.RED)
        self.btn_new = self._button(actions, "NUEVA SESIÓN", self.new_session, self.BLUE)
        self.btn_on.grid(row=0, column=0, sticky="ew", padx=5)
        self.btn_pause.grid(row=0, column=1, sticky="ew", padx=5)
        self.btn_logout.grid(row=0, column=2, sticky="ew", padx=5)
        self.btn_new.grid(row=0, column=3, sticky="ew", padx=5)

        secondary = tk.Frame(self, bg=self.BG)
        secondary.pack(fill="x", padx=25, pady=(0, 10))
        tk.Button(
            secondary,
            text="CONFIGURACIÓN",
            command=self.open_configurator,
            font=("Segoe UI", 10, "bold"),
            bg=self.BLUE,
            fg="white",
            activebackground=self.BLUE,
            activeforeground="white",
            relief="flat",
            bd=0,
            padx=14,
            pady=8,
            cursor="hand2",
        ).pack(side="left")
        admin_button_holder = tk.Frame(secondary, bg=self.BG)
        admin_button_holder.pack(side="left", padx=(8, 0))
        self.btn_admin = tk.Button(
            admin_button_holder,
            text="ADMINISTRACIÓN",
            command=self.open_admin_panel,
            font=("Segoe UI", 10, "bold"),
            bg=self.NAVY,
            fg="white",
            activebackground=self.NAVY,
            activeforeground="white",
            relief="flat",
            bd=0,
            padx=14,
            pady=8,
            cursor="hand2",
        )
        self.btn_admin.pack()
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
        tk.Button(
            secondary,
            text="Abrir manual",
            command=self.open_manual,
            font=("Segoe UI", 10, "bold"),
            bg=self.PANEL,
            fg=self.NAVY,
            activebackground="#eef4ff",
            relief="solid",
            bd=1,
            padx=14,
            pady=7,
            cursor="hand2",
        ).pack(side="left", padx=(8, 0))
        update_button_holder = tk.Frame(secondary, bg=self.BG)
        update_button_holder.pack(side="left", padx=(8, 0))
        self.btn_settings = tk.Button(
            update_button_holder,
            text="⬆ ACTUALIZACIÓN",
            command=self.open_settings,
            font=("Segoe UI", 10, "bold"),
            bg=self.PANEL,
            fg=self.NAVY,
            activebackground="#eef4ff",
            relief="solid",
            bd=1,
            padx=14,
            pady=7,
            cursor="hand2",
        )
        self.btn_settings.pack()
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
        tk.Label(
            secondary,
            text="Reservas, agenda y versión del sistema.",
            font=("Segoe UI", 9),
            bg=self.BG,
            fg=self.MUTED,
        ).pack(side="left", padx=14)

        log_panel = tk.Frame(self, bg=self.PANEL, bd=1, relief="solid")
        log_panel.pack(fill="both", expand=True, padx=24, pady=(0, 18))
        tk.Label(
            log_panel,
            text="Actividad",
            font=("Segoe UI", 11, "bold"),
            fg=self.NAVY,
            bg=self.PANEL,
            anchor="w",
        ).pack(fill="x", padx=12, pady=(10, 5))
        self.log = tk.Text(
            log_panel,
            height=16,
            wrap="word",
            bg="#07111f",
            fg="#dce7f7",
            insertbackground="white",
            font=("Consolas", 9),
            relief="flat",
            padx=10,
            pady=10,
        )
        self.log.pack(fill="both", expand=True, padx=10, pady=(0, 10))
        self.log.configure(state="disabled")
        self._append_log("CANCHERIA listo. Presioná ENCENDER para usar la sesión guardada o NUEVA SESIÓN para escanear un QR nuevo.")

    def _button(self, parent: tk.Widget, label: str, command, color: str) -> tk.Button:
        return tk.Button(
            parent,
            text=label,
            command=command,
            font=("Segoe UI", 10, "bold"),
            bg=color,
            fg="white",
            activebackground=color,
            activeforeground="white",
            relief="flat",
            bd=0,
            padx=12,
            pady=12,
            cursor="hand2",
        )

    def _append_log(self, text: str) -> None:
        if not text:
            return
        self.log.configure(state="normal")
        self.log.insert("end", text.rstrip() + "\n")
        self.log.see("end")
        self.log.configure(state="disabled")

    def _set_status(self, text: str, color: str) -> None:
        self.status_var.set(text)
        self.status_label.configure(fg=color)

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

        self._set_status("Verificando API key...", self.ORANGE)
        self.update_idletasks()
        credential_check = verify_openai_api_key(AppSettings.from_env().openai_api_key)
        if credential_check.status != CredentialStatus.VALID:
            self._set_status("Configuración requerida", self.RED)
            self._append_log(f"⚠ No se inició: {credential_check.message}")
            messagebox.showerror(
                "CANCHERIA · API key",
                f"{credential_check.message}\n\n"
                "Abrí CONFIGURACIÓN, pegá una clave válida y guardá nuevamente.\n\n"
                "https://platform.openai.com/api-keys",
            )
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

        self._set_status("Encendido", self.GREEN)
        self._append_log(f"▶ CANCHERIA iniciado con profile: {self.profile_dir.name}")
        threading.Thread(target=self._read_worker_output, args=(self.process,), daemon=True).start()

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
            if self.status_var.get() == "Encendido":
                self._set_status("Apagado", self.MUTED if code == 0 else self.RED)
            self.process = None
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

    def pause_agent(self) -> None:
        if not self.process or self.process.poll() is not None:
            self._set_status("Pausado", self.ORANGE)
            self._append_log("CANCHERIA ya estaba detenido. La sesión de WhatsApp sigue guardada.")
            return
        self._stop_process()
        self._set_status("Pausado", self.ORANGE)
        self._append_log("⏸ Pausado. El perfil wa_profile se conserva; ENCENDER retoma la misma sesión.")

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

    def _schedule_update_notification_poll(self, delay_ms: int | None = None) -> None:
        if self._closing:
            return
        if self._update_notification_poll_id is not None:
            try:
                self.after_cancel(self._update_notification_poll_id)
            except Exception:
                pass
        self._update_notification_poll_id = self.after(
            delay_ms or self.UPDATE_POLL_INTERVAL_MS,
            self._poll_update_notifications,
        )

    def _poll_update_notifications(self) -> None:
        self._update_notification_poll_id = None
        if self._closing:
            return
        if self._update_check_in_progress:
            self._schedule_update_notification_poll(60_000)
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
        if self._startup_update_checks_remaining > 0:
            self._startup_update_checks_remaining -= 1
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
        retry_startup = (
            release is None
            and self._startup_update_checks_remaining > 0
        )
        self._schedule_update_notification_poll(
            self.UPDATE_STARTUP_RETRY_MS if retry_startup else None
        )

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
        if self._update_notification_poll_id is not None:
            try:
                self.after_cancel(self._update_notification_poll_id)
            except Exception:
                pass
        self._stop_process()
        self.destroy()


def main() -> int:
    app = CancheriaDesktop()
    app.mainloop()
    return 0
