from __future__ import annotations
import csv
from pathlib import Path
from typing import Iterable, Mapping

class CSVStore:
    def __init__(self, path: str | Path, fieldnames: Iterable[str]):
        self.path = Path(path)
        self.fieldnames = list(fieldnames)

    def read_all(self) -> list[dict[str, str]]:
        if not self.path.exists(): return []
        with self.path.open("r", encoding="utf-8-sig", newline="") as fh:
            return list(csv.DictReader(fh))

    def write_all(self, rows: Iterable[Mapping[str, object]]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("w", encoding="utf-8-sig", newline="") as fh:
            writer=csv.DictWriter(fh, fieldnames=self.fieldnames, extrasaction="ignore")
            writer.writeheader(); writer.writerows(rows)
