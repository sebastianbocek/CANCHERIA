from __future__ import annotations

import argparse
import hashlib
import os
import re
import shutil
import subprocess
import sys
import tempfile
import traceback
import zipfile
from datetime import datetime
from pathlib import Path


APP_TITLE = "CANCHERIA - Backup fresco"
OUTPUT_DIRECTORY = "backups_clientes"
ZIP_PREFIX = "CANCHERIA_CLIENTE_FRESCO"

ROOT_FILES = (
    "WPSetter.py",
    "calendario.py",
    "cancheria_desktop.py",
    "config.py",
    "configurador_cancheria.py",
    "event_registration_engine.py",
    ".env.example",
    "README.md",
    "SECURITY.md",
    "CONTRIBUTING.md",
    "CHANGELOG.md",
    "pyproject.toml",
    "requirements.txt",
)
SOURCE_DIRECTORIES = ("src", "legacy", "assets", "docs", "examples")
EMPTY_DATA_DIRECTORIES = ("runtime", "wa_profile", "sessions")
REQUIRED_MARKERS = (
    "cancheria_desktop.py",
    "configurador_cancheria.py",
    "src/cancheria/config/legacy_config.py",
)

OPENAI_KEY_PATTERN = re.compile(rb"sk-[A-Za-z0-9_-]{16,}")
PRIVATE_KEY_PATTERN = re.compile(rb"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----")
TEXT_EXTENSIONS = {
    ".bat",
    ".cfg",
    ".cmd",
    ".env",
    ".ini",
    ".json",
    ".md",
    ".ps1",
    ".py",
    ".toml",
    ".txt",
    ".yaml",
    ".yml",
}

COMMON_HIDDEN_IMPORTS = (
    "json",
    "sqlite3",
    "_sqlite3",
    "decimal",
    "zoneinfo",
    "email.mime.image",
    "email.mime.multipart",
    "email.mime.text",
    "openai",
    "playwright.async_api",
    "pytz",
    "dotenv",
    "cancheria.legacy_bridge",
    "cancheria.paths",
    "cancheria.config.legacy_config",
    "cancheria.domain.events.registration",
    "cancheria.domain.reservations.calendar",
    "cancheria.admin.desktop_service",
    "cancheria.desktop.admin_panel",
)


class BuildError(RuntimeError):
    pass


def log(message: str) -> None:
    print(message, flush=True)


def is_project_root(path: Path) -> bool:
    return all((path / marker).is_file() for marker in REQUIRED_MARKERS)


def find_project_root(explicit: str | None = None) -> Path:
    candidates: list[Path] = []
    if explicit:
        candidates.append(Path(explicit))
    if getattr(sys, "frozen", False):
        executable_dir = Path(sys.executable).resolve().parent
        candidates.extend((executable_dir, executable_dir.parent))
    else:
        candidates.append(Path(__file__).resolve().parents[1])
    candidates.append(Path.cwd())

    checked: set[Path] = set()
    for candidate in candidates:
        try:
            resolved = candidate.expanduser().resolve()
        except OSError:
            continue
        for possible in (resolved, *resolved.parents):
            if possible in checked:
                continue
            checked.add(possible)
            if is_project_root(possible):
                return possible
    raise BuildError(
        "No encontré la carpeta CANCHERIA_DESKTOP_PACKAGEPATH_FIXED. "
        "Guardá este EXE en la raíz del proyecto o usá --source RUTA."
    )


def safe_remove_tree(path: Path, root: Path) -> None:
    resolved_path = path.resolve()
    resolved_root = root.resolve()
    if resolved_path == resolved_root or resolved_root not in resolved_path.parents:
        raise BuildError(f"Se rechazó una limpieza fuera del build: {resolved_path}")
    if resolved_path.exists():
        shutil.rmtree(resolved_path)


def copy_fresh_source(root: Path, source_root: Path) -> Path:
    log("[1/7] Preparando una copia limpia del proyecto...")
    source_root.mkdir(parents=True, exist_ok=True)
    for name in ROOT_FILES:
        source = root / name
        if source.is_file():
            shutil.copy2(source, source_root / name)
    for name in SOURCE_DIRECTORIES:
        source = root / name
        if not source.is_dir():
            raise BuildError(f"Falta la carpeta requerida: {source}")
        shutil.copytree(
            source,
            source_root / name,
            ignore=shutil.ignore_patterns(
                "__pycache__", "*.pyc", "*.pyo", "*.egg-info", "config_backups"
            ),
        )

    template = (
        root
        / "src"
        / "cancheria"
        / "config"
        / "config_backups"
        / "config_20261006_213845.py"
    )
    if not template.is_file():
        raise BuildError(f"No existe la plantilla limpia: {template}")
    clean_config = source_root / "src" / "cancheria" / "config" / "legacy_config.py"
    shutil.copy2(template, clean_config)

    # Preserve the current safe model fallback without copying the configured
    # source file, which can contain the owner's real credentials.
    config_text = clean_config.read_text(encoding="utf-8")
    config_text, replacements = re.subn(
        r"^OPENAI_MODEL\s*=.*$",
        'OPENAI_MODEL = os.getenv("OPENAI_MODEL", "").strip() or "gpt-4o-mini"',
        config_text,
        count=1,
        flags=re.MULTILINE,
    )
    if replacements != 1:
        raise BuildError("No pude preparar el modelo predeterminado de la configuración limpia.")
    clean_config.write_text(config_text, encoding="utf-8", newline="\n")
    return clean_config


