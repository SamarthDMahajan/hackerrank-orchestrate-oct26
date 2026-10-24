"""
Log evidence parser for HackerRank Orchestrate (October 2026).
Parses key-value observability logs and resource readback traces.
"""

import re
from typing import List, Dict, Optional
from .models import ResourceObservation, StateSignal
from code.identity import IdentitySet


def _matches(val: Optional[str], identity: IdentitySet) -> Optional[str]:
    if not val:
        return None
    s = str(val).strip().strip('"\'').lower()
    if s == identity.user_id.lower():
        return identity.user_id
    if s in identity.emails:
        return s
    if s in identity.email_hashes:
        return s
    if str(val).strip().strip('"\'') in identity.phones:
        return str(val).strip().strip('"\'')
    return None


def parse_log(file_path: str, file_id: str, captured_at: str, identity: IdentitySet,
              candidate_resources: Optional[set] = None) -> List[ResourceObservation]:
    observations = []

    # Regex for key=value or key="quoted value"
    kv_pattern = re.compile(r'([a-zA-Z0-9_]+)=(?:"([^"]*)"|([^\s]+))')

    # Keep track of trace context across started/completed event pairs
    trace_context: Dict[str, dict] = {}

    with open(file_path, "r", encoding="utf-8", errors="replace") as f:
        for line_no, raw_line in enumerate(f, start=1):
            line = raw_line.strip()
            if not line:
                continue

            kvs = {}
            for m in kv_pattern.finditer(line):
                k = m.group(1)
                v = m.group(2) if m.group(2) is not None else m.group(3)
                kvs[k] = v

            trace_id = kvs.get("trace_id")
            service = kvs.get("service", "")
            event = kvs.get("event", "")
            res_id = kvs.get("resource_id", "")

            # Check for identity match across all keys in kvs
            matched = None
            for k in ["lookup_key", "match_key", "user_id", "customer_reference", "subject_key",
                      "correlation_key", "matched_value", "subject_ref", "customer_email", "email"]:
                if k in kvs:
                    matched = _matches(kvs[k], identity)
                    if matched:
                        break

            if not matched:
                for v in kvs.values():
                    matched = _matches(v, identity)
                    if matched:
                        break

            if trace_id:
                if trace_id not in trace_context:
                    trace_context[trace_id] = {}
                if matched:
                    trace_context[trace_id]["matched"] = matched
                if res_id:
                    trace_context[trace_id]["resource_id"] = res_id
                if service:
                    trace_context[trace_id]["service"] = service

                ctx_matched = trace_context[trace_id].get("matched") or matched
                ctx_res_id = trace_context[trace_id].get("resource_id") or res_id
                ctx_service = trace_context[trace_id].get("service") or service
            else:
                ctx_matched = matched
                ctx_res_id = res_id
                ctx_service = service

            if ctx_matched and ctx_res_id:
                # Determine state signal
                state = StateSignal.UNPARSED
                http_status = kvs.get("http_status")
                rows = kvs.get("rows")
                enabled = kvs.get("enabled")
                restore_access = kvs.get("restore_access")
                deletion_block = kvs.get("deletion_block")
                result = kvs.get("result")

                if http_status == "404" or rows == "0":
                    state = StateSignal.ABSENT
                elif event == "analytics_profile_read_completed":
                    has_pii = (kvs.get("email") not in (None, "null") or
                               kvs.get("phone") not in (None, "null") or
                               kvs.get("email_hash") not in (None, "null"))
                    state = StateSignal.PRESENT if has_pii else StateSignal.ANONYMIZED
                elif event == "support_ticket_read_completed":
                    has_pii = (kvs.get("requester_email") not in (None, "null") or
                               kvs.get("requester_name") not in (None, "null") or
                               kvs.get("requester_phone") not in (None, "null"))
                    state = StateSignal.PRESENT if has_pii else StateSignal.REDACTED
                elif rows == "1" or event.endswith("_completed") or result == "hit" or event == "message_pii_scan":
                    state = StateSignal.PRESENT

                if enabled is not None:
                    en_bool = str(enabled).lower() in ("true", "1")
                    state = StateSignal.ACTIVE if en_bool else StateSignal.DISABLED

                if deletion_block is not None:
                    # deletion_block=false means restore is NOT blocked -> active restore risk!
                    del_blocked = str(deletion_block).lower() in ("true", "1")
                    state = StateSignal.BLOCKED if del_blocked else StateSignal.ACTIVE

                if restore_access is not None:
                    rest_bool = str(restore_access).lower() in ("enabled", "true", "1", "allowed")
                    state = StateSignal.ACTIVE if rest_bool else StateSignal.BLOCKED

                if state != StateSignal.UNPARSED:
                    observations.append(ResourceObservation(
                        file_id=file_id, captured_at=captured_at, system_id=ctx_service,
                        resource_id=ctx_res_id, identifier_matched=ctx_matched, state_signal=state,
                        raw_excerpt=line[:300], line_ref=str(line_no)
                    ))
            elif candidate_resources and res_id in candidate_resources:
                if event == "analytics_profile_read_completed":
                    has_pii = (kvs.get("email") not in (None, "null") or
                               kvs.get("phone") not in (None, "null") or
                               kvs.get("email_hash") not in (None, "null") or
                               kvs.get("customer_reference") not in (None, "null"))
                    state = StateSignal.PRESENT if has_pii else StateSignal.ANONYMIZED
                    observations.append(ResourceObservation(
                        file_id=file_id, captured_at=captured_at, system_id=service or "analytics_platform",
                        resource_id=res_id, identifier_matched=identity.user_id, state_signal=state,
                        raw_excerpt=line[:300], line_ref=str(line_no)
                    ))

    return observations

