from __future__ import annotations

from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DATA_DIR = PROJECT_ROOT / "data"
DEFAULT_STATE_DIR = PROJECT_ROOT / ".state"
DEFAULT_DB_PATH = DEFAULT_STATE_DIR / "digital_brain.db"
DEFAULT_WEB_DIR = PROJECT_ROOT / "web"
