# Dataset Discovery and Profiling Report

This report presents the findings from executing read-only profiling via `code/discover.py` against all files in `dataset/`. Every metric cites exact row counts, file locations, or line numbers. Unverified assumptions are explicitly tagged as **HYPOTHESIS**.

---

## 1. Dataset File Inventory

| File | Size (Bytes) | Row Count | Columns | Notes |
|---|---|---|---|---|
| `dataset/deletion_requests.csv` | 164,183 | 518 data rows | 7 | Evaluation set. Exactly 518 cases to audit. |
| `dataset/deletion_rules.csv` | 1,055 | 15 data rows | 4 | Policy mapping for 15 data categories. |
| `dataset/evidence_files.csv` | 11,184 | 94 data rows | 4 | Manifest of all 94 evidence files. |
| `dataset/output.csv` | 36 | 0 data rows | 3 | Blank output template (`case_id,deletion_status,steps_json`). |
| `dataset/sample_deletion_requests.csv` | 9,043 | 32 data rows | 7 | Public sample subset of 32 cases. |
| `dataset/sample_output.csv` | 38,681 | 32 data rows | 3 | Ground truth output for the 32 sample cases. |
| `dataset/system_activity.csv` | 661,372 | 4,011 data rows | 8 | Global stream of operations/activity across systems. |
| `dataset/user_audit_log.csv` | 37,016 | 306 data rows | 6 | History of identity changes (`email`, `email_hash`, `phone`). |
| `dataset/user_identities.csv` | 127,262 | 850 data rows | 6 | Current identity snapshot for 850 users. |

Evidence directory (`dataset/evidence/`) contains 94 files across 5 categories:
- `databases/`: 24 SQLite-compatible `.sql` snapshot files
- `documents/`: 4 `.pdf` documents
- `images/`: 11 `.png` application/console screenshots
- `logs/`: 26 `.log` observability trace and stream files
- `records/`: 29 files (28 `.json` files, 1 `.txt` file)

---

## 2. Profiling `deletion_requests.csv`

Total cases: **518** (`dataset/deletion_requests.csv:2-519`).

### 2.1 Column Profiles
- `case_id`: 518 distinct strings (`case_33` through `case_550`). 0 nulls (0.0%).
- `email`: 517 distinct strings (1 duplicate email across two distinct cases). 0 nulls (0.0%).
- `requested_at`: ISO-8601 UTC timestamps. Min: `2026-01-05T06:00:00Z`, Max: `2026-09-24T08:00:00Z`. 0 nulls (0.0%).
- `reported_status`: Categorical claim with 3 values:
  - `COMPLETE`: 254 cases (49.03%)
  - `PARTIALLY_COMPLETE`: 152 cases (29.34%)
  - `NOT_STARTED`: 112 cases (21.62%)
- `reported_at`: ISO-8601 UTC timestamps. Min: `2026-01-06T06:00:00Z`, Max: `2026-09-26T02:00:00Z`. 0 nulls (0.0%).
- `audit_at`: ISO-8601 UTC timestamps. Min: `2026-01-29T12:00:00Z`, Max: `2026-10-01T12:00:00Z`. 72 distinct cutoff times. 0 nulls (0.0%).
- `request_text`: Freeform text submitted by user. 375 distinct texts. 0 nulls (0.0%).

### 2.2 Request Intent & Multilingual Characteristics
- Multi-language coverage detected in `request_text`:
  - English (e.g. `case_33`: *"Please close my account and process the associated personal-data deletion..."*)
  - Portuguese (e.g. `case_67`: *"Solicito a exclusão permanente da conta associada a este e-mail..."*)
  - Korean (e.g. `case_95`: *"이 이메일 주소에 연결된 계정의 영구 삭제를 요청합니다..."*)
  - Spanish (e.g. `case_112`: *"Solicito la eliminación permanente de la cuenta asociada a este correo..."*)
  - Japanese (e.g. `case_134`: *"このメールアドレスに関連するアカウントの完全な削除を依頼します..."*)
  - French (e.g. `case_158`: *"Je demande la suppression définitive du compte associé à cette adresse e-mail..."*)
- Keyword screening identified non-deletion requests (which must be mapped to `NOT_APPLICABLE` with `steps_json=[]` per `AGENTS.md:270`):
  - Access requests (`access`, `what data`, `copy of`)
  - Export requests (`export`, `download`, `portability`)
  - Correction requests (`correct`, `rectif`, `update my`)
  - Marketing opt-out requests (`unsubscribe`, `opt out`)

---

## 3. Evidence Files & Temporal Cutoff Analysis

Manifest: `dataset/evidence_files.csv` (94 files).

### 3.1 Format Distribution
- `.log`: 26 files (27.66%)
- `.json`: 28 files (29.79%)
- `.sql`: 24 files (25.53%)
- `.png`: 11 files (11.70%)
- `.pdf`: 4 files (4.26%)
- `.txt`: 1 file (1.06%)

### 3.2 Temporal Boundary (`audit_at` Cutoff)
- `captured_at` range: `2026-01-29T11:44:59Z` to `2026-10-01T12:00:00Z`.
- Cross-comparison against all 518 cases in `deletion_requests.csv`:
  - **511 out of 518 cases (98.6%)** have evidence files captured strictly after their `audit_at`.
  - For affected cases, between **2 and 93 evidence files** (mean: **54.56 files**) were captured after `audit_at`.
