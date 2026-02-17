from __future__ import annotations

import os
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DATA_DIR = PROJECT_ROOT / "data"
DEFAULT_STATE_DIR = PROJECT_ROOT / ".state"
DEFAULT_DB_PATH = DEFAULT_STATE_DIR / "digital_brain.db"
DEFAULT_WEB_DIR = PROJECT_ROOT / "web"
DEFAULT_FRONTEND_DIR = PROJECT_ROOT / "frontend"
DEFAULT_FRONTEND_DIST_DIR = DEFAULT_FRONTEND_DIR / "dist"


def env_flag(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


AUTH_ENABLED = env_flag("DIGITAL_BRAIN_AUTH_ENABLED", default=False)
AUTH_SESSION_HOURS = int(os.getenv("DIGITAL_BRAIN_AUTH_SESSION_HOURS", "12"))
AUTH_COOKIE_NAME = os.getenv("DIGITAL_BRAIN_AUTH_COOKIE_NAME", "digital_brain_session")
AUTH_COOKIE_SECURE = env_flag("DIGITAL_BRAIN_AUTH_COOKIE_SECURE", default=False)
BOOTSTRAP_ADMIN_USER = os.getenv("DIGITAL_BRAIN_BOOTSTRAP_ADMIN_USER", "admin")
BOOTSTRAP_ADMIN_PASSWORD = os.getenv("DIGITAL_BRAIN_BOOTSTRAP_ADMIN_PASSWORD", "admin123")
