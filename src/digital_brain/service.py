from __future__ import annotations

import json
import uuid
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
from itertools import zip_longest
from pathlib import Path
from typing import Any

from .chunking import TextChunk, build_chunks
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
        flow = self._build_dynamic_flow(machine_id, question, triage)
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

    def admin_analytics(self) -> dict[str, Any]:
        analytics = self.repo.admin_analytics()
        analytics["knowledge_gaps"] = self._knowledge_gap_clusters(analytics)
        return analytics

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
    formats = ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d")
    for fmt in formats:
        try:
            return datetime.strptime(value, fmt)
        except ValueError:
            continue
    return None
