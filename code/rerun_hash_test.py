import os
import sys
import csv
import json

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO_ROOT)
DATASET_DIR = os.path.join(REPO_ROOT, "dataset")

from code.identity import get_identity_manager, IdentitySet
from code.evidence.index import EvidenceIndex

id_mgr = get_identity_manager(DATASET_DIR)
index = EvidenceIndex(DATASET_DIR)

with open(os.path.join(DATASET_DIR, "deletion_requests.csv"), "r", encoding="utf-8", errors="replace") as f:
    requests = list(csv.DictReader(f))

# Compare evidence matches for all 518 cases:
# Mode A: Current identifiers only
# Mode B: Full IdentitySet (current + historical)

current_only_matches = 0
full_identity_matches = 0

cases_with_extra_matches = 0
total_extra_observations = 0

for req in requests:
    audit_at = req["audit_at"]
    full_ident = id_mgr.resolve(req["email"], audit_at)
    if not full_ident:
        continue

    # Build a current-only IdentitySet
    # Look up current snapshot from user_identities
    current_user = id_mgr.users.get(full_ident.user_id, {})
    curr_email = current_user.get("email", "").strip().lower()
    curr_hash = current_user.get("email_hash", "").strip().lower()
    curr_phone = current_user.get("phone", "").strip()

    curr_ident = IdentitySet(
        user_id=full_ident.user_id,
        name=full_ident.name,
        emails=frozenset([curr_email]) if curr_email else frozenset(),
        email_hashes=frozenset([curr_hash]) if curr_hash else frozenset(),
        phones=frozenset([curr_phone]) if curr_phone else frozenset(),
        active_email=curr_email,
        active_email_hash=curr_hash,
        active_phone=curr_phone
    )


    obs_curr = index.observe_for_case(curr_ident, audit_at, req.get("requested_at"), req.get("reported_at"))
    obs_full = index.observe_for_case(full_ident, audit_at, req.get("requested_at"), req.get("reported_at"))

    c_count = len(obs_curr)
    f_count = len(obs_full)

    current_only_matches += c_count
    full_identity_matches += f_count

    if f_count > c_count:
        cases_with_extra_matches += 1
        total_extra_observations += (f_count - c_count)

print("=" * 60)
print("EVIDENCE MATCH RE-COUNT: CURRENT ONLY vs FULL IDENTITYSET")
print("=" * 60)
print(f"Total evaluation requests:                {len(requests)}")
print(f"Total observations (current only):        {current_only_matches}")
print(f"Total observations (full IdentitySet):    {full_identity_matches}")
print(f"Net new observations from historical IDs: {total_extra_observations}")
print(f"Cases benefiting from historical IDs:     {cases_with_extra_matches}")
print("=" * 60)
