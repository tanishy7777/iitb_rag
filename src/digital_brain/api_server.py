from __future__ import annotations

import json
import os
import re
from http.cookies import SimpleCookie
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from .config import (
    AUTH_COOKIE_NAME,
    AUTH_COOKIE_SECURE,
    DEFAULT_FRONTEND_DIST_DIR,
    DEFAULT_WEB_DIR,
)
from .service import DigitalBrainService


DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


class BrainHandler(SimpleHTTPRequestHandler):
    service: DigitalBrainService
    ui_mode = "legacy"

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)

        if parsed.path == "/api/auth/me":
            self._handle_auth_me()
            return

        if parsed.path == "/api/machines":
            if self._require_roles({"operator", "admin"}) is None:
                return
            self._json_response(200, {"machines": self.service.list_machines()})
            return

        if parsed.path == "/api/machines/recent":
            if self._require_roles({"operator", "admin"}) is None:
                return
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
            if self._require_roles({"admin"}) is None:
                return
            query = parse_qs(parsed.query)

            raw_machine_id = str((query.get("machine_id") or [""])[0]).strip()
            machine_id: int | None = None
            if raw_machine_id:
                try:
                    machine_id = int(raw_machine_id)
                except ValueError:
                    self._json_response(400, {"error": "machine_id must be an integer"})
                    return
                if machine_id <= 0:
                    self._json_response(400, {"error": "machine_id must be a positive integer"})
                    return

            category = str((query.get("category") or [""])[0]).strip()
            if category and len(category) > 80:
                self._json_response(400, {"error": "category is too long"})
                return

            date_from, err_from = self._optional_date(query, "date_from")
            if err_from:
                self._json_response(400, {"error": err_from})
                return
            date_to, err_to = self._optional_date(query, "date_to")
            if err_to:
                self._json_response(400, {"error": err_to})
                return
            if date_from and date_to and date_from > date_to:
                self._json_response(400, {"error": "date_from must be less than or equal to date_to"})
                return

            self._json_response(
                200,
                self.service.admin_analytics(
                    machine_id=machine_id,
                    category=(category or None),
                    date_from=date_from,
                    date_to=date_to,
                ),
            )
            return

        if parsed.path == "/api/admin/users":
            if self._require_roles({"admin"}) is None:
                return
            self._json_response(200, {"users": self.service.list_users()})
            return

        if parsed.path == "/api/troubleshoot/session":
            if self._require_roles({"operator", "admin"}) is None:
                return
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

        if self._is_react_ui():
            self._handle_react_get(parsed)
            return

        if parsed.path == "/login.html":
            if self.service.auth_enabled:
                user = self._current_user(refresh=False)
                if user:
                    if str(user.get("role") or "") == "admin":
                        self.send_response(302)
                        self.send_header("Location", "/admin.html")
                        self.end_headers()
                        return
                    self.send_response(302)
                    self.send_header("Location", "/operator.html")
                    self.end_headers()
                    return
            super().do_GET()
            return

        if parsed.path == "/":
            if self.service.auth_enabled:
                user = self._current_user(refresh=False)
                if user:
                    if str(user.get("role") or "") == "admin":
                        self.path = "/admin.html"
                    else:
                        self.path = "/operator.html"
                else:
                    self.path = "/login.html"
            else:
                self.path = "/operator.html"

        if parsed.path == "/operator.html" and self.service.auth_enabled:
            user = self._current_user(refresh=False)
            if user is None:
                self.send_response(302)
                self.send_header("Location", "/login.html?next=/operator.html")
                self.end_headers()
                return
            if str(user.get("role") or "") not in {"operator", "admin"}:
                self.send_response(302)
                self.send_header("Location", "/login.html?next=/operator.html")
                self.end_headers()
                return

        if parsed.path == "/admin.html" and self.service.auth_enabled:
            user = self._current_user(refresh=False)
            if user is None:
                self.send_response(302)
                self.send_header("Location", "/login.html?next=/admin.html")
                self.end_headers()
                return
            if str(user.get("role") or "") != "admin":
                self.send_response(302)
                self.send_header("Location", "/operator.html")
                self.end_headers()
                return

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

        if parsed.path == "/api/auth/login":
            self._handle_auth_login(payload)
            return

        if parsed.path == "/api/auth/logout":
            self._handle_auth_logout()
            return

        if parsed.path == "/api/query":
            if self._require_roles({"operator", "admin"}) is None:
                return
            self._handle_query(payload)
            return

        if parsed.path == "/api/troubleshoot/start":
            if self._require_roles({"operator", "admin"}) is None:
                return
            self._handle_troubleshoot_start(payload)
            return

        if parsed.path == "/api/troubleshoot/next":
            if self._require_roles({"operator", "admin"}) is None:
                return
            self._handle_troubleshoot_next(payload)
            return

        if parsed.path == "/api/realtime/document":
            if self._require_roles({"admin"}) is None:
                return
            self._handle_realtime_document(payload)
            return

        if parsed.path == "/api/realtime/complaint":
            if self._require_roles({"admin"}) is None:
                return
            self._handle_realtime_complaint(payload)
            return

        if parsed.path == "/api/realtime/trouble-event":
            if self._require_roles({"admin"}) is None:
                return
            self._handle_realtime_trouble_event(payload)
            return

        if parsed.path == "/api/admin/users":
            if self._require_roles({"admin"}) is None:
                return
            self._handle_admin_create_user(payload)
            return

        if parsed.path == "/api/admin/users/update":
            if self._require_roles({"admin"}) is None:
                return
            self._handle_admin_update_user(payload)
            return

        if parsed.path == "/api/feedback":
            if self._require_roles({"operator", "admin"}) is None:
                return
            self._handle_feedback(payload)
            return

        self._json_response(404, {"error": "Not found"})

    def _handle_auth_me(self) -> None:
        if not self.service.auth_enabled:
            self._json_response(200, {"auth_enabled": False, "authenticated": False})
            return
        user = self._current_user(refresh=True)
        if user is None:
            self._json_response(200, {"auth_enabled": True, "authenticated": False})
            return
        self._json_response(
            200,
            {
                "auth_enabled": True,
                "authenticated": True,
                "user": {
                    "id": user.get("id"),
                    "username": user.get("username"),
                    "role": user.get("role"),
                },
                "expires_at": user.get("expires_at"),
            },
        )

    def _handle_auth_login(self, payload: dict) -> None:
        if not self.service.auth_enabled:
            self._json_response(400, {"error": "Authentication is disabled"})
            return
        username = str(payload.get("username") or "").strip()
        password = str(payload.get("password") or "")
        try:
            login_payload = self.service.login(username=username, password=password)
        except ValueError as exc:
            msg = str(exc)
            status = 401 if "credentials" in msg.lower() or "inactive" in msg.lower() else 400
            self._json_response(status, {"error": msg})
            return

        cookie_value = self._build_auth_cookie(str(login_payload.get("session_token") or ""))
        self._json_response(
            200,
            {
                "ok": True,
                "user": login_payload.get("user"),
                "expires_at": login_payload.get("expires_at"),
            },
            headers={"Set-Cookie": cookie_value},
        )

    def _handle_auth_logout(self) -> None:
        token = self._session_token()
        self.service.logout(token)
        self._json_response(
            200,
            {"ok": True},
            headers={"Set-Cookie": self._clear_auth_cookie()},
        )

    def _session_token(self) -> str:
        cookie_name = os.getenv("DIGITAL_BRAIN_AUTH_COOKIE_NAME", AUTH_COOKIE_NAME)
        raw = self.headers.get("Cookie", "")
        if not raw:
            return ""
        jar = SimpleCookie()
        try:
            jar.load(raw)
        except Exception:  # noqa: BLE001
            return ""
        item = jar.get(cookie_name)
        if item is None:
            return ""
        return str(item.value or "")

    def _current_user(self, refresh: bool) -> dict | None:
        if not self.service.auth_enabled:
            return {"id": None, "username": "local", "role": "admin", "expires_at": None}
        token = self._session_token()
        if not token:
            return None
        return self.service.get_authenticated_user(token, refresh=refresh)

    def _optional_date(self, query: dict, key: str) -> tuple[str | None, str]:
        raw = str((query.get(key) or [""])[0]).strip()
        if not raw:
            return None, ""
        if not DATE_RE.fullmatch(raw):
            return None, f"{key} must be YYYY-MM-DD"
        return raw, ""

    def _is_react_ui(self) -> bool:
        return str(getattr(self, "ui_mode", "legacy")).strip().lower() == "react"

    def _redirect(self, location: str) -> None:
        self.send_response(302)
        self.send_header("Location", location)
        self.end_headers()

    def _handle_react_get(self, parsed) -> None:
        path = parsed.path

        if path in {"/login.html", "/operator.html", "/admin.html"}:
            redirect_map = {
                "/login.html": "/login",
                "/operator.html": "/operator",
                "/admin.html": "/admin",
            }
            self._redirect(redirect_map[path])
            return

        if path == "/":
            if self.service.auth_enabled:
                user = self._current_user(refresh=False)
                if user:
                    if str(user.get("role") or "") == "admin":
                        self._redirect("/admin")
                        return
                    self._redirect("/operator")
                    return
                self._redirect("/login")
                return
            self._redirect("/operator")
            return

        if path == "/login":
            if self.service.auth_enabled:
                user = self._current_user(refresh=False)
                if user:
                    if str(user.get("role") or "") == "admin":
                        self._redirect("/admin")
                        return
                    self._redirect("/operator")
                    return
            self.path = "/index.html"
            super().do_GET()
            return

        if path == "/operator":
            if self.service.auth_enabled:
                user = self._current_user(refresh=False)
                if user is None or str(user.get("role") or "") not in {"operator", "admin"}:
                    self._redirect("/login?next=/operator")
                    return
            self.path = "/index.html"
            super().do_GET()
            return

        if path == "/admin":
            if self.service.auth_enabled:
                user = self._current_user(refresh=False)
                if user is None:
                    self._redirect("/login?next=/admin")
                    return
                if str(user.get("role") or "") != "admin":
                    self._redirect("/operator")
                    return
            self.path = "/index.html"
            super().do_GET()
            return

        super().do_GET()

    def _require_roles(self, roles: set[str]) -> dict | None:
        if not self.service.auth_enabled:
            return {"id": None, "username": "local", "role": "admin"}
        user = self._current_user(refresh=True)
        if user is None:
            self._json_response(401, {"error": "Authentication required"})
            return None
        role = str(user.get("role") or "")
        if role not in roles:
            self._json_response(403, {"error": "Forbidden"})
            return None
        return user

    def _build_auth_cookie(self, token: str) -> str:
        cookie_name = os.getenv("DIGITAL_BRAIN_AUTH_COOKIE_NAME", AUTH_COOKIE_NAME)
        secure_cookie = os.getenv("DIGITAL_BRAIN_AUTH_COOKIE_SECURE", str(AUTH_COOKIE_SECURE)).strip().lower()
        jar = SimpleCookie()
        jar[cookie_name] = token
        jar[cookie_name]["path"] = "/"
        jar[cookie_name]["httponly"] = True
        jar[cookie_name]["samesite"] = "Lax"
        if secure_cookie in {"1", "true", "yes", "on"}:
            jar[cookie_name]["secure"] = True
        return jar.output(header="").strip()

    def _clear_auth_cookie(self) -> str:
        cookie_name = os.getenv("DIGITAL_BRAIN_AUTH_COOKIE_NAME", AUTH_COOKIE_NAME)
        secure_cookie = os.getenv("DIGITAL_BRAIN_AUTH_COOKIE_SECURE", str(AUTH_COOKIE_SECURE)).strip().lower()
        jar = SimpleCookie()
        jar[cookie_name] = ""
        jar[cookie_name]["path"] = "/"
        jar[cookie_name]["httponly"] = True
        jar[cookie_name]["samesite"] = "Lax"
        jar[cookie_name]["max-age"] = 0
        if secure_cookie in {"1", "true", "yes", "on"}:
            jar[cookie_name]["secure"] = True
        return jar.output(header="").strip()

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

    def _handle_admin_create_user(self, payload: dict) -> None:
        username = str(payload.get("username") or "").strip()
        password = str(payload.get("password") or "")
        role = str(payload.get("role") or "").strip().lower()
        if not username:
            self._json_response(400, {"error": "username is required"})
            return
        if not password:
            self._json_response(400, {"error": "password is required"})
            return
        if role not in {"operator", "admin"}:
            self._json_response(400, {"error": "role must be one of: operator, admin"})
            return
        is_active = bool(payload.get("is_active", True))
        upsert = bool(payload.get("upsert", True))
        try:
            response = self.service.create_user(
                username=username,
                password=password,
                role=role,
                is_active=is_active,
                upsert=upsert,
            )
        except ValueError as exc:
            self._json_response(400, {"error": str(exc)})
            return
        self._json_response(200, {"ok": True, "user": response})

    def _handle_admin_update_user(self, payload: dict) -> None:
        user_id = payload.get("user_id")
        try:
            user_id_int = int(user_id)
        except (TypeError, ValueError):
            self._json_response(400, {"error": "user_id must be an integer"})
            return

        role_raw = payload.get("role")
        role = str(role_raw).strip().lower() if role_raw is not None else None

        is_active = payload.get("is_active")
        if is_active is not None:
            is_active = bool(is_active)

        password_raw = payload.get("password")
        password = str(password_raw) if password_raw is not None else None
        if password is not None and not password:
            password = None

        try:
            updated = self.service.update_user(
                user_id=user_id_int,
                role=role,
                is_active=is_active,
                password=password,
            )
        except ValueError as exc:
            self._json_response(400, {"error": str(exc)})
            return
        self._json_response(200, {"ok": True, "user": updated})

    def _json_response(self, code: int, payload: dict, headers: dict[str, str] | None = None) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        if headers:
            for key, value in headers.items():
                self.send_header(key, value)
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: object) -> None:
        # keep server output concise
        return


