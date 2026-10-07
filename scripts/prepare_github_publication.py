from __future__ import annotations

import argparse
import re
import shutil
from pathlib import Path

from create_fresh_client_zip import copy_fresh_source, find_project_root, safe_remove_tree


PUBLIC_DIRECTORIES = (".github", "scripts", "installer", "tests")
PUBLIC_ROOT_FILES = (
    ".gitattributes",
    ".gitignore",
    "build_backup_creator.bat",
    "build_installer.bat",
    "build_linux_installer.bat",
    "build_windows.bat",
    "BUILD_FIX_20261006.md",
    "BUILD_FIX_20261007.md",
    "OPEN_SOURCE_MIGRATION_REPORT.md",
    "REFACTOR_PLAN.md",
)
IGNORED_NAMES = {
    ".build-venv",
    ".git",
    ".pytest_cache",
    "__pycache__",
    "build",
    "dist",
    "release",
}
OPENAI_KEY_PATTERN = re.compile(rb"sk-[A-Za-z0-9_-]{16,}")
PRIVATE_KEY_PATTERN = re.compile(rb"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----")


def ignore_public_copy(_directory: str, names: list[str]) -> set[str]:
    ignored = {name for name in names if name in IGNORED_NAMES}
    ignored.update(name for name in names if name.endswith((".pyc", ".pyo")))
    return ignored


def scan_public_tree(public_root: Path) -> None:
    forbidden_names = {
        ".env",
        "auth.json",
        "storage_state.json",
        "private_key.pem",
    }
    forbidden_suffixes = {".exe", ".run", ".zip", ".db", ".sqlite", ".sqlite3", ".pkl"}

    for path in public_root.rglob("*"):
        relative = path.relative_to(public_root)
        if any(part in IGNORED_NAMES for part in relative.parts):
            raise RuntimeError(f"Directorio privado o de build incluido: {relative}")
        if not path.is_file():
            continue
        if path.name.lower() in forbidden_names:
            raise RuntimeError(f"Archivo privado incluido: {relative}")
        if path.suffix.lower() in forbidden_suffixes:
            raise RuntimeError(f"Binario o dato operativo incluido en Git: {relative}")
        data = path.read_bytes()
        if OPENAI_KEY_PATTERN.search(data):
            raise RuntimeError(f"Posible OpenAI API key encontrada en: {relative}")
        if PRIVATE_KEY_PATTERN.search(data):
            raise RuntimeError(f"Clave privada encontrada en: {relative}")

    config = public_root / "src" / "cancheria" / "config" / "legacy_config.py"
    config_text = config.read_text(encoding="utf-8")
    if "OPENAI_API_KEY = ''" not in config_text:
        raise RuntimeError("La configuración pública no tiene la API key vacía.")

    for private_dir in ("wa_profile", "sessions"):
        directory = public_root / private_dir
        if directory.exists() and any(directory.rglob("*")):
            raise RuntimeError(f"La carpeta privada {private_dir} contiene archivos.")


def prepare_publication(root: Path) -> Path:
    build_root = root / "build" / "github-publication"
    safe_remove_tree(build_root, root / "build")
    public_root = build_root / "CANCHERIA"

    print("[1/4] Copiando el núcleo con configuración limpia...", flush=True)
    copy_fresh_source(root, public_root)

    print("[2/4] Agregando tests, scripts e instaladores reproducibles...", flush=True)
    for directory_name in PUBLIC_DIRECTORIES:
        source = root / directory_name
        shutil.copytree(
            source,
            public_root / directory_name,
            dirs_exist_ok=True,
            ignore=ignore_public_copy,
        )
    for file_name in PUBLIC_ROOT_FILES:
        source = root / file_name
        if source.is_file():
            shutil.copy2(source, public_root / file_name)

    # The clean template is required by both installer builders.
    clean_config = public_root / "src" / "cancheria" / "config" / "legacy_config.py"
    template = (
        public_root
        / "src"
        / "cancheria"
        / "config"
        / "config_backups"
        / "config_20261006_213845.py"
    )
    template.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(clean_config, template)

    runtime = public_root / "runtime"
    runtime.mkdir(parents=True, exist_ok=True)
    (runtime / ".gitkeep").write_text("", encoding="utf-8")

    print("[3/4] Escaneando credenciales, sesiones y datos privados...", flush=True)
    scan_public_tree(public_root)

    print("[4/4] Publicación limpia preparada.", flush=True)
    return public_root


def main() -> int:
    parser = argparse.ArgumentParser(description="Prepara el árbol público limpio de CANCHERIA.")
    parser.add_argument("--source", help="Raíz del proyecto")
    args = parser.parse_args()
    root = find_project_root(args.source)
    public_root = prepare_publication(root)
    print(f"Carpeta pública: {public_root}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
