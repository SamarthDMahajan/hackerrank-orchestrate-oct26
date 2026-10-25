"""
JSON evidence parser for HackerRank Orchestrate (October 2026).
Parses service resource exports, snapshot bundles, analytics reports, and export jobs.
"""

import json
from typing import List, Any, Optional
from .models import ResourceObservation, StateSignal
from code.identity import IdentitySet


def _matches_identity(val: Any, identity: IdentitySet) -> Optional[str]:
    if not val or not isinstance(val, (str, int)):
        return None
    s = str(val).strip().lower()
    if s == identity.user_id.lower():
        return identity.user_id
    if s in identity.emails:
        return s
    if s in identity.email_hashes:
        return s
    if str(val).strip() in identity.phones:
        return str(val).strip()
    return None


def parse_json(file_path: str, file_id: str, captured_at: str, identity: IdentitySet,
               candidate_resources: Optional[set] = None) -> List[ResourceObservation]:
    observations = []
    with open(file_path, "r", encoding="utf-8", errors="replace") as f:
        try:
            data = json.load(f)
        except Exception:
            return []

    # 1. Structure: service_exports (e.g. evidence_92)
    if "service_exports" in data and isinstance(data["service_exports"], dict):
        se = data["service_exports"]

        # account_service
        acc = se.get("account_service", {})
        for lookup in acc.get("profile_lookups", []):
            res_id = lookup.get("resource_id", "")
            prof = lookup.get("profile")
            code = lookup.get("status_code")
            # match on prof if present
            matched = None
            if prof and isinstance(prof, dict):
                matched = (_matches_identity(prof.get("customer_reference"), identity) or
                           _matches_identity(prof.get("email"), identity) or
                           _matches_identity(prof.get("phone"), identity))
                if matched:
                    state = StateSignal.ABSENT if code == 404 else StateSignal.PRESENT
                    observations.append(ResourceObservation(
                        file_id=file_id, captured_at=captured_at, system_id="account_service",
                        resource_id=res_id, identifier_matched=matched, state_signal=state,
                        raw_excerpt=json.dumps(lookup)[:300], line_ref="profile_lookups"
                    ))
            elif code == 404 and res_id and (candidate_resources and res_id in candidate_resources):
                observations.append(ResourceObservation(
                    file_id=file_id, captured_at=captured_at, system_id="account_service",
                    resource_id=res_id, identifier_matched=identity.user_id, state_signal=StateSignal.ABSENT,
                    raw_excerpt=json.dumps(lookup)[:300], line_ref="profile_lookups"
                ))

        # analytics_platform
        ana = se.get("analytics_platform", {})
        for prof in ana.get("profiles", []):
            res_id = prof.get("resource_id", "")
            matched = (_matches_identity(prof.get("customer_reference"), identity) or
                       _matches_identity(prof.get("email"), identity) or
                       _matches_identity(prof.get("phone"), identity) or
                       _matches_identity(prof.get("email_hash"), identity))
            if matched:
                has_pii = bool(prof.get("email") or prof.get("phone") or prof.get("email_hash"))
                state = StateSignal.PRESENT if has_pii else StateSignal.ANONYMIZED
                observations.append(ResourceObservation(
                    file_id=file_id, captured_at=captured_at, system_id="analytics_platform",
                    resource_id=res_id, identifier_matched=matched, state_signal=state,
                    raw_excerpt=json.dumps(prof)[:300], line_ref="profiles"
                ))
            elif res_id and (candidate_resources and res_id in candidate_resources):
                has_pii = bool(prof.get("email") or prof.get("phone") or prof.get("email_hash") or prof.get("customer_reference"))
                if not has_pii:
                    observations.append(ResourceObservation(
                        file_id=file_id, captured_at=captured_at, system_id="analytics_platform",
                        resource_id=res_id, identifier_matched=identity.user_id, state_signal=StateSignal.ANONYMIZED,
                        raw_excerpt=json.dumps(prof)[:300], line_ref="profiles"
                    ))

        # backup_service
        bak = se.get("backup_service", {})
        for entry in bak.get("restore_entries", []):
            res_id = entry.get("resource_id", "")
            matched = (_matches_identity(entry.get("customer_reference"), identity) or
                       _matches_identity(entry.get("customer_email"), identity))
            if matched:
                allowed = entry.get("restore_allowed", False)
                state = StateSignal.ACTIVE if allowed else StateSignal.BLOCKED
                observations.append(ResourceObservation(
                    file_id=file_id, captured_at=captured_at, system_id="backup_service",
                    resource_id=res_id, identifier_matched=matched, state_signal=state,
                    raw_excerpt=json.dumps(entry)[:300], line_ref="restore_entries"
                ))

        # export_service
        exp = se.get("export_service", {})
        for item in exp.get("exports", []):
            res_id = item.get("resource_id", "")
            matched = (_matches_identity(item.get("customer_reference"), identity) or
                       _matches_identity(item.get("owner_email"), identity) or
                       _matches_identity(item.get("owner_phone"), identity))
            if matched:
                observations.append(ResourceObservation(
                    file_id=file_id, captured_at=captured_at, system_id="export_service",
                    resource_id=res_id, identifier_matched=matched, state_signal=StateSignal.PRESENT,
                    raw_excerpt=json.dumps(item)[:300], line_ref="exports"
                ))

        # integration_service
        integ = se.get("integration_service", {})
        for conn in integ.get("connectors", []):
            res_id = conn.get("resource_id", "")
            matched = (_matches_identity(conn.get("customer_reference"), identity) or
                       _matches_identity(conn.get("customer_email"), identity))
            if matched:
                enabled = conn.get("enabled", False)
                state = StateSignal.ACTIVE if enabled else StateSignal.DISABLED
                observations.append(ResourceObservation(
                    file_id=file_id, captured_at=captured_at, system_id="integration_service",
                    resource_id=res_id, identifier_matched=matched, state_signal=state,
                    raw_excerpt=json.dumps(conn)[:300], line_ref="connectors"
                ))

        # search_service
        sea = se.get("search_service", {})
        for q in sea.get("index_queries", []):
            res_id = q.get("resource_id", "")
            matched = _matches_identity(q.get("query"), identity)
            hits = q.get("hits", {}).get("documents", [])
            for doc in hits:
                d_matched = (_matches_identity(doc.get("customer_reference"), identity) or
                             _matches_identity(doc.get("email"), identity) or
                             _matches_identity(doc.get("phone"), identity) or
                             _matches_identity(doc.get("email_hash"), identity))
                if d_matched or matched:
                    m = d_matched or matched
                    observations.append(ResourceObservation(
                        file_id=file_id, captured_at=captured_at, system_id="search_service",
                        resource_id=res_id or doc.get("resource_id", ""), identifier_matched=m,
                        state_signal=StateSignal.PRESENT, raw_excerpt=json.dumps(doc)[:300], line_ref="index_queries"
                    ))

        # security_service
        sec = se.get("security_service", {})
        for audit in sec.get("audit_records", []):
            res_id = audit.get("resource_id", "")
            matched = _matches_identity(audit.get("subject_reference"), identity)
            if matched:
                observations.append(ResourceObservation(
                    file_id=file_id, captured_at=captured_at, system_id="security_service",
                    resource_id=res_id, identifier_matched=matched, state_signal=StateSignal.PRESENT,
                    raw_excerpt=json.dumps(audit)[:300], line_ref="audit_records"
                ))

        # support_platform
        sup = se.get("support_platform", {})
        for ticket in sup.get("tickets", []):
            res_id = ticket.get("resource_id", "")
            matched = (_matches_identity(ticket.get("customer_reference"), identity) or
                       _matches_identity(ticket.get("requester_email"), identity) or
                       _matches_identity(ticket.get("requester_name"), identity) or
                       _matches_identity(ticket.get("requester_phone"), identity))
            if matched:
                has_pii = bool(ticket.get("requester_email") or ticket.get("requester_name") or ticket.get("requester_phone"))
                state = StateSignal.PRESENT if has_pii else StateSignal.REDACTED
                observations.append(ResourceObservation(
                    file_id=file_id, captured_at=captured_at, system_id="support_platform",
                    resource_id=res_id, identifier_matched=matched, state_signal=state,
                    raw_excerpt=json.dumps(ticket)[:300], line_ref="tickets"
                ))

    # 2. Structure: snapshots array (e.g. evidence_51)
    if "snapshots" in data and isinstance(data["snapshots"], list):
        for snap in data["snapshots"]:
            data_store = snap.get("data_store", "")
            collection = snap.get("collection", "")
            records = snap.get("records", [])

            if collection == "customer_profiles" and len(records) == 0 and candidate_resources:
                for c_res in candidate_resources:
                    if c_res.startswith("account_"):
                        observations.append(ResourceObservation(
                            file_id=file_id, captured_at=captured_at, system_id=data_store or "account_service",
                            resource_id=c_res, identifier_matched=identity.user_id, state_signal=StateSignal.ABSENT,
                            raw_excerpt=json.dumps(snap)[:300], line_ref=collection
                        ))

            for rec in records:
                res_id = rec.get("resource_id", "")
                matched = (_matches_identity(rec.get("customer_reference"), identity) or
                           _matches_identity(rec.get("subject_reference"), identity) or
                           _matches_identity(rec.get("email"), identity) or
                           _matches_identity(rec.get("phone"), identity) or
                           _matches_identity(rec.get("email_hash"), identity))
                if matched:
                    if collection == "deleted_customer_references" or "tombstone" in res_id:
                        has_pii = bool(rec.get("name") or rec.get("email") or rec.get("phone") or rec.get("email_hash"))
                        state = StateSignal.PRESENT if has_pii else StateSignal.REDACTED
                        system_id = data_store or "identity_service"
                    elif collection == "security_audit_events":
                        state = StateSignal.PRESENT
                        system_id = data_store or "security_service"
                    elif collection == "customer_analytics_reports":
                        has_pii = bool(rec.get("email") or rec.get("phone") or rec.get("email_hash"))
                        state = StateSignal.PRESENT if has_pii else StateSignal.ANONYMIZED
                        system_id = data_store or "analytics_platform"
                    else:
                        state = StateSignal.PRESENT
                        system_id = data_store or "platform_service"

                    observations.append(ResourceObservation(
                        file_id=file_id, captured_at=captured_at, system_id=system_id,
                        resource_id=res_id, identifier_matched=matched, state_signal=state,
                        raw_excerpt=json.dumps(rec)[:300], line_ref=collection
                    ))

    # 3. Structure: records list (e.g. customer_analytics_report_*.json, customer_export_jobs_*.json, connector_configurations_*.json, customer_export_manifest_*.json)
    if "records" in data and isinstance(data["records"], list):
        source = data.get("source", "")
        collection = data.get("collection", "")
        for rec in data["records"]:
            res_id = rec.get("resource_id", "")
            rec_sys = rec.get("system")
            rec_res = rec.get("result")
            matched = (_matches_identity(rec.get("user_id"), identity) or
                       _matches_identity(rec.get("customer_reference"), identity) or
                       _matches_identity(rec.get("owner_email"), identity) or
                       _matches_identity(rec.get("email"), identity) or
                       _matches_identity(rec.get("phone"), identity) or
                       _matches_identity(rec.get("email_hash"), identity) or
                       _matches_identity(rec.get("subject_reference"), identity))
            if matched:
                if rec_sys:
                    system_id = rec_sys
                    if rec_res:
                        res_up = str(rec_res).upper()
                        if res_up in ("NOT_FOUND", "ABSENT"):
                            state = StateSignal.ABSENT
                        elif res_up in ("FOUND", "IDENTIFIABLE", "PRESENT"):
                            state = StateSignal.PRESENT
                        elif res_up == "ANONYMIZED":
                            state = StateSignal.ANONYMIZED
                        elif res_up in ("ACTIVE", "ENABLED"):
                            state = StateSignal.ACTIVE
                        elif res_up == "DISABLED":
                            state = StateSignal.DISABLED
                        elif res_up == "BLOCKED":
                            state = StateSignal.BLOCKED
                        else:
                            state = StateSignal.PRESENT
                    else:
                        state = StateSignal.PRESENT
                elif "analytics" in collection or "analytics" in source:
                    has_pii = bool(rec.get("email") or rec.get("phone") or rec.get("email_hash"))
                    state = StateSignal.PRESENT if has_pii else StateSignal.ANONYMIZED
                    system_id = "analytics_platform"
                elif "export" in collection or "export" in source:
                    state = StateSignal.PRESENT
                    system_id = "export_service"
                elif "connector" in collection or "connector" in source:
                    enabled = rec.get("enabled", False)
                    state = StateSignal.ACTIVE if enabled else StateSignal.DISABLED
                    system_id = "integration_service"
                elif "security" in collection or "audit" in source:
                    state = StateSignal.PRESENT
                    system_id = "security_service"
                else:
                    state = StateSignal.PRESENT
                    system_id = source or "platform_service"

                rec_time = (rec.get("recorded_at") or rec.get("observed_at") or
                            rec.get("event_time") or rec.get("created_at") or
                            rec.get("timestamp") or rec.get("updated_at"))
                observations.append(ResourceObservation(
                    file_id=file_id, captured_at=captured_at, system_id=system_id,
                    resource_id=res_id, identifier_matched=matched, state_signal=state,
                    raw_excerpt=json.dumps(rec)[:300], line_ref=collection or "records",
                    observed_timestamp=rec_time
                ))
            elif res_id and (candidate_resources and res_id in candidate_resources):
                if "analytics" in collection or "analytics" in source:
                    has_pii = bool(rec.get("email") or rec.get("phone") or rec.get("email_hash") or rec.get("user_id"))
                    state = StateSignal.PRESENT if has_pii else StateSignal.ANONYMIZED
                    rec_time = (rec.get("recorded_at") or rec.get("observed_at") or
                                rec.get("event_time") or rec.get("created_at") or
                                rec.get("timestamp") or rec.get("updated_at"))
                    observations.append(ResourceObservation(
                        file_id=file_id, captured_at=captured_at, system_id="analytics_platform",
                        resource_id=res_id, identifier_matched=identity.user_id, state_signal=state,
                        raw_excerpt=json.dumps(rec)[:300], line_ref=collection or "records",
                        observed_timestamp=rec_time
                    ))

    return observations
