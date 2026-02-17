#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

PYTHONPATH=src python3 -m digital_brain ingest --data-dir data
PYTHONPATH=src python3 -m digital_brain serve --host 127.0.0.1 --port 8080