def run_command(command: list[str], *, env: dict[str, str], description: str) -> None:
    log(description)
    completed = subprocess.run(command, env=env, check=False)
    if completed.returncode != 0:
        raise BuildError(f"Falló el comando con código {completed.returncode}: {description}")


def pyinstaller_command(
    python_exe: Path,
    *,
    name: str,
    entrypoint: Path,
    source_root: Path,
    dist_root: Path,
    work_root: Path,
    spec_root: Path,
    icon: Path,
    hidden_imports: tuple[str, ...],
) -> list[str]:
    command = [
        str(python_exe),
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--clean",
        "--onefile",
        "--windowed",
        "--name",
        name,
        "--distpath",
        str(dist_root),
        "--workpath",
        str(work_root),
        "--specpath",
        str(spec_root),
        "--icon",
        str(icon),
        "--paths",
        str(source_root / "src"),
    ]
    for module_name in hidden_imports:
        command.extend(("--hidden-import", module_name))
    command.append(str(entrypoint))
    return command


def build_clean_executables(root: Path, source_root: Path, build_root: Path) -> Path:
    build_python = root / ".build-venv" / "Scripts" / "python.exe"
    icon = root / "assets" / "cancheria.ico"
    if not build_python.is_file():
        raise BuildError(
            f"No existe el entorno de compilación {build_python}. Ejecutá build_windows.bat una vez."
        )
    if not icon.is_file():
        raise BuildError(f"No existe el icono requerido: {icon}")

    dist_root = build_root / "bin"
    spec_root = build_root / "spec"
    dist_root.mkdir(parents=True, exist_ok=True)
    spec_root.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    env["PYTHONPATH"] = str(source_root / "src")

    main_command = pyinstaller_command(
        build_python,
        name="cancheria",
        entrypoint=source_root / "cancheria_desktop.py",
        source_root=source_root,
        dist_root=dist_root,
        work_root=build_root / "pyinstaller-cancheria",
        spec_root=spec_root,
        icon=icon,
        hidden_imports=COMMON_HIDDEN_IMPORTS,
    )
    run_command(main_command, env=env, description="[2/7] Reconstruyendo cancheria.exe limpio...")

    configurator_imports = (
        "json",
        "sqlite3",
        "_sqlite3",
        "decimal",
        "zoneinfo",
        "cancheria.paths",
        "cancheria.config.legacy_config",
    )
    configurator_command = pyinstaller_command(
        build_python,
        name="configurador_cancheria",
        entrypoint=source_root / "configurador_cancheria.py",
        source_root=source_root,
        dist_root=dist_root,
        work_root=build_root / "pyinstaller-configurador",
        spec_root=spec_root,
        icon=icon,
        hidden_imports=configurator_imports,
    )
    run_command(
        configurator_command,
        env=env,
        description="[3/7] Reconstruyendo configurador_cancheria.exe limpio...",
    )
    for executable in (dist_root / "cancheria.exe", dist_root / "configurador_cancheria.exe"):
        if not executable.is_file():
            raise BuildError(f"La compilación no produjo {executable}")
    return dist_root


def assemble_payload(source_root: Path, bin_root: Path, payload_root: Path) -> None:
    log("[4/7] Armando el contenido fresco para el cliente...")
    payload_root.mkdir(parents=True, exist_ok=True)
    for name in ROOT_FILES:
        source = source_root / name
        if source.is_file():
            shutil.copy2(source, payload_root / name)
    for name in SOURCE_DIRECTORIES:
        shutil.copytree(source_root / name, payload_root / name)
    for name in ("cancheria.exe", "configurador_cancheria.exe"):
        shutil.copy2(bin_root / name, payload_root / name)
    for name in EMPTY_DATA_DIRECTORIES:
        (payload_root / name).mkdir(parents=True, exist_ok=True)


def scan_payload(payload_root: Path) -> None:
    log("[5/7] Verificando que no haya credenciales ni datos privados...")
    forbidden_names = {
        "private_key.pem",
        ".env",
        "storage_state.json",
        "auth.json",
    }
    for path in payload_root.rglob("*"):
        relative_parts = {part.lower() for part in path.relative_to(payload_root).parts}
        if "installer" in relative_parts:
            raise BuildError(f"Se detectó la carpeta installer en el paquete: {path}")
        if not path.is_file():
            continue
        if path.name.lower() in forbidden_names:
            raise BuildError(f"Se detectó un archivo privado en el paquete: {path}")
        if path.suffix.lower() not in TEXT_EXTENSIONS and path.name != ".env.example":
            continue
        data = path.read_bytes()
        if OPENAI_KEY_PATTERN.search(data):
            raise BuildError(f"Se detectó una API key en {path}")
        if PRIVATE_KEY_PATTERN.search(data):
            raise BuildError(f"Se detectó una clave privada en {path}")
    for name in EMPTY_DATA_DIRECTORIES:
        if any((payload_root / name).rglob("*")):
            raise BuildError(f"La carpeta limpia {name} contiene datos inesperados.")


