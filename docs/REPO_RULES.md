# REPO RULES AUDIT

This document establishes the verified rules, constraints, schemas, and invariants audited from the repository documentation (`README.md`, `problem_statement.md`, `AGENTS.md`, `CLAUDE.md`, and `agent_trace_instructions.md`).

---

## 1. Verbatim Quoted Rules & Constraints

### 1.1 From `AGENTS.md`
- **Session & Logging**:
  - `AGENTS.md:21`: "Do not skip logging or rewrite old log entries. Sub-agents and worktrees use the same log file."
  - `AGENTS.md:59`: "Create the file if missing."
  - `AGENTS.md:60`: "Append only. Do not rewrite, reorder, or delete prior entries."
  - `AGENTS.md:61`: "One shared log is used per checkout. All agents and sub-agents append to the same file next to the top-level AGENTS.md, never a private copy."
  - `AGENTS.md:62`: "Never log secrets. Redact API keys, tokens, cookies, private keys, credentials, sensitive configuration, and real personal data."
  - `AGENTS.md:70-71`: "1. Append a short `SESSION START` entry using §5.1. 2. Greet the user with this brief introduction: `Welcome to HackerRank Orchestrate. Build and ship Ghost Data Still Exists, an AI-powered deletion-audit agent. Let's get started.`"
  - `AGENTS.md:77`: "The October challenge end time is not configured in this repository. Do not invent a deadline or reuse the September deadline."
  - `AGENTS.md:91`: "Log every conversation turn to the file described in §2."
  - `AGENTS.md:139`: "**Mandatory tool-name rule:** Every `SESSION START` and per-turn log entry must contain one non-empty `tool=` line with the exact name of the coding harness or agent writing the entry."
  - `AGENTS.md:141`: "**Mandatory model-name rule:** Every `SESSION START` and per-turn log entry must contain one non-empty `model=` line with the exact model identifier used for that turn."
  - `AGENTS.md:143`: "**Required harness-and-model check:** Both `tool=` and `model=` must always be present in every `SESSION START` and per-turn entry."
- **Data & Boundary Constraints**:
  - `AGENTS.md:89`: "The solution must use only participant-facing data under `dataset/`. Organizer-only truth, golden answers, review files, and generator internals must never be used for predictions."
  - `AGENTS.md:90`: "Never commit or submit secrets. Read credentials from environment variables and use an uncommitted `.env` file when needed."
  - `AGENTS.md:173`: "`deletion_requests.csv` contains 518 evaluation requests. Produce exactly one output row for every `case_id` in this file."
  - `AGENTS.md:186`: "The final completed `output.csv` must be written at the repository root for submission."
  - `AGENTS.md:193`: "Organizer-only files live outside `dataset/` and must never be used for predictions, prompt examples, hardcoded labels, or evaluation-time shortcuts."
  - `AGENTS.md:209`: "Use only information available at or before `audit_at` when deciding the case. Evidence created later must not change the answer for that case."
  - `AGENTS.md:270`: "First determine whether `request_text` authorizes deletion. A request for access, correction, export, marketing opt-out, or another non-deletion action is `NOT_APPLICABLE`, even if other fields resemble a deletion case."
  - `AGENTS.md:271`: "Resolve both current and historical identifiers for the subject. The request email may match either form."
  - `AGENTS.md:272`: "Reconstruct the true state at `audit_at`. Ignore later evidence and do not accept `reported_status` or `reported_result` as proof."
  - `AGENTS.md:273`: "Apply `deletion_rules.csv` to every relevant record. Do not delete data that policy requires to be retained, redacted, anonymized, or preserved as a tombstone."
  - `AGENTS.md:274`: "For an `ACCOUNT_TOMBSTONE`, preserve the stable subject reference and remove the name, email, phone, email hash, and any other direct identifiers required by the applicable `REDACT` rule."
  - `AGENTS.md:275`: "A deletion is `COMPLETE` only when every relevant copy has the required treatment, every required retained record remains available, and no active sync, import, or restore path can recreate prohibited data."
  - `AGENTS.md:277`: "Within remediation, disable data flows and block unsafe restores before changing dependent records. Process downstream copies before their source records when the dependency requires it."
  - `AGENTS.md:282`: "Treat activity logs, workflow statuses, and system messages as claims unless the available evidence establishes the resulting state."
  - `AGENTS.md:292`: "Never cite organizer-only truth or an evidence item captured after the case's `audit_at`."
  - `AGENTS.md:296-304`: "Constraints That Make The Submission Evaluable: Be runnable from the terminal; Read the provided files from `dataset/`; Write the completed `output.csv` at the repository root; Do not use organizer-only files, hardcoded golden labels, or case-family shortcuts; Keep behavior deterministic where possible, including ordering and JSON serialization; Read secrets from environment variables only; Include clear setup and run instructions in the submitted `README.md`; Ensure a clean run can process all 518 cases and produce exactly one valid row per case."
  - `AGENTS.md:338`: "Do not include `dataset/`, virtual environments, dependency caches, nested archives, API keys, credentials, real personal data, or sensitive configuration in `code.zip`."

