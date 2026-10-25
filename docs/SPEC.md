# SPEC.md — Ghost Data Still Exists: State Engine & Evidence Specification

This document defines the formal deterministic specifications for Layer 5 (State Determination) and Layer 6 (Step Assembly) of the deletion-audit agent.

---

## 1. Ground Truth Dataset Counts

Reconciled via code execution over all CSV files in `dataset/`:

| File | Size (bytes) | Data Rows | Description |
|---|---|---|---|
| `dataset/deletion_requests.csv` | 164,183 | 518 | Evaluation dataset requests |
| `dataset/sample_deletion_requests.csv` | 9,043 | 32 | Public sample benchmark requests |
| `dataset/sample_output.csv` | 38,681 | 32 | Ground truth public benchmark answers |
| `dataset/output.csv` | 36 | 0 | Blank prediction template |
| `dataset/deletion_rules.csv` | 1,055 | 15 | Company deletion policy rules |
| `dataset/evidence_files.csv` | 11,184 | 94 | Manifest mapping file IDs to paths and origins |
| `dataset/system_activity.csv` | 661,372 | 4,011 | Global activity and event stream |
| `dataset/user_audit_log.csv` | 37,016 | 306 | Historical changes to identity fields |
| `dataset/user_identities.csv` | 127,262 | 850 | Current user identity snapshots |

*Reconciliation Note*: Prompt 0 numbers (`identities=850, audit_log=306, activity=4011, evidence_files=94`) are verified correct by code. Prompt 1 user prompt numbers (`5000/2000/10000/100`) were incorrect and have been reconciled.

---

## 2. Deletion Policy Rules (`deletion_rules.csv`) Verbatim

| rule_id | data_category | condition | required_action |
|---|---|---|---|
| `rule_01` | `USER_PROFILE` | Always | `DELETE` |
| `rule_02` | `SECONDARY_IDENTIFIER` | Always | `DELETE` |
| `rule_03` | `SEARCH_INDEX_ENTRY` | Always | `DELETE` |
| `rule_04` | `CACHE_ENTRY` | Always | `DELETE` |
| `rule_05` | `SUPPORT_MESSAGE` | Conversation contains shared customer, agent, or order context that must be retained | `REDACT` |
| `rule_06` | `SUPPORT_ATTACHMENT` | Attachment belongs only to the deletion subject | `DELETE` |
| `rule_07` | `ANALYTICS_PROFILE` | Record is still attributable to a user | `ANONYMIZE` |
| `rule_08` | `PRODUCT_TELEMETRY` | Record is still attributable to a user | `ANONYMIZE` |
| `rule_09` | `USER_EXPORT` | Always | `DELETE` |
| `rule_10` | `MARKETING_PROFILE` | Always | `DELETE` |
| `rule_11` | `EMAIL_DELIVERY_LOG` | Log contains a user email address | `REDACT` |
| `rule_12` | `SECURITY_AUDIT_LOG` | Record is within the supplied retention period | `RETAIN` |
| `rule_13` | `LEGAL_HOLD_RECORD` | A supplied legal hold is active | `RETAIN` |
| `rule_14` | `BACKUP_ARCHIVE` | Restore access can be blocked | `RETAIN` |
| `rule_15` | `ACCOUNT_TOMBSTONE` | Account is deleted and only a stable internal user_id is needed to preserve references to retained records | `REDACT` |

### System to Category Mapping & Policy Citations

| System ID | Data Category | Rule | Required Action | Evidence / Sample Citation |
|---|---|---|---|---|
| `account_service` | `USER_PROFILE` | `rule_01` | `DELETE` | `sample_output.csv` (case_01, case_05) |
| `search_service` | `SEARCH_INDEX_ENTRY` | `rule_03` | `DELETE` | `sample_output.csv` (case_06, case_11) |
| `export_service` | `USER_EXPORT` | `rule_09` | `DELETE` | `sample_output.csv` (case_08, case_23) |
| `support_platform` (tickets) | `SUPPORT_MESSAGE` | `rule_05` | `REDACT` | `sample_output.csv` (case_18, case_19) |
| `support_platform` (attachments) | `SUPPORT_ATTACHMENT` | `rule_06` | `DELETE` | `sample_output.csv` (case_07, case_10, case_13) |
| `analytics_platform` (user profile) | `ANALYTICS_PROFILE` | `rule_07` | `ANONYMIZE` | `sample_output.csv` (case_03, case_11, case_29) |
| `analytics_platform` (opt-in list) | `MARKETING_PROFILE` | `rule_10` | `DELETE` | `sample_output.csv` (case_12) |
| `integration_service` | `ACTIVE_DATA_FLOW` | Contract | `DISABLE` | `sample_output.csv` (case_11, case_15, case_20) |
| `backup_service` | `BACKUP_ARCHIVE` | `rule_14` | `BLOCK` | `sample_output.csv` (case_09, case_14, case_17) |
| `security_service` | `SECURITY_AUDIT_LOG` | `rule_12` | `RETAIN` | `sample_output.csv` (case_03, case_09, case_11) |
| `identity_service` | `ACCOUNT_TOMBSTONE` | `rule_15` | `REDACT` | `sample_output.csv` (case_31, case_32) |

