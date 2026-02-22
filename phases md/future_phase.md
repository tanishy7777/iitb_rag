Next:
• 1. Stabilize this React cutover

  - Run frontend build/test in your local env (npm install, npm run build), fix any runtime/UI regressions.
  - Add frontend smoke tests for /login, /operator, /admin, filters/tabs, and auth redirects.

  2. Add backend tests for new analytics filters

  - Cover /api/admin/analytics filter combinations (machine_id, category, date_from, date_to).
  - Add negative tests for invalid date formats/ranges.

  3. Security hardening (next major feature)

  - Implement password reset + rotation policy.
  - Add account lifecycle controls (lock/disable/force reset/unlock) end-to-end.

  4. Retrieval upgrade

  - Implement hybrid retrieval (BM25 + vector) with configurable weights and fallback.
  - Add retrieval debug metadata + relevance evaluation set.

  5. Operational readiness

  - Add metrics/audit views for fallback rate, latency, confidence distribution, and flow mode usage.
  - Add deployment/runbook docs for review/demo environments.



Next (found):
ok so I tried the operator ui and I asked about vacuum pressure leak gas flow issue in machineid: 1 DSA
  machine, got a confidence score 0.641. Went through the interactive troubleshooting flow. And clicked
  thumbs up on did it fix it? Now what all is getting updateed? I ran the same query again, got the same
  confidence score (shldnt it increase since similar query previously fixed it), update the historical
  suggestions section? If the issue got reesolved is it not being shown in the analytics panel? if not then
  why is this a design choice?


  What got updated when you clicked thumbs-up:

  - feedback table got a new row:
      - machine_id=1
      - issue='vacuum pressure leak gas flow issue'
      - helpful=1
      - workaround='' (empty)
      - created_at='2026-02-18 06:25:18'
  - audit_logs got a feedback event with workaround_present=false.
  - Your troubleshoot session/events were already updated during flow steps in:
      - troubleshoot_sessions
      - troubleshoot_events

  Why confidence stayed 0.641:

  - Confidence formula is fixed in src/digital_brain/service.py:729.
  - It depends on:
      - citation BM25 score
      - score separation
      - history signal from historical_suggestions
  - Your latest thumbs-up had no workaround text. In code, helpful feedback is only added to suggestions if
    helpful=1 AND workaround is non-empty (src/digital_brain/service.py:1015 to src/digital_brain/
    service.py:1021).
  - Also, for your query, history_signal is already saturated at 1.0 (max), so even more history would not
    raise confidence further.
  - I reproduced your query; it still computes to 0.641 from unchanged citation signals + maxed history
    signal.

  Historical suggestions update behavior:

  - Yes, they can update, but only from:
      1. complaint/trouble history, and
      2. helpful feedback with non-empty workaround and term overlap.
  - So thumbs-up alone (no workaround) does not enrich the suggestions list.

  Why “resolved” may not appear in analytics:

  - “Unresolved Issues” panel is based on complaints.status != 2 (src/digital_brain/repository.py:803+713).
  - Submitting feedback does not change complaint status (submit_feedback only inserts into feedback).
  - This is a deliberate separation:
      - feedback = “assistant answer quality”
      - complaint status = “incident lifecycle truth”
  - So auto-closing complaints from thumbs-up is intentionally avoided to prevent false resolution reporting.

  Where your thumbs-up is visible in analytics:

  - It appears in feedback_summary (helpful/not helpful counts), not unresolved list.
  - “At-Risk Queue” shows only failed feedback (helpful=0), so thumbs-up won’t show there.

  If you want, I can implement the behavior you expected:

  1. Option A: allow helpful feedback (even without workaround) to boost history/confidence.
  2. Option B: when flow is closed + thumbs-up, auto-mark or suggest marking related complaint as resolved.
  3. Option C: add a new analytics card: “Resolved by assistant feedback” separate from complaint status.

