from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from digital_brain.service import DigitalBrainService


class HybridFlowTest(unittest.TestCase):
    def _seed_minimal(self, service: DigitalBrainService) -> None:
        service.repo.replace_machines(
            [
                {
                    "machine_id": 7,
                    "name": "Demo Tool",
                    "category": "Etching",
                    "location": "Lab-1",
                    "tool_sop": None,
                    "policy_documents": None,
                    "standard_recipies": None,
                    "manual_ref": None,
                }
            ]
        )
        service.repo.replace_documents(
            [
                {
                    "doc_id": "demo_manual",
                    "machine_id": 7,
                    "doc_type": "manual",
                    "path": "data/demo_manual.pdf",
                    "text": "Check interlock and breaker before restart.",
                }
            ]
        )
        service.repo.replace_chunks(
            [
                {
                    "chunk_id": "demo_chunk_1",
                    "doc_id": "demo_manual",
                    "machine_id": 7,
                    "doc_type": "manual",
                    "text": "Check interlock and breaker before restart.",
                }
            ]
        )
        service.retriever = service._build_retriever()

    def test_valid_llm_flow_is_used(self) -> None:
        with TemporaryDirectory() as tmp:
            service = DigitalBrainService(Path(tmp) / "brain.db")
            self._seed_minimal(service)
            service._must_fallback = lambda citations, score: False  # type: ignore[method-assign]
            service.synthesizer.synthesize = lambda payload: ("LLM answer", {"mode": "llm_ollama"})  # type: ignore[method-assign]
            service.synthesizer.synthesize_flow = (  # type: ignore[method-assign]
                lambda payload: (
                    {
                        "start_node_id": "q1",
                        "nodes": [
                            {"id": "q1", "kind": "question", "text": "Is breaker healthy?", "yes": "a1", "no": "a2"},
                            {"id": "a1", "kind": "action", "text": "Run controlled restart.", "next": "done"},
                            {"id": "a2", "kind": "action", "text": "Reset interlock chain.", "next": "done"},
                            {"id": "done", "kind": "final", "text": "Submit thumbs and workaround."},
                        ],
                    },
                    {"mode": "llm_ollama_flow"},
                )
            )

            response = service.query(machine_id=7, question="breaker interlock issue")
            self.assertEqual(response.answer_mode, "llm_ollama")
            self.assertEqual(response.troubleshooting_flow.get("flow_mode"), "llm_assisted")
            self.assertEqual(response.troubleshooting_flow.get("start_node_id"), "q1")
            self.assertGreaterEqual(len(response.troubleshooting_flow.get("nodes") or []), 3)

    def test_invalid_llm_flow_falls_back(self) -> None:
        with TemporaryDirectory() as tmp:
            service = DigitalBrainService(Path(tmp) / "brain.db")
            self._seed_minimal(service)
            service._must_fallback = lambda citations, score: False  # type: ignore[method-assign]
            service.synthesizer.synthesize = lambda payload: ("LLM answer", {"mode": "llm_ollama"})  # type: ignore[method-assign]
            service.synthesizer.synthesize_flow = (  # type: ignore[method-assign]
                lambda payload: (
                    {
                        "start_node_id": "q1",
                        "nodes": [
                            {"id": "q1", "kind": "question", "text": "Incomplete flow"},
                        ],
                    },
                    {"mode": "llm_ollama_flow"},
                )
            )

            response = service.query(machine_id=7, question="breaker interlock issue")
            self.assertEqual(response.answer_mode, "llm_ollama")
            self.assertEqual(response.troubleshooting_flow.get("flow_mode"), "deterministic_fallback")
            self.assertIn("flow_reason", response.troubleshooting_flow)
            self.assertEqual(response.troubleshooting_flow.get("start_node_id"), "q1")


if __name__ == "__main__":
    unittest.main()