- **CRITICAL INVARIANT**: Any evidence file with `captured_at > case.audit_at` must be strictly excluded when auditing that case (`AGENTS.md:209`, `AGENTS.md:292`).

### 3.3 Resource State Encoding in Evidence
- **SQL Snapshots** (`.sql`): Contain table dumps (`customer_accounts`, `customer_profiles`, `user_metadata`, etc.). Presence of a row for `user_id` or `email_hash` indicates `PRESENT` state.
- **Log Streams** (`.log`): Contain structured or unstructured event records showing data flows, indexing actions, and lookups.
- **JSON Bundles** (`.json`): Contain structured exports of service resources, connector configs, and ledger records.
- **Visual Evidence** (`.png` / `.pdf`): Admin console screenshots, handover documents, and retention registers documenting specific user records.

---

## 4. Identifier & Hash Hypothesis Testing

### 4.1 `user_identities.csv` Email Hash Verification
- Hypothesis: `email_hash` is computed as `SHA-256(email.strip().lower())`.
- Test: Computed `hashlib.sha256(email.strip().lower().encode('utf-8')).hexdigest()` for all 850 rows in `dataset/user_identities.csv`.
- **Result: 850 / 850 matches (100.0%)**.
- Also tested raw (unnormalized) `hashlib.sha256(email.encode('utf-8')).hexdigest()`: **850 / 850 matches (100.0%)** (all emails in the dataset are already lowercased and trimmed).
- Alternative algorithms (MD5, SHA-1): 0 / 850 matches (0.0%).

### 4.2 Hash Matching in Evidence Files
- Scanned all 79 text-based evidence files (`.log`, `.json`, `.sql`, `.txt`):
  - 25 evidence files contain 64-character hexadecimal SHA-256 strings (417 total occurrences).
  - 58 occurrences in 21 evidence files exactly match a user's `email_hash` from `user_identities.csv`.
  - 77 evidence files contain exact email string matches.
  - 73 evidence files contain exact `user_id` matches (e.g. `user_01`).

---

## 5. Reverse-Engineering Step Ordering Invariant

Ground truth file: `dataset/sample_output.csv` (32 cases, 193 total steps).

### 5.1 Evaluated Order Hierarchy
1. **Phase Precedence**:
   `FINDING` (0) → `REMEDIATION` (1) → `VERIFICATION` (2)
2. **Operation Precedence**:
   - `FINDING`:
     1. `REPORT_REMAINING_RECORD`
     2. `REPORT_EXPOSED_PII`
     3. `REPORT_ACTIVE_DATA_FLOW`
     4. `REPORT_RESTORE_RISK`
   - `REMEDIATION`:
     1. `DISABLE_DATA_FLOW`
     2. `BLOCK_RESTORE`
     3. `DELETE_RECORD`
     4. `REDACT_RECORD`
     5. `ANONYMIZE_RECORD`
   - `VERIFICATION`:
     1. `VERIFY_RECORD_ABSENT`
     2. `VERIFY_RECORD_PRESENT`
     3. `VERIFY_RECORD_REDACTED`
     4. `VERIFY_RECORD_ANONYMIZED`
     5. `VERIFY_DATA_FLOW_DISABLED`
     6. `VERIFY_RESTORE_BLOCKED`
3. **Lexicographical Secondary Keys**:
   - `system_id` ascending (A → Z)
   - `resource_id` ascending (A → Z)

### 5.2 Test Outcome
- Total steps checked across all 32 cases: **193 steps**.
- Consecutive `step_no` validation: **0 violations** (every case strictly numbers `1, 2, ..., N`).
- Pairwise ordering validation: **0 violations**.
- **Conclusion**: The ordering invariant stated in `problem_statement.md:126` and `README.md:75` is 100% verified against canonical ground truth with zero discrepancies.

### 5.3 Evidence Citation Pattern in Sample Outputs
- In `FINDING` steps: 41 / 41 (100.0%) cite a non-empty `evidence_id`.
- In `REMEDIATION` steps: 41 / 41 (100.0%) have `evidence_id == ""`.
- In `VERIFICATION` steps:
  - For `COMPLETE` cases: 34 / 34 (100.0%) cite a non-empty `evidence_id` proving current state.
  - For `INCOMPLETE` cases: 77 / 77 (100.0%) have `evidence_id == ""` (future verification checks).

---

## 6. Open Questions & Hypotheses

1. **Multilingual Non-Deletion Intent Detection**:
   - *Status*: **HYPOTHESIS**.
   - *Detail*: A subset of requests in `deletion_requests.csv` are written in languages like French, Korean, Spanish, Portuguese, and Japanese. Some represent non-deletion intents (such as access or correction). A deterministic multilingual keyword dictionary or high-precision translation parser is required to accurately classify `NOT_APPLICABLE` vs deletion requests without false positives.
2. **Account Tombstone Identifier Scope**:
   - *Status*: **HYPOTHESIS**.
   - *Detail*: When an account tombstone is preserved (`rule_15`), `system_id` and `resource_id` must retain the user's stable reference while removing direct PII. The exact systems implementing tombstones appear to be `account_service` and `customer_account_service`.
3. **Replication Drift in SQL Snapshots**:
   - *Status*: **HYPOTHESIS**.
   - *Detail*: SQL snapshot evidence contains primary, regional, read, and failover replicas. Some replicas may lag behind primary deletion. State must be determined by the most recent snapshot at or before `audit_at` for each replica.
