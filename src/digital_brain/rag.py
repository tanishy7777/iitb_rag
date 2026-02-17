from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from typing import Any


class RagSynthesizer:
    def __init__(self) -> None:
        self.provider = os.getenv("DIGITAL_BRAIN_LLM_PROVIDER", "ollama").strip().lower()
        self.openai_api_key = os.getenv("OPENAI_API_KEY", "").strip()
        self.openai_model = os.getenv("DIGITAL_BRAIN_OPENAI_MODEL", "gpt-4.1-mini").strip()
        self.ollama_model = os.getenv("DIGITAL_BRAIN_OLLAMA_MODEL", "llama3").strip()
        self.ollama_base_url = os.getenv("DIGITAL_BRAIN_OLLAMA_BASE_URL", "http://127.0.0.1:11434").strip()
        self.timeout_s = float(os.getenv("DIGITAL_BRAIN_LLM_TIMEOUT_SEC", "20"))

    def synthesize(self, payload: dict[str, Any]) -> tuple[str, dict[str, Any]]:
        if self.provider == "ollama":
            try:
                answer = self._ollama_generate(payload)
                return answer, {"mode": "llm_ollama", "provider": "ollama", "model": self.ollama_model}
            except Exception as exc:  # noqa: BLE001
                fallback = self._deterministic(payload)
                return fallback, {"mode": "deterministic_fallback", "error": str(exc)}

        if self.provider == "openai" and self.openai_api_key:
            try:
                answer = self._openai_chat(payload)
                return answer, {"mode": "llm_openai", "provider": "openai", "model": self.openai_model}
            except Exception as exc:  # noqa: BLE001
                fallback = self._deterministic(payload)
                return fallback, {"mode": "deterministic_fallback", "error": str(exc)}

        return self._deterministic(payload), {"mode": "deterministic", "provider": "none"}

    def synthesize_flow(self, payload: dict[str, Any]) -> tuple[dict[str, Any] | None, dict[str, Any]]:
        if self.provider == "ollama":
            try:
                out = self._ollama_generate_flow(payload)
                return out, {"mode": "llm_ollama_flow", "provider": "ollama", "model": self.ollama_model}
            except Exception as exc:  # noqa: BLE001
                return None, {"mode": "flow_unavailable", "error": str(exc)}

        if self.provider == "openai" and self.openai_api_key:
            try:
                out = self._openai_flow(payload)
                return out, {"mode": "llm_openai_flow", "provider": "openai", "model": self.openai_model}
            except Exception as exc:  # noqa: BLE001
                return None, {"mode": "flow_unavailable", "error": str(exc)}

        return None, {"mode": "flow_unavailable", "provider": "none"}

    def _ollama_generate(self, payload: dict[str, Any]) -> str:
        prompt = self._build_prompt(payload)
        req_body = {
            "model": self.ollama_model,
            "prompt": prompt,
            "stream": False,
            "options": {"temperature": 0.1},
        }
        data = json.dumps(req_body).encode("utf-8")
        req = urllib.request.Request(
            self.ollama_base_url.rstrip("/") + "/api/generate",
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout_s) as resp:
                raw = resp.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="ignore")
            raise RuntimeError(f"Ollama HTTP {exc.code}: {detail[:300]}") from exc

        parsed = json.loads(raw)
        answer = str(parsed.get("response") or "").strip()
        if not answer:
            raise RuntimeError("Ollama response is empty")
        return answer

    def _deterministic(self, payload: dict[str, Any]) -> str:
        machine_id = payload.get("machine_id")
        triage = payload.get("triage")
        lines = [
            f"Machine {machine_id} triage category: {triage}.",
            "Use the checklist below and verify each step before moving forward.",
        ]

        citations = payload.get("citations") or []
        if citations:
            lines.append("Manual context:")
            for citation in citations:
                lines.append(f"- {citation.get('snippet', '')}")
        else:
            lines.append("No direct manual snippet matched this query. Use historical fixes and operator checklist.")

        suggestions = payload.get("historical_suggestions") or []
        if suggestions:
            lines.append("Historically effective actions:")
            for item in suggestions:
                lines.append(f"- {item.get('action', '')} (seen {item.get('support_count', 0)} times)")

        confidence_label = str(payload.get("confidence_label") or "unknown")
        lines.append(f"Evidence confidence: {confidence_label}.")
        lines.append("Dynamic yes/no flow generated from machine-specific complaint history.")
        return "\n".join(lines)

    def _ollama_generate_flow(self, payload: dict[str, Any]) -> dict[str, Any]:
        prompt = self._build_flow_prompt(payload)
        req_body = {
            "model": self.ollama_model,
            "prompt": prompt,
            "stream": False,
            "options": {"temperature": 0.1},
        }
        data = json.dumps(req_body).encode("utf-8")
        req = urllib.request.Request(
            self.ollama_base_url.rstrip("/") + "/api/generate",
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout_s) as resp:
                raw = resp.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="ignore")
            raise RuntimeError(f"Ollama HTTP {exc.code}: {detail[:300]}") from exc

        parsed = json.loads(raw)
        content = str(parsed.get("response") or "").strip()
        if not content:
            raise RuntimeError("Ollama flow response is empty")
        flow = _extract_json_object(content)
        if not isinstance(flow, dict):
            raise RuntimeError("Ollama flow response is not a JSON object")
        return flow

    def _openai_chat(self, payload: dict[str, Any]) -> str:
        prompt = self._build_prompt(payload)
        req_body = {
            "model": self.openai_model,
            "temperature": 0.1,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "You are an industrial troubleshooting assistant. "
                        "Answer only from provided evidence. "
                        "If evidence is insufficient, clearly say so. "
                        "Do not invent details. Keep answers concise and actionable."
                    ),
                },
                {"role": "user", "content": prompt},
            ],
        }
        data = json.dumps(req_body).encode("utf-8")
        req = urllib.request.Request(
            "https://api.openai.com/v1/chat/completions",
            data=data,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.openai_api_key}",
            },
            method="POST",
        )

        try:
            with urllib.request.urlopen(req, timeout=self.timeout_s) as resp:
                raw = resp.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="ignore")
            raise RuntimeError(f"OpenAI HTTP {exc.code}: {detail[:400]}") from exc

        parsed = json.loads(raw)
        choices = parsed.get("choices") or []
        if not choices:
            raise RuntimeError("OpenAI response missing choices")
        content = ((choices[0] or {}).get("message") or {}).get("content")
        if not content:
            raise RuntimeError("OpenAI response missing content")
        return str(content).strip()

    def _openai_flow(self, payload: dict[str, Any]) -> dict[str, Any]:
        prompt = self._build_flow_prompt(payload)
        req_body = {
            "model": self.openai_model,
            "temperature": 0.1,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "You generate troubleshooting flow JSON only. "
                        "No markdown, no explanations, only valid JSON object."
                    ),
                },
                {"role": "user", "content": prompt},
            ],
        }
        data = json.dumps(req_body).encode("utf-8")
        req = urllib.request.Request(
            "https://api.openai.com/v1/chat/completions",
            data=data,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.openai_api_key}",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout_s) as resp:
                raw = resp.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="ignore")
            raise RuntimeError(f"OpenAI HTTP {exc.code}: {detail[:400]}") from exc

        parsed = json.loads(raw)
        choices = parsed.get("choices") or []
        if not choices:
            raise RuntimeError("OpenAI flow response missing choices")
        content = ((choices[0] or {}).get("message") or {}).get("content")
        if not content:
            raise RuntimeError("OpenAI flow response missing content")
        flow = _extract_json_object(str(content))
        if not isinstance(flow, dict):
            raise RuntimeError("OpenAI flow response is not a JSON object")
        return flow

    def _build_prompt(self, payload: dict[str, Any]) -> str:
        machine_id = payload.get("machine_id")
        question = payload.get("question")
        triage = payload.get("triage")
        checklist = payload.get("checklist") or []
        citations = payload.get("citations") or []
        suggestions = payload.get("historical_suggestions") or []
        confidence_label = payload.get("confidence_label")

        lines: list[str] = []
        lines.append(f"Machine ID: {machine_id}")
        lines.append(f"Issue: {question}")
        lines.append(f"Triage: {triage}")
        lines.append(f"Confidence: {confidence_label}")
        lines.append("Checklist:")
        for step in checklist:
            lines.append(f"- {step}")

        lines.append("Manual Evidence (with source path):")
        for citation in citations:
            lines.append(
                f"- [{citation.get('doc_type')}] {citation.get('path')}: {citation.get('snippet')}"
            )

        lines.append("Historical Evidence:")
        for item in suggestions:
            lines.append(f"- {item.get('action')} (support={item.get('support_count')})")

        lines.append(
            "Produce: (1) short actionable answer, (2) manual-vs-history guidance, "
            "(3) explicit caution if evidence is weak."
        )
        return "\n".join(lines)

    def _build_flow_prompt(self, payload: dict[str, Any]) -> str:
        machine_id = payload.get("machine_id")
        question = payload.get("question")
        triage = payload.get("triage")
        checklist = payload.get("checklist") or []
        citations = payload.get("citations") or []
        suggestions = payload.get("historical_suggestions") or []

        lines: list[str] = []
        lines.append("Build an interactive troubleshooting flow in JSON.")
        lines.append(f"Machine ID: {machine_id}")
        lines.append(f"Issue: {question}")
        lines.append(f"Triage: {triage}")
        lines.append("Checklist:")
        for step in checklist:
            lines.append(f"- {step}")
        lines.append("Manual evidence:")
        for citation in citations[:3]:
            lines.append(f"- {citation.get('snippet')}")
        lines.append("Historical suggestions:")
        for item in suggestions[:3]:
            lines.append(f"- {item.get('action')} (support={item.get('support_count')})")
        lines.append(
            "Return ONLY JSON object with fields: "
            "start_node_id, nodes. "
            "Each node has id, kind(question|action|final), text, and transitions. "
            "question nodes require yes/no; action nodes require next; final nodes have no transitions. "
            "Use 4-8 nodes max."
        )
        return "\n".join(lines)


def _extract_json_object(text: str) -> dict[str, Any] | None:
    candidate = text.strip()
    if candidate.startswith("{") and candidate.endswith("}"):
        try:
            parsed = json.loads(candidate)
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            pass

    start = candidate.find("{")
    end = candidate.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return None
    snippet = candidate[start : end + 1]
    try:
        parsed = json.loads(snippet)
    except json.JSONDecodeError:
        return None
    if isinstance(parsed, dict):
        return parsed
    return None
