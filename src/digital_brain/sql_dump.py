from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

INSERT_RE = re.compile(r"^INSERT INTO\s+`(?P<table>[^`]+)`\s*\((?P<cols>[^)]+)\)\s+VALUES", re.IGNORECASE)


@dataclass
class InsertBlock:
    table: str
    columns: list[str]
    rows: list[list[Any]]


def parse_sql_dump(path: Path) -> list[InsertBlock]:
    """Parse MySQL dump INSERT blocks.

    The parser is intentionally limited to the file style used in the provided
    dumps: one INSERT header followed by row tuples that may span many lines.
    """
    blocks: list[InsertBlock] = []
    current: InsertBlock | None = None

    for raw_line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = raw_line.strip()
        if not line:
            continue

        match = INSERT_RE.match(line)
        if match:
            cols = [c.strip().strip("`") for c in match.group("cols").split(",")]
            current = InsertBlock(table=match.group("table"), columns=cols, rows=[])
            blocks.append(current)
            continue

        if current is None:
            continue

        if not line.startswith("("):
            continue

        tuple_line = _strip_tuple_suffix(line)
        current.rows.append(_parse_tuple(tuple_line))

        if line.endswith(";"):
            current = None

    return blocks


def rows_for_table(path: Path, table_name: str) -> tuple[list[str], list[list[Any]]]:
    columns: list[str] = []
    rows: list[list[Any]] = []
    for block in parse_sql_dump(path):
        if block.table != table_name:
            continue
        columns = block.columns
        rows.extend(block.rows)
    return columns, rows


def _strip_tuple_suffix(line: str) -> str:
    stripped = line.strip()
    if stripped.endswith(","):
        stripped = stripped[:-1]
    if stripped.endswith(";"):
        stripped = stripped[:-1]
    return stripped


def _parse_tuple(tuple_text: str) -> list[Any]:
    if not tuple_text.startswith("(") or not tuple_text.endswith(")"):
        raise ValueError(f"Invalid tuple format: {tuple_text[:120]}")

    payload = tuple_text[1:-1]
    parts: list[str] = []
    buf: list[str] = []
    in_quote = False
    escaped = False

    for ch in payload:
        if ch == "'" and not escaped:
            in_quote = not in_quote
            buf.append(ch)
            continue

        if ch == "\\" and in_quote and not escaped:
            escaped = True
            buf.append(ch)
            continue

        if ch == "," and not in_quote:
            parts.append("".join(buf).strip())
            buf = []
            escaped = False
            continue

        buf.append(ch)
        escaped = False

    if buf:
        parts.append("".join(buf).strip())

    return [_decode_value(part) for part in parts]


def _decode_value(raw: str) -> Any:
    token = raw.strip()
    upper = token.upper()
    if upper == "NULL":
        return None

    if token.startswith("'") and token.endswith("'"):
        inner = token[1:-1]
        inner = inner.replace("\\r\\n", "\n")
        inner = inner.replace("\\n", "\n")
        inner = inner.replace("\\r", "\r")
        inner = inner.replace("\\t", "\t")
        inner = inner.replace("\\'", "'")
        inner = inner.replace('\\"', '"')
        inner = inner.replace("\\\\", "\\")
        return inner

    if token == "":
        return ""

    try:
        if "." in token:
            return float(token)
        return int(token)
    except ValueError:
        return token
