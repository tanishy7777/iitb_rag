from __future__ import annotations

import json
import os
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from .config import DEFAULT_WEB_DIR
from .service import DigitalBrainService


class BrainHandler(SimpleHTTPRequestHandler):
    service: DigitalBrainService

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)

        if parsed.path == "/api/machines":
            self._json_response(200, {"machines": self.service.list_machines()})
            return

        if parsed.path == "/api/machines/recent":
            query = parse_qs(parsed.query)
            raw_limit = str((query.get("limit") or ["8"])[0]).strip()
            try:
                limit = max(1, min(20, int(raw_limit)))
            except ValueError:
                self._json_response(400, {"error": "limit must be an integer"})
                return
            self._json_response(200, {"recent_machines": self.service.list_recent_machines(limit=limit)})
            return

        if parsed.path == "/api/admin/analytics":
            self._json_response(200, self.service.admin_analytics())
            return

        if parsed.path == "/api/troubleshoot/session":
            query = parse_qs(parsed.query)
            session_id = str((query.get("session_id") or [""])[0]).strip()
            if not session_id:
                self._json_response(400, {"error": "session_id is required"})
                return
            try:
                payload = self.service.get_troubleshoot_session(session_id)
            except ValueError as exc:
                self._json_response(404, {"error": str(exc)})
                return
            self._json_response(200, payload)
            return

        if parsed.path == "/":
            self.path = "/operator.html"

        super().do_GET()

    def do_POST(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        content_len = int(self.headers.get("Content-Length", "0"))
        body = self.rfile.read(content_len) if content_len else b"{}"

        try:
            payload = json.loads(body.decode("utf-8"))
        except json.JSONDecodeError:
            self._json_response(400, {"error": "Invalid JSON payload"})
            return

        if parsed.path == "/api/query":
            self._handle_query(payload)
            return

        if parsed.path == "/api/troubleshoot/start":
            self._handle_troubleshoot_start(payload)
            return

        if parsed.path == "/api/troubleshoot/next":
            self._handle_troubleshoot_next(payload)
            return

        if parsed.path == "/api/realtime/document":
            self._handle_realtime_document(payload)
            return

        if parsed.path == "/api/realtime/complaint":
            self._handle_realtime_complaint(payload)
            return

        if parsed.path == "/api/realtime/trouble-event":
            self._handle_realtime_trouble_event(payload)
            return

        if parsed.path == "/api/feedback":
            self._handle_feedback(payload)
            return

        self._json_response(404, {"error": "Not found"})

    def _handle_query(self, payload: dict) -> None:
        machine_id = payload.get("machine_id")
        question = str(payload.get("question") or "").strip()

        if machine_id is None:
            self._json_response(400, {"error": "machine_id is required"})
            return
        if not question:
            self._json_response(400, {"error": "question is required"})
            return

        try:
            response = self.service.query(int(machine_id), question)
        except ValueError:
            self._json_response(400, {"error": "machine_id must be an integer"})
            return

        self._json_response(
            200,
            {
                "session_id": response.session_id,
                "machine_id": response.machine_id,
                "answer": response.answer,
                "answer_mode": response.answer_mode,
                "triage": response.triage,
                "confidence_score": response.confidence_score,
                "confidence_label": response.confidence_label,
                "checklist": response.checklist,
                "citations": response.citations,
                "historical_suggestions": response.historical_suggestions,
                "troubleshooting_flow": response.troubleshooting_flow,
            },
        )

    def _handle_feedback(self, payload: dict) -> None:
        required = ["session_id", "machine_id", "issue", "helpful"]
        for field in required:
            if field not in payload:
                self._json_response(400, {"error": f"{field} is required"})
                return

        workaround = str(payload.get("workaround") or "")
        helpful = bool(payload.get("helpful"))

        self.service.submit_feedback(
            session_id=str(payload["session_id"]),
            machine_id=int(payload["machine_id"]),
            issue=str(payload["issue"]),
            helpful=helpful,
            workaround=workaround,
        )
        self._json_response(200, {"ok": True})

    def _handle_troubleshoot_start(self, payload: dict) -> None:
        machine_id = payload.get("machine_id")
        question = str(payload.get("question") or "").strip()
        if machine_id is None:
            self._json_response(400, {"error": "machine_id is required"})
            return
        if not question:
            self._json_response(400, {"error": "question is required"})
            return

        try:
            response = self.service.start_troubleshoot(int(machine_id), question)
        except ValueError as exc:
            self._json_response(400, {"error": str(exc)})
            return
        self._json_response(200, response)

    def _handle_troubleshoot_next(self, payload: dict) -> None:
        session_id = str(payload.get("session_id") or "").strip()
        response_value = str(payload.get("response") or "").strip()
        if not session_id:
            self._json_response(400, {"error": "session_id is required"})
            return
        if not response_value:
            self._json_response(400, {"error": "response is required"})
            return

        try:
            response = self.service.next_troubleshoot(session_id, response_value)
        except ValueError as exc:
            msg = str(exc)
            status = 404 if "not found" in msg.lower() else 400
            self._json_response(status, {"error": msg})
            return

        self._json_response(200, response)

    def _handle_realtime_document(self, payload: dict) -> None:
        path = str(payload.get("path") or "").strip()
        if not path:
            self._json_response(400, {"error": "path is required"})
            return
        machine_id = payload.get("machine_id")
        doc_type = payload.get("doc_type")
        try:
            response = self.service.realtime_add_document(
                path=path,
                machine_id=(int(machine_id) if machine_id is not None else None),
                doc_type=(str(doc_type) if doc_type is not None else None),
            )
        except ValueError as exc:
            self._json_response(400, {"error": str(exc)})
            return
        self._json_response(200, response)

    def _handle_realtime_complaint(self, payload: dict) -> None:
        if payload.get("machine_id") is None:
            self._json_response(400, {"error": "machine_id is required"})
            return
        if payload.get("complaint_description") is None:
            self._json_response(400, {"error": "complaint_description is required"})
            return
        try:
            response = self.service.realtime_upsert_complaint(payload)
        except ValueError as exc:
            self._json_response(400, {"error": str(exc)})
            return
        self._json_response(200, response)

    def _handle_realtime_trouble_event(self, payload: dict) -> None:
        try:
            response = self.service.realtime_add_trouble_event(payload)
        except ValueError as exc:
            self._json_response(400, {"error": str(exc)})
            return
        self._json_response(200, response)

    def _json_response(self, code: int, payload: dict) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: object) -> None:
        # keep server output concise
        return


def run_server(service: DigitalBrainService, host: str = "127.0.0.1", port: int = 8080) -> None:
    os.chdir(DEFAULT_WEB_DIR)

    class Handler(BrainHandler):
        pass

    Handler.service = service

    server = ThreadingHTTPServer((host, port), Handler)
    print(f"Digital Brain server running on http://{host}:{port}")
    server.serve_forever()


def ensure_web_assets() -> Path:
    DEFAULT_WEB_DIR.mkdir(parents=True, exist_ok=True)
    return DEFAULT_WEB_DIR
