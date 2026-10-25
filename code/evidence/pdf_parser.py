"""
Digital PDF evidence parser for HackerRank Orchestrate (October 2026).
Decodes compressed stream text from digital PDF reports and integrates
verified visual sidecars with strict row-level association.
"""

from __future__ import annotations
import os
import re
import zlib
import base64
from typing import List, Optional, Set
from .models import ResourceObservation, StateSignal
from .image_parser import parse_visual_evidence, DEFAULT_SIDECAR_DIR
from code.identity import IdentitySet


def _matches(text: str, identity: IdentitySet) -> Optional[str]:
    if not identity or not text:
        return None
    t_lower = text.lower()
    tokens = set(re.split(r'[\s,;:\'\"=()<>{}\[\]]+', t_lower))
    if identity.user_id and identity.user_id.lower() in tokens:
        return identity.user_id
    for em in identity.emails:
        if em and em.lower() in tokens:
            return em
    for h in identity.email_hashes:
        if h and h.lower() in tokens:
            return h
    for ph in identity.phones:
        if ph and ph in tokens:
            return ph
    for em in identity.emails:
        if em:
            pattern = r'(?<![a-zA-Z0-9_\-\.])' + re.escape(em.lower()) + r'(?![a-zA-Z0-9_\-\.])'
            if re.search(pattern, t_lower):
                return em
    if identity.user_id:
        pattern = r'(?<![a-zA-Z0-9_])' + re.escape(identity.user_id.lower()) + r'(?![a-zA-Z0-9_])'
        if re.search(pattern, t_lower):
            return identity.user_id
    return None


def parse_pdf(
    file_path: str,
    file_id: str,
    captured_at: str,
    identity: Optional[IdentitySet],
    sidecar_dir: Optional[str] = None,
    audit_at: Optional[str] = None
) -> List[ResourceObservation]:
    """
    Parses a PDF evidence file.
    If a verified VisualSidecar exists in sidecar_dir, delegates to parse_visual_evidence.
    Otherwise, extracts text streams and applies row/block locality matching.
    """
    resolved_sidecar_dir = sidecar_dir or DEFAULT_SIDECAR_DIR
    sidecar_path = os.path.join(resolved_sidecar_dir, f"{file_id}.json")
    if os.path.exists(sidecar_path):
        return parse_visual_evidence(
            file_path=file_path,
            file_id=file_id,
            captured_at=captured_at,
            identity=identity,
            sidecar_dir=resolved_sidecar_dir,
            audit_at=audit_at
        )

    if not identity:
        return []

    observations: List[ResourceObservation] = []
    if not os.path.exists(file_path):
        return observations

    with open(file_path, "rb") as f:
        data = f.read()

    extracted_blocks = []

    # 1. ASCII85 + FlateDecode streams
    idx = 0
    while True:
        pos = data.find(b'/Filter [ /ASCII85Decode /FlateDecode ]', idx)
        if pos == -1:
            break
        s_pos = data.find(b'stream', pos)
        if s_pos != -1:
            s_start = s_pos + 6
            while s_start < len(data) and data[s_start:s_start+1] in (b'\r', b'\n'):
                s_start += 1
            s_end = data.find(b'~>', s_start)
            if s_end != -1:
                raw_chunk = data[s_start:s_end]
                try:
                    a85_data = base64.a85decode(b'<~' + raw_chunk + b'~>', adobe=True)
                    decomp = zlib.decompress(a85_data)
                    extracted_blocks.append(decomp.decode("utf-8", errors="replace"))
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
        s_pos = data.find(b'stream', pos)
        if s_pos != -1:
            s_start = s_pos + 6
            while s_start < len(data) and data[s_start:s_start+1] in (b'\r', b'\n'):
                s_start += 1
            s_end = data.find(b'endstream', s_start)
            if s_end != -1:
                raw_chunk = data[s_start:s_end].rstrip(b'\r\n')
                try:
                    decomp = zlib.decompress(raw_chunk)
                    extracted_blocks.append(decomp.decode("utf-8", errors="replace"))
                except Exception:
                    pass
        idx = pos + 30

    # Strict row-level / block-level inspection
    for block in extracted_blocks:
        lines = block.split("\n")
        for line in lines:
            matched = _matches(line, identity)
            if matched:
                res_matches = re.findall(r'\b(support_\d+|account_\d+|audit_record_\d+|search_\d+|ORD-\d+|object_\d+)\b', line)
                res_id = res_matches[0] if res_matches else ""
                if res_id:
                    if "support" in res_id or "delivery" in file_path.lower():
                        sys_id = "support_platform"
                    elif "account" in res_id:
                        sys_id = "account_service"
                    elif "audit" in res_id or "security" in file_path.lower():
                        sys_id = "security_service"
                    elif "ORD-" in res_id:
                        sys_id = "finance_service"
                    else:
                        sys_id = "support_platform"

                    observations.append(ResourceObservation(
                        file_id=file_id,
                        captured_at=captured_at,
                        system_id=sys_id,
                        resource_id=res_id,
                        identifier_matched=matched,
                        state_signal=StateSignal.PRESENT,
                        raw_excerpt=line.strip()[:300],
                        line_ref="pdf_stream_line"
                    ))

    return observations
