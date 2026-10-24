"""
SQL evidence parser for HackerRank Orchestrate (October 2026).
Loads point-in-time SQL database dumps in memory using SQLite and extracts resource observations.
"""

import sqlite3
import json
from typing import List, Optional
from .models import ResourceObservation, StateSignal
from code.identity import IdentitySet


def _matches(val: Optional[str], identity: IdentitySet) -> Optional[str]:
    if not val:
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


def parse_sql(file_path: str, file_id: str, captured_at: str, identity: IdentitySet,
              candidate_resources: Optional[set] = None) -> List[ResourceObservation]:
    observations = []
    with open(file_path, "r", encoding="utf-8", errors="replace") as f:
        sql = f.read()

    conn = sqlite3.connect(":memory:")
    try:
        conn.executescript(sql)
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = [r[0] for r in cursor.fetchall()]

        for tbl in tables:
            # Check table columns
            cursor.execute(f"PRAGMA table_info({tbl})")
            cols = [r[1] for r in cursor.fetchall()]

            # Replica absence check for failover replica
            if "customer_profiles_failover_replica" in tbl and candidate_resources:
                cursor.execute(f"SELECT resource_id FROM {tbl}")
                present_res = {r[0] for r in cursor.fetchall()}
                for c_res in candidate_resources:
                    if c_res.startswith("account_") and c_res not in present_res:
                        observations.append(ResourceObservation(
                            file_id=file_id, captured_at=captured_at, system_id="account_service",
                            resource_id=c_res, identifier_matched=identity.user_id, state_signal=StateSignal.ABSENT,
                            raw_excerpt=f"Resource {c_res} confirmed absent from {tbl}", line_ref=tbl
                        ))

            # Case A: tables with record_json (customer_data_primary, customer_data_read_replica, etc.)
            if "record_json" in cols:
                cursor.execute(f"SELECT resource_id, origin_system, collection_name, record_json FROM {tbl}")

                for res_id, origin_sys, coll_name, rec_json_str in cursor.fetchall():
                    try:
                        rec = json.loads(rec_json_str)
                    except Exception:
                        continue

                    # Search top-level fields
                    matched = (_matches(rec.get("user_id"), identity) or
                               _matches(rec.get("customer_reference"), identity) or
                               _matches(rec.get("subject_reference"), identity) or
                               _matches(rec.get("email"), identity) or
                               _matches(rec.get("phone"), identity) or
                               _matches(rec.get("email_hash"), identity) or
                               _matches(rec.get("owner_email"), identity))

                    # Also search inside nested "document" if present
                    if not matched and "document" in rec and isinstance(rec["document"], dict):
                        doc = rec["document"]
                        for v in doc.values():
                            matched = _matches(v, identity)
                            if matched:
                                break

                    if not matched:
                        # Recursively check any value in rec
                        for v in rec.values():
                            if isinstance(v, (str, int)):
                                matched = _matches(v, identity)
                                if matched:
                                    break

                    if matched:
                        # Determine system and state
                        sys_id = origin_sys or "platform_service"
                        if "analytics" in coll_name or "analytics" in sys_id:
                            has_pii = bool(rec.get("email") or rec.get("phone") or rec.get("email_hash"))
                            state = StateSignal.PRESENT if has_pii else StateSignal.ANONYMIZED
                            sys_id = "analytics_platform"
                        elif "support" in coll_name or "support" in sys_id:
                            has_pii = bool(rec.get("requester_email") or rec.get("requester_name") or rec.get("requester_phone"))
                            state = StateSignal.PRESENT if has_pii else StateSignal.REDACTED
                            sys_id = "support_platform"
                        elif "search" in coll_name or "search" in sys_id:
                            state = StateSignal.PRESENT
                            sys_id = "search_service"
                        elif "account" in coll_name or "account" in sys_id:
                            state = StateSignal.PRESENT
                            sys_id = "account_service"
                        else:
                            state = StateSignal.PRESENT

                        observations.append(ResourceObservation(
                            file_id=file_id, captured_at=captured_at, system_id=sys_id,
                            resource_id=res_id, identifier_matched=matched, state_signal=state,
                            raw_excerpt=rec_json_str[:300], line_ref=tbl
                        ))

            # Case B: inventory tables or specialized replica tables
            else:
                cursor.execute(f"SELECT * FROM {tbl}")
                rows = cursor.fetchall()
                for row in rows:
                    row_dict = dict(zip(cols, row))
                    res_id = row_dict.get("resource_id", "")

                    matched = None
                    for v in row_dict.values():
                        if v is not None:
                            matched = _matches(v, identity)
                            if matched:
                                break

                    if matched:
                        # Map table name to system and state
                        if "customer_profiles" in tbl:
                            sys_id = "account_service"
                            state = StateSignal.PRESENT
                        elif "search_documents" in tbl or "customer_search" in tbl:
                            sys_id = "search_service"
                            state = StateSignal.PRESENT
                        elif "analytics" in tbl:
                            sys_id = "analytics_platform"
                            has_pii = bool(row_dict.get("email") or row_dict.get("phone") or row_dict.get("email_hash"))
                            state = StateSignal.PRESENT if has_pii else StateSignal.ANONYMIZED
                        elif "support" in tbl:
                            sys_id = "support_platform"
                            has_pii = bool(row_dict.get("requester_email") or row_dict.get("requester_name") or row_dict.get("requester_phone"))
                            state = StateSignal.PRESENT if has_pii else StateSignal.REDACTED
                        elif "connector" in tbl:
                            sys_id = "integration_service"
                            en = row_dict.get("enabled", 0)
                            state = StateSignal.ACTIVE if (en == 1 or en == "1" or en is True or en == "true") else StateSignal.DISABLED
                        elif "backup" in tbl:
                            sys_id = "backup_service"
                            allowed = row_dict.get("restore_allowed") or row_dict.get("restore_access", 0)
                            state = StateSignal.ACTIVE if (allowed == 1 or allowed == "1" or allowed is True or allowed == "true") else StateSignal.BLOCKED
                        elif "audit" in tbl or "security" in tbl:
                            sys_id = "security_service"
                            state = StateSignal.PRESENT
                        elif "export" in tbl:
                            sys_id = "export_service"
                            state = StateSignal.PRESENT
                        else:
                            sys_id = tbl
                            state = StateSignal.PRESENT

                        observations.append(ResourceObservation(
                            file_id=file_id, captured_at=captured_at, system_id=sys_id,
                            resource_id=res_id, identifier_matched=matched, state_signal=state,
                            raw_excerpt=str(row_dict)[:300], line_ref=tbl
                        ))

    except Exception as e:
        pass
    finally:
        conn.close()

    return observations