---

## 3. Evidence Citation and State Rules

### Tabulation of Ground Truth Steps (193 Total Steps)

| Phase | Operation | Evidence ID Status | Step Count |
|---|---|---|---|
| `FINDING` | `REPORT_ACTIVE_DATA_FLOW` | Cited (`evidence_id != ""`) | 6 |
| `FINDING` | `REPORT_EXPOSED_PII` | Cited (`evidence_id != ""`) | 11 |
| `FINDING` | `REPORT_REMAINING_RECORD` | Cited (`evidence_id != ""`) | 21 |
| `FINDING` | `REPORT_RESTORE_RISK` | Cited (`evidence_id != ""`) | 3 |
| `REMEDIATION` | `ANONYMIZE_RECORD` | Empty (`evidence_id == ""`) | 5 |
| `REMEDIATION` | `BLOCK_RESTORE` | Empty (`evidence_id == ""`) | 3 |
| `REMEDIATION` | `DELETE_RECORD` | Empty (`evidence_id == ""`) | 21 |
| `REMEDIATION` | `DISABLE_DATA_FLOW` | Empty (`evidence_id == ""`) | 6 |
| `REMEDIATION` | `REDACT_RECORD` | Empty (`evidence_id == ""`) | 6 |
| `VERIFICATION` | `VERIFY_DATA_FLOW_DISABLED` | Cited in COMPLETE, Empty in INCOMPLETE | 3 cited / 6 empty |
| `VERIFICATION` | `VERIFY_RECORD_ABSENT` | Cited in COMPLETE, Empty in INCOMPLETE | 10 cited / 40 empty |
| `VERIFICATION` | `VERIFY_RECORD_ANONYMIZED` | Cited in COMPLETE, Empty in INCOMPLETE | 7 cited / 5 empty |
| `VERIFICATION` | `VERIFY_RECORD_PRESENT` | Cited in COMPLETE, Empty in INCOMPLETE | 7 cited / 17 empty |
| `VERIFICATION` | `VERIFY_RECORD_REDACTED` | Cited in COMPLETE, Empty in INCOMPLETE | 4 cited / 6 empty |
| `VERIFICATION` | `VERIFY_RESTORE_BLOCKED` | Cited in COMPLETE, Empty in INCOMPLETE | 3 cited / 3 empty |

### Exact Citation Rules
1. **FINDING Steps**: Always cite the participant-visible `evidence_id` proving non-compliance or recreation risk (`evidence_id != ""`).
2. **REMEDIATION Steps**: Describe proposed future actions; strictly use an empty string (`evidence_id = ""`).
3. **VERIFICATION Steps**:
   - For `COMPLETE` cases: Cite the participant-visible `evidence_id` proving compliant state at `audit_at`.
   - For `INCOMPLETE` cases: Describe post-remediation verification checks that must pass after remediation; strictly use an empty string (`evidence_id = ""`).

### Operation to State Mapping
- `REPORT_ACTIVE_DATA_FLOW` -> `ACTIVE`
- `REPORT_RESTORE_RISK` -> `ACTIVE`
- `REPORT_REMAINING_RECORD` -> `PRESENT`
- `REPORT_EXPOSED_PII` -> `PRESENT`
- `DISABLE_DATA_FLOW` -> `DISABLED`
- `BLOCK_RESTORE` -> `BLOCKED`
- `DELETE_RECORD` -> `ABSENT`
- `REDACT_RECORD` -> `REDACTED`
- `ANONYMIZE_RECORD` -> `ANONYMIZED`
- `VERIFY_DATA_FLOW_DISABLED` -> `DISABLED`
- `VERIFY_RESTORE_BLOCKED` -> `BLOCKED`
- `VERIFY_RECORD_ABSENT` -> `ABSENT`
- `VERIFY_RECORD_PRESENT` -> `PRESENT`
- `VERIFY_RECORD_REDACTED` -> `REDACTED`
- `VERIFY_RECORD_ANONYMIZED` -> `ANONYMIZED`

