from __future__ import annotations
import sqlite3
from contextlib import contextmanager
from pathlib import Path

class SQLiteStore:
    def __init__(self, path: str | Path):
        self.path=Path(path)

    @contextmanager
    def connect(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        connection=sqlite3.connect(self.path)
        try:
            yield connection
            connection.commit()
        finally:
            connection.close()
