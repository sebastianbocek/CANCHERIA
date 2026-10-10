from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import traceback
from datetime import datetime
from pathlib import Path

from cancheria.desktop.update_service import UpdateError, validate_staged_update


def _stop_installed_configurator(install_dir: Path) -> None:
    """Stop only the configurator that belongs to this installation on Windows."""
    if os.name != "nt":
        return
    target = str((Path(install_dir) / "configurador_cancheria.exe").resolve())
    script = (
        "$target=[IO.Path]::GetFullPath($args[0]);"
        "Get-CimInstance Win32_Process -Filter \"Name='configurador_cancheria.exe'\" "
        "-ErrorAction SilentlyContinue | Where-Object { $_.ExecutablePath -and "
        "([IO.Path]::GetFullPath($_.ExecutablePath) -eq $target) } | "
        "ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }"
    )
    try:
        subprocess.run(
            [
                "powershell.exe", "-NoProfile", "-NonInteractive",
                "-ExecutionPolicy", "Bypass", "-Command", script, target,
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=15,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        pass


def _preflight_windows_executables(
    install_dir: Path, files: dict[str, str]
) -> None:
    """Detect locked executables before replacing any installation file."""
    if os.name != "nt":
        return
    for relative in files:
        destination = _safe_destination(install_dir, relative)
        if destination.suffix.casefold() != ".exe" or not destination.exists():
            continue
        probe = destination.with_name(destination.name + ".cancheria-lock-check")
        try:
            probe.unlink(missing_ok=True)
            os.replace(destination, probe)
            os.replace(probe, destination)
        except OSError as exc:
            if probe.exists() and not destination.exists():
                try:
                    os.replace(probe, destination)
                except OSError:
                    pass
            raise UpdateError(
                f"No se puede actualizar porque {destination.name} sigue abierto. "
                "Cerralo y volvé a intentar. No se modificó ningún archivo."
            ) from exc


def _wait_for_parent(parent_pid: int, timeout: float = 120.0) -> None:
    if os.name == "nt":
        _wait_for_windows_process(parent_pid, timeout)
        return

    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            os.kill(parent_pid, 0)
        except (OSError, SystemError):
            return
        time.sleep(0.25)
    raise UpdateError("CANCHERIA no se cerró a tiempo y la actualización fue cancelada.")


def _wait_for_windows_process(parent_pid: int, timeout: float) -> None:
    """Wait on a Windows process handle without relying on ``os.kill(pid, 0)``.

    CPython's frozen Windows runtime can raise ``SystemError`` when the probed
    process exits between the internal handle checks.  Waiting on the native
    process handle is atomic and also protects against PID reuse.
    """
    import ctypes
    from ctypes import wintypes

    synchronize = 0x00100000
    wait_object_0 = 0x00000000
    wait_timeout = 0x00000102
    error_invalid_parameter = 87

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.OpenProcess.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
    kernel32.OpenProcess.restype = wintypes.HANDLE
    kernel32.WaitForSingleObject.argtypes = (wintypes.HANDLE, wintypes.DWORD)
    kernel32.WaitForSingleObject.restype = wintypes.DWORD
    kernel32.CloseHandle.argtypes = (wintypes.HANDLE,)
    kernel32.CloseHandle.restype = wintypes.BOOL

    handle = kernel32.OpenProcess(synchronize, False, int(parent_pid))
    if not handle:
        error = ctypes.get_last_error()
        if error == error_invalid_parameter:
            return
        raise UpdateError(
            f"No se pudo comprobar el cierre de CANCHERIA (error de Windows {error})."
        )

    try:
        result = kernel32.WaitForSingleObject(handle, max(1, int(timeout * 1000)))
    finally:
        kernel32.CloseHandle(handle)

    if result == wait_object_0:
        return
    if result == wait_timeout:
        raise UpdateError("CANCHERIA no se cerró a tiempo y la actualización fue cancelada.")
    raise UpdateError(
        f"Windows no pudo esperar el cierre de CANCHERIA (resultado {int(result)})."
    )


def _safe_destination(install_dir: Path, relative: str) -> Path:
    destination = (install_dir / Path(relative)).resolve()
    try:
        destination.relative_to(install_dir.resolve())
    except ValueError as exc:
        raise UpdateError(f"Destino inseguro en la actualización: {relative}") from exc
    return destination


def _hash_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def apply_staged_update(
    install_dir: Path,
    staged_dir: Path,
    version: str,
    target_platform: str,
    *,
    reinstall_linux_dependencies: bool = True,
) -> None:
    install_dir = Path(install_dir).resolve()
    staged_dir = Path(staged_dir).resolve()
    if not (install_dir / "WPSetter.py").is_file() or not (install_dir / "src" / "cancheria").is_dir():
        raise UpdateError("La carpeta seleccionada no parece una instalación válida de CANCHERIA.")
    manifest = validate_staged_update(staged_dir, version, target_platform)
    files: dict[str, str] = manifest["files"]
    _stop_installed_configurator(install_dir)
    _preflight_windows_executables(install_dir, files)
    rollback_dir = Path(tempfile.mkdtemp(prefix="cancheria-rollback-"))
    replaced: list[str] = []
    newly_created: list[str] = []
    try:
        for relative in files:
            source = staged_dir / Path(relative)
            destination = _safe_destination(install_dir, relative)
            if destination.exists():
                rollback_target = rollback_dir / Path(relative)
                rollback_target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(destination, rollback_target)
                replaced.append(relative)
            else:
                newly_created.append(relative)

            destination.parent.mkdir(parents=True, exist_ok=True)
            temporary = destination.with_name(destination.name + ".cancheria-new")
            shutil.copy2(source, temporary)
            os.replace(temporary, destination)

        for relative, expected_hash in files.items():
            destination = _safe_destination(install_dir, relative)
            if not destination.is_file() or _hash_file(destination).lower() != expected_hash.lower():
                raise UpdateError(f"No se pudo verificar el archivo instalado: {relative}")

        if target_platform == "linux" and reinstall_linux_dependencies:
            python = install_dir / ".venv" / "bin" / "python"
            if not python.is_file():
                raise UpdateError("No se encontró el entorno Python de la instalación Debian.")
            completed = subprocess.run(
                [str(python), "-m", "pip", "install", "--disable-pip-version-check", "--upgrade", "-e", str(install_dir)],
                cwd=install_dir,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=300,
            )
            if completed.returncode != 0:
                raise UpdateError("No se pudieron actualizar las dependencias de Debian.")
    except Exception:
        for relative in reversed(newly_created):
            destination = _safe_destination(install_dir, relative)
            destination.unlink(missing_ok=True)
        for relative in reversed(replaced):
            backup = rollback_dir / Path(relative)
            destination = _safe_destination(install_dir, relative)
            destination.parent.mkdir(parents=True, exist_ok=True)
            if backup.is_file():
                shutil.copy2(backup, destination)
        raise
    finally:
        shutil.rmtree(rollback_dir, ignore_errors=True)


def _write_status(install_dir: Path, success: bool, version: str, detail: str, backup_zip: str) -> None:
    status_path = install_dir / "Backups" / "ultima_actualizacion.json"
    status_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "success": success,
        "version": version,
        "date": datetime.now().isoformat(timespec="seconds"),
        "detail": detail,
        "backup": backup_zip,
    }
    status_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Auxiliar seguro de actualización de CANCHERIA")
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--parent-pid", type=int)
    parser.add_argument("--install-dir")
    parser.add_argument("--staged-dir")
    parser.add_argument("--version")
    parser.add_argument("--platform", choices=("windows", "linux"))
    parser.add_argument("--backup-zip", default="")
    parser.add_argument("--restart-command-json", default="[]")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.self_test:
        return 0
    if not args.apply or not all(
        (args.parent_pid, args.install_dir, args.staged_dir, args.version, args.platform)
    ):
        return 2

    install_dir = Path(args.install_dir).resolve()
    restart_command: list[str] = []
    try:
        decoded = json.loads(args.restart_command_json)
        if isinstance(decoded, list) and all(isinstance(item, str) for item in decoded):
            restart_command = decoded
        _wait_for_parent(args.parent_pid)
        apply_staged_update(
            install_dir,
            Path(args.staged_dir),
            args.version,
            args.platform,
        )
        _write_status(
            install_dir,
            True,
            args.version,
            "Actualización instalada correctamente.",
            args.backup_zip,
        )
        exit_code = 0
    except Exception as exc:
        detail = f"{type(exc).__name__}: {exc}"
        try:
            _write_status(install_dir, False, args.version or "", detail, args.backup_zip)
            log_path = install_dir / "Backups" / "ultima_actualizacion_error.log"
            log_path.write_text(traceback.format_exc(), encoding="utf-8")
        except Exception:
            pass
        exit_code = 1

    if restart_command:
        try:
            subprocess.Popen(
                restart_command,
                cwd=install_dir,
                start_new_session=(os.name != "nt"),
                creationflags=(subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0),
            )
        except OSError:
            pass
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