---

## 4. Multi-Source Precedence & State Determination

### Precedence and Supersession Rules
1. **Logical Resource vs. Physical Replica Scope**:
   - A *logical resource* (e.g. account profile, support message, search index entry) may be manifested across multiple *physical stores/replicas* (primary SQL database, failover SQL replica, regional read replicas, observability logs, search index dumps).
   - Each source represents an observation of a specific physical copy.
2. **Same-Copy Temporal Supersession**:
   - A newer observation supersedes an older observation **ONLY for the exact same physical copy/store**. For example, if a read replica snapshot at `2026-09-10` shows a record `PRESENT`, but a subsequent read replica snapshot of that same replica at `2026-09-20` (both `<= audit_at`) shows `ABSENT`, the newer observation supersedes the older one for that specific replica.
3. **Cross-Copy Non-Transferability**:
   - Absence in one copy does **NOT** prove absence in other copies. If primary database shows `ABSENT` (e.g., HTTP 404 in readback), but failover replica or reporting replica shows `PRESENT`, the data still physically exists on the platform. The finding `REPORT_REMAINING_RECORD` must be reported.
4. **Rejection of Embedded Post-Audit Events**:
   - Even if an evidence file's `captured_at` is `<= audit_at`, any individual event, row, or timestamp embedded within that file that occurred after `audit_at` is strictly rejected and excluded from decision evidence.
5. **No Arbitrary "Presence Always Wins" Rule**:
   - A record is classified as `PRESENT` only when grounded in an eligible, non-superseded observation. If evidence sources conflict without causal or temporal resolution, the conflict must be preserved as unresolved rather than resolved by an invented global hierarchy.

### Universal Account Verification: SAMPLE-DERIVED Invariant
- **Contract Reality**: The challenge specification (`problem_statement.md` §6.3, §6.5) states that verification covers *remediated records* and *policy-required retained records*.
- **Sample-Derived Nature**: Across all 32 public sample cases, every case emitted an `account_service <primary_acc> VERIFY_RECORD_ABSENT` verification step. This invariant is **SAMPLE-DERIVED** because the sample dataset was curated specifically around user accounts that were either deleted or reported deleted.
- **Evaluation Constraint**: For the 518 evaluation requests, account IDs must be grounded in raw evidence (SQL rows, lookup logs, service exports). Account IDs must **NEVER** be synthesized from case IDs or unproven naming conventions.

---

## 5. Layer 4 Request Authorization Contract (`code/intent.py`)

### Scope & Pipeline Order
L4 Request Authorization operates strictly on `request_text` before any identity resolution or evidence state determination:
1. `NON_DELETION` -> Immediately emits `NOT_APPLICABLE` with `steps_json=[]`.
2. `DELETE_AUTHORIZED` -> Routes to Layer 2 (Identity), Layer 3 (Evidence), and Layer 5 (State Engine).
3. `UNRESOLVED` -> Halts processing with an explicit diagnostic; blocks final submission generation until resolved.

L4 **never** emits `COMPLETE` or `INCOMPLETE`.

### Classification Outcomes
- `DELETE_AUTHORIZED`: Subject explicitly authorizes account deletion, personal data removal, or erasure.
- `NON_DELETION`: Subject requests access/export, invoice copies, correction of misspelled fields, marketing opt-out, password reset, or includes explicit instructions NOT to delete ("leave active", "do not close").
- `UNRESOLVED`: Ambiguous language, empty text, or unverified spans.

### Adapter Contract
- Optional provider-agnostic `LLMAdapter` interface behind a single configuration switch (`MockLLMAdapter` provided for tests).
- All spans returned by an adapter must be verified verbatim against `request_text` (`all(s in request_text for s in supporting_spans)`).
- Malformed JSON, invalid enums, fabricated spans, or provider timeouts strictly fall back to `UNRESOLVED` (no silent defaults).