def run_server(service: DigitalBrainService, host: str = "127.0.0.1", port: int = 8080) -> None:
    ui_mode, static_dir = _resolve_ui_mode_and_static_dir()
    os.chdir(static_dir)

    class Handler(BrainHandler):
        pass

    Handler.service = service
    Handler.ui_mode = ui_mode

    server = ThreadingHTTPServer((host, port), Handler)
    print(f"Digital Brain server running on http://{host}:{port} (ui={ui_mode}, static_dir={static_dir})")
    server.serve_forever()


def ensure_web_assets() -> Path:
    DEFAULT_WEB_DIR.mkdir(parents=True, exist_ok=True)
    return DEFAULT_WEB_DIR


def _resolve_ui_mode_and_static_dir() -> tuple[str, Path]:
    requested = os.getenv("DIGITAL_BRAIN_UI_MODE", "legacy").strip().lower()
    if requested not in {"legacy", "react", "auto"}:
        requested = "legacy"

    react_ready = (DEFAULT_FRONTEND_DIST_DIR / "index.html").exists()
    if requested == "auto":
        mode = "react" if react_ready else "legacy"
    elif requested == "react":
        mode = "react" if react_ready else "legacy"
    else:
        mode = "legacy"

    static_dir = DEFAULT_FRONTEND_DIST_DIR if mode == "react" else DEFAULT_WEB_DIR
    static_dir.mkdir(parents=True, exist_ok=True)
    return mode, static_dir
