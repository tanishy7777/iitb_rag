from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

DOC_NAME_RE = re.compile(r"^(?P<machine_id>\d+)_(?P<kind>[A-Za-z]+)\.pdf$", re.IGNORECASE)


@dataclass
class PdfDocument:
    machine_id: int | None
    doc_type: str
    path: str
    text: str


def load_pdf_documents(data_dir: Path) -> list[PdfDocument]:
    docs: list[PdfDocument] = []
    for path in sorted(data_dir.glob("*.pdf")):
        machine_id, doc_type = _infer_identity(path.name)
        text = extract_text(path)
        docs.append(
            PdfDocument(
                machine_id=machine_id,
                doc_type=doc_type,
                path=str(path),
                text=text,
            )
        )
    return docs


def load_pdf_document(path: Path, machine_id: int | None = None, doc_type: str | None = None) -> PdfDocument:
    inferred_machine_id, inferred_doc_type = _infer_identity(path.name)
    return PdfDocument(
        machine_id=machine_id if machine_id is not None else inferred_machine_id,
        doc_type=(doc_type or inferred_doc_type),
        path=str(path),
        text=extract_text(path),
    )


def extract_text(path: Path) -> str:
    cmd = ["pdftotext", "-layout", str(path), "-"]
    try:
        proc = subprocess.run(cmd, check=True, text=True, capture_output=True)
        return proc.stdout.strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return ""


def _infer_identity(filename: str) -> tuple[int | None, str]:
    match = DOC_NAME_RE.match(filename)
    if not match:
        return None, "manual"

    machine_id = int(match.group("machine_id"))
    raw = match.group("kind").lower()

    if "sop" in raw:
        return machine_id, "sop"
    if "policy" in raw:
        return machine_id, "policy"
    if "recep" in raw or "recipe" in raw:
        return machine_id, "recipe"
    if "manual" in raw:
        return machine_id, "manual"

    return machine_id, raw
