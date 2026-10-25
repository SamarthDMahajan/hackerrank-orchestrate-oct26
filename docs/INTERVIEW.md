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

---

### Decision 11: Point-in-Time Precedence in Observation Selection
- **Rationale**: When multiple eligible evidence files observe the same resource, point-in-time service export dumps and latest verified readbacks take precedence over stale database dumps or prior snapshots. If multiple observations exist, the latest observation (`captured_at <= audit_at`) from authoritative system readbacks is selected.
- **Implementation**: [`code/engine/state.py:StateEngine.select_best_observation`](file:///c:/Users/Samarth%20Mahajan/Desktop/hackerrank-orchestrate-oct26/hackerrank-orchestrate-october26/code/engine/state.py)

---

### Decision 12: Deterministic Policy Mapping & Finding/Remediation Synthesis
- **Rationale**: Every resource category is strictly mapped to `deletion_rules.csv`. Compliant state yields verification only. Non-compliant state yields finding(s) with evidence citation, safe remediation operation with empty evidence ID, and post-remediation verification.
- **Implementation**: [`code/engine/state.py:StateEngine.evaluate_case`](file:///c:/Users/Samarth%20Mahajan/Desktop/hackerrank-orchestrate-oct26/hackerrank-orchestrate-october26/code/engine/state.py)

---

### Decision 13: Universal Post-Remediation Account Verification Invariant
- **Rationale**: Ground truth across all 32 sample cases demonstrates that every authorized deletion case includes verification that the subject's primary account record is absent (`account_service <primary_acc> ABSENT`). For `COMPLETE` cases, this step cites the proving service export or lookup log; for `INCOMPLETE` cases, it reflects post-remediation verification with an empty `evidence_id`.
- **Implementation**: [`code/engine/state.py:StateEngine.evaluate_case`](file:///c:/Users/Samarth%20Mahajan/Desktop/hackerrank-orchestrate-oct26/hackerrank-orchestrate-october26/code/engine/state.py)

---

### Decision 14: Strict Evidence-Citation Rule (Zero-Exception Contract)
- **Rationale**: As proven across all 193 sample steps:
  1. `FINDING`: Always cites participant-visible evidence ID proving non-compliance (`evidence_id != ""`).
  2. `REMEDIATION`: Future planned action, strictly empty evidence ID (`evidence_id = ""`).
  3. `VERIFICATION`: For `COMPLETE` cases, always cites evidence proving compliance at `audit_at`. For `INCOMPLETE` cases, future post-remediation check, strictly empty evidence ID (`evidence_id = ""`).
- **Implementation**: [`code/engine/state.py:StateEngine.evaluate_case`](file:///c:/Users/Samarth%20Mahajan/Desktop/hackerrank-orchestrate-oct26/hackerrank-orchestrate-october26/code/engine/state.py)

---

### Decision 15: Canonical Step Ordering and Deterministic Serialization
- **Rationale**: Steps are numbered consecutively from 1 and ordered strictly by phase: `FINDING` -> `REMEDIATION` -> `VERIFICATION`. Within remediation, data flows and restores are neutralized before dependent records. Serialization matches sample formatting deterministically without extraneous whitespace.
- **Implementation**: [`code/engine/assemble.py:assemble_steps`](file:///c:/Users/Samarth%20Mahajan/Desktop/hackerrank-orchestrate-oct26/hackerrank-orchestrate-october26/code/engine/assemble.py) & [`code/engine/assemble.py:serialize_steps`](file:///c:/Users/Samarth%20Mahajan/Desktop/hackerrank-orchestrate-oct26/hackerrank-orchestrate-october26/code/engine/assemble.py)

---

### Decision 16: Independent Regression Gate & Non-Lossy Semantic Comparator
- **Rationale**: An evaluator must never mask missing or extra cases through `zip()` or inner joins. The comparator performs full outer set comparison of case IDs, semantic array comparison of steps, field-by-field verification, and sequence checking. Its sensitivity was independently verified by demonstrating that 7 targeted mutations (status flip, evidence_id change, step removal, step swap, case removal, unexpected case addition, duplicate case) all cause exact-match failure.
- **Implementation**: [`code/evaluation/comparator.py:compare_outputs`](file:///c:/Users/Samarth%20Mahajan/Desktop/hackerrank-orchestrate-oct26/hackerrank-orchestrate-october26/code/evaluation/comparator.py)
- **Supporting Tests**: [`tests/test_comparator_mutations.py`](file:///c:/Users/Samarth%20Mahajan/Desktop/hackerrank-orchestrate-oct26/hackerrank-orchestrate-october26/tests/test_comparator_mutations.py)

---

### Decision 17: Request-Only L4 Intent Classification & Strict Scope Enforcement
- **Rationale**: The challenge contract mandates determining whether the request authorizes deletion based strictly on `request_text`. Supplying `reported_status`, evidence, or case IDs to the intent classifier causes data leakage. We enforce strict Pydantic contracts (`extra="forbid"`), closed internal outcomes (`DELETE_AUTHORIZED`, `NON_DELETION`, `UNRESOLVED`), deterministic multilingual patterns covering all 27 request templates in the dataset, and verbatim input span verification.
- **Implementation**: [`code/intent.py:classify_intent`](file:///c:/Users/Samarth%20Mahajan/Desktop/hackerrank-orchestrate-oct26/hackerrank-orchestrate-october26/code/intent.py)
- **Supporting Tests**: [`tests/test_intent.py`](file:///c:/Users/Samarth%20Mahajan/Desktop/hackerrank-orchestrate-oct26/hackerrank-orchestrate-october26/tests/test_intent.py)

---

### Decision 18: Pipeline Order & Boundary Decoupling (L4 before L5)
- **Rationale**: L4 authorization runs strictly before identity and evidence evaluation:
  1. `NON_DELETION` -> Emits `NOT_APPLICABLE` with `steps_json=[]`.
  2. `DELETE_AUTHORIZED` -> Passes to Layer 2 identity resolution, Layer 3 evidence indexing, and Layer 5 state engine.
  3. `UNRESOLVED` -> Produces an explicit diagnostic and blocks submission generation.
  L4 never emits `COMPLETE` or `INCOMPLETE`.
- **Implementation**: [`code/main.py:process_requests`](file:///c:/Users/Samarth%20Mahajan/Desktop/hackerrank-orchestrate-oct26/hackerrank-orchestrate-october26/code/main.py) & [`code/engine/run_samples.py`](file:///c:/Users/Samarth%20Mahajan/Desktop/hackerrank-orchestrate-oct26/hackerrank-orchestrate-october26/code/engine/run_samples.py)

---

### Decision 19: Provenance Repair & Purge of Answer-Derived Shortcuts
- **Decision**: Invalidate prior 32/32 sample replay claim and eliminate all answer-derived shortcuts from production inference.
- **Implementation**:
  - Removed `COMPLETE_ANON_MAP` from [`code/engine/state.py:evaluate_case`](file:///c:/Users/Samarth%20Mahajan/Desktop/hackerrank-orchestrate-oct26/hackerrank-orchestrate-october26/code/engine/state.py).
  - Removed `EXTRA_ACCOUNTS` and `SYNTHETIC_ACCOUNTS` from [`code/engine/state.py:_load_account_maps`](file:///c:/Users/Samarth%20Mahajan/Desktop/hackerrank-orchestrate-oct26/hackerrank-orchestrate-october26/code/engine/state.py) and [`code/engine/state.py:determine_account`](file:///c:/Users/Samarth%20Mahajan/Desktop/hackerrank-orchestrate-oct26/hackerrank-orchestrate-october26/code/engine/state.py).
  - Removed hardcoded unobserved audit records (`user_48 -> audit_record_5569`, `user_50 -> audit_record_6645`) from [`code/engine/state.py:_load_audit_records`](file:///c:/Users/Samarth%20Mahajan/Desktop/hackerrank-orchestrate-oct26/hackerrank-orchestrate-october26/code/engine/state.py).
  - Removed account-specific evidence ID branching and unconditional account verification when no account is observed.
  - Removed invented naming patterns (`account_{num_str}`) and time-proximity deletion-worker guessing from [`code/evidence/index.py:get_candidate_resources`](file:///c:/Users/Samarth%20Mahajan/Desktop/hackerrank-orchestrate-oct26/hackerrank-orchestrate-october26/code/evidence/index.py).
  - Implemented typed provenance records in [`code/engine/provenance.py`](file:///c:/Users/Samarth%20Mahajan/Desktop/hackerrank-orchestrate-oct26/hackerrank-orchestrate-october26/code/engine/provenance.py).
- **Test**: Clean replay against staged dataset without `sample_output.csv` achieves 100.0% status accuracy (32/32) and 31.25% sequence accuracy (10/32 exact sequence matches). Verified in [`scratch/eval_staged_predictions.py`](file:///C:/Users/Samarth%20Mahajan/.gemini/antigravity-ide/brain/0731d87a-1718-406e-aa1b-b1fd1723e5ec/scratch/eval_staged_predictions.py).
- **Source & Limitation**: Unobserved accounts (e.g. `account_001` for `user_01`) remain unresolved in raw text evidence until image extraction or additional evidence linking is conducted.

---

### Decision 20: Precedence and Multi-Replica Persistence Invariants
- **Decision**: Observations must strictly respect temporal and architectural precedence:
  1. Newer authoritative observation supersedes older observation of same physical copy.
  2. Absence in primary does not erase presence in a different replica.
  3. Embedded post-audit events cannot change audit-time decisions.
  4. Unorderable conflicting observations remain explicitly unresolved.
  5. Workflow success claims alone cannot establish record absence.
  6. Unknown resource/category mappings do not silently default to DELETE.
  7. Retention conditions are checked from supplied facts.
- **Implementation**: [`code/engine/state.py:StateEngine.select_best_observation`](file:///c:/Users/Samarth%20Mahajan/Desktop/hackerrank-orchestrate-oct26/hackerrank-orchestrate-october26/code/engine/state.py).
- **Test**: 7 focused unit tests in [`tests/test_precedence.py`](file:///c:/Users/Samarth%20Mahajan/Desktop/hackerrank-orchestrate-oct26/hackerrank-orchestrate-october26/tests/test_precedence.py) (All 7 passed).
- **Source & Limitation**: Multi-replica drift requires explicit table comparison between primary and replica SQL dumps.

---

### Decision 21: Full-Text Request Authorization & Negation Priority
- **Decision**: Request authorization must inspect the entire request text, never just the prefix or opening sentence, and prioritize negations/restrictions over deletion keywords.
- **Implementation**: [`code/intent.py:classify_intent`](file:///c:/Users/Samarth%20Mahajan/Desktop/hackerrank-orchestrate-oct26/hackerrank-orchestrate-october26/code/intent.py).
- **Test**: 10 unit tests in [`tests/test_intent.py`](file:///c:/Users/Samarth%20Mahajan/Desktop/hackerrank-orchestrate-oct26/hackerrank-orchestrate-october26/tests/test_intent.py) (All 10 passed).
- **Source & Limitation**: Authorization manifest is preserved under label `PROPOSED_AUTOMATED` (508 deletion authorized / 10 non-deletion) and not certified as ground truth without human review.

---

### Decision 22: Independence and Mutation Robustness
- **Decision**: Predictions must remain strictly invariant to arbitrary case ID renaming, row reordering, claim manipulation in request text, and evaluator label poisoning.
- **Implementation**: Production pipeline [`code/engine/state.py`](file:///c:/Users/Samarth%20Mahajan/Desktop/hackerrank-orchestrate-oct26/hackerrank-orchestrate-october26/code/engine/state.py) and [`code/main.py`](file:///c:/Users/Samarth%20Mahajan/Desktop/hackerrank-orchestrate-oct26/hackerrank-orchestrate-october26/code/main.py).
- **Test**: 5 unit tests in [`tests/test_independence.py`](file:///c:/Users/Samarth%20Mahajan/Desktop/hackerrank-orchestrate-oct26/hackerrank-orchestrate-october26/tests/test_independence.py) (All 5 passed).
- **Source & Limitation**: Applies to all deterministically discoverable resources; does not resolve unobserved resources without evidence.

---

### Decision 23: Grounded Visual Evidence Ingestion & Bidirectional Temporal Scope
- **Decision**: All 11 PNG console screenshots under `dataset/evidence/images/` represent ground-truth participant evidence files for evaluation requests. Evidence eligibility must enforce both lower and upper temporal bounds: `requested_at <= captured_at <= audit_at`. Historical evidence captured prior to the deletion request reflects pre-request states and must not be used to audit the post-request deletion workflow.
- **Implementation**: [`code/evidence/image_parser.py:parse_image`](file:///c:/Users/Samarth%20Mahajan/Desktop/hackerrank-orchestrate-oct26/hackerrank-orchestrate-october26/code/evidence/image_parser.py), registered in [`code/evidence/index.py:EvidenceIndex`](file:///c:/Users/Samarth%20Mahajan/Desktop/hackerrank-orchestrate-oct26/hackerrank-orchestrate-october26/code/evidence/index.py).
- **Test**: Added `test_image_parsing_extraction` in [`tests/test_evidence.py`](file:///c:/Users/Samarth%20Mahajan/Desktop/hackerrank-orchestrate-oct26/hackerrank-orchestrate-october26/tests/test_evidence.py). Evaluated against staged inputs without `sample_output.csv`, achieving 100.0% status accuracy (32/32) and 31.25% sequence accuracy (10/32 exact sequence matches, 67 matched steps, 0 field mismatches).
- **Source & Limitation**: Image transcription is grounded strictly in on-screen UI elements (Northstar Shop, BridgeOps, Pulse Analytics, Sentinel, Nimbus Object Storage, Helpline, Vault Recovery Manager).

---

### Decision 24: Multi-Format Log Parsing & Trace Correlation for Observability Streams
- **Decision**: Production log files utilize diverse log formats across systems (RFC 5424 Syslog with priority tags, pipe-delimited microservice logs, and bracketed application traces) where trace IDs (`tr-*`, `rb-*`) appear in headers without explicit `trace_id=` key-value prefixes. The log parser extracts structured headers, propagates correlation contexts across started and completed event pairs, and handles backup restore policy signals (`restore_allowed="true"`, `archive_present="true"` -> `StateSignal.ACTIVE`).
- **Implementation**: [`code/evidence/log_parser.py:parse_log`](file:///c:/Users/Samarth%20Mahajan/Desktop/hackerrank-orchestrate-oct26/hackerrank-orchestrate-october26/code/evidence/log_parser.py) & [`code/engine/state.py:_load_account_maps`](file:///c:/Users/Samarth%20Mahajan/Desktop/hackerrank-orchestrate-oct26/hackerrank-orchestrate-october26/code/engine/state.py)
- **Test**: Resolves observability stream evaluation cases (`case_171`, `case_291`, `case_413`–`422`, `case_514`–`521`) with 0 schema violations.

---

### Decision 25: Activity Link Correlation & Extended System Scope (`marketing_platform`, `object_storage`)
- **Decision**: Explicit data catalog linkages (`activity_4000`–`activity_4011` in `system_activity.csv`) establish pre-audit associations between resources and identities. The state engine enforces deletion policy rules for `marketing_platform` (Rule 10: `DELETE`) and `object_storage` (Rule 06: `DELETE`) when residual records or attachments persist at `audit_at`.
- **Implementation**: [`code/engine/state.py:StateEngine._load_account_maps`](file:///c:/Users/Samarth%20Mahajan/Desktop/hackerrank-orchestrate-oct26/hackerrank-orchestrate-october26/code/engine/state.py), [`code/engine/state.py:StateEngine._load_audit_records`](file:///c:/Users/Samarth%20Mahajan/Desktop/hackerrank-orchestrate-oct26/hackerrank-orchestrate-october26/code/engine/state.py), and [`code/engine/state.py:StateEngine.evaluate_case`](file:///c:/Users/Samarth%20Mahajan/Desktop/hackerrank-orchestrate-oct26/hackerrank-orchestrate-october26/code/engine/state.py).
- **Test**: Verified across `case_61` (object storage attachment) and `case_63` (marketing profile audience console). Validated full 518-case output with zero contract violations in `code/validate_output.py`.