• Next phase is production hardening + pilot readiness.

  1. Enterprise Auth Hardening

  - Password reset/rotation policy
  - Account lifecycle controls
  - Optional SSO integration
  - Session security tuning and admin audit reports

  2. Scale the Data/RAG Layer

  - Move from SQLite to Postgres
  - Add hybrid retrieval (BM25 + vector)
  - Background async ingest workers for realtime data growth

  3. Observability + Reliability

  - Metrics dashboard: latency, fallback rates, confidence distribution,
    flow-mode distribution
  - Structured error tracking and alerting
  - Basic load/concurrency validation

  4. Grounding Quality Guardrails

  - Stronger citation-to-answer checks
  - Flow validation telemetry and failure analysis
  - Better semantic clustering for knowledge gaps

  5. Pilot UAT

  - Run defined operator scenarios
  - Measure time-to-diagnose and resolution success
  - Tune ranking/flows from pilot feedback

  If you want, I can convert this into a concrete Day 1-10 execution plan
  with deliverables and exit criteria next.


› Lets do this Password reset/rotation policy, Account lifecycle controls,
  Add hybrid retrieval (BM25 + vector). Create a plan first


• Plan: Security + Lifecycle + Hybrid Retrieval (10 working days)

  ## 1. Scope Lock and Design (Day 1)

  1. Freeze requirements for:

  - Password reset
  - Password rotation policy
  - Account lifecycle controls
  - Hybrid retrieval scoring behavior

  2. Define policy defaults:

  - Password max age (for example 90 days)
  - Reset token expiry (for example 15 minutes)
  - Lockout threshold (for example 5 failed attempts)
  - Roles allowed to manage users

  3. Finalize hybrid ranking formula:

  - final_score = w_bm25 * bm25 + w_vec * cosine + bonuses

  Exit criteria: signed-off policy/config defaults and scoring formula.

  ## 2. Password Reset + Rotation (Days 2-4)

  1. DB/schema additions:

  - password_resets (token hash, user_id, expires_at, used_at)
  - users additions: password_changed_at, must_change_password,
    failed_login_attempts, locked_until

  2. Auth service updates:

  - Request reset token
  - Confirm reset token + set new password
  - Enforce max password age and must_change_password
  - Enforce lockout/backoff on repeated failed login

  3. API endpoints:

  - POST /api/auth/request-reset
  - POST /api/auth/confirm-reset
  - POST /api/auth/change-password

  4. Admin controls:

  - Force password reset
  - Unlock account

  Exit criteria: reset + rotation fully enforced in backend, audited, and
  test-covered.

  ## 3. Account Lifecycle Controls (Days 5-6)

  1. Lifecycle states and transitions:

  - Active
  - Locked (temporary)
  - Disabled (admin)
  - Soft-deleted (optional)

  2. Admin user-management expansion:

  - Disable/enable account
  - Lock/unlock account
  - Force reset/must-change-password
  - Preserve “cannot remove last active admin” safeguard

  3. Audit log events:

  - auth_reset_requested, auth_reset_completed
  - auth_account_locked, auth_account_unlocked
  - auth_account_disabled, auth_password_forced_reset

  Exit criteria: lifecycle transitions work end-to-end in admin UI/API.

  ## 4. Hybrid Retrieval (BM25 + Vector) (Days 7-9)

  1. Vector index pipeline:

  - Generate embeddings for chunks (local embedding model)
  - Store vectors + metadata
  - Rebuild/incremental update on ingest/realtime document add

  2. Query-time hybrid retrieval:

  - BM25 top-k
  - Vector top-k
  - Normalize and fuse with weighted score
  - Dedupe by chunk id

  3. Response observability:

  - Include retrieval breakdown in debug/audit metadata:
      - bm25 rank/score
      - vector score
      - fused score

  4. Config flags:

  - DIGITAL_BRAIN_RETRIEVAL_MODE (bm25|vector|hybrid)
  - Weight knobs and top-k knobs

  Exit criteria: hybrid mode improves relevance on benchmark queries and can
  be toggled safely.

  ## 5. Validation, Docs, and Rollout (Day 10)

  1. Tests:

  - Auth reset/rotation/lifecycle tests
  - Hybrid retrieval unit + smoke tests

  2. Docs:

  - API changes
  - Admin runbook
  - Security policy config
  - Retrieval tuning guide

  3. Migration + rollout:

  - Backfill script for password fields and embeddings
  - Safe fallback to BM25 if vector model/index unavailable

  Exit criteria: all tests pass, docs updated, feature flags allow staged
  rollout.