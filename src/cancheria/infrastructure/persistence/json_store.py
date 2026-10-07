from __future__ import annotations
import json, os, tempfile, threading
from pathlib import Path
from typing import Any

class JSONStore:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self._lock = threading.RLock()

    def read(self, default: Any = None) -> Any:
        with self._lock:
            if not self.path.exists():
                return default
            with self.path.open("r", encoding="utf-8") as fh:
                return json.load(fh)

    def write(self, value: Any) -> None:
        with self._lock:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            fd, tmp = tempfile.mkstemp(prefix=self.path.name + ".", suffix=".tmp", dir=self.path.parent)
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as fh:
                    json.dump(value, fh, ensure_ascii=False, indent=2, default=str)
                    fh.flush(); os.fsync(fh.fileno())
                os.replace(tmp, self.path)
            finally:
                if os.path.exists(tmp): os.unlink(tmp)
