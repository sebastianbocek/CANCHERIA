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
from tkinter import messagebox

from cancheria.desktop.session_manager import ensure_profile, reset_profile, SessionResetError


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

    def __init__(self) -> None:
        super().__init__()
        self.root_dir = install_root()
        self.profile_dir = self.root_dir / "wa_profile"
        self.manual_path = self.root_dir / "docs" / "MANUAL_DE_USO_CANCHERIA_DUENOS_ENCARGADOS.pdf"
        self.process: subprocess.Popen[str] | None = None
        self.admin_window: tk.Toplevel | None = None
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
        tk.Button(
            secondary,
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
        ).pack(side="left", padx=(8, 0))
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
        tk.Label(
            secondary,
            text="Administración gestiona reservas, pagos, agenda y casos humanos.",
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

            self.admin_window = AdminPanel(
                self,
                DesktopAdminService(self.root_dir),
                self.open_configurator,
            )
            self.admin_window.protocol(
                "WM_DELETE_WINDOW",
                lambda: (self.admin_window.destroy(), setattr(self, "admin_window", None)),
            )
            self._append_log("🛠 Panel de administración abierto.")
        except Exception as exc:
            self.admin_window = None
            messagebox.showerror("CANCHERIA", f"No pude abrir Administración:\n{exc}")

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
