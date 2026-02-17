from __future__ import annotations

import binascii
import hashlib
import hmac
import json
import os
import re
import secrets
import uuid
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from itertools import zip_longest
from pathlib import Path
from typing import Any

from .chunking import TextChunk, build_chunks
from .config import (
    AUTH_ENABLED,
    AUTH_SESSION_HOURS,
    BOOTSTRAP_ADMIN_PASSWORD,
    BOOTSTRAP_ADMIN_USER,
)
from .pdf_ingest import load_pdf_document, load_pdf_documents
from .rag import RagSynthesizer
from .repository import Repository
from .retrieval import BM25Retriever, IndexedChunk, tokenize
from .sql_dump import rows_for_table


@dataclass
class QueryResponse:
    session_id: str
    machine_id: int
    answer: str
    answer_mode: str
    triage: str
    confidence_score: float
    confidence_label: str
    checklist: list[str]
    citations: list[dict[str, Any]]
    historical_suggestions: list[dict[str, Any]]
    troubleshooting_flow: dict[str, Any]


class DigitalBrainService:
    def __init__(self, db_path: Path) -> None:
        self.repo = Repository(db_path)
        self.retriever = self._build_retriever()
        self.synthesizer = RagSynthesizer()
        self.auth_enabled = _env_bool("DIGITAL_BRAIN_AUTH_ENABLED", AUTH_ENABLED)
        self.auth_session_hours = max(
            1,
            _env_int("DIGITAL_BRAIN_AUTH_SESSION_HOURS", AUTH_SESSION_HOURS),
        )
        self.flow_llm_assist = _env_bool("DIGITAL_BRAIN_FLOW_LLM_ASSIST", True)
        if self.auth_enabled:
            self._bootstrap_admin_if_needed()

    def create_user(
        self,
        username: str,
        password: str,
        role: str,
        is_active: bool = True,
        upsert: bool = False,
    ) -> dict[str, Any]:
        username_clean = username.strip()
        role_clean = role.strip().lower()
        if not username_clean:
            raise ValueError("username is required")
        if not password:
            raise ValueError("password is required")
        if role_clean not in {"operator", "admin"}:
            raise ValueError("role must be one of: operator, admin")
        pw_hash = _hash_password(password)
        if upsert:
            user_id = self.repo.upsert_user(
                username=username_clean,
                password_hash=pw_hash,
                role=role_clean,
                is_active=is_active,
            )
        else:
            user_id = self.repo.create_user(
                username=username_clean,
                password_hash=pw_hash,
                role=role_clean,
                is_active=is_active,
            )
        self._audit(
            "auth_user_create",
            {"user_id": user_id, "username": username_clean, "role": role_clean, "upsert": upsert},
        )
        return {
            "id": user_id,
            "username": username_clean,
            "role": role_clean,
            "is_active": bool(is_active),
        }

    def list_users(self) -> list[dict[str, Any]]:
        rows = self.repo.list_users()
        out: list[dict[str, Any]] = []
        for row in rows:
            out.append(
                {
                    "id": int(row.get("id") or 0),
                    "username": str(row.get("username") or ""),
                    "role": str(row.get("role") or "operator"),
                    "is_active": int(row.get("is_active") or 0) == 1,
                    "created_at": str(row.get("created_at") or ""),
                }
            )
        return out

    def update_user(
        self,
        user_id: int,
        role: str | None = None,
        is_active: bool | None = None,
        password: str | None = None,
    ) -> dict[str, Any]:
        if user_id <= 0:
            raise ValueError("user_id must be a positive integer")
        existing = self.repo.get_user_by_id(user_id)
        if existing is None:
            raise ValueError("User not found")

        role_clean: str | None = None
        if role is not None:
            role_clean = role.strip().lower()
            if role_clean not in {"operator", "admin"}:
                raise ValueError("role must be one of: operator, admin")

        current_role = str(existing.get("role") or "operator")
        current_active = int(existing.get("is_active") or 0) == 1
        next_role = role_clean if role_clean is not None else current_role
        next_active = is_active if is_active is not None else current_active

        # Prevent lockout by removing/deactivating the last active admin.
        if current_role == "admin" and current_active and (next_role != "admin" or not next_active):
            if self.repo.count_admin_users() <= 1:
                raise ValueError("Cannot remove or deactivate the last active admin")

        password_hash: str | None = None
        if password is not None:
            if not password:
                raise ValueError("password cannot be empty")
            password_hash = _hash_password(password)

        updated = self.repo.update_user(
            user_id=user_id,
            role=role_clean,
            is_active=is_active,
            password_hash=password_hash,
        )
        if not updated:
            raise ValueError("No fields to update")
        self._audit(
            "auth_user_update",
            {
                "user_id": user_id,
                "role_changed": role_clean is not None,
                "active_changed": is_active is not None,
                "password_changed": password is not None,
            },
        )
        row = self.repo.get_user_by_id(user_id)
        if row is None:
            raise ValueError("User not found after update")
        return {
            "id": int(row.get("id") or 0),
            "username": str(row.get("username") or ""),
            "role": str(row.get("role") or "operator"),
            "is_active": int(row.get("is_active") or 0) == 1,
            "created_at": str(row.get("created_at") or ""),
        }

    def login(self, username: str, password: str) -> dict[str, Any]:
        if not self.auth_enabled:
            raise ValueError("Authentication is disabled")
        username_clean = username.strip()
        if not username_clean or not password:
            raise ValueError("Invalid credentials")
        user = self.repo.get_user_by_username(username_clean)
        if user is None:
            raise ValueError("Invalid credentials")
        if int(user.get("is_active") or 0) != 1:
            raise ValueError("User is inactive")
        stored_hash = str(user.get("password_hash") or "")
        if not _verify_password(password, stored_hash):
            raise ValueError("Invalid credentials")

        now = _utc_now_naive()
        expires_at = now + timedelta(hours=self.auth_session_hours)
        token = secrets.token_urlsafe(32)
        token_hash = _hash_token(token)
        session_id = str(uuid.uuid4())
        self.repo.delete_expired_auth_sessions(_fmt_dt(now))
        self.repo.create_auth_session(
            session_id=session_id,
            user_id=int(user.get("id") or 0),
            token_hash=token_hash,
            expires_at=_fmt_dt(expires_at),
        )
        self._audit(
            "auth_login",
            {"user_id": int(user.get("id") or 0), "username": username_clean, "session_id": session_id},
        )
        return {
            "session_token": token,
            "session_id": session_id,
            "expires_at": _fmt_dt(expires_at),
            "user": {
                "id": int(user.get("id") or 0),
                "username": str(user.get("username") or ""),
                "role": str(user.get("role") or "operator"),
            },
        }

    def get_authenticated_user(self, session_token: str, refresh: bool = True) -> dict[str, Any] | None:
        if not self.auth_enabled:
            return None
        token = session_token.strip()
        if not token:
            return None
        row = self.repo.get_auth_session(_hash_token(token))
        if row is None:
            return None
        if int(row.get("is_active") or 0) != 1:
            self.repo.delete_auth_session(str(row.get("session_id") or ""))
            return None
        expires_at = _parse_datetime(str(row.get("expires_at") or ""))
        now = _utc_now_naive()
        if expires_at is None or expires_at <= now:
            self.repo.delete_auth_session(str(row.get("session_id") or ""))
            return None
        if refresh:
            new_expires_at = now + timedelta(hours=self.auth_session_hours)
            self.repo.touch_auth_session(str(row.get("session_id") or ""), _fmt_dt(new_expires_at))
            expires_at = new_expires_at
        return {
            "id": int(row.get("user_id") or 0),
            "username": str(row.get("username") or ""),
            "role": str(row.get("role") or "operator"),
            "session_id": str(row.get("session_id") or ""),
            "expires_at": _fmt_dt(expires_at),
        }

    def logout(self, session_token: str) -> None:
        if not self.auth_enabled:
            return
        token = session_token.strip()
        if not token:
            return
        self.repo.delete_auth_session_by_token(_hash_token(token))
        self._audit("auth_logout", {"token_present": True})

    def ingest_all(self, data_dir: Path) -> dict[str, int]:
        machines = self._load_machines(data_dir / "eqp-process_resources.sql")
        complaints = self._load_complaints(data_dir / "equipment_complaint.sql")
        trouble_events = self._load_trouble_events(data_dir / "trouble_track.sql")
        docs = self._load_documents(data_dir)
        chunks = self._build_all_chunks(docs)

        self.repo.replace_machines(machines)
        self.repo.replace_complaints(complaints)
        self.repo.replace_trouble_events(trouble_events)
        self.repo.replace_documents(docs)
        self.repo.replace_chunks(chunks)

        self.retriever = self._build_retriever()

        return {
            "machines": len(machines),
            "complaints": len(complaints),
            "trouble_events": len(trouble_events),
            "documents": len(docs),
            "chunks": len(chunks),
        }

    def list_machines(self) -> list[dict[str, Any]]:
        return self.repo.list_machines()

    def list_recent_machines(self, limit: int = 8) -> list[dict[str, Any]]:
        return self.repo.list_recent_machines(limit=limit)

    def realtime_add_document(
        self,
        path: str,
        machine_id: int | None = None,
        doc_type: str | None = None,
    ) -> dict[str, Any]:
        p = Path(path)
        if not p.exists():
            raise ValueError(f"Document not found: {path}")
        if p.suffix.lower() != ".pdf":
            raise ValueError("Only PDF document ingestion is supported")

        doc = load_pdf_document(p, machine_id=machine_id, doc_type=doc_type)
        doc_id = Path(doc.path).stem
        self.repo.upsert_document(
            {
                "doc_id": doc_id,
                "machine_id": doc.machine_id,
                "doc_type": doc.doc_type,
                "path": doc.path,
                "text": doc.text,
            }
        )
        chunks = self._build_all_chunks(
            [
                {
                    "doc_id": doc_id,
                    "machine_id": doc.machine_id,
                    "doc_type": doc.doc_type,
                    "path": doc.path,
                    "text": doc.text,
                }
            ]
        )
        self.repo.replace_chunks_for_doc(doc_id, chunks)
        self.retriever = self._build_retriever()
        self._audit(
            "realtime_document_ingest",
            {
                "doc_id": doc_id,
                "machine_id": doc.machine_id,
                "doc_type": doc.doc_type,
                "chunk_count": len(chunks),
            },
        )
        return {"doc_id": doc_id, "chunk_count": len(chunks)}

    def realtime_upsert_complaint(self, payload: dict[str, Any]) -> dict[str, Any]:
        complaint_id = self.repo.upsert_complaint(
            {
                "complaint_id": payload.get("complaint_id"),
                "machine_id": int(payload.get("machine_id") or 0),
                "complaint_description": str(payload.get("complaint_description") or ""),
                "time_of_complaint": str(payload.get("time_of_complaint") or ""),
                "status": int(payload.get("status") or 0),
                "status_resolved": str(payload.get("status_resolved") or ""),
            }
        )
        machine_id = int(payload.get("machine_id") or 0)
        if machine_id > 0:
            self.repo.record_recent_machine(
                machine_id=machine_id,
                issue=str(payload.get("complaint_description") or ""),
                session_id=f"complaint-{complaint_id}",
            )
        self._audit(
            "realtime_complaint_upsert",
            {"complaint_id": complaint_id, "machine_id": machine_id},
        )
        return {"complaint_id": complaint_id}

    def realtime_add_trouble_event(self, payload: dict[str, Any]) -> dict[str, Any]:
        complaint_id = int(payload.get("complaint_id") or 0)
        if complaint_id <= 0:
            raise ValueError("complaint_id is required")
        self.repo.insert_trouble_event_row(
            {
                "complaint_id": complaint_id,
                "timestamp": str(payload.get("timestamp") or ""),
                "diagnosis": str(payload.get("diagnosis") or ""),
                "action_taken": str(payload.get("action_taken") or ""),
                "comments": str(payload.get("comments") or ""),
            }
        )
        self._audit("realtime_trouble_event_insert", {"complaint_id": complaint_id})
        return {"ok": True, "complaint_id": complaint_id}

    def query(self, machine_id: int, question: str) -> QueryResponse:
        response = self._compose_query_response(
            machine_id=machine_id,
            question=question,
            session_id=str(uuid.uuid4()),
        )
        self.repo.record_recent_machine(machine_id=machine_id, issue=question, session_id=response.session_id)
        self._audit(
            "query",
            {
                "session_id": response.session_id,
                "machine_id": machine_id,
                "triage": response.triage,
                "confidence_score": response.confidence_score,
                "answer_mode": response.answer_mode,
            },
        )
        return response

    def start_troubleshoot(self, machine_id: int, question: str) -> dict[str, Any]:
        response = self._compose_query_response(
            machine_id=machine_id,
            question=question,
            session_id=str(uuid.uuid4()),
        )
        start_node_id = str(response.troubleshooting_flow.get("start_node_id") or "q1")
        self.repo.create_troubleshoot_session(
            session_id=response.session_id,
            machine_id=machine_id,
            question=question,
            triage=response.triage,
            flow_json=json.dumps(response.troubleshooting_flow),
            current_node_id=start_node_id,
        )
        self.repo.record_recent_machine(machine_id=machine_id, issue=question, session_id=response.session_id)
        current_node = self._flow_node(response.troubleshooting_flow, start_node_id)
        self._audit(
            "troubleshoot_start",
            {
                "session_id": response.session_id,
                "machine_id": machine_id,
                "start_node_id": start_node_id,
                "triage": response.triage,
                "answer_mode": response.answer_mode,
            },
        )

        return {
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
            "current_node": current_node,
            "is_closed": current_node.get("kind") == "final",
        }

    def next_troubleshoot(self, session_id: str, response_value: str) -> dict[str, Any]:
        state = self.repo.get_troubleshoot_session(session_id)
        if state is None:
            raise ValueError("Session not found")

        flow = json.loads(str(state.get("flow_json") or "{}"))
        current_node_id = str(state.get("current_node_id") or "")
        current_node = self._flow_node(flow, current_node_id)
        if not current_node:
            raise ValueError("Current troubleshooting node not found")

        if bool(state.get("is_closed")) or current_node.get("kind") == "final":
            return {
                "session_id": session_id,
                "machine_id": state.get("machine_id"),
                "current_node": current_node,
                "is_closed": True,
                "message": "Session already closed",
            }

        decision = response_value.strip().lower()
        next_node_id = ""
        if current_node.get("kind") == "question":
            if decision not in ("yes", "no"):
                raise ValueError("Question node accepts response: yes/no")
            next_node_id = str(current_node.get(decision) or "")
        elif current_node.get("kind") == "action":
            if decision not in ("done", "completed", "next"):
                raise ValueError("Action node accepts response: done")
            next_node_id = str(current_node.get("next") or "")
        else:
            raise ValueError("Unsupported node kind for transition")

        if not next_node_id:
            raise ValueError("Next node not configured")

        next_node = self._flow_node(flow, next_node_id)
        if not next_node:
            raise ValueError("Next troubleshooting node not found")

        is_closed = next_node.get("kind") == "final"
        self.repo.insert_troubleshoot_event(
            session_id=session_id,
            node_id=current_node_id,
            response=decision,
            next_node_id=next_node_id,
        )
        self.repo.update_troubleshoot_session(
            session_id=session_id,
            current_node_id=next_node_id,
            is_closed=is_closed,
        )
        self._audit(
            "troubleshoot_next",
            {
                "session_id": session_id,
                "node_id": current_node_id,
                "response": decision,
                "next_node_id": next_node_id,
                "is_closed": is_closed,
            },
        )

        return {
            "session_id": session_id,
            "machine_id": state.get("machine_id"),
            "current_node": next_node,
            "is_closed": is_closed,
            "allowed_responses": self._allowed_responses(next_node),
        }

    def get_troubleshoot_session(self, session_id: str) -> dict[str, Any]:
        state = self.repo.get_troubleshoot_session(session_id)
        if state is None:
            raise ValueError("Session not found")
        flow = json.loads(str(state.get("flow_json") or "{}"))
        current_node_id = str(state.get("current_node_id") or "")
        current_node = self._flow_node(flow, current_node_id)
        return {
            "session_id": state.get("session_id"),
            "machine_id": state.get("machine_id"),
            "question": state.get("question"),
            "triage": state.get("triage"),
            "is_closed": bool(state.get("is_closed")),
            "current_node": current_node,
            "allowed_responses": self._allowed_responses(current_node),
        }

    def _compose_query_response(
        self,
        machine_id: int,
        question: str,
        session_id: str,
    ) -> QueryResponse:
        results = self.retriever.search(question, machine_id=machine_id, top_k=5)
        triage = self._infer_triage(question)
        checklist = self._generate_checklist(triage)
        suggestions = self._historical_suggestions(machine_id, question)
        doc_lookup = self.repo.document_lookup()
        citations: list[dict[str, Any]] = []

        for result in results[:3]:
            doc = doc_lookup.get(result.doc_id, {})
            citations.append(
                {
                    "doc_type": result.doc_type,
                    "path": doc.get("path", result.doc_id),
                    "snippet": _shorten(result.text, 260),
                    "score": round(result.score, 3),
                }
            )
        confidence_score = self._confidence_score(citations, suggestions)
        confidence_label = self._confidence_label(confidence_score)
        must_fallback = self._must_fallback(citations, confidence_score)

        synthesis_payload = {
            "machine_id": machine_id,
            "question": question,
            "triage": triage,
            "checklist": checklist,
            "citations": citations,
            "historical_suggestions": suggestions,
            "confidence_score": confidence_score,
            "confidence_label": confidence_label,
        }

        answer_mode = "deterministic"
        answer, synthesis_meta = self.synthesizer.synthesize(synthesis_payload)
        answer_mode = str(synthesis_meta.get("mode") or "deterministic")
        if must_fallback:
            answer = self._low_confidence_answer(
                machine_id=machine_id,
                triage=triage,
                checklist=checklist,
                citations=citations,
                suggestions=suggestions,
                confidence_label=confidence_label,
            )
            answer_mode = "deterministic_guardrail"

        flow = self._build_hybrid_flow(
            machine_id=machine_id,
            question=question,
            triage=triage,
            checklist=checklist,
            citations=citations,
            suggestions=suggestions,
            confidence_label=confidence_label,
            answer_mode=answer_mode,
            must_fallback=must_fallback,
        )

        return QueryResponse(
            session_id=session_id,
            machine_id=machine_id,
            answer=answer,
            answer_mode=answer_mode,
            triage=triage,
            confidence_score=confidence_score,
            confidence_label=confidence_label,
            checklist=checklist,
            citations=citations,
            historical_suggestions=suggestions,
            troubleshooting_flow=flow,
        )

    def _build_hybrid_flow(
        self,
        machine_id: int,
        question: str,
        triage: str,
        checklist: list[str],
        citations: list[dict[str, Any]],
        suggestions: list[dict[str, Any]],
        confidence_label: str,
        answer_mode: str,
        must_fallback: bool,
    ) -> dict[str, Any]:
        deterministic_flow = self._build_dynamic_flow(machine_id, question, triage)
        deterministic_flow["flow_mode"] = "deterministic"
        deterministic_flow["flow_source"] = "history_rules"

        if not self.flow_llm_assist:
            deterministic_flow["flow_reason"] = "llm_assist_disabled"
            return deterministic_flow
        if must_fallback:
            deterministic_flow["flow_reason"] = "low_evidence_guardrail"
            return deterministic_flow
        if not answer_mode.startswith("llm_"):
            deterministic_flow["flow_reason"] = "llm_answer_not_available"
            return deterministic_flow

        proposed, meta = self.synthesizer.synthesize_flow(
            {
                "machine_id": machine_id,
                "question": question,
                "triage": triage,
                "checklist": checklist,
                "citations": citations,
                "historical_suggestions": suggestions,
                "confidence_label": confidence_label,
            }
        )
        validated, reason = self._validate_llm_flow(proposed)
        if validated is None:
            deterministic_flow["flow_mode"] = "deterministic_fallback"
            deterministic_flow["flow_reason"] = reason or str(meta.get("error") or "invalid_llm_flow")
            deterministic_flow["flow_source"] = "history_rules"
            return deterministic_flow

        validated["query_terms"] = tokenize(question)
        validated["history_snapshot"] = deterministic_flow.get("history_snapshot", {})
        validated["flow_mode"] = "llm_assisted"
        validated["flow_source"] = str(meta.get("mode") or "llm_flow")
        return validated

    def submit_feedback(
        self,
        session_id: str,
        machine_id: int,
        issue: str,
        helpful: bool,
        workaround: str,
    ) -> dict[str, Any]:
        self.repo.insert_feedback(
            session_id=session_id,
            machine_id=machine_id,
            issue=issue,
            helpful=helpful,
            workaround=workaround,
        )
        self._audit(
            "feedback",
            {
                "session_id": session_id,
                "machine_id": machine_id,
                "helpful": helpful,
                "workaround_present": bool(workaround.strip()),
            },
        )
        return {"ok": True}

    def admin_analytics(
        self,
        machine_id: int | None = None,
        category: str | None = None,
        date_from: str | None = None,
        date_to: str | None = None,
    ) -> dict[str, Any]:
        analytics = self.repo.admin_analytics(
            machine_id=machine_id,
            category=category,
            date_from=date_from,
            date_to=date_to,
        )
        analytics["knowledge_gaps"] = self._knowledge_gap_clusters(analytics)
        analytics["applied_filters"] = {
            "machine_id": machine_id,
            "category": category or "",
            "date_from": date_from or "",
            "date_to": date_to or "",
        }
        return analytics

    def _bootstrap_admin_if_needed(self) -> None:
        if self.repo.count_admin_users() > 0:
            return
        username = os.getenv("DIGITAL_BRAIN_BOOTSTRAP_ADMIN_USER", BOOTSTRAP_ADMIN_USER).strip()
        password = os.getenv(
            "DIGITAL_BRAIN_BOOTSTRAP_ADMIN_PASSWORD",
            BOOTSTRAP_ADMIN_PASSWORD,
        )
        if not username or not password:
            return
        self.create_user(
            username=username,
            password=password,
            role="admin",
            is_active=True,
            upsert=True,
        )

    def _audit(self, event_type: str, payload: dict[str, Any]) -> None:
        try:
            self.repo.insert_audit_log(event_type, json.dumps(payload, ensure_ascii=True))
        except Exception:  # noqa: BLE001
            # Auditing must never break operator flow.
            return

    def _confidence_score(self, citations: list[dict[str, Any]], suggestions: list[dict[str, Any]]) -> float:
        if not citations:
            return 0.0
        top_score = float(citations[0].get("score") or 0.0)
        second_score = float(citations[1].get("score") or 0.0) if len(citations) > 1 else 0.0
        score_signal = min(1.0, top_score / 12.0)
        separation_signal = 0.0
        if top_score > 0.0:
            separation_signal = min(1.0, max(0.0, (top_score - second_score) / top_score))
        history_signal = min(1.0, sum(int(item.get("support_count") or 0) for item in suggestions) / 8.0)
        blended = 0.6 * score_signal + 0.2 * separation_signal + 0.2 * history_signal
        return round(max(0.0, min(1.0, blended)), 3)

    def _confidence_label(self, confidence_score: float) -> str:
        if confidence_score >= 0.75:
            return "high"
        if confidence_score >= 0.45:
            return "medium"
        return "low"

    def _must_fallback(self, citations: list[dict[str, Any]], confidence_score: float) -> bool:
        if not citations:
            return True
        return confidence_score < 0.2

    def _low_confidence_answer(
        self,
        machine_id: int,
        triage: str,
        checklist: list[str],
        citations: list[dict[str, Any]],
        suggestions: list[dict[str, Any]],
        confidence_label: str,
    ) -> str:
        lines = [
            f"Machine {machine_id} triage category: {triage}.",
            f"Evidence confidence: {confidence_label}.",
            "Insufficient strong evidence for a definitive root cause. Follow checklist and escalate if issue persists.",
        ]
        if citations:
            lines.append("Closest manual evidence:")
            for citation in citations[:2]:
                lines.append(f"- {citation.get('snippet', '')}")
        if suggestions:
            lines.append("Closest historical actions:")
            for item in suggestions[:2]:
                lines.append(f"- {item.get('action', '')} (seen {item.get('support_count', 0)} times)")
        lines.append("Dynamic yes/no flow generated from machine-specific complaint history.")
        return "\\n".join(lines)

    def _knowledge_gap_clusters(self, analytics: dict[str, Any]) -> list[dict[str, Any]]:
        texts: list[str] = []
        for row in analytics.get("unresolved_issues") or []:
            texts.append(str(row.get("complaint_description") or ""))
        for row in analytics.get("failed_feedback") or []:
            texts.append(str(row.get("issue") or ""))
            texts.append(str(row.get("workaround") or ""))

        stop_words = {
            "the", "and", "for", "with", "this", "that", "from", "have", "been", "not",
            "are", "was", "were", "into", "after", "before", "need", "kindly", "please",
            "issue", "system", "tool", "machine", "daily", "task", "work", "done", "check",
            "lab", "line", "mode", "manual", "test", "sample", "run",
        }

        token_counter: Counter[str] = Counter()
        for text in texts:
            for token in tokenize(text):
                if len(token) < 4 or token in stop_words:
                    continue
                token_counter[token] += 1

        gaps: list[dict[str, Any]] = []
        for keyword, count in token_counter.most_common(12):
            gaps.append({"keyword": keyword, "count": count})
        return gaps

    def _flow_node(self, flow: dict[str, Any], node_id: str) -> dict[str, Any]:
        nodes = flow.get("nodes") or []
        for node in nodes:
            if str(node.get("id")) == node_id:
                return node
        return {}

    def _allowed_responses(self, node: dict[str, Any]) -> list[str]:
        kind = str(node.get("kind") or "")
        if kind == "question":
            return ["yes", "no"]
        if kind == "action":
            return ["done"]
        return []

    def _build_retriever(self) -> BM25Retriever:
        chunks = [
            IndexedChunk(
                chunk_id=row["chunk_id"],
                doc_id=row["doc_id"],
                machine_id=row["machine_id"],
                doc_type=row["doc_type"],
                text=row["text"],
            )
            for row in self.repo.list_chunks()
        ]
        return BM25Retriever(chunks)

    def _load_machines(self, sql_path: Path) -> list[dict[str, Any]]:
        columns, rows = rows_for_table(sql_path, "resources")
        out: list[dict[str, Any]] = []
        for row in rows:
            mapped = _as_record(columns, row)
            manual_ref = None
            elements_allowed = str(mapped.get("Elements_allowed") or "")
            if "manuals/" in elements_allowed.lower():
                manual_ref = elements_allowed

            out.append(
                {
                    "machine_id": _safe_int(mapped.get("machid")),
                    "name": mapped.get("name") or "Unknown",
                    "category": mapped.get("category"),
                    "location": str(mapped.get("location") or ""),
                    "tool_sop": mapped.get("tool_sop"),
                    "policy_documents": mapped.get("policy_documents"),
                    "standard_recipies": mapped.get("standard_recipies"),
                    "manual_ref": manual_ref,
                }
            )
        return out

    def _load_complaints(self, sql_path: Path) -> list[dict[str, Any]]:
        columns, rows = rows_for_table(sql_path, "equipment_complaint")
        out: list[dict[str, Any]] = []
        for row in rows:
            mapped = _as_record(columns, row)
            out.append(
                {
                    "complaint_id": _safe_int(mapped.get("complaint_id")),
                    "machine_id": _safe_int(mapped.get("machine_id")),
                    "complaint_description": mapped.get("complaint_description") or "",
                    "time_of_complaint": str(mapped.get("time_of_complaint") or ""),
                    "status": _safe_int(mapped.get("status"), default=0),
                    "status_resolved": str(mapped.get("status_resolved") or ""),
                }
            )
        return out

    def _load_trouble_events(self, sql_path: Path) -> list[dict[str, Any]]:
        columns, rows = rows_for_table(sql_path, "trouble_track")
        out: list[dict[str, Any]] = []
        for row in rows:
            mapped = _as_record(columns, row)
            out.append(
                {
                    "complaint_id": _safe_int(mapped.get("complaint_id")),
                    "timestamp": str(mapped.get("timestamp") or ""),
                    "diagnosis": mapped.get("diagnosis") or "",
                    "action_taken": mapped.get("action_taken") or "",
                    "comments": mapped.get("comments") or "",
                }
            )
        return out

    def _load_documents(self, data_dir: Path) -> list[dict[str, Any]]:
        docs: list[dict[str, Any]] = []
        for pdf in load_pdf_documents(data_dir):
            doc_id = Path(pdf.path).stem
            docs.append(
                {
                    "doc_id": doc_id,
                    "machine_id": pdf.machine_id,
                    "doc_type": pdf.doc_type,
                    "path": pdf.path,
                    "text": pdf.text,
                }
            )
        return docs

    def _build_all_chunks(self, docs: list[dict[str, Any]]) -> list[dict[str, Any]]:
        all_chunks: list[dict[str, Any]] = []
        for doc in docs:
            built: list[TextChunk] = build_chunks(
                doc_id=doc["doc_id"],
                machine_id=doc["machine_id"],
                doc_type=doc["doc_type"],
                text=doc["text"] or "",
            )
            for chunk in built:
                all_chunks.append(
                    {
                        "chunk_id": chunk.chunk_id,
                        "doc_id": chunk.doc_id,
                        "machine_id": chunk.machine_id,
                        "doc_type": chunk.doc_type,
                        "text": chunk.text,
                    }
                )
        return all_chunks

    def _infer_triage(self, question: str) -> str:
        q = question.lower()
        if any(term in q for term in ["power", "voltage", "electrical", "current", "rf"]):
            return "Power"
        if any(term in q for term in ["gas", "pressure", "leak", "vacuum", "flow"]):
            return "Hydraulics"
        if any(term in q for term in ["align", "recipe", "mask", "wafer", "plasma", "temperature"]):
            return "Tooling"
        return "General"

    def _generate_checklist(self, triage: str) -> list[str]:
        if triage == "Power":
            return [
                "Is the machine main power indicator ON? [Yes/No]",
                "Are breaker and interlock statuses normal? [Yes/No]",
                "Run one controlled dummy cycle and verify alarms. [Pass/Fail]",
            ]
        if triage == "Hydraulics":
            return [
                "Is the required gas or flow source available and within range? [Yes/No]",
                "Any visible leak or abnormal pressure behavior? [Yes/No]",
                "Re-seat critical lines/valves and repeat a short test cycle. [Pass/Fail]",
            ]
        if triage == "Tooling":
            return [
                "Is the selected recipe and setup correct for this sample? [Yes/No]",
                "Are consumables/chucks/holders clean and correctly mounted? [Yes/No]",
                "Perform one low-risk verification run and inspect output. [Pass/Fail]",
            ]
        return [
            "Confirm current machine state and active alarms. [Done]",
            "Check last known good run conditions and compare. [Done]",
            "Escalate with captured observations if issue persists. [Done]",
        ]

    def _historical_suggestions(self, machine_id: int, question: str) -> list[dict[str, Any]]:
        complaints = self.repo.list_machine_complaints(machine_id, limit=250)
        q_terms = set(tokenize(question))
        scored: list[tuple[float, dict[str, Any]]] = []
        now = datetime.now(timezone.utc).replace(tzinfo=None)

        for complaint in complaints:
            text = str(complaint.get("complaint_description") or "")
            terms = set(tokenize(text))
            intersection = len(q_terms.intersection(terms))
            if intersection == 0:
                continue
            union = len(q_terms.union(terms)) or 1
            similarity = intersection / union
            resolution_bonus = 0.25 if int(complaint.get("status") or 0) == 2 else 0.0
            recency_bonus = 0.0
            dt = _parse_datetime(str(complaint.get("time_of_complaint") or ""))
            if dt is not None:
                days_old = max(0.0, (now - dt).days)
                recency_bonus = max(0.0, 0.2 - min(0.2, days_old / 3650.0))
            final_score = similarity + resolution_bonus + recency_bonus
            scored.append((final_score, complaint))

        complaint_weight: dict[int, float] = {}
        if not scored:
            complaint_ids = []
        else:
            scored.sort(key=lambda item: item[0], reverse=True)
            selected = [item for item in scored[:25] if item[1].get("complaint_id")]
            complaint_ids = []
            for rank, (score, complaint) in enumerate(selected):
                cid = int(complaint["complaint_id"])
                complaint_ids.append(cid)
                complaint_weight[cid] = max(0.05, score + (0.2 / (rank + 1)))

        suggestion_scores: dict[tuple[str, str], float] = {}
        events = self.repo.list_trouble_events(complaint_ids)
        for event in events:
            action = str(event.get("action_taken") or "").strip()
            if not action:
                continue
            normalized = _shorten(" ".join(action.split()), 180)
            if normalized:
                cid = int(event.get("complaint_id") or 0)
                event_weight = complaint_weight.get(cid, 0.1)
                dt = _parse_datetime(str(event.get("timestamp") or ""))
                recency_boost = 0.0
                if dt is not None:
                    days_old = max(0.0, (now - dt).days)
                    recency_boost = max(0.0, 0.4 - min(0.4, days_old / 3650.0))
                key = (normalized, "equipment_complaint + trouble_track")
                suggestion_scores[key] = suggestion_scores.get(key, 0.0) + event_weight + recency_boost

        feedback_rows = self.repo.list_feedback_for_machine(machine_id, limit=250)
        for row in feedback_rows:
            helpful = int(row.get("helpful") or 0)
            workaround = str(row.get("workaround") or "").strip()
            issue = str(row.get("issue") or "")
            if helpful != 1 or not workaround:
                continue
            terms = set(tokenize(issue + " " + workaround))
            overlap = len(q_terms.intersection(terms))
            if overlap == 0 and q_terms:
                continue
            weight = 2 + overlap
            normalized = _shorten(" ".join(workaround.split()), 180)
            key = (normalized, "feedback_loop")
            suggestion_scores[key] = suggestion_scores.get(key, 0.0) + weight

        if not suggestion_scores:
            return []

        suggestions: list[dict[str, Any]] = []
        ranked = sorted(suggestion_scores.items(), key=lambda item: item[1], reverse=True)
        for (action, trace), support_count in ranked[:3]:
            suggestions.append(
                {
                    "action": action,
                    "support_count": int(round(support_count)),
                    "trace": trace,
                }
            )
        return suggestions

    def _validate_llm_flow(self, flow: dict[str, Any] | None) -> tuple[dict[str, Any] | None, str]:
        if not isinstance(flow, dict):
            return None, "llm_flow_missing"

        start_node_id = str(flow.get("start_node_id") or "").strip()
        raw_nodes = flow.get("nodes")
        if not start_node_id:
            return None, "llm_flow_missing_start_node"
        if not isinstance(raw_nodes, list):
            return None, "llm_flow_nodes_not_list"
        if len(raw_nodes) < 3 or len(raw_nodes) > 10:
            return None, "llm_flow_nodes_out_of_range"

        node_ids: set[str] = set()
        sanitized_nodes: list[dict[str, Any]] = []
        final_count = 0

        for raw in raw_nodes:
            if not isinstance(raw, dict):
                return None, "llm_flow_node_invalid"
            node_id = str(raw.get("id") or "").strip()
            kind = str(raw.get("kind") or "").strip().lower()
            text = _shorten(str(raw.get("text") or "").strip(), 220)
            if not node_id or not re.fullmatch(r"[a-zA-Z0-9_\\-]+", node_id):
                return None, "llm_flow_node_id_invalid"
            if node_id in node_ids:
                return None, "llm_flow_node_id_duplicate"
            if kind not in {"question", "action", "final"}:
                return None, "llm_flow_kind_invalid"
            if not text:
                return None, "llm_flow_text_missing"
            node_ids.add(node_id)

            node: dict[str, Any] = {"id": node_id, "kind": kind, "text": text}
            if kind == "question":
                yes = str(raw.get("yes") or "").strip()
                no = str(raw.get("no") or "").strip()
                if not yes or not no:
                    return None, "llm_flow_question_missing_edges"
                node["yes"] = yes
                node["no"] = no
            elif kind == "action":
                nxt = str(raw.get("next") or "").strip()
                if not nxt:
                    return None, "llm_flow_action_missing_next"
                node["next"] = nxt
            else:
                final_count += 1
            sanitized_nodes.append(node)

        if start_node_id not in node_ids:
            return None, "llm_flow_start_not_found"
        if final_count == 0:
            return None, "llm_flow_missing_final"

        node_lookup = {str(node["id"]): node for node in sanitized_nodes}
        for node in sanitized_nodes:
            kind = str(node.get("kind") or "")
            if kind == "question":
                yes = str(node.get("yes") or "")
                no = str(node.get("no") or "")
                if yes not in node_lookup or no not in node_lookup:
                    return None, "llm_flow_question_edge_unknown"
            elif kind == "action":
                nxt = str(node.get("next") or "")
                if nxt not in node_lookup:
                    return None, "llm_flow_action_next_unknown"

        # Verify at least one path from start reaches a final node.
        stack = [start_node_id]
        visited: set[str] = set()
        reaches_final = False
        steps = 0
        while stack and steps < 200:
            steps += 1
            current = stack.pop()
            if current in visited:
                continue
            visited.add(current)
            node = node_lookup.get(current)
            if not node:
                continue
            kind = str(node.get("kind") or "")
            if kind == "final":
                reaches_final = True
                break
            if kind == "question":
                stack.append(str(node.get("yes") or ""))
                stack.append(str(node.get("no") or ""))
            elif kind == "action":
                stack.append(str(node.get("next") or ""))
        if not reaches_final:
            return None, "llm_flow_no_final_path"

        return {"start_node_id": start_node_id, "nodes": sanitized_nodes}, ""

    def _build_dynamic_flow(self, machine_id: int, question: str, triage: str) -> dict[str, Any]:
        stats = self._history_signal_stats(machine_id)
        default_action = self._signal_action(stats, "general", "Escalate to EMT with latest alarm snapshot.")
        power_action = self._signal_action(stats, "power", "Verify breaker/interlock chain and retest.")
        pressure_action = self._signal_action(stats, "pressure", "Check chamber pressure and pump health.")
        leak_action = self._signal_action(stats, "leak", "Inspect leak points and re-seat suspect lines.")
        process_action = self._signal_action(stats, "process", "Review recipe/alignment setup and rerun test wafer.")
        thermal_action = self._signal_action(stats, "thermal", "Check temperature sensors/heaters and recalibrate.")

        nodes: list[dict[str, Any]]
        if triage == "Power":
            nodes = [
                {
                    "id": "q1",
                    "kind": "question",
                    "text": "Is the machine powered and interlocks healthy?",
                    "yes": "q2",
                    "no": "a_power",
                },
                {
                    "id": "q2",
                    "kind": "question",
                    "text": "After one controlled dummy run, is the alarm gone?",
                    "yes": "done",
                    "no": "a_general",
                },
                {
                    "id": "a_power",
                    "kind": "action",
                    "text": power_action,
                    "next": "q2",
                },
                {
                    "id": "a_general",
                    "kind": "action",
                    "text": default_action,
                    "next": "done",
                },
                {
                    "id": "done",
                    "kind": "final",
                    "text": "Close this session with thumbs up/down and capture workaround if needed.",
                },
            ]
        elif triage == "Hydraulics":
            nodes = [
                {
                    "id": "q1",
                    "kind": "question",
                    "text": "Is vacuum/pressure in expected operating range?",
                    "yes": "q2",
                    "no": "a_pressure",
                },
                {
                    "id": "q2",
                    "kind": "question",
                    "text": "Do you observe leak or unstable gas/flow behavior?",
                    "yes": "a_leak",
                    "no": "q3",
                },
                {
                    "id": "q3",
                    "kind": "question",
                    "text": "After re-seating lines/valves, did the short test cycle pass?",
                    "yes": "done",
                    "no": "a_general",
                },
                {
                    "id": "a_pressure",
                    "kind": "action",
                    "text": pressure_action,
                    "next": "q2",
                },
                {
                    "id": "a_leak",
                    "kind": "action",
                    "text": leak_action,
                    "next": "q3",
                },
                {
                    "id": "a_general",
                    "kind": "action",
                    "text": default_action,
                    "next": "done",
                },
                {
                    "id": "done",
                    "kind": "final",
                    "text": "Close this session with thumbs up/down and capture workaround if needed.",
                },
            ]
        elif triage == "Tooling":
            nodes = [
                {
                    "id": "q1",
                    "kind": "question",
                    "text": "Is recipe/alignment configuration correct for this sample?",
                    "yes": "q2",
                    "no": "a_process",
                },
                {
                    "id": "q2",
                    "kind": "question",
                    "text": "Is temperature/plasma behavior within expected range?",
                    "yes": "q3",
                    "no": "a_thermal",
                },
                {
                    "id": "q3",
                    "kind": "question",
                    "text": "Did a low-risk verification run succeed?",
                    "yes": "done",
                    "no": "a_general",
                },
                {
                    "id": "a_process",
                    "kind": "action",
                    "text": process_action,
                    "next": "q2",
                },
                {
                    "id": "a_thermal",
                    "kind": "action",
                    "text": thermal_action,
                    "next": "q3",
                },
                {
                    "id": "a_general",
                    "kind": "action",
                    "text": default_action,
                    "next": "done",
                },
                {
                    "id": "done",
                    "kind": "final",
                    "text": "Close this session with thumbs up/down and capture workaround if needed.",
                },
            ]
        else:
            nodes = [
                {
                    "id": "q1",
                    "kind": "question",
                    "text": "Is the symptom closer to power/interlock behavior?",
                    "yes": "a_power",
                    "no": "q2",
                },
                {
                    "id": "q2",
                    "kind": "question",
                    "text": "Is the symptom closer to pressure/flow/leak behavior?",
                    "yes": "a_pressure",
                    "no": "a_process",
                },
                {
                    "id": "a_power",
                    "kind": "action",
                    "text": power_action,
                    "next": "done",
                },
                {
                    "id": "a_pressure",
                    "kind": "action",
                    "text": pressure_action,
                    "next": "done",
                },
                {
                    "id": "a_process",
                    "kind": "action",
                    "text": process_action,
                    "next": "done",
                },
                {
                    "id": "done",
                    "kind": "final",
                    "text": "Close this session with thumbs up/down and capture workaround if needed.",
                },
            ]

        return {
            "start_node_id": "q1",
            "query_terms": tokenize(question),
            "history_snapshot": {
                key: {"count": value["count"], "support_count": value["support_count"]}
                for key, value in stats.items()
            },
            "nodes": nodes,
        }

    def _history_signal_stats(self, machine_id: int) -> dict[str, dict[str, Any]]:
        complaints = self.repo.list_machine_complaints(machine_id, limit=350)
        if not complaints:
            return {}

        signal_keywords = {
            "power": ["power", "breaker", "trip", "electrical", "voltage", "rf", "current"],
            "pressure": ["pressure", "vacuum", "pump", "chamber"],
            "leak": ["leak", "flow", "gas", "line", "valve"],
            "process": ["recipe", "align", "mask", "wafer", "plasma", "calibration"],
            "thermal": ["temperature", "heater", "hot", "cool", "pyrometer", "thermo"],
        }

        complaint_ids_by_signal: dict[str, set[int]] = {key: set() for key in signal_keywords}
        complaint_ids_by_signal["general"] = set()

        for complaint in complaints:
            complaint_id = complaint.get("complaint_id")
            if not complaint_id:
                continue
            text = str(complaint.get("complaint_description") or "").lower()
            terms = set(tokenize(text))
            matched = False
            for signal, keywords in signal_keywords.items():
                if any(keyword in terms for keyword in keywords):
                    complaint_ids_by_signal[signal].add(int(complaint_id))
                    matched = True
            if matched:
                complaint_ids_by_signal["general"].add(int(complaint_id))

        all_ids: list[int] = sorted(
            {complaint_id for ids in complaint_ids_by_signal.values() for complaint_id in ids}
        )
        events = self.repo.list_trouble_events(all_ids)
        events_by_complaint: dict[int, list[dict[str, Any]]] = {}
        for event in events:
            cid = int(event.get("complaint_id") or 0)
            if cid == 0:
                continue
            events_by_complaint.setdefault(cid, []).append(event)

        out: dict[str, dict[str, Any]] = {}
        for signal, complaint_ids in complaint_ids_by_signal.items():
            action_counter: Counter[str] = Counter()
            for complaint_id in complaint_ids:
                for event in events_by_complaint.get(complaint_id, []):
                    action = str(event.get("action_taken") or "").strip()
                    if not action:
                        continue
                    normalized = _shorten(" ".join(action.split()), 180)
                    if normalized:
                        action_counter[normalized] += 1

            top_action = ""
            support_count = 0
            if action_counter:
                top_action, support_count = action_counter.most_common(1)[0]

            out[signal] = {
                "count": len(complaint_ids),
                "top_action": top_action,
                "support_count": support_count,
            }

        return out

    def _signal_action(self, stats: dict[str, dict[str, Any]], signal: str, fallback: str) -> str:
        signal_stat = stats.get(signal) or {}
        top_action = str(signal_stat.get("top_action") or "").strip()
        support_count = int(signal_stat.get("support_count") or 0)
        if top_action:
            return f"Historical action ({support_count} similar cases): {top_action}"
        return fallback


