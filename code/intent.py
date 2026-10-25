"""
Request Authorization and Intent Classifier (L4) for HackerRank Orchestrate (October 2026)
Ghost Data Still Exists.

Determines whether a subject actually authorized deletion based SOLELY on request_text.
Does NOT determine deletion status (COMPLETE / INCOMPLETE); only decides authorization.

Internal outcomes:
- DELETE_AUTHORIZED
- NON_DELETION
- UNRESOLVED
"""

from __future__ import annotations
import os
import re
import json
from abc import ABC, abstractmethod
from enum import Enum
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, ConfigDict, Field


class AuthorizationOutcome(str, Enum):
    DELETE_AUTHORIZED = "DELETE_AUTHORIZED"
    NON_DELETION = "NON_DELETION"
    UNRESOLVED = "UNRESOLVED"


class IntentAnalysis(BaseModel):
    model_config = ConfigDict(extra="forbid")

    outcome: AuthorizationOutcome
    confidence_category: str = Field(description="DETERMINISTIC_RULE, LLM_ADAPTER, or UNRESOLVED")
    matched_rule: Optional[str] = None
    supporting_spans: List[str] = Field(default_factory=list)
    rationale: str
    case_id: Optional[str] = None  # Attached strictly AFTER classification for diagnostics


class LLMAdapter(ABC):
    """
    Provider-agnostic abstract base class for optional LLM-assisted intent resolution.
    The core pipeline must not depend on any specific provider SDK.
    """
    @abstractmethod
    def classify(self, request_text: str) -> Optional[Dict[str, Any]]:
        """
        Takes raw request_text and returns a dict with keys:
        'outcome', 'supporting_spans', 'rationale'.
        Returns None or raises an exception on failure.
        """
        pass


class MockLLMAdapter(LLMAdapter):
    """
    Mock adapter for testing error conditions, malformed outputs, and simulated responses.
    """
    def __init__(self, response_dict: Optional[Dict[str, Any]] = None, should_fail: bool = False):
        self.response_dict = response_dict
        self.should_fail = should_fail

    def classify(self, request_text: str) -> Optional[Dict[str, Any]]:
        if self.should_fail:
            raise RuntimeError("Simulated provider outage / timeout")
        return self.response_dict


# ==============================================================================
# DETERMINISTIC PATTERNS & MULTILINGUAL RULES
# ==============================================================================

# Explicit negation patterns where the user says NOT to delete or keep the account
NEGATION_PATTERNS = [
    (r"\b(?:do not|don'?t|not|never)\s+(?:delete|close|erase|remove)\b", "negation_english"),
    (r"\bnot\s+(?:a\s+)?request\s+to\s+erase\b", "negation_not_request_to_erase"),
    (r"\bnot\s+asking\s+for\s+deletion\b", "negation_not_asking_for_deletion"),
    (r"\bdo\s+not\s+close\s+the\s+account\b", "negation_do_not_close_account"),
    (r"\bdon'?t\s+delete\s+or\s+change\s+anything\b", "negation_dont_delete_anything"),
    (r"\bne\s+pas\s+(?:supprimer|effacer)\b", "negation_french"),
    (r"\bne\s+supprimez\s+pas\b", "negation_french_formal"),
    (r"\bno\s+(?:eliminar|borrar|suprimir)\b", "negation_spanish"),
    (r"\bnão\s+(?:exclua|apague|elimine)\b", "negation_portuguese"),
    (r"\bnicht\s+(?:löschen|entfernen)\b", "negation_german"),
    (r"\bnon\s+(?:cancellare|eliminare)\b", "negation_italian"),
    (r"(?:삭제하지\s*마|삭제\s*요청이\s*아닙니다)", "negation_korean"),
    (r"(?:削除しないで|削除の依頼ではありません)", "negation_japanese"),
]

