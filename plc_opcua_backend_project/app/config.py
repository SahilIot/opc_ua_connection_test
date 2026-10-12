import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

def env_path(name: str, *, required: bool = True) -> Path | None:
    raw = os.getenv(name, "").strip()
    if not raw:
        if required:
            raise RuntimeError(f"Missing required environment setting: {name}")
        return None
    path = Path(raw)
    if not path.is_absolute():
        path = BASE_DIR / path
    if not path.is_file():
        raise FileNotFoundError(f"{name} points to a file that does not exist: {path}")
    return path


def required_env(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise RuntimeError(f"Missing required environment setting: {name}")
    return value
