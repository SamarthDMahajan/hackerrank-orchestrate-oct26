# INTERVIEW.md — Architectural & Design Decisions

This document tracks every key design decision implemented in the deletion-audit agent, along with its rationale and the exact `file:function` where it is implemented.

---

### Decision 1: Temporal Cutoff Enforcement for Identity Replay
- **Rationale**: Any identity changes occurring after `audit_at` represent future state and must not bleed into pre-audit identity resolution. Conversely, changes occurring at or before `audit_at` provide valid historical identifiers.
- **Implementation**: [`code/identity.py:IdentityManager.resolve`](file:///c:/Users/Samarth%20Mahajan/Desktop/hackerrank-orchestrate-oct26/hackerrank-orchestrate-october26/code/identity.py)

---

### Decision 2: Bidirectional Identity Recovery from Current Snapshot + Historical Audit Log
- **Rationale**: Requests in `deletion_requests.csv` may specify a current or historical email. The resolver maps either email to a stable `user_id`, then reconstructs the complete `IdentitySet` (stable `user_id`, all valid emails, normalized SHA-256 email hashes, valid phone numbers, and active identifiers at `audit_at`).
- **Implementation**: [`code/identity.py:IdentityManager.find_user_id`](file:///c:/Users/Samarth%20Mahajan/Desktop/hackerrank-orchestrate-oct26/hackerrank-orchestrate-october26/code/identity.py) & [`code/identity.py:IdentityManager.resolve`](file:///c:/Users/Samarth%20Mahajan/Desktop/hackerrank-orchestrate-oct26/hackerrank-orchestrate-october26/code/identity.py)

---

### Decision 3: Strict Temporal Boundary on Evidence Ingestion (`captured_at <= audit_at`)
- **Rationale**: As mandated by `AGENTS.md` line 209: *"Use only information available at or before audit_at when deciding the case. Evidence created later must not change the answer for that case."* The indexer strictly drops any evidence file whose `captured_at` is strictly greater than `audit_at`.
- **Implementation**: [`code/evidence/index.py:EvidenceIndex.get_eligible_files`](file:///c:/Users/Samarth%20Mahajan/Desktop/hackerrank-orchestrate-oct26/hackerrank-orchestrate-october26/code/evidence/index.py)

---

### Decision 4: Candidate Resource Discovery via System Activity Temporal Clustering
- **Rationale**: When personal records are successfully deleted or anonymized, direct PII has been removed from the final system state (e.g. 404 lookups in JSON exports, absent rows in failover SQL replicas, or anonymized profiles). Without candidate resource correlation, such evidence cannot be linked to the subject. We correlate candidate resources from `system_activity.csv` executed within `reported_at ± 2h` (at or before `audit_at`) and verify their state in eligible evidence.
- **Implementation**: [`code/evidence/index.py:EvidenceIndex.get_candidate_resources`](file:///c:/Users/Samarth%20Mahajan/Desktop/hackerrank-orchestrate-oct26/hackerrank-orchestrate-october26/code/evidence/index.py)

---

### Decision 5: Closed `StateSignal` Enum Discovered from Ground Truth
- **Rationale**: Eliminates guessing or hallucinatory status codes. The state signal is strictly typed as a closed enum (`PRESENT`, `ABSENT`, `REDACTED`, `ANONYMIZED`, `ACTIVE`, `DISABLED`, `BLOCKED`, `UNPARSED`). Any unrecognized state is labeled `UNPARSED` and never guessed.
- **Implementation**: [`code/evidence/models.py:StateSignal`](file:///c:/Users/Samarth%20Mahajan/Desktop/hackerrank-orchestrate-oct26/hackerrank-orchestrate-october26/code/evidence/models.py)

---

### Decision 6: Pure-Python Decompression for Vector PDF Text Extraction
- **Rationale**: The dataset's PDF files (`evidence_18`, `evidence_27`, `evidence_55`, `evidence_58`) are digital vector documents encoded using Adobe ASCII85 (`/ASCII85Decode`) and zlib Flate (`/FlateDecode`). Using Python's standard `base64.a85decode` and `zlib.decompress` extracts 100% of text streams deterministically in milliseconds without heavy external OCR or PDF binary dependencies.
- **Implementation**: [`code/evidence/pdf_parser.py:parse_pdf`](file:///c:/Users/Samarth%20Mahajan/Desktop/hackerrank-orchestrate-oct26/hackerrank-orchestrate-october26/code/evidence/pdf_parser.py)

---

### Decision 7: In-Memory SQLite Execution for SQL Snapshot Drift Analysis
- **Rationale**: Participant SQL evidence files are SQLite-compatible text dumps. Executing them in an in-memory SQLite database enables robust schema and row inspection, deep document searching inside serialized JSON strings, and exact absence checks in failover replicas.
- **Implementation**: [`code/evidence/sql_parser.py:parse_sql`](file:///c:/Users/Samarth%20Mahajan/Desktop/hackerrank-orchestrate-oct26/hackerrank-orchestrate-october26/code/evidence/sql_parser.py)

---

### Decision 8: Specialized JSON Multi-Type Dispatcher
- **Rationale**: JSON files in the dataset have distinct structures: `service_exports` (HTTP response dumps like 404 not found or connector configs), `snapshots` (database table row dumps), and `records` (flat item lists). Dispatching by structure ensures correct extraction of `ABSENT`, `ANONYMIZED`, `BLOCKED`, and `DISABLED` signals.
- **Implementation**: [`code/evidence/json_parser.py:parse_json`](file:///c:/Users/Samarth%20Mahajan/Desktop/hackerrank-orchestrate-oct26/hackerrank-orchestrate-october26/code/evidence/json_parser.py)

---

### Decision 9: Trace Inheritance in Observability Log Parsing
- **Rationale**: Log files contain multi-line structured event logs where initial requests contain identity strings and correlation IDs, while downstream errors or completions carry only `trace_id`. The parser indexes trace IDs to maintain correlation and evaluate status codes.
- **Implementation**: [`code/evidence/log_parser.py:parse_log`](file:///c:/Users/Samarth%20Mahajan/Desktop/hackerrank-orchestrate-oct26/hackerrank-orchestrate-october26/code/evidence/log_parser.py)

---

### Decision 10: Tabular & Pipe-Delimited Shift Handover Text Parser
- **Rationale**: Operations handover reports are plain text with pipe delimiters (`|`). The text parser extracts system IDs, resource IDs, and identity tokens directly from handover records.
- **Implementation**: [`code/evidence/txt_parser.py:parse_txt`](file:///c:/Users/Samarth%20Mahajan/Desktop/hackerrank-orchestrate-oct26/hackerrank-orchestrate-october26/code/evidence/txt_parser.py)