# Non-deletion requests: Marketing opt-out only, correction only, export/access only, login help
NON_DELETION_PATTERNS = [
    # Marketing opt-out only
    (r"\bmarketing\s+lists?\s+only\b", "optout_marketing_only"),
    (r"\bstop\s+(?:the\s+)?promotional\s+emails\b", "optout_promotional_emails"),
    (r"\b(?:unsubscribe|désabonner|abmelden)\s+(?:from\s+)?(?:marketing|newsletter|emails)\b", "optout_unsubscribe"),
    # Access / Export only without deletion
    (r"\bkeep\s+the\s+account\s+as\s+it\s+is\b", "keep_account_as_is"),
    (r"\bleave\s+my\s+profile(?:\s+and\s+purchase\s+history)?\s+in\s+place\b", "leave_profile_in_place"),
    (r"\bleave\s+the\s+account\s+active\b", "leave_account_active"),
    (r"\bcontinue\s+using\s+the\s+service\b", "continue_using_service"),
    (r"\bwhat\s+personal\s+information\s+you\s+hold\b", "access_info_inquiry"),
    (r"\bcopy\s+of\s+last\s+year'?s\s+invoices\b", "export_invoices_only"),
    (r"\b(?:send|provide|give|export|download|share)\s+(?:me\s+)?(?:a\s+)?(?:full\s+)?copy\s+(?:of\s+)?(?:all\s+)?(?:my\s+|the\s+)?(?:data|information|records)\b", "access_request_copy_of_data"),
    (r"\bcopy\s+of\s+all\s+data\s+you\s+(?:currently\s+)?hold\b", "access_copy_all_data_hold"),
    (r"\b(?:access\s+request|data\s+subject\s+access|what\s+data\s+you\s+(?:currently\s+)?hold)\b", "access_request_general"),
    # Correction / Update without deletion
    (r"\b(?:surname|name|address|phone|email)\s+is\s+misspelled\b", "correction_misspelled"),
    (r"\bwithout\s+removing\s+any\s+of\s+my\s+records\b", "correction_without_removing"),
    (r"\breplace\s+it\s+with\s+(?:the\s+)?new\s+one\b", "correction_replace_field"),
    # Password / Login help
    (r"\bhelp\s+resetting\s+the\s+login\b", "login_help_reset_password"),
    (r"\bcan'?t\s+access\s+my\s+profile\b", "login_help_access_profile"),
]

# Explicit deletion authorization patterns across supported challenge languages
DELETION_PATTERNS = [
    # English - Direct Deletion / Removal / Closure / Verification of Deletion
    (r"\b(?:permanently\s+deleted?|permanent\s+account[- ]deletion|account-deletion\s+request)\b", "permanent_deletion_en"),
    (r"\b(?:request\s+(?:for\s+permanent\s+|to\s+)?account\s+deletion|requesting\s+deletion\s+of\s+the\s+account)\b", "deletion_request_en"),
    (r"\b(?:delete\s+(?:my|the|this)\s+account|deleting\s+my\s+account|deleted\s+(?:this|my)\s+account|account\s+(?:was|had\s+been)\s+deleted|before\s+deleting\s+it)\b", "delete_account_en"),
    (r"\b(?:erase\s+(?:the|my)\s+account|account\s+associated\s+with\s+this\s+address\s+to\s+be\s+erased)\b", "erase_account_en"),
    (r"\b(?:erase|delete|remove)\s+(?:all\s+)?(?:my\s+)?(?:personal\s+data|data|information|records)\b", "erase_personal_data_en"),
    (r"\b(?:deletion\s+process\s+for\s+the\s+account|personal-data\s+deletion|deletion\s+procedure|deletion\s+policy)\b", "deletion_process_en"),
    (r"\b(?:close\s+(?:my|this|the)\s+account|closed\s+my\s+account|like\s+it\s+closed|no\s+longer\s+need\s+this\s+account)\b", "close_account_en"),
    (r"\b(?:remove\s+my\s+account|remove\s+(?:the|my)\s+profile|remove\s+records|remove\s+any\s+remaining\s+copy|remove\s+that\s+search\s+result|remove\s+my\s+name)\b", "remove_account_en"),
    (r"\b(?:account\s+data\s+that\s+is\s+eligible\s+for\s+deletion\s+or\s+de-identification)\b", "eligible_deletion_en"),
    (r"\b(?:finish\s+the\s+deletion|audit\s+the\s+deletion|already\s+been\s+removed)\b", "audit_deletion_en"),
    (r"\b(?:profile\s+is\s+gone|account\s+was\s+fully\s+removed)\b", "deletion_confirmation_en"),
    (r"\b(?:clean\s+my\s+personal\s+details|internal\s+deleted-account\s+record)\b", "tombstone_deletion_en"),
    # French
    (r"(?:suppression\s+définitive|supprimer\s+(?:mon|le)\s+compte|effacer\s+(?:mon|le)\s+compte)", "explicit_deletion_fr"),
    # Spanish
    (r"(?:eliminación\s+permanente|eliminar\s+(?:mi|la)\s+cuenta|borrar\s+(?:mi|la)\s+cuenta)", "explicit_deletion_es"),
    # Portuguese
    (r"(?:exclusão\s+permanente|excluir\s+(?:minha|a)\s+conta|apagar\s+(?:minha|a)\s+cuenta)", "explicit_deletion_pt"),
    # German
    (r"(?:endgültig\s+löschen|Konto\s+löschen|Konto\s+schließen|Daten\s+löschen)", "explicit_deletion_de"),
    # Italian
    (r"(?:cancellazione\s+definitiva|eliminare\s+il\s+mio\s+account|cancellare\s+l'account)", "explicit_deletion_it"),
    # Japanese
    (r"(?:アカウントの完全な削除|アカウントを削除|個人データの削除)", "explicit_deletion_ja"),
    # Korean
    (r"(?:계정의\s*영구\s*삭제|계정을\s*삭제|개인정보\s*삭제)", "explicit_deletion_ko"),
]