def _as_record(columns: list[str], row: list[Any]) -> dict[str, Any]:
    return {key: value for key, value in zip_longest(columns, row, fillvalue=None)}


def _safe_int(value: Any, default: int | None = None) -> int | None:
    if value is None:
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _shorten(text: str, max_len: int) -> str:
    if len(text) <= max_len:
        return text
    return text[: max_len - 3].rstrip() + "..."


def _parse_datetime(raw: str) -> datetime | None:
    value = raw.strip()
    if not value:
        return None
    formats = ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d", "%Y-%m-%dT%H:%M:%S")
    for fmt in formats:
        try:
            return datetime.strptime(value, fmt)
        except ValueError:
            continue
    return None


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        return int(raw.strip())
    except ValueError:
        return default


def _utc_now_naive() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _fmt_dt(value: datetime) -> str:
    return value.strftime("%Y-%m-%d %H:%M:%S")


def _hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    iterations = 240000
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    return f"pbkdf2_sha256${iterations}${binascii.hexlify(salt).decode('ascii')}${binascii.hexlify(digest).decode('ascii')}"


def _verify_password(password: str, encoded: str) -> bool:
    try:
        algo, iter_raw, salt_hex, hash_hex = encoded.split("$", 3)
    except ValueError:
        return False
    if algo != "pbkdf2_sha256":
        return False
    try:
        iterations = int(iter_raw)
        salt = binascii.unhexlify(salt_hex.encode("ascii"))
        expected = binascii.unhexlify(hash_hex.encode("ascii"))
    except (ValueError, binascii.Error):
        return False
    computed = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    return hmac.compare_digest(computed, expected)


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()