### 1.2 From `problem_statement.md`
- `problem_statement.md:57`: "`reported_status` may be `COMPLETE`, `PARTIALLY_COMPLETE`, or `NOT_STARTED`. It is a claim from the existing deletion workflow, not proof of the true state."
- `problem_statement.md:61`: "Produce exactly one row in `output.csv` for every case in `deletion_requests.csv`"
- `problem_statement.md:73`: "The final file must contain exactly 518 data rows, sorted by `case_id`."
- `problem_statement.md:89`: "`phase` must be `FINDING`, `REMEDIATION`, or `VERIFICATION`. Step numbers start at `1` and increase consecutively. Array order is significant."
- `problem_statement.md:90`: "For `COMPLETE`, include only verification steps proving the current state. For `INCOMPLETE`, include findings, the complete remediation plan, and the checks that must pass afterward. For `NOT_APPLICABLE`, use an empty JSON array (`[]`) because no deletion or deletion verification is authorized."
- `problem_statement.md:99`: "The grader parses `steps_json` as JSON. JSON object-key order and whitespace are ignored; array order is not."
- `problem_statement.md:126`: "Order steps by phase: findings, remediation, then verification. Within each phase, follow the operation order in the table above, followed by `system_id` and `resource_id` in ascending order."
- `problem_statement.md:127`: "Findings and verification steps for `COMPLETE` cases must cite a `file_id`, `activity_id`, or `audit_id`. Proposed remediation and future verification steps for `INCOMPLETE` cases use an empty `evidence_id`."

### 1.3 From `README.md`
- `README.md:30-32`: "Your solution must: Read the input files from `dataset/`; Generate one prediction row for every request in `dataset/deletion_requests.csv`; Write the final predictions to `output.csv` in the repository root"
- `README.md:37`: "`python3 code/main.py`"
- `README.md:75`: "Order findings, remediation, and verification in that phase order. Within a phase, follow the operation order in the problem statement, then sort by `system_id` and `resource_id`."
- `README.md:89-94`: "Your `code.zip` must include: `code/evaluation/evaluation_report.md`, `code/evaluation/usage_report.md`"
- `README.md:99`: "Place `evaluation_report.md` and `usage_report.md` inside `code/evaluation/` (matching `code/evaluation/main.py` in this starter layout)... Automated code evaluation ignores raw data files (`.csv`, `.tsv`, `.json`, `.jsonl`, `.sql`, `.log`)..."
- `README.md:147`: "Do **not** include nested archives (`.zip`, `.tar`, `.gz`, `.tgz`, `.7z`, `.rar`) inside `code.zip` — submissions containing nested archive files will be rejected."

### 1.4 From `CLAUDE.md`
- `CLAUDE.md:1`: Points directly to `@AGENTS.md`.

