
  1. Input data files in data/ (SQL dumps + PDFs)
  2. App database (.state/digital_brain.db) where the app stores everything in a cleaner structure

  The app DB schema is in src/digital_brain/repository.py:8.

  Big Picture

  - machines, complaints, trouble_events come from SQL dump files.
  - documents and chunks come from PDFs.
  - Everything else is app-generated while users interact (sessions, logs, feedback, auth).

  ———

  Core Data Tables (knowledge + history)

  - machines
    One row per machine/tool.
    Key: machine_id
    Used as the main anchor for troubleshooting.
  - complaints
    Historical issues reported for a machine.
    Important field: machine_id (links complaint to machine).
  - trouble_events
    Actions/diagnosis taken for a complaint over time.
    Important field: complaint_id (links to complaints).
  - documents
    Raw text extracted from PDFs (manuals/SOP/policy/recipes).
    Fields include doc_id, machine_id, doc_type, path, text.
  - chunks
    Smaller text pieces split from documents.text for retrieval/search.
    Fields include chunk_id, doc_id, machine_id, doc_type, text.

  How these connect logically:

  - machines.machine_id -> complaints.machine_id
  - complaints.complaint_id -> trouble_events.complaint_id
  - documents.doc_id -> chunks.doc_id
  - chunks are searched by BM25 to produce citations (src/digital_brain/retrieval.py:30)

  ———

  Interaction Tables (created during runtime)

  - troubleshoot_sessions
    Stores one active troubleshooting flow for a user query.
  - troubleshoot_events
    Stores each step/answer inside a session (yes/no/done transitions).
  - feedback
    Thumbs up/down + workaround text after response quality.
  - recent_machine_access
    Recent machines queried, for quick UI/API access.
  - audit_logs
    Event log for important actions (query, login, realtime ingest, etc.).
  - users, auth_sessions
    Login + role handling (operator/admin) when auth is enabled.

  ———

  How data moves (step-by-step)

  1. Ingest

  - ingest_all() reads SQL dumps and PDFs: src/digital_brain/service.py:261
  - Writes:
      - SQL-derived -> machines, complaints, trouble_events
      - PDF-derived -> documents, then split into chunks
  - Rebuilds in-memory retriever from chunks: src/digital_brain/service.py:821

  2. Query

  - User asks question for a machine.
  - App searches chunks with BM25 (retriever.search(...)): src/digital_brain/service.py:534
  - Top results become citations/snippets (from documents path info).
  - App also pulls historical suggestions from complaints + trouble_events.
  - Final response is generated, then session/audit info is stored.

  3. Troubleshooting session

  - troubleshoot_sessions stores the flow JSON and current node.
  - Each user response creates a row in troubleshoot_events.
  - Session updates until final node/closed.

  4. Realtime updates

  - New PDF -> documents upsert -> chunks replaced for that doc -> retriever rebuilt.
  - New complaint/trouble event inserted and immediately influences future ranking.


erDiagram
      MACHINES {
          int machine_id PK
          string name
          string category
          string location
          string tool_sop
          string policy_documents
          string standard_recipies
          string manual_ref
      }

      COMPLAINTS {
          int complaint_id PK
          int machine_id
          string complaint_description
          string time_of_complaint
          int status
          string status_resolved
      }

      TROUBLE_EVENTS {
          int id PK
          int complaint_id
          string timestamp
          string diagnosis
          string action_taken
          string comments
      }

      DOCUMENTS {
          string doc_id PK
          int machine_id
          string doc_type
          string path
          string text
      }

      CHUNKS {
          string chunk_id PK
          string doc_id
          int machine_id
          string doc_type
          string text
      }

      TROUBLESHOOT_SESSIONS {
          string session_id PK
          int machine_id
          string question
          string triage
          string flow_json
          string current_node_id
          int is_closed
          string created_at
          string updated_at
      }

      TROUBLESHOOT_EVENTS {
          int id PK
          string session_id
          string node_id
          string response
          string next_node_id
          string created_at
      }

      FEEDBACK {
          int id PK
          string session_id
          int machine_id
          string issue
          int helpful
          string workaround
          string created_at
      }

      RECENT_MACHINE_ACCESS {
          int id PK
          int machine_id
          string issue
          string session_id
          string created_at
      }

      AUDIT_LOGS {
          int id PK
          string event_type
          string payload_json
          string created_at
      }

      USERS {
          int id PK
          string username
          string password_hash
          string role
          int is_active
          string created_at
      }

      AUTH_SESSIONS {
          string session_id PK
          int user_id
          string token_hash
          string expires_at
          string created_at
          string last_seen_at
      }

      MACHINES ||--o{ COMPLAINTS : "has complaints"
      COMPLAINTS ||--o{ TROUBLE_EVENTS : "has troubleshooting history"

      MACHINES ||--o{ DOCUMENTS : "has docs"
      DOCUMENTS ||--o{ CHUNKS : "split into"

      MACHINES ||--o{ TROUBLESHOOT_SESSIONS : "queried in session"
      TROUBLESHOOT_SESSIONS ||--o{ TROUBLESHOOT_EVENTS : "step events"

      MACHINES ||--o{ FEEDBACK : "feedback on machine query"
      TROUBLESHOOT_SESSIONS ||--o{ FEEDBACK : "optional link by session_id"

      MACHINES ||--o{ RECENT_MACHINE_ACCESS : "recent usage"

      USERS ||--o{ AUTH_SESSIONS : "login sessions"

      AUDIT_LOGS }o--o{ MACHINES : "event payload may reference"
      AUDIT_LOGS }o--o{ USERS : "event payload may reference"
      AUDIT_LOGS }o--o{ TROUBLESHOOT_SESSIONS : "event payload may reference"