from __future__ import annotations

import argparse
import hashlib
import io
import os
import shutil
import sys
import tarfile
import tempfile
from pathlib import Path

SCRIPT_ROOT = Path(__file__).resolve().parents[1]
if str(SCRIPT_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(SCRIPT_ROOT / "src"))

from create_fresh_client_zip import (
    EMPTY_DATA_DIRECTORIES,
    ROOT_FILES,
    SOURCE_DIRECTORIES,
    copy_fresh_source,
    find_project_root,
    safe_remove_tree,
    scan_payload,
    write_manifest,
)
from cancheria.desktop.update_service import UPDATE_ASSETS, create_update_archive


OUTPUT_NAME = "InstaladorCancheriaLinux.run"
MARKER = b"__CANCHERIA_PAYLOAD_BELOW__\n"


def assemble_linux_payload(source_root: Path, payload_root: Path) -> None:
    payload_root.mkdir(parents=True, exist_ok=True)
    for name in ROOT_FILES:
        source = source_root / name
        if source.is_file():
            shutil.copy2(source, payload_root / name)
    for name in SOURCE_DIRECTORIES:
        shutil.copytree(source_root / name, payload_root / name)
    for name in EMPTY_DATA_DIRECTORIES:
        (payload_root / name).mkdir(parents=True, exist_ok=True)


def compressed_payload(payload_root: Path) -> bytes:
    output = io.BytesIO()
    with tarfile.open(fileobj=output, mode="w:gz", compresslevel=9) as archive:
        for path in sorted(payload_root.iterdir(), key=lambda item: item.name.lower()):
            archive.add(path, arcname=path.name, recursive=True)
    return output.getvalue()


def build_installer(root: Path) -> tuple[Path, str]:
    build_root = root / "build" / "linux-installer"
    safe_remove_tree(build_root, root / "build")
    source_root = build_root / "source"
    payload_root = build_root / "payload"

    print("[1/4] Preparando el paquete limpio para Debian...", flush=True)
    copy_fresh_source(root, source_root)
    assemble_linux_payload(source_root, payload_root)
    scan_payload(payload_root)
    write_manifest(payload_root)

    print("[2/4] Comprimiendo el contenido interno...", flush=True)
    payload = compressed_payload(payload_root)
    bootstrap_path = root / "installer" / "cancheria-linux-installer.sh"
    bootstrap = bootstrap_path.read_text(encoding="utf-8").replace("\r\n", "\n").encode("utf-8")
    if bootstrap.count(MARKER) != 1 or not bootstrap.endswith(MARKER):
        raise RuntimeError("El instalador Linux debe terminar con un único marcador de payload.")

    print("[3/4] Generando el instalador de un solo archivo...", flush=True)
    release_dir = root / "release"
    release_dir.mkdir(parents=True, exist_ok=True)
    final_path = release_dir / OUTPUT_NAME
    with tempfile.NamedTemporaryFile(
        prefix="InstaladorCancheriaLinux_",
        suffix=".tmp",
        dir=release_dir,
        delete=False,
    ) as temporary_file:
        temporary_path = Path(temporary_file.name)
        temporary_file.write(bootstrap)
        temporary_file.write(payload)
    try:
        os.replace(temporary_path, final_path)
    finally:
        temporary_path.unlink(missing_ok=True)

    digest = hashlib.sha256(final_path.read_bytes()).hexdigest().upper()
    final_path.with_suffix(".run.sha256.txt").write_text(
        f"{digest}  {final_path.name}\n", encoding="ascii"
    )
    update_path = release_dir / UPDATE_ASSETS["linux"]
    _, update_digest = create_update_archive(payload_root, update_path, "0.2.16", "linux")
    print(f"Paquete de actualización: {update_path}")
    print(f"SHA-256 actualización: {update_digest.upper()}")
    print("[4/4] Instalador Linux creado correctamente.", flush=True)
    return final_path, digest


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Crea el instalador fresco de CANCHERIA para Debian con escritorio."
    )
    parser.add_argument("--source", help="Ruta raíz de CANCHERIA")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    root = find_project_root(args.source)
    final_path, digest = build_installer(root)
    print(f"Archivo: {final_path}")
    print(f"SHA-256: {digest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
