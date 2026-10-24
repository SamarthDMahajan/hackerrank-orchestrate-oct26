"""
Digital PDF evidence parser for HackerRank Orchestrate (October 2026).
Decodes compressed stream text from digital PDF reports without external OCR dependencies.
"""

import re
import zlib
import base64
from typing import List, Optional
from .models import ResourceObservation, StateSignal
from code.identity import IdentitySet


def _matches(text: str, identity: IdentitySet) -> Optional[str]:
    t_lower = text.lower()
    if identity.user_id.lower() in t_lower:
        return identity.user_id
    for em in identity.emails:
        if em in t_lower:
            return em
    for h in identity.email_hashes:
        if h in t_lower:
            return h
    for ph in identity.phones:
        if ph in text:
            return ph
    return None


def parse_pdf(file_path: str, file_id: str, captured_at: str, identity: IdentitySet) -> List[ResourceObservation]:
    observations = []
    with open(file_path, "rb") as f:
        data = f.read()

    # Search for all streams
    extracted_text = []

    # 1. ASCII85 + FlateDecode streams
    idx = 0
    while True:
        pos = data.find(b'/Filter [ /ASCII85Decode /FlateDecode ]', idx)
        if pos == -1:
            break
        s_start = data.find(b'stream\n', pos)
        if s_start != -1:
            s_start += 7
            s_end = data.find(b'~>', s_start)
            if s_end != -1:
                raw_chunk = data[s_start:s_end]
                try:
                    a85_data = base64.a85decode(b'<~' + raw_chunk + b'~>', adobe=True)
                    decomp = zlib.decompress(a85_data)
                    extracted_text.append(decomp.decode("utf-8", errors="replace"))
                except Exception:
                    pass
        idx = pos + 30

    # 2. Pure FlateDecode streams
    idx = 0
    while True:
        pos = data.find(b'/Filter [ /FlateDecode ]', idx)
        if pos == -1:
            pos = data.find(b'/Filter /FlateDecode', idx)
            if pos == -1:
                break
        s_start = data.find(b'stream\n', pos)
        if s_start != -1:
            s_start += 7
            s_end = data.find(b'endstream', s_start)
            if s_end != -1:
                raw_chunk = data[s_start:s_end].rstrip(b'\r\n')
                try:
                    decomp = zlib.decompress(raw_chunk)
                    extracted_text.append(decomp.decode("utf-8", errors="replace"))
                except Exception:
                    pass
        idx = pos + 30

    combined_text = "\n".join(extracted_text)
    matched = _matches(combined_text, identity)
    if matched:
        # Extract resource ID (e.g. support_001, account_XXXX)
        res_matches = re.findall(r'\b(support_\d+|account_\d+|audit_record_\d+|search_\d+)\b', combined_text)
        res_id = res_matches[0] if res_matches else ""
        if res_id:
            # Map system
            if "support" in res_id or "delivery" in file_path.lower():
                sys_id = "support_platform"
            elif "account" in res_id:
                sys_id = "account_service"
            elif "audit" in res_id or "security" in file_path.lower():
                sys_id = "security_service"
            else:
                sys_id = "support_platform"

            observations.append(ResourceObservation(
                file_id=file_id,
                captured_at=captured_at,
                system_id=sys_id,
                resource_id=res_id,
                identifier_matched=matched,
                state_signal=StateSignal.PRESENT,
                raw_excerpt=combined_text[:300].replace("\n", " "),
                line_ref="pdf_stream"
            ))

    return observations
