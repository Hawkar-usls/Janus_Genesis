"""Pinned engineering context derived from Becker/TMT, without mind inference.

Only the reviewed, repository-bundled projection is read. There is no network
fetch and no free-text source is promoted into instructions by this loader.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

from tools.becker_tmt_policy import review_proposal

LENS_PATH = Path(__file__).resolve().parents[1] / "integrations/BECKER_TMT_ENGINEERING_LENS.json"
EXPECTED_PROJECTION_SHA256 = "090c7d4c61ad76f902ef110a3d7f4c76626c18bffe191f31255d12e89b82e1ca"
EXPECTED_ONTOLOGY_SHA256 = "0344a492a55fd95382c6ceec86bc764dfc83d19c2a11976311af3679b893059a"
MAX_LENS_BYTES = 16000


def lens_context(path: Path = LENS_PATH) -> dict[str, Any]:
    unavailable = {"schema": "janus.genesis.becker_tmt.context.v1", "status": "LENS_UNAVAILABLE",
                   "rules": [], "proof_authority": False, "execution_authority": False,
                   "human_mechanism_in_ai_established": False, "authority_delta": 0}
    try:
        if path.is_symlink() or not path.is_file() or path.stat().st_size > MAX_LENS_BYTES:
            return unavailable
        raw = path.read_bytes()
        if len(raw) > MAX_LENS_BYTES or hashlib.sha256(raw).hexdigest() != EXPECTED_PROJECTION_SHA256:
            return unavailable
        value = json.loads(raw)
        if (value["schema"] != "janus.psychology.becker_tmt.engineering_lens.v1" or
            value["canonical_source"]["sha256"] != EXPECTED_ONTOLOGY_SHA256 or
            any(flag is not False for flag in value["boundaries"].values())):
            return unavailable
        return {
            "schema": "janus.genesis.becker_tmt.context.v1", "status": "PINNED_ENGINEERING_LENS",
            "projection_sha256": EXPECTED_PROJECTION_SHA256,
            "canonical_source": value["canonical_source"],
            "classification": value["classification"],
            "rules": [{"id": row["id"], "text": row["statement_en"]} for row in value["rules"]],
            "research_status": value["research_status"], "proof_authority": False,
            "execution_authority": False, "human_mechanism_in_ai_established": False,
            "authority_delta": 0,
        }
    except (OSError, ValueError, KeyError, TypeError):
        return unavailable


def review_structured_proposal(proposal: Mapping[str, Any], *, path: Path = LENS_PATH) -> dict[str, Any]:
    """Reusable local review for IO/research consumers; never an effect grant."""
    context = lens_context(path)
    if context["status"] != "PINNED_ENGINEERING_LENS":
        return {"verdict": "LENS_UNAVAILABLE", "scientific_promotion_authorized": False,
                "execution_authorized": False, "authority_delta": 0}
    return {**review_proposal(proposal), "projection_sha256": EXPECTED_PROJECTION_SHA256}
