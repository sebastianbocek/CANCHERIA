#!/usr/bin/env python3
from pathlib import Path
import re, sys
ROOT=Path(__file__).resolve().parents[1]
SKIP={".git",".venv","venv","runtime","__pycache__"}
patterns={
 "openai_key": re.compile(r"sk-[A-Za-z0-9_-]{16,}"),
 "email": re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"),
 "arg_phone": re.compile(r"\+54\d{10,13}"),
}
# Datos de contacto que el autor autorizó expresamente a publicar.
PUBLIC_CONTACTS = {
    ("email", Path("README.md"), "sebastianbocek.marketing" + "@gmail.com"),
}
findings=[]
for p in ROOT.rglob("*"):
    if not p.is_file() or any(part in SKIP for part in p.parts): continue
    if p.suffix.lower() not in {".py",".md",".toml",".yml",".yaml",".json",".txt",".env",".example"}: continue
    text=p.read_text(encoding="utf-8",errors="ignore")
    for kind,pat in patterns.items():
        matches=list(pat.finditer(text))
        relative_path=p.relative_to(ROOT)
        matches=[
            match for match in matches
            if (kind,relative_path,match.group(0)) not in PUBLIC_CONTACTS
        ]
        if kind == "arg_phone":
            matches=[m for m in matches if not m.group(0).startswith("+5491100")]
        if matches: findings.append((kind,relative_path))
if findings:
    for kind,p in findings: print(f"{kind}: {p}")
    raise SystemExit(1)
print("No obvious hard-coded secrets/PII patterns found.")