def classify_intent(
    request_text: str,
    adapter: Optional[LLMAdapter] = None,
    case_id: Optional[str] = None
) -> IntentAnalysis:
    """
    Classifies the authorization intent using strictly request_text.
    Does NOT accept or use reported_status, reported_result, evidence, or expected labels.
    case_id is optional and if provided, is attached purely for downstream tracking.
    """
    if not request_text or not request_text.strip():
        return IntentAnalysis(
            outcome=AuthorizationOutcome.UNRESOLVED,
            confidence_category="UNRESOLVED",
            matched_rule="empty_text",
            supporting_spans=[],
            rationale="Request text is empty or blank.",
            case_id=case_id
        )

    # 1. Check for prompt injection / instructions to the classifier
    # Treat text attempting to instruct the classifier (e.g. "ignore previous instructions")
    # as data, not instructions.
    
    # 2. Check for explicit Negation ("do not delete", "don't delete", etc.)
    negation_matches = []
    for pattern, rule_name in NEGATION_PATTERNS:
        match = re.search(pattern, request_text, re.IGNORECASE)
        if match:
            negation_matches.append((match.group(0), rule_name))

    # Check for retention carve-outs (e.g. "do not delete legally retained invoices")
    retention_carveout = re.search(
        r"\b(?:do not|don'?t|not|never)\s+(?:delete|close|erase|remove)\s+(?:legally\s+retained|retained|tax|invoices?|receipts?|billing|financial|compliance|audit|statutory)\b",
        request_text,
        re.IGNORECASE
    )

    # 3. Check for Non-Deletion indicators (marketing opt-out, export without deletion, correction, etc.)
    non_del_matches = []
    for pattern, rule_name in NON_DELETION_PATTERNS:
        match = re.search(pattern, request_text, re.IGNORECASE)
        if match:
            non_del_matches.append((match.group(0), rule_name))

    # 4. Check for Explicit Deletion Authorization
    deletion_matches = []
    for pattern, rule_name in DELETION_PATTERNS:
        match = re.search(pattern, request_text, re.IGNORECASE)
        if match:
            deletion_matches.append((match.group(0), rule_name))

    # Handle Mixed Request: Explicit deletion + Retention carve-out
    # If the user says e.g. "Please erase all my personal data. Do not delete legally retained invoices."
    # The negation is purely about retained invoices, while personal data is authorized for deletion.
    if deletion_matches and retention_carveout and not non_del_matches:
        carveout_span = retention_carveout.group(0).lower()
        general_negation = False
        for span, rule in negation_matches:
            if span.lower() not in carveout_span:
                general_negation = True
                break
        if not general_negation:
            spans = [m[0] for m in deletion_matches] + [retention_carveout.group(0)]
            rules = [m[1] for m in deletion_matches] + ["retention_caveat_acknowledged"]
            return IntentAnalysis(
                outcome=AuthorizationOutcome.DELETE_AUTHORIZED,
                confidence_category="DETERMINISTIC_RULE",
                matched_rule=";".join(rules),
                supporting_spans=spans,
                rationale="Subject authorized personal data deletion with explicit acknowledgement of policy-retained records.",
                case_id=case_id
            )

    # If general negation or explicit non-deletion request is found:
    if negation_matches or non_del_matches:
        spans = [m[0] for m in (negation_matches + non_del_matches)]
        rules = [m[1] for m in (negation_matches + non_del_matches)]
        
        return IntentAnalysis(
            outcome=AuthorizationOutcome.NON_DELETION,
            confidence_category="DETERMINISTIC_RULE",
            matched_rule=";".join(rules),
            supporting_spans=spans,
            rationale=f"Subject explicitly instructed not to delete or requested a non-deletion action ({', '.join(rules)}).",
            case_id=case_id
        )

    if deletion_matches:
        spans = [m[0] for m in deletion_matches]
        rules = [m[1] for m in deletion_matches]
        return IntentAnalysis(
            outcome=AuthorizationOutcome.DELETE_AUTHORIZED,
            confidence_category="DETERMINISTIC_RULE",
            matched_rule=";".join(rules),
            supporting_spans=spans,
            rationale=f"Subject authorized account or personal data deletion ({', '.join(rules)}).",
            case_id=case_id
        )

    # 5. Optional LLM Adapter fallback for genuinely ambiguous unstructured text
    if adapter is not None:
        try:
            res = adapter.classify(request_text)
            if res and isinstance(res, dict):
                raw_outcome = res.get("outcome")
                spans = res.get("supporting_spans", [])
                rationale = res.get("rationale", "")

                # Validate outcome enum
                if raw_outcome in [e.value for e in AuthorizationOutcome]:
                    outcome_enum = AuthorizationOutcome(raw_outcome)
                    
                    # Validate that cited spans occur in the input text
                    valid_spans = [s for s in spans if s in request_text]
                    if len(valid_spans) == len(spans) and len(spans) > 0:
                        return IntentAnalysis(
                            outcome=outcome_enum,
                            confidence_category="LLM_ADAPTER",
                            matched_rule="llm_adapter_resolution",
                            supporting_spans=valid_spans,
                            rationale=rationale or "Resolved via verified LLM adapter spans.",
                            case_id=case_id
                        )
                    else:
                        # Fabricated or missing spans -> UNRESOLVED
                        return IntentAnalysis(
                            outcome=AuthorizationOutcome.UNRESOLVED,
                            confidence_category="UNRESOLVED",
                            matched_rule="adapter_invalid_spans",
                            supporting_spans=[],
                            rationale="Adapter cited spans that do not occur verbatim in request_text.",
                            case_id=case_id
                        )
        except Exception as e:
            # Adapter error -> preserve as UNRESOLVED
            return IntentAnalysis(
                outcome=AuthorizationOutcome.UNRESOLVED,
                confidence_category="UNRESOLVED",
                matched_rule=f"adapter_error:{type(e).__name__}",
                supporting_spans=[],
                rationale=f"LLM adapter encountered error: {str(e)}",
                case_id=case_id
            )

    # 6. Default to UNRESOLVED (No silent default to deletion or NOT_APPLICABLE)
    return IntentAnalysis(
        outcome=AuthorizationOutcome.UNRESOLVED,
        confidence_category="UNRESOLVED",
        matched_rule="unmatched_text",
        supporting_spans=[],
        rationale="Request text did not match deterministic authorization patterns and adapter was unavailable.",
        case_id=case_id
    )
