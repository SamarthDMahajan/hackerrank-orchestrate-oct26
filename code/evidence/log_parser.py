"""
Log evidence parser for HackerRank Orchestrate (October 2026).
Parses key-value observability logs and resource readback traces.
"""

import json
import re
from typing import List, Dict, Optional
from .models import ResourceObservation, StateSignal
from code.identity import IdentitySet


def _matches(val: Optional[str], identity: IdentitySet) -> Optional[str]:
    if not val:
        return None
    s = str(val).replace('\\', '').strip('"\'').lower()
    if s == identity.user_id.lower():
        return identity.user_id
    if s in identity.emails:
        return s
    if s in identity.email_hashes:
        return s
    if str(val).replace('\\', '').strip('"\'') in identity.phones:
        return str(val).replace('\\', '').strip('"\'')
    return None


def parse_log(file_path: str, file_id: str, captured_at: str, identity: IdentitySet,
              candidate_resources: Optional[set] = None) -> List[ResourceObservation]:
    observations = []

    # Regex for key=value or key="quoted value"
    kv_pattern = re.compile(r'([a-zA-Z0-9_]+)=(?:"([^"]*)"|([^\s]+))')

    # Regexes for structured log headers
    syslog_re = re.compile(r'^\S+\s+<\d+>\d+\s+\S+\s+(\w+)\s+([\w\-]+)\s+-\s+-\s+(.*)$')
    pipe_re = re.compile(r'^\S+\s*\|\s*\w+\s*\|\s*(\w+)\s*\|\s*([\w\-]+)\s*\|\s*(\w+)\s*\|\s*(.*)$')
    bracket_re = re.compile(r'^\S+\s*\[\w+\]\s*\[(\w+)\]\s*\[([\w\-]+)\]\s*(\w+):\s*(.*)$')

    # Keep track of trace context across started/completed event pairs
    trace_context: Dict[str, dict] = {}

    with open(file_path, "r", encoding="utf-8", errors="replace") as f:
        for line_no, raw_line in enumerate(f, start=1):
            line = raw_line.strip()
            if not line:
                continue

            line_ts = None
            ts_m = re.match(r'^(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?Z)', line)
            if ts_m:
                line_ts = ts_m.group(1)

            hdr_service = None
            hdr_trace = None
            hdr_event = None
            kv_text = line

            sm = syslog_re.match(line)
            if sm:
                hdr_service = sm.group(1)
                hdr_trace = sm.group(2)
                kv_text = sm.group(3)
            else:
                pm = pipe_re.match(line)
                if pm:
                    hdr_service = pm.group(1)
                    hdr_trace = pm.group(2)
                    hdr_event = pm.group(3)
                    kv_text = pm.group(4)
                else:
                    bm = bracket_re.match(line)
                    if bm:
                        hdr_service = bm.group(1)
                        hdr_trace = bm.group(2)
                        hdr_event = bm.group(3)
                        kv_text = bm.group(4)

            json_m = re.match(r'^(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?Z)?\s*(\{.*\})$', line)
            if json_m:
                if json_m.group(1):
                    line_ts = json_m.group(1)
                try:
                    loaded = json.loads(json_m.group(2))
                    kvs = {str(k): str(v).replace('\\', '').strip('"\'') for k, v in loaded.items() if v is not None}
                except Exception:
                    kvs = {}
            else:
                kvs = {}
                for m in kv_pattern.finditer(kv_text):
                    k = m.group(1)
                    v = m.group(2) if m.group(2) is not None else m.group(3)
                    if v is not None:
                        v = v.replace('\\', '').strip('"\'')
                    kvs[k] = v

            trace_id = kvs.get("trace_id") or kvs.get("requestId") or kvs.get("request_id") or hdr_trace
            service = kvs.get("system") or kvs.get("service") or kvs.get("function") or hdr_service or ""
            event = kvs.get("event") or hdr_event or ""
            res_id = kvs.get("resource_id", "")

            # Check for identity match across all keys in kvs
            matched = None
            for k in ["lookup_key", "match_key", "user_id", "customer_reference", "subject_key",
                      "correlation_key", "matched_value", "subject_ref", "customer_email", "email",
                      "subject_reference", "scan_key"]:
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
                restore_allowed = kvs.get("restore_allowed")
                archive_present = kvs.get("archive_present")
                deletion_block = kvs.get("deletion_block")
                result = kvs.get("result")

                if result:
                    res_upper = str(result).upper()
                    if res_upper in ("NOT_FOUND", "ABSENT"):
                        state = StateSignal.ABSENT
                    elif res_upper in ("FOUND", "IDENTIFIABLE", "HIT", "PRESENT"):
                        state = StateSignal.PRESENT
                    elif res_upper == "ANONYMIZED":
                        state = StateSignal.ANONYMIZED
                    elif res_upper in ("ACTIVE", "ENABLED"):
                        state = StateSignal.ACTIVE
                    elif res_upper == "DISABLED":
                        state = StateSignal.DISABLED
                    elif res_upper == "BLOCKED":
                        state = StateSignal.BLOCKED

                if state == StateSignal.UNPARSED:
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

                if restore_allowed is not None:
                    rest_bool = str(restore_allowed).lower() in ("true", "1")
                    state = StateSignal.ACTIVE if rest_bool else StateSignal.BLOCKED
                elif archive_present is not None:
                    arch_bool = str(archive_present).lower() in ("true", "1")
                    state = StateSignal.ACTIVE if arch_bool else StateSignal.BLOCKED
                elif restore_access is not None:
                    rest_bool = str(restore_access).lower() in ("enabled", "true", "1", "allowed")
                    state = StateSignal.ACTIVE if rest_bool else StateSignal.BLOCKED
                elif ctx_service == "backup_service" and state == StateSignal.PRESENT:
                    state = StateSignal.ACTIVE

                if ctx_service in ("support_replica", "support_service", "support"):
                    ctx_service = "support_platform"

                if state != StateSignal.UNPARSED:
                    observations.append(ResourceObservation(
                        file_id=file_id, captured_at=captured_at, system_id=ctx_service,
                        resource_id=ctx_res_id, identifier_matched=ctx_matched, state_signal=state,
                        raw_excerpt=line[:300], line_ref=str(line_no),
                        observed_timestamp=line_ts
                    ))
            elif candidate_resources and res_id in candidate_resources:
                if event == "analytics_profile_read_completed":
                    has_pii = (kvs.get("email") not in (None, "null") or
                               kvs.get("phone") not in (None, "null") or
                               kvs.get("email_hash") not in (None, "null") or
                               kvs.get("customer_reference") not in (None, "null"))
                    if not has_pii:
                        observations.append(ResourceObservation(
                            file_id=file_id, captured_at=captured_at, system_id=service or "analytics_platform",
                            resource_id=res_id, identifier_matched=identity.user_id, state_signal=StateSignal.ANONYMIZED,
                            raw_excerpt=line[:300], line_ref=str(line_no),
                            observed_timestamp=line_ts
                        ))

    return observations

