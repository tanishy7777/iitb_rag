from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from digital_brain.service import DigitalBrainService


class ServiceSmokeTest(unittest.TestCase):
    def test_ingest_and_query(self) -> None:
        project_root = Path(__file__).resolve().parents[1]
        data_dir = project_root / "data"

        with TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "brain.db"
            service = DigitalBrainService(db_path)
            summary = service.ingest_all(data_dir)

            self.assertGreater(summary["machines"], 100)
            self.assertGreater(summary["complaints"], 1000)
            self.assertGreater(summary["documents"], 0)
            self.assertGreater(summary["chunks"], 0)

            response = service.query(machine_id=7, question="vacuum pressure leak in RTP")
            self.assertEqual(response.machine_id, 7)
            self.assertTrue(response.answer)
            self.assertTrue(response.checklist)
            self.assertTrue(response.answer_mode)
            self.assertGreaterEqual(response.confidence_score, 0.0)
            self.assertIn("start_node_id", response.troubleshooting_flow)
            self.assertIn("nodes", response.troubleshooting_flow)
            self.assertGreater(len(response.troubleshooting_flow["nodes"]), 3)

            low_conf = service.query(machine_id=7, question="zzzxqv prblm unknwn 918273645")
            self.assertEqual(low_conf.confidence_label, "low")
            self.assertIn("Insufficient strong evidence", low_conf.answer)

            started = service.start_troubleshoot(
                machine_id=7,
                question="vacuum pressure leak in RTP",
            )
            self.assertIn("session_id", started)
            self.assertIn("current_node", started)
            self.assertFalse(started["is_closed"])

            current_kind = started["current_node"].get("kind")
            step_response = "yes" if current_kind == "question" else "done"
            advanced = service.next_troubleshoot(started["session_id"], step_response)
            self.assertIn("current_node", advanced)

            recent = service.list_recent_machines(limit=5)
            self.assertTrue(recent)

            rt = service.realtime_upsert_complaint(
                {
                    "machine_id": 7,
                    "complaint_description": "Realtime test complaint for fuse replacement",
                    "status": 2,
                    "time_of_complaint": "2026-02-17 10:00:00",
                }
            )
            self.assertIn("complaint_id", rt)
            cid = int(rt["complaint_id"])
            service.realtime_add_trouble_event(
                {
                    "complaint_id": cid,
                    "action_taken": "Replaced fuse and restored power.",
                    "diagnosis": "Fuse failure",
                    "timestamp": "2026-02-17 10:05:00",
                    "comments": "Realtime inserted event",
                }
            )
            boosted = service.query(machine_id=7, question="fuse replacement power issue")
            self.assertTrue(boosted.historical_suggestions)

            service.submit_feedback(
                session_id=started["session_id"],
                machine_id=7,
                issue="power issue fuse",
                helpful=True,
                workaround="Use spare fuse 2A from rack and restart controller",
            )
            from_feedback = service.query(machine_id=7, question="fuse controller restart")
            self.assertTrue(from_feedback.historical_suggestions)

            analytics = service.admin_analytics()
            self.assertIn("knowledge_gaps", analytics)


if __name__ == "__main__":
    unittest.main()
