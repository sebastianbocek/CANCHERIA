from __future__ import annotations

import hashlib
import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path, PurePosixPath
from typing import Callable, Iterable


GITHUB_OWNER = "sebastianbocek"
GITHUB_REPOSITORY = "CANCHERIA"
LATEST_RELEASE_API = (
    f"https://api.github.com/repos/{GITHUB_OWNER}/{GITHUB_REPOSITORY}/releases/latest"
)
UPDATE_ASSETS = {
    "windows": "CANCHERIA-update-windows.zip",
    "linux": "CANCHERIA-update-linux.zip",
}
MAX_RELEASE_JSON_BYTES = 2 * 1024 * 1024
MAX_UPDATE_BYTES = 500 * 1024 * 1024

# Nunca se incluyen en un paquete de actualización. Son datos privados o
# generados por cada instalación y deben sobrevivir intactos a toda versión.
PROTECTED_PATHS = (
    "config.py",
    ".env",
    "src/cancheria/config/legacy_config.py",
    "src/cancheria/config/config_backups",
    "config_backups",
    "runtime",
    "wa_profile",
    "sessions",
    "Backups",
    ".venv",
    "audios",
    "comprobantes",
    "torneos",
    "agent_learning",
    "blacklist_numbers.json",
    "bot_state.pkl",
    "business_events.json",
    "calendar_events.db",
    "calendario_turnos.csv",
    "calendario_turnos.csv.reservation_id.seq",
    "client_memory.json",
    "conversation_log.jsonl",
    "conversation_states.json",
    "human_cases.json",
    "operations_metrics.jsonl",
    "proactive_state.json",
    "reservas_contactos.csv",
    "selector_adaptation_cache.json",
    "selector_health_history.json",
    "turnos_terminados.csv",
)

BACKUP_PATHS = tuple(path for path in PROTECTED_PATHS if path not in {"Backups", ".venv"})
CACHE_DIRECTORY_NAMES = {
    "cache",
    "code cache",
    "gpucache",
    "dawncache",
    "grshadercache",
    "shadercache",
    "crashpad",
}


class UpdateError(RuntimeError):
    pass


@dataclass(frozen=True)
class UpdateAsset:
    name: str
    url: str
    size: int
    sha256: str


@dataclass(frozen=True)
class ReleaseInfo:
    version: str
    title: str
    notes: str
    page_url: str
    asset: UpdateAsset


ProgressCallback = Callable[[int, int], None]


def platform_key() -> str:
    return "windows" if os.name == "nt" else "linux"


def version_tuple(value: str) -> tuple[int, ...]:
    normalized = value.strip().lower()
    if normalized.startswith("v"):
        normalized = normalized[1:]
    normalized = normalized.split("+", 1)[0].split("-", 1)[0]
    if not normalized or any(not part.isdigit() for part in normalized.split(".")):
        raise UpdateError(f"Versión inválida recibida: {value!r}")
    return tuple(int(part) for part in normalized.split("."))


def is_newer_version(candidate: str, current: str) -> bool:
    left = version_tuple(candidate)
    right = version_tuple(current)
    width = max(len(left), len(right))
    return left + (0,) * (width - len(left)) > right + (0,) * (width - len(right))


def _trusted_download_url(url: str) -> bool:
    parsed = urllib.parse.urlparse(url)
    return parsed.scheme == "https" and parsed.hostname in {
        "github.com",
        "objects.githubusercontent.com",
        "release-assets.githubusercontent.com",
    }


