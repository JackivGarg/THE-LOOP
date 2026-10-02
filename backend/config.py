"""Application configuration; secrets stay exclusively on the server."""
import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    database_path: Path
    origins: tuple[str, ...]
    secure_cookies: bool = False
    enable_demo: bool = True
    start_worker: bool = True

    @classmethod
    def from_env(cls):
        return cls(
            database_path=Path(os.getenv("LOOP_DATABASE_PATH", "data/loop.sqlite3")),
            origins=tuple(item.strip() for item in os.getenv("LOOP_ORIGINS", "http://127.0.0.1:5173,http://localhost:5173,http://127.0.0.1:8000,http://localhost:8000").split(",") if item.strip()),
            secure_cookies=os.getenv("LOOP_SECURE_COOKIES", "false").lower() == "true",
            enable_demo=os.getenv("LOOP_ENABLE_DEMO", "true").lower() == "true",
        )
