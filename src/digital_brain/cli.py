from __future__ import annotations

import argparse
import json
from pathlib import Path

from .api_server import run_server
from .config import DEFAULT_DATA_DIR, DEFAULT_DB_PATH
from .service import DigitalBrainService


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Digital Brain MVP CLI")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB_PATH, help="SQLite database path")

    sub = parser.add_subparsers(dest="command", required=True)

    ingest = sub.add_parser("ingest", help="Ingest SQL and PDF seed data")
    ingest.add_argument("--data-dir", type=Path, default=DEFAULT_DATA_DIR)

    query = sub.add_parser("query", help="Run one machine query")
    query.add_argument("--machine-id", type=int, required=True)
    query.add_argument("--question", type=str, required=True)

    tstart = sub.add_parser("troubleshoot-start", help="Start persistent troubleshooting session")
    tstart.add_argument("--machine-id", type=int, required=True)
    tstart.add_argument("--question", type=str, required=True)

    tnext = sub.add_parser("troubleshoot-next", help="Advance troubleshooting session")
    tnext.add_argument("--session-id", type=str, required=True)
    tnext.add_argument("--response", type=str, required=True, help="yes|no|done")

    tstate = sub.add_parser("troubleshoot-session", help="Get troubleshooting session state")
    tstate.add_argument("--session-id", type=str, required=True)

    sub.add_parser("machines", help="List machine inventory")
    recent = sub.add_parser("recent-machines", help="List recent machine sessions")
    recent.add_argument("--limit", type=int, default=8)
    sub.add_parser("analytics", help="Show admin analytics JSON")

    add_doc = sub.add_parser("realtime-add-document", help="Realtime add/update one PDF document")
    add_doc.add_argument("--path", type=str, required=True)
    add_doc.add_argument("--machine-id", type=int)
    add_doc.add_argument("--doc-type", type=str)

    add_complaint = sub.add_parser("realtime-add-complaint", help="Realtime add/update complaint")
    add_complaint.add_argument("--machine-id", type=int, required=True)
    add_complaint.add_argument("--description", type=str, required=True)
    add_complaint.add_argument("--status", type=int, default=0)
    add_complaint.add_argument("--status-resolved", type=str, default="")
    add_complaint.add_argument("--time-of-complaint", type=str, default="")
    add_complaint.add_argument("--complaint-id", type=int)

    add_event = sub.add_parser("realtime-add-trouble-event", help="Realtime add trouble event")
    add_event.add_argument("--complaint-id", type=int, required=True)
    add_event.add_argument("--action", type=str, required=True)
    add_event.add_argument("--timestamp", type=str, default="")
    add_event.add_argument("--diagnosis", type=str, default="")
    add_event.add_argument("--comments", type=str, default="")

    create_user = sub.add_parser("create-user", help="Create or update auth user")
    create_user.add_argument("--username", type=str, required=True)
    create_user.add_argument("--password", type=str, required=True)
    create_user.add_argument("--role", type=str, required=True, choices=["operator", "admin"])
    create_user.add_argument("--inactive", action="store_true", help="Create user as inactive")
    create_user.add_argument(
        "--upsert",
        action="store_true",
        help="Update existing user by username if present",
    )

    serve = sub.add_parser("serve", help="Run local HTTP server")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8080)

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    service = DigitalBrainService(args.db)

    if args.command == "ingest":
        summary = service.ingest_all(args.data_dir)
        print(json.dumps(summary, indent=2))
        return

    if args.command == "query":
        response = service.query(machine_id=args.machine_id, question=args.question)
        payload = {
            "session_id": response.session_id,
            "answer": response.answer,
            "answer_mode": response.answer_mode,
            "triage": response.triage,
            "confidence_score": response.confidence_score,
            "confidence_label": response.confidence_label,
            "checklist": response.checklist,
            "citations": response.citations,
            "historical_suggestions": response.historical_suggestions,
            "troubleshooting_flow": response.troubleshooting_flow,
        }
        print(json.dumps(payload, indent=2))
        return

    if args.command == "troubleshoot-start":
        payload = service.start_troubleshoot(machine_id=args.machine_id, question=args.question)
        print(json.dumps(payload, indent=2))
        return

    if args.command == "troubleshoot-next":
        payload = service.next_troubleshoot(session_id=args.session_id, response_value=args.response)
        print(json.dumps(payload, indent=2))
        return

    if args.command == "troubleshoot-session":
        payload = service.get_troubleshoot_session(session_id=args.session_id)
        print(json.dumps(payload, indent=2))
        return

    if args.command == "machines":
        print(json.dumps({"machines": service.list_machines()}, indent=2))
        return

    if args.command == "recent-machines":
        print(json.dumps({"recent_machines": service.list_recent_machines(limit=args.limit)}, indent=2))
        return

    if args.command == "analytics":
        print(json.dumps(service.admin_analytics(), indent=2))
        return

    if args.command == "realtime-add-document":
        payload = service.realtime_add_document(
            path=args.path,
            machine_id=args.machine_id,
            doc_type=args.doc_type,
        )
        print(json.dumps(payload, indent=2))
        return

    if args.command == "realtime-add-complaint":
        payload = service.realtime_upsert_complaint(
            {
                "complaint_id": args.complaint_id,
                "machine_id": args.machine_id,
                "complaint_description": args.description,
                "time_of_complaint": args.time_of_complaint,
                "status": args.status,
                "status_resolved": args.status_resolved,
            }
        )
        print(json.dumps(payload, indent=2))
        return

    if args.command == "realtime-add-trouble-event":
        payload = service.realtime_add_trouble_event(
            {
                "complaint_id": args.complaint_id,
                "timestamp": args.timestamp,
                "diagnosis": args.diagnosis,
                "action_taken": args.action,
                "comments": args.comments,
            }
        )
        print(json.dumps(payload, indent=2))
        return

    if args.command == "create-user":
        payload = service.create_user(
            username=args.username,
            password=args.password,
            role=args.role,
            is_active=not args.inactive,
            upsert=args.upsert,
        )
        print(json.dumps(payload, indent=2))
        return

    if args.command == "serve":
        run_server(service=service, host=args.host, port=args.port)
        return


if __name__ == "__main__":
    main()