def _request_json(url: str, timeout: float = 20.0) -> dict:
    request = urllib.request.Request(
        url,
        headers={
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "CANCHERIA-Updater",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read(MAX_RELEASE_JSON_BYTES + 1)
    except urllib.error.HTTPError as exc:
        raise UpdateError(f"GitHub respondió con error HTTP {exc.code}.") from exc
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise UpdateError("No se pudo conectar con GitHub. Revisá la conexión a Internet.") from exc
    if len(raw) > MAX_RELEASE_JSON_BYTES:
        raise UpdateError("La respuesta de GitHub fue inesperadamente grande.")
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise UpdateError("GitHub devolvió una respuesta inválida.") from exc
    if not isinstance(payload, dict):
        raise UpdateError("GitHub devolvió un formato de versión inválido.")
    return payload


def release_from_payload(payload: dict, target_platform: str) -> ReleaseInfo:
    tag = str(payload.get("tag_name") or "").strip()
    version_tuple(tag)
    expected_name = UPDATE_ASSETS.get(target_platform)
    if not expected_name:
        raise UpdateError(f"Plataforma de actualización no soportada: {target_platform}")

    selected: dict | None = None
    for candidate in payload.get("assets") or []:
        if isinstance(candidate, dict) and candidate.get("name") == expected_name:
            selected = candidate
            break
    if selected is None:
        raise UpdateError(
            f"La versión {tag} no contiene el paquete requerido {expected_name}."
        )

    url = str(selected.get("browser_download_url") or "")
    digest = str(selected.get("digest") or "")
    if not _trusted_download_url(url):
        raise UpdateError("GitHub devolvió una URL de descarga no confiable.")
    if not digest.lower().startswith("sha256:") or len(digest.split(":", 1)[1]) != 64:
        raise UpdateError("El paquete publicado no posee un hash SHA-256 verificable.")
    try:
        size = int(selected.get("size") or 0)
    except (TypeError, ValueError) as exc:
        raise UpdateError("El tamaño del paquete publicado es inválido.") from exc
    if size <= 0 or size > MAX_UPDATE_BYTES:
        raise UpdateError("El tamaño del paquete de actualización no es seguro.")

    return ReleaseInfo(
        version=tag.removeprefix("v"),
        title=str(payload.get("name") or tag),
        notes=str(payload.get("body") or "Sin notas de versión."),
        page_url=str(payload.get("html_url") or ""),
        asset=UpdateAsset(
            name=expected_name,
            url=url,
            size=size,
            sha256=digest.split(":", 1)[1].lower(),
        ),
    )


def fetch_latest_release(target_platform: str | None = None) -> ReleaseInfo:
    return release_from_payload(_request_json(LATEST_RELEASE_API), target_platform or platform_key())


def check_for_update(current_version: str, target_platform: str | None = None) -> ReleaseInfo | None:
    payload = _request_json(LATEST_RELEASE_API)
    latest = str(payload.get("tag_name") or "").strip().removeprefix("v")
    if not is_newer_version(latest, current_version):
        return None
    return release_from_payload(payload, target_platform or platform_key())


def download_update(
    asset: UpdateAsset,
    destination: Path,
    progress: ProgressCallback | None = None,
    timeout: float = 45.0,
) -> Path:
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    request = urllib.request.Request(asset.url, headers={"User-Agent": "CANCHERIA-Updater"})
    digest = hashlib.sha256()
    downloaded = 0
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response, destination.open("wb") as output:
            if not _trusted_download_url(response.geturl()):
                raise UpdateError("La descarga fue redirigida a un servidor no confiable.")
            while True:
                chunk = response.read(1024 * 1024)
                if not chunk:
                    break
                downloaded += len(chunk)
                if downloaded > MAX_UPDATE_BYTES or downloaded > asset.size:
                    raise UpdateError("El paquete descargado excede el tamaño publicado.")
                output.write(chunk)
                digest.update(chunk)
                if progress:
                    progress(downloaded, asset.size)
    except UpdateError:
        destination.unlink(missing_ok=True)
        raise
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        destination.unlink(missing_ok=True)
        raise UpdateError("La descarga de la actualización no pudo completarse.") from exc

    if downloaded != asset.size:
        destination.unlink(missing_ok=True)
        raise UpdateError("La descarga quedó incompleta.")
    if digest.hexdigest().lower() != asset.sha256.lower():
        destination.unlink(missing_ok=True)
        raise UpdateError("El hash SHA-256 no coincide. La actualización fue cancelada.")
    return destination


def _normalized_relative_path(value: str) -> PurePosixPath:
    path = PurePosixPath(value.replace("\\", "/"))
    if path.is_absolute() or not path.parts or any(part in {"", ".", ".."} for part in path.parts):
        raise UpdateError(f"Ruta insegura dentro del paquete: {value!r}")
    if ":" in path.parts[0]:
        raise UpdateError(f"Ruta insegura dentro del paquete: {value!r}")
    return path


def is_protected_path(relative: str | PurePosixPath) -> bool:
    candidate = str(relative).replace("\\", "/").strip("/").casefold()
    for protected in PROTECTED_PATHS:
        item = protected.replace("\\", "/").strip("/").casefold()
        if candidate == item or candidate.startswith(item + "/"):
            return True
    return False


def _hash_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def validate_staged_update(staged_root: Path, expected_version: str, target_platform: str) -> dict:
    staged_root = Path(staged_root).resolve()
    manifest_path = staged_root / "update-manifest.json"
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise UpdateError("El paquete no contiene un manifiesto válido.") from exc
    if str(manifest.get("version")) != str(expected_version):
        raise UpdateError("La versión del paquete no coincide con la publicada.")
    if manifest.get("platform") != target_platform:
        raise UpdateError("El paquete descargado corresponde a otra plataforma.")
    files = manifest.get("files")
    if not isinstance(files, dict) or not files:
        raise UpdateError("El manifiesto de actualización no contiene archivos.")

    expected_files: set[str] = set()
    for raw_name, expected_hash in files.items():
        relative = _normalized_relative_path(str(raw_name))
        normalized = relative.as_posix()
        if is_protected_path(relative):
            raise UpdateError(f"El paquete intentó incluir un archivo privado: {normalized}")
        target = staged_root.joinpath(*relative.parts)
        if not target.is_file() or target.is_symlink():
            raise UpdateError(f"Falta un archivo declarado en la actualización: {normalized}")
        if _hash_file(target).lower() != str(expected_hash).lower():
            raise UpdateError(f"Falló la verificación interna de {normalized}.")
        expected_files.add(normalized)

    actual_files = {
        path.relative_to(staged_root).as_posix()
        for path in staged_root.rglob("*")
        if path.is_file() and path.name != "update-manifest.json"
    }
    if actual_files != expected_files:
        raise UpdateError("El paquete contiene archivos no declarados en su manifiesto.")
    return manifest


def extract_and_validate_update(
    archive_path: Path,
    destination: Path,
    expected_version: str,
    target_platform: str,
) -> Path:
    destination = Path(destination)
    destination.mkdir(parents=True, exist_ok=True)
    try:
        with zipfile.ZipFile(archive_path) as archive:
            for info in archive.infolist():
                relative = _normalized_relative_path(info.filename)
                mode = (info.external_attr >> 16) & 0o170000
                if mode == stat.S_IFLNK:
                    raise UpdateError("El paquete contiene un enlace simbólico no permitido.")
                if is_protected_path(relative):
                    raise UpdateError(
                        f"El paquete intentó reemplazar datos privados: {relative.as_posix()}"
                    )
                target = destination.joinpath(*relative.parts)
                target.resolve().relative_to(destination.resolve())
            archive.extractall(destination)
    except (zipfile.BadZipFile, OSError, ValueError) as exc:
        raise UpdateError("No se pudo extraer de forma segura la actualización.") from exc
    validate_staged_update(destination, expected_version, target_platform)
    return destination


def _iter_backup_files(root: Path) -> Iterable[Path]:
    for relative in BACKUP_PATHS:
        source = root / Path(relative)
        if source.is_file():
            yield source
        elif source.is_dir():
            for path in source.rglob("*"):
                if not path.is_file():
                    continue
                relative_parts = {part.casefold() for part in path.relative_to(source).parts}
                if relative_parts & CACHE_DIRECTORY_NAMES:
                    continue
                yield path


def create_data_backup(install_dir: Path) -> Path:
    install_dir = Path(install_dir).resolve()
    backup_dir = install_dir / "Backups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = backup_dir / f"CANCHERIA_BACKUP_ANTES_ACTUALIZAR_{stamp}.zip"
    try:
        with zipfile.ZipFile(backup_path, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
            archive.writestr(
                "LEEME_RESPALDO.txt",
                "CANCHERIA - Respaldo automático antes de actualizar\n"
                f"Fecha: {datetime.now():%Y-%m-%d %H:%M:%S}\n"
                f"Instalación original: {install_dir}\n\n"
                "Contiene configuración y datos privados. No debe compartirse públicamente.\n",
            )
            seen: set[Path] = set()
            for source in _iter_backup_files(install_dir):
                resolved = source.resolve()
                if resolved in seen:
                    continue
                seen.add(resolved)
                archive.write(source, source.relative_to(install_dir).as_posix())
    except OSError as exc:
        backup_path.unlink(missing_ok=True)
        raise UpdateError("No se pudo crear el respaldo. La actualización fue cancelada.") from exc
    return backup_path


def prepare_update(
    release: ReleaseInfo,
    install_dir: Path,
    progress: ProgressCallback | None = None,
    target_platform: str | None = None,
) -> tuple[Path, Path, Path]:
    selected_platform = target_platform or platform_key()
    work_dir = Path(tempfile.mkdtemp(prefix="cancheria-update-"))
    try:
        archive = download_update(release.asset, work_dir / release.asset.name, progress)
        staged = extract_and_validate_update(
            archive,
            work_dir / "staged",
            release.version,
            selected_platform,
        )
        backup = create_data_backup(install_dir)
        return work_dir, staged, backup
    except Exception:
        shutil.rmtree(work_dir, ignore_errors=True)
        raise


def launch_update_helper(
    install_dir: Path,
    work_dir: Path,
    staged_dir: Path,
    version: str,
    backup_zip: Path,
) -> subprocess.Popen:
    install_dir = Path(install_dir).resolve()
    work_dir = Path(work_dir).resolve()
    staged_dir = Path(staged_dir).resolve()
    if os.name == "nt":
        installed_helper = install_dir / "CancheriaUpdater.exe"
        if not installed_helper.is_file():
            raise UpdateError("No se encontró CancheriaUpdater.exe. Reinstalá esta versión una sola vez.")
        temporary_helper = work_dir / "CancheriaUpdater.exe"
        shutil.copy2(installed_helper, temporary_helper)
        command = [str(temporary_helper)]
        restart_command = [str(install_dir / "cancheria.exe"), "--update-finished", version]
        kwargs: dict = {
            "cwd": str(work_dir),
            "creationflags": subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS,
            "close_fds": True,
        }
    else:
        helper_script = install_dir / "cancheria_updater.py"
        if not helper_script.is_file():
            raise UpdateError("No se encontró el auxiliar de actualización.")
        command = [sys.executable, str(helper_script)]
        restart_command = [
            sys.executable,
            str(install_dir / "cancheria_desktop.py"),
            "--update-finished",
            version,
        ]
        kwargs = {"cwd": str(work_dir), "start_new_session": True, "close_fds": True}

    command.extend(
        [
            "--apply",
            "--parent-pid",
            str(os.getpid()),
            "--install-dir",
            str(install_dir),
            "--staged-dir",
            str(staged_dir),
            "--version",
            version,
            "--platform",
            platform_key(),
            "--backup-zip",
            str(backup_zip),
            "--restart-command-json",
            json.dumps(restart_command, ensure_ascii=False),
        ]
    )
    try:
        return subprocess.Popen(command, **kwargs)
    except OSError as exc:
        raise UpdateError("No se pudo iniciar el auxiliar de actualización.") from exc


def create_update_archive(
    payload_root: Path,
    output_path: Path,
    version: str,
    target_platform: str,
) -> tuple[Path, str]:
    payload_root = Path(payload_root).resolve()
    output_path = Path(output_path).resolve()
    if target_platform not in UPDATE_ASSETS:
        raise UpdateError(f"Plataforma no soportada: {target_platform}")
    files: dict[str, str] = {}
    for source in sorted(payload_root.rglob("*"), key=lambda item: item.as_posix().casefold()):
        if not source.is_file() or source.is_symlink():
            continue
        relative = source.relative_to(payload_root).as_posix()
        if is_protected_path(relative) or "__pycache__" in source.parts or source.suffix in {".pyc", ".pyo"}:
            continue
        files[relative] = _hash_file(source)
    if not files:
        raise UpdateError("No hay archivos para crear el paquete de actualización.")
    manifest = {
        "schema": 1,
        "version": version,
        "platform": target_platform,
        "files": files,
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = output_path.with_suffix(output_path.suffix + ".tmp")
    try:
        with zipfile.ZipFile(temporary, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
            archive.writestr(
                "update-manifest.json",
                json.dumps(manifest, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
            )
            for relative in files:
                archive.write(payload_root / Path(relative), relative)
        os.replace(temporary, output_path)
    finally:
        temporary.unlink(missing_ok=True)
    return output_path, _hash_file(output_path)
