from pathlib import Path
import re

def test_public_sources_do_not_contain_obvious_real_secrets():
    root=Path(__file__).resolve().parents[2]
    paths=[root/"src", root/"legacy", root/"config.py", root/"WPSetter.py"]
    chunks=[]
    for base in paths:
        files=[base] if base.is_file() else list(base.rglob("*.py"))
        chunks.extend(f.read_text(encoding="utf-8", errors="ignore") for f in files)
    text="\n".join(chunks)
    assert not re.search(r"sk-[A-Za-z0-9_-]{16,}", text)
    assert not re.search(r"[A-Za-z0-9._%+-]+@gmail\.com", text, re.I)
