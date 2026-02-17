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