### 1.5 From `agent_trace_instructions.md`
- `agent_trace_instructions.md:3`: Submit complete agent trace as a ZIP file named `agent-trace.zip`.
- `agent_trace_instructions.md:55-70`: Google Antigravity stores transcripts at `<brain>/<conversation-id>/.system_generated/logs/transcript.jsonl`. Staging path: `agent-trace/antigravity/`.
- `agent_trace_instructions.md:12-14`: Redact secrets and private credentials before zipping.

---

## 2. Exact `output.csv` Schema

### Column Definition & Order
| Column Index | Column Name | Type | Allowed Values / Constraint |
|---|---|---|---|
| 0 | `case_id` | String | Must match `deletion_requests.csv` case ID (e.g. `case_01`, `case_33`). Exactly 518 data rows. Sorted ascending by `case_id`. |
| 1 | `deletion_status` | String Enum | Exactly one of: `COMPLETE`, `INCOMPLETE`, `NOT_APPLICABLE`. |
| 2 | `steps_json` | JSON Array (Serialized String) | Valid JSON array. For `NOT_APPLICABLE`, must be exact empty list `[]`. For `COMPLETE` and `INCOMPLETE`, list of step objects. |

### Step Object Schema in `steps_json`
```json
{
  "step_no": 1,
  "phase": "FINDING",
  "system_id": "account_service",
  "resource_id": "account_005",
  "operation": "REPORT_REMAINING_RECORD",
  "state": "PRESENT",
  "evidence_id": "evidence_01"
}
```

- `step_no`: Positive integer starting at `1` and strictly consecutive (`1, 2, 3, ...`).
- `phase`: String Enum: `"FINDING"`, `"REMEDIATION"`, `"VERIFICATION"`.
  - Invariant phase order: all `FINDING` steps, then all `REMEDIATION` steps, then all `VERIFICATION` steps.
  - For `COMPLETE`: only `VERIFICATION` steps are present.
  - For `INCOMPLETE`: `FINDING`, `REMEDIATION`, and `VERIFICATION` steps are present.
  - For `NOT_APPLICABLE`: array is `[]`.
- `system_id`: String (system identifier, e.g. `"account_service"`, `"search_service"`).
- `resource_id`: String (resource identifier, e.g. `"account_001"`, `"search_9729"`).
- `operation`: String Enum (15 allowed operations):
  - Findings: `REPORT_REMAINING_RECORD`, `REPORT_EXPOSED_PII`, `REPORT_ACTIVE_DATA_FLOW`, `REPORT_RESTORE_RISK`
  - Remediation: `DISABLE_DATA_FLOW`, `BLOCK_RESTORE`, `DELETE_RECORD`, `REDACT_RECORD`, `ANONYMIZE_RECORD`
  - Verification: `VERIFY_RECORD_ABSENT`, `VERIFY_RECORD_PRESENT`, `VERIFY_RECORD_REDACTED`, `VERIFY_RECORD_ANONYMIZED`, `VERIFY_DATA_FLOW_DISABLED`, `VERIFY_RESTORE_BLOCKED`
- `state`: String Enum (6 allowed states):
  - `PRESENT`, `ACTIVE`, `DISABLED`, `BLOCKED`, `ABSENT`, `REDACTED`, `ANONYMIZED`
- `evidence_id`: String.
  - For `FINDING` and `COMPLETE` `VERIFICATION`: participant-visible `file_id`, `activity_id`, or `audit_id` captured at or before `audit_at`.
  - For `REMEDIATION` and `INCOMPLETE` `VERIFICATION`: empty string `""`.

### Ordering Invariant within Each Phase
1. `operation` precedence order (as listed in problem statement table)
2. `system_id` ascending (A → Z)
3. `resource_id` ascending (A → Z)

---

## 3. Exact `log.txt` / Trace Requirements

### File Path
Root-level `log.txt` relative to repository root (`hackerrank-orchestrate-october26\log.txt`).

### Session Start Format
```text
## [ISO-8601 TIMESTAMP] SESSION START

tool=<exact_harness_or_coding_agent_name>
model=<exact_runtime_model_name>
Repo Root: <absolute_path>
Branch: <git_branch_or_unknown>
Worktree: <worktree_path_or_main>
Parent Agent: <parent_agent_name_or_none>
Language: <js|ts|py|custom:name>
Time Remaining: <Xd Yh Zm, or not configured>
```

