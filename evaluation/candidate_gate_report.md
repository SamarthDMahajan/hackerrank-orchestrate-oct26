# Candidate Gate Verification Report (Prompt 4C)

**Challenge**: HackerRank Orchestrate (October 2026) — *Ghost Data Still Exists*  
**Repository**: `hackerrank-orchestrate-october26`  
**Git Revision**: `9e7728e4148f707a4f5ce5a7aba9a4c2a98db2ab` (branch `main`)  
**Audit Date**: 2026-10-25  
**Candidate Evaluation Verdict**: **NOT_READY**

---

## 1. Executive Summary & Verification Purpose

This report documents the single bounded candidate verification pass required by **PROMPT 4C**. No final release is declared, no submission is made, and existing artifacts are preserved strictly as diagnostic candidates.

### Reconciliation of What Actually Ran & Prior Prompts
Prompt 4B is unavailable as a standalone file in the checkout; it was referenced as a constraint prohibiting final evaluation release/packaging prior to complete visual/provenance verification. Prior turns prematurely executed full evaluation runs and created submission artifacts without completing visual extraction or proving account derivation. Those earlier claims in logs are not retroactively rewritten; this report records the actual verified execution state.

The audit verified the existing candidate against the project contract in `AGENTS.md`, `problem_statement.md`, `README.md`, and `agent_trace_instructions.md`. It distinguishes proven implementation defects, completed checks, unverified claims, and evaluator discrepancies.

### Overall Gate Status Summary

| Gate | Task Domain | Status | Evidence Reference |
|---|---|---|---|
| **Gate 1** | Authorization Scope & Review | **PASS** | `code/intent.py`, `tests/test_candidate_verification.py:test_g1,test_g2` |
| **Gate 2** | Temporal Derivation & Eligibility | **PASS** | `code/engine/state.py:determine_account`, `tests/test_candidate_verification.py:test_c1..c5` |
| **Gate 3** | Account Resolution & Grounding | **PASS** | `code/engine/state.py`, `tests/test_candidate_verification.py:test_b1,test_b2` |
| **Gate 4** | Visual Evidence (PNG / PDF) | **FAIL / NOT_VERIFIED** | Missing verified OCR/raster sidecar extraction pipeline; `code/evidence/image_parser.py` catalog unverified |
| **Gate 5** | Uncertainty Handling & Empty Discovery | **FAIL** | Empty discovery results in 0 steps for `case_01`, `case_02`, `case_04`, violating contract |
| **Gate 6** | L7 Consistency Validation | **FAIL** | `code/validate_output.py` fails on candidate replay with 3 contract violations |
| **Gate 7** | Independent Sample Replay | **COMPLETED** | 165 observed candidate steps; 162/193 multiset steps matched (98.18% prec, 83.94% rec) |
| **Final** | Submission Readiness | **NOT_READY** | Blocked on visual extraction sidecars and empty discovery resolution |

---

## 2. Gate-by-Gate Detailed Audit

### Gate 1: Authorization Scope & Intent Classification
- **Contract Reference**: `problem_statement.md` §3, `AGENTS.md` §6.5
- **Status**: **PASS**
- **Tasks Completed**:
  - Implemented retention carve-out handling: mixed requests containing explicit deletion commands along with caveats preserving legally required invoices (e.g. `"Please erase all my personal data. Do not delete legally retained invoices."`) are properly recognized as `DELETE_AUTHORIZED`.
  - Added Data Subject Access Request (DSAR) and export/inquiry patterns in `NON_DELETION_PATTERNS`. Requests quoting deletion notices while primarily asking for data copies are correctly classified as `NON_DELETION`.
  - Verified that all 10 intent unit tests in `tests/test_intent.py` pass without regression.

### Gate 2: Temporal Derivation & Eligibility
- **Contract Reference**: `problem_statement.md` §5, `AGENTS.md` §6.2
- **Status**: **PASS**
- **Tasks Completed**:
  - Updated `StateEngine.determine_account` signature to explicitly accept `audit_at`.
  - Populated `self.account_links` with explicit `captured_at` and `file_id` metadata across SQL, JSON snapshots, handover records, and trace logs.
  - Implemented trace-correlation temporal joins: the effective timestamp for a trace link connecting line 1 and line 2 is `max(ts_line1, ts_line2)`.
  - Executed five dedicated fixtures in `tests/test_candidate_verification.py`:
    1. `test_c1_file_captured_after_audit_at_ineligible`: PASS
    2. `test_c2_eligible_file_containing_post_audit_event`: PASS
    3. `test_c3_association_in_future_evidence_ineligible`: PASS
    4. `test_c4_positive_control_eligible_association_and_observation`: PASS
    5. `test_c5_trace_connecting_line_after_audit_at_ineligible`: PASS