def run_self_tests(payload_root: Path) -> None:
    log("[6/7] Ejecutando verificaciones de los dos EXE...")
    env = os.environ.copy()
    env["CANCHERIA_INSTALL_ROOT"] = str(payload_root)
    for name in ("cancheria.exe", "configurador_cancheria.exe"):
        completed = subprocess.run([str(payload_root / name), "--self-test"], env=env, check=False)
        if completed.returncode != 0:
            raise BuildError(f"Falló el self-test de {name}")
    generated_build = payload_root / "build"
    if generated_build.exists():
        shutil.rmtree(generated_build)
    for cache in payload_root.rglob("__pycache__"):
        if cache.is_dir():
            shutil.rmtree(cache)
    for bytecode in (*payload_root.rglob("*.pyc"), *payload_root.rglob("*.pyo")):
        bytecode.unlink(missing_ok=True)


def write_manifest(payload_root: Path) -> None:
    lines: list[str] = []
    for path in sorted(item for item in payload_root.rglob("*") if item.is_file()):
        if path.name == "MANIFEST.sha256":
            continue
        digest = hashlib.sha256(path.read_bytes()).hexdigest().upper()
        relative = path.relative_to(payload_root).as_posix()
        lines.append(f"{digest}  {relative}")
    (payload_root / "MANIFEST.sha256").write_text("\n".join(lines) + "\n", encoding="ascii")


def create_zip(payload_root: Path, output_root: Path) -> tuple[Path, str]:
    log("[7/7] Comprimiendo el ZIP final...")
    output_root.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    final_path = output_root / f"{ZIP_PREFIX}_{timestamp}.zip"
    with tempfile.NamedTemporaryFile(
        prefix=f"{ZIP_PREFIX}_", suffix=".tmp", dir=output_root, delete=False
    ) as temp_file:
        temporary_path = Path(temp_file.name)
    try:
        with zipfile.ZipFile(
            temporary_path, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9
        ) as archive:
            for path in sorted(item for item in payload_root.rglob("*") if item.is_file()):
                archive.write(path, Path("CANCHERIA") / path.relative_to(payload_root))
        os.replace(temporary_path, final_path)
    finally:
        temporary_path.unlink(missing_ok=True)
    digest = hashlib.sha256(final_path.read_bytes()).hexdigest().upper()
    final_path.with_suffix(".zip.sha256.txt").write_text(
        f"{digest}  {final_path.name}\n", encoding="ascii"
    )
    return final_path, digest


def create_fresh_backup(root: Path) -> tuple[Path, str]:
    build_root = root / "build" / "fresh-client-zip"
    safe_remove_tree(build_root, root / "build")
    source_root = build_root / "source"
    payload_root = build_root / "payload"
    copy_fresh_source(root, source_root)
    bin_root = build_clean_executables(root, source_root, build_root)
    assemble_payload(source_root, bin_root, payload_root)
    scan_payload(payload_root)
    run_self_tests(payload_root)
    scan_payload(payload_root)
    write_manifest(payload_root)
    return create_zip(payload_root, root / OUTPUT_DIRECTORY)


def show_message(title: str, message: str, *, error: bool = False) -> None:
    if os.name != "nt":
        return
    try:
        import ctypes

        ctypes.windll.user32.MessageBoxW(None, message, title, 0x10 if error else 0x40)
    except Exception:
        pass


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Genera un ZIP fresco y sin credenciales para entregar a un cliente."
    )
    parser.add_argument("--source", help="Ruta de CANCHERIA_DESKTOP_PACKAGEPATH_FIXED")
    parser.add_argument(
        "--no-dialog", action="store_true", help="No mostrar cuadros de diálogo al terminar"
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        root = find_project_root(args.source)
        log(f"Proyecto: {root}")
        zip_path, digest = create_fresh_backup(root)
        message = (
            "BACKUP FRESCO CREADO CORRECTAMENTE\n\n"
            f"Archivo: {zip_path}\n\n"
            f"SHA-256: {digest}\n\n"
            "No contiene la carpeta installer, sesiones ni configuración privada."
        )
        log("\n" + message)
        if not args.no_dialog:
            show_message(APP_TITLE, message)
        return 0
    except Exception as exc:
        message = f"No se pudo crear el backup fresco.\n\n{exc}"
        log("\nERROR: " + message)
        traceback.print_exc()
        if not args.no_dialog:
            show_message(APP_TITLE, message, error=True)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