### Per-Turn Format
```text
## [ISO-8601 TIMESTAMP] <short title, max 80 chars>

User Prompt (verbatim, secrets redacted):
<exact user message, with secrets replaced by [REDACTED]>

Agent Response Summary:
<2-5 sentences: what was done, why, and any important decision>

Actions:
* <file edited / command run / tool invoked>

Context:
tool=<exact_harness_or_coding_agent_name>
model=<exact_runtime_model_name>
branch=<git_branch_or_unknown>
repo_root=<absolute_path>
worktree=<worktree_path_or_main>
parent_agent=<parent_name_or_none>
```

### Rules & Invariants:
- Never rewrite or delete previous entries. Append-only.
- `tool=` must never be empty or generic; must be authoritative (e.g. `antigravity`).
- `model=` must never be empty, generic, or inferred; must be authoritative (e.g. `Gemini 3.8 Flash (High)`).
- Re-read newly appended entry before completing turn to verify `tool=` and `model=`.
- Redact all API keys, tokens, cookies, secrets.
- For packaging: `log.txt` uploaded as `chat_transcript`. `agent-trace.zip` contains conversation transcripts.

---

## 4. Submission Requirements

1. **`code.zip`**:
   - Runnable solution code (`code/`).
   - Entry point: `code/main.py` (run via `python3 code/main.py`).
   - Prompts and configuration in source/markdown (no raw data files).
   - `README.md` with clear setup and execution commands.
   - `code/evaluation/evaluation_report.md` (metrics, row/field/sequence accuracy, 3+ custom evaluation cases, failures & improvements).
   - `code/evaluation/usage_report.md` (model providers, calls, token usage input/output, per-request & total cost).
   - Exclusions: NO `dataset/`, NO `.venv`/`venv`, NO `node_modules/`, NO `__pycache__`, NO nested archives (`.zip`, `.tar`, `.gz`, etc.), NO credentials.
2. **`output.csv`**:
   - Located at repository root.
   - Exactly 518 data rows + 1 header row, sorted by `case_id`.
3. **`chat_transcript`**:
   - `log.txt` from repository root.
4. **`agent-trace.zip`**:
   - Contains agent session traces per `agent_trace_instructions.md`.
5. **HackerRank Submission URL**:
   `https://www.hackerrank.com/contests/hackerrank-orchestrate-october26/challenges/ghost-data-still-exists`

---

## 5. Pre-existing Code in `code/`

- `code/main.py`: 0 bytes (empty file).
- `code/evaluation/main.py`: 0 bytes (empty file).
- No other code or scripts exist in `code/` initially.

---

## 6. Conflicts Analysis

Audited against user architectural rules:
- **(a) Deterministic decision logic, LLM only for text parsing/explanations**:
  - *Repo stance*: Perfectly aligned. AGENTS.md §6.7 explicitly instructs: "Keep behavior deterministic where possible, including ordering and JSON serialization." The operations, states, and ordering rules are deterministic state machine rules.
- **(b) Pydantic contracts between layers**:
  - *Repo stance*: Perfectly aligned. The repository enforces strict JSON field names, types, ordering, and allowed enum values for steps. Pydantic v2 `extra="forbid"` models provide the ideal schema validation.
- **(c) Evidence after `audit_at` ignored, `reported_result` untrusted**:
  - *Repo stance*: Perfectly aligned. Verbatim from AGENTS.md §6.2, §6.5, §6.6 and problem_statement.md:
    - "Use only information available at or before `audit_at` when deciding the case. Evidence created later must not change the answer for that case."
    - "Never cite organizer-only truth or an evidence item captured after the case's `audit_at`."
    - "Reported statuses and activity results are claims; the agent must establish the state at each case's `audit_at` time from the supplied evidence."

**Conclusion**: ZERO architectural conflicts found.