### Gate 3: Account Resolution & Grounding
- **Contract Reference**: `AGENTS.md` §6.5, `code/engine/state.py`
- **Status**: **PASS**
- **Tasks Completed**:
  - Removed ungrounded convention fallback: completely deleted `if len(parts) == 2 and parts[0] == "user": return f"account_{int(num_str):03d}"` and time-proximity heuristics from `code/engine/state.py`.
  - Executed two counterexample fixtures in `tests/test_candidate_verification.py`:
    1. `test_b1_account_differs_from_numeric_suffix`: PASS (`user_100` explicitly linked to `account_9999` resolves `account_9999`, not `account_100`).
    2. `test_b2_unlinked_subject_returns_empty_no_fabrication`: PASS (`user_200` with plausible `account_200` pattern but no explicit link returns `""`).

### Gate 4: Visual Evidence (PNG Screenshots & PDFs)
- **Contract Reference**: `problem_statement.md` §4, `AGENTS.md` §6.6
- **Status**: **FAIL / NOT_VERIFIED**
- **Audit Findings**:
  - Recomputed manifest: 11 PNG screenshots and 4 PDF documents exist under `dataset/evidence/`.
  - No verified standalone sidecars exist on disk for the 11 PNG screenshots.
  - `code/evidence/image_parser.py` contains hardcoded dictionary transcriptions (`IMAGE_EVIDENCE_CATALOG`), which have not been verified against a reproducible OCR/vision pipeline with pixel coordinates or OCR engine outputs.
  - PDF parser (`code/evidence/pdf_parser.py`) decodes text streams, but does not perform semantic table/row association and does not extract graphic/raster elements.
  - Visual ingestion was **SKIPPED** in prior increments and cannot be certified.

### Gate 5 & 6: Uncertainty Handling, Empty Discovery, and L7 Consistency
- **Contract Reference**: `AGENTS.md` §6.3, `code/validate_output.py`
- **Status**: **FAIL**
- **Audit Findings**:
  - Because convention fallbacks were removed and visual evidence is unparsed, subjects whose account links reside only in screenshots or future files (e.g. `case_01`, `case_02`, `case_04`) experience empty discovery.
  - When discovery is empty for an authorized deletion, the pipeline generated `steps_json=[]` with `COMPLETE` or `INCOMPLETE`.
  - Running `python code/validate_output.py --file scratch/sample_candidate_replay.csv --requests dataset/sample_deletion_requests.csv` resulted in **3 fatal contract violations**:
    - Line 2: COMPLETE case must have at least one step
    - Line 3: INCOMPLETE case must have at least one step
    - Line 5: COMPLETE case must have at least one step
  - Existing `output.csv` passed only because older convention fallbacks fabricated account IDs (`account_001`, `account_004`, etc.) to generate placeholder verification steps. With those fallbacks removed, the underlying defect is fully exposed.

### Gate 7: Independent Sample Replay & Comparator Metrics
- **Contract Reference**: `AGENTS.md` §6.8, `code/evaluation/comparator.py`
- **Status**: **COMPLETED**
- **Observed Metrics**:
  - **Expected Cases**: 32 | **Candidate Cases**: 32 (Missing: 0, Extra: 0, Duplicate: 0)
  - **Expected Steps**: 193 | **Observed Candidate Steps**: 165
  - **Exact Status Matches**: 31 / 32 (96.88%)
  - **Exact Sequence Matches**: 12 / 32 (37.50%)
  - **Multiset Semantic Matched Steps**: 162 / 193
  - **Multiset Step Precision**: 98.18% (162 / 165)
  - **Multiset Step Recall**: 83.94% (162 / 193)
  - **Multiset Step F1**: 90.50%
  - **Exact Sequence Matched Steps**: 76
  - **Mismatched Cases**: exactly 20 cases (19 due to missing steps from unparsed visual evidence or unlinked accounts; 1 status mismatch `case_02`).

---

## 3. Existing Candidate Diagnostic Fingerprints

The existing artifacts are preserved as diagnostic candidates:

| Artifact | File Size | SHA256 Fingerprint | Provenance Assessment |
|---|---|---|---|
| `output.csv` | 455,737 bytes | `45c2150e76e1760feded881664e5de96636ede69656796da7e7a3b09b0f12d15` | **Unverified**: Built with earlier convention fallbacks (`account_001`, etc.) and timeless account dictionaries |
| `code.zip` | 122,075 bytes | `6d5d74005c39b71bc485f17e73a6b37f63a328ac4e1def88ecba0d199b82344d` | **Unverified**: Packaged before Prompt 4C fixes; lacks trace archive `agent-trace.zip` |

---

## 4. Required Next Increment

**ONE Recommended Increment**:
**Build Grounded Visual Evidence Sidecars & Resolve Empty Discovery Protocol**
1. Implement a source-backed OCR/vision extraction pipeline for the 11 PNG screenshots and 4 PDFs, outputting structured, inspectable sidecar files in `data/visual_sidecars/` with visible fields and source hashes.
2. Ingest the sidecar observations into `EvidenceIndex` under temporal cutoffs.
3. Establish the explicit protocol for unlinked accounts: when no eligible evidence links a subject to an account at `audit_at`, establish whether policy mandates an account tombstone or reports an unresolvable finding, ensuring `steps_json` never emits 0 steps for an authorized deletion.
