from __future__ import annotations

import shutil
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "release" / "CANCHERIA"
TARGET.mkdir(parents=True, exist_ok=True)

# New builds emit both executables directly in the project root.  Keep a
# dist/ fallback only so an older build can still be assembled.
for exe_name in ("cancheria.exe", "configurador_cancheria.exe"):
    candidates = [ROOT / exe_name, ROOT / "dist" / exe_name]
    for built_exe in candidates:
        if built_exe.exists():
            shutil.copy2(built_exe, TARGET / exe_name)
            break

FILES = [
    "WPSetter.py",
    "calendario.py",
    "config.py",
    "configurador_cancheria.py",
    "event_registration_engine.py",
    ".env.example",
    "README.md",
    "SECURITY.md",
    "CONTRIBUTING.md",
    "CHANGELOG.md",
]
DIRS = ["src", "legacy", "assets", "docs", "examples"]

for name in FILES:
    src = ROOT / name
    if src.exists():
        shutil.copy2(src, TARGET / name)

for name in DIRS:
    src = ROOT / name
    dst = TARGET / name
    if dst.exists():
        shutil.rmtree(dst)
    if src.exists():
        shutil.copytree(src, dst, ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "*.pyo"))

(TARGET / "runtime").mkdir(exist_ok=True)
(TARGET / "wa_profile").mkdir(exist_ok=True)
(TARGET / "sessions").mkdir(exist_ok=True)

zip_path = ROOT / "release" / "CANCHERIA_WINDOWS.zip"
if zip_path.exists():
    zip_path.unlink()
with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
    for path in TARGET.rglob("*"):
        if path.is_file():
            zf.write(path, Path("CANCHERIA") / path.relative_to(TARGET))
print(zip_path)
