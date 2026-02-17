  Data Analysis (based on uploaded subset)

  - Corpus is sufficient for an end-to-end MVP: 4 PDFs + 6 SQL dumps.
  - PDFs are usable and scoped: data/1_POLICY.pdf (2 pages), data/1_SOP.pdf (13), data/3_RECEPIES.pdf (5),
    data/7_manuals.pdf (112).
  - Machine-document linkage exists in data/eqp-process_resources.sql:99 (machine 1 -> SOP/Policy), data/eqp-
    process_resources.sql:100 (machine 3 -> recipes), data/eqp-process_resources.sql:101 (machine 7 -> manual
    reference).
  - Historical troubleshooting signal is strong: equipment_complaint (~3423 rows) and trouble_track (~5890
    rows).
  - Existing data already supports learning loop bootstrap:
      - machine_id=1: 60 complaints, 111 trouble updates
      - machine_id=3: 36 complaints, 69 trouble updates
      - machine_id=7: 48 complaints, 70 trouble updates
  - Data caveats to handle in MVP:
      - Many complaints with machine_id=0 (generic tasks), so filter/exclude for machine-grounded diagnosis.
      - Mixed date quality and legacy MySQL dump formatting; treat some fields as strings initially.

  Replanned MVP (end-to-end first, data-minimal)

  1. Operator can pick a machine, ask issue in plain language, and get grounded answer from available PDFs.
  2. Operator gets guided yes/no troubleshooting steps.
  3. Operator submits “Did this work?” + optional workaround comment.
  4. System shows “manual suggestion + historically successful actions” from complaint/trouble history.
  5. Admin sees top breakdowns and unresolved/open items.

  Scope for This Phase

  - In scope:
      - Machine-centric RAG for machines 1, 3, 7
      - Complaint/trouble history retrieval and ranking
      - Feedback capture and reuse
      - Admin dashboard basics
  - Deferred:
      - FullAnalysis of Uploaded Seed Data

  1. PDFs are sufficient for a meaningful MVP RAG corpus now: data/1_SOP.pdf (13 pages), data/1_POLICY.pdf (2
     pages), data/3_RECEPIES.pdf (5 pages), data/7_manuals.pdf (112 pages).
  2. SQL dumps already give strong historical signal for the learning loop:
      - data/eqp-process_resources.sql: machine master (resources) with SOP/policy/recipe/manual path fields.
      - data/equipment_complaint.sql: complaint events (equipment_complaint), ~3.4k rows.
      - data/trouble_track.sql: troubleshooting actions (trouble_track), ~5.9k rows.
      - data/facility_resources.sql, data/safety_resources.sql, data/lab_incharge.sql: contextual inventory
        and lab ownership.
  3. Key relationship for end-to-end:
      - equipment_complaint.machine_id -> resources.machid
      - trouble_track.complaint_id -> equipment_complaint.complaint_id
  4. Your uploaded docs align with active machines that already have history:
      - Machine 1: ~60 complaints, ~111 trouble-track entries.
      - Machine 3: ~36 complaints, ~69 trouble-track entries.
      - Machine 7: ~48 complaints, ~70 trouble-track entries.
  5. Data quality issues to handle in code (not manual cleanup):
      - Legacy/invalid date formats (example patterns like YYYY-DD-MM in some rows).
      - Many machine_id=0 complaints (general tasks, not tool-specific).
      - Path references in SQL are logical (SOP/1_SOP.pdf) and need mapping to uploaded files in data/.

  Replan (End-to-End First, Data Engineering Light)
  
  1. Phase 1: Thin Vertical Slice (Days 1-3)
      - Ingest the 4 PDFs into chunked vector index with citations.
      - Load SQL dumps into canonical app tables (machines, complaints, trouble_events) via tolerant parser.
      - Build one working query flow: machine selection -> ask issue -> grounded answer + relevant historical
        fixes.
      - Exit criteria: single API and minimal UI can answer and cite sources.
  2. Phase 2: Operator Workflow MVP (Days 4-7)
      - Home view: search, quick machine picker, recent machines.
      - Diagnosis view: triage chips (Power, Hydraulics, Tooling), checklist-style step flow, yes/no
        branching.
      - Session close: Did this fix it? thumbs up/down + workaround comment.
      - Exit criteria: complete repair session can be executed and stored.
  3. Phase 3: Learning Loop from Existing History (Days 8-10)
      - Seed “workaround memory” from equipment_complaint + trouble_track.
      - Rank recommendations by relevance + prior resolution patterns.
      - Show dual guidance: “Manual says X” and “Historically worked: Y”.
      - Exit criteria: answers include manual evidence plus historical suggestion with traceability.
  4. Phase 4: Admin Dashboard MVP (Days 11-13)
      - Breakdown analytics by machine/category/time.
      - Unresolved/at-risk queue from open complaints and failed feedback.
      - Knowledge-gap panel for topics with repeated failures.
      - Exit criteria: management can see top failures and unresolved patterns.
  5. Phase 5: Hardening (Days 14-15)
      - Add confidence gating, citation requirement, and audit logs.
      - Basic test coverage for ingest, retrieval, checklist routing, feedback persistence.
      - Exit criteria: demo-ready end-to-end stability.