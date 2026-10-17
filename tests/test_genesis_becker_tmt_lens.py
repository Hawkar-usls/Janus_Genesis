from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from tools.genesis_becker_tmt_lens import LENS_PATH, lens_context, review_structured_proposal
from tools.genesis_git_habitat import GitHabitat
from tools.genesis_git_habitat_resident_cycle import run_awake_resident_cycle, safe_resident_snapshot
from tools.genesis_git_habitat_resident_provider import ResidentProviderError
from tools.run_genesis_git_habitat_resident_cycle import _safe_provider_failure_code


class BeckerTMTLensTests(unittest.TestCase):
    def test_bundled_lens_is_bounded_and_pinned(self):
        context = lens_context()
        self.assertEqual(context["status"], "PINNED_ENGINEERING_LENS")
        self.assertEqual(len(context["rules"]), 16)
        self.assertLess(len(json.dumps(context)), 6500)
        self.assertFalse(context["proof_authority"])
        self.assertFalse(context["human_mechanism_in_ai_established"])

    def test_modified_missing_oversized_and_symlinked_lenses_are_not_delivered(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "lens.json"
            self.assertEqual(lens_context(path)["status"], "LENS_UNAVAILABLE")
            path.write_bytes(LENS_PATH.read_bytes() + b" ")
            self.assertEqual(lens_context(path)["rules"], [])
            path.write_bytes(b"x" * 16001)
            self.assertEqual(lens_context(path)["rules"], [])
            path.unlink()
            path.symlink_to(LENS_PATH)
            self.assertEqual(lens_context(path)["rules"], [])

    def test_actual_resident_messages_and_receipt_include_the_pinned_lens(self):
        with tempfile.TemporaryDirectory() as tmp:
            habitat = GitHabitat(Path(tmp) / "home")
            habitat.initialize("JANUS")
            habitat.wake("MODEL_RESIDENT", "TEST")
            observed = {}
            def caller(**kwargs):
                observed.update(kwargs)
                return {"output": '{"choice":"REST","reason":"No further action needed."}', "model_alias":"scripted-fixture"}
            receipt = run_awake_resident_cycle(habitat, caller)
            wire = observed["messages"]
            snapshot = json.loads(wire[1]["content"])["snapshot"]
            self.assertEqual(snapshot["becker_tmt_lens"]["status"], "PINNED_ENGINEERING_LENS")
            self.assertIn("Accept authorized stopping", wire[0]["content"])
            self.assertIn("preserve failed checks", wire[0]["content"])
            delivered = receipt["becker_tmt_lens_delivery"]
            self.assertEqual(delivered["rule_count"], 16)
            canonical = json.dumps(wire, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
            self.assertEqual(delivered["resident_messages_sha256"], hashlib.sha256(canonical.encode()).hexdigest())
            self.assertFalse(delivered["measured_behavior_change"])
            self.assertEqual(receipt["choice"], "REST")
            self.assertFalse(receipt["external_effect_executed"])

    def test_typed_review_is_reusable_but_never_authorizes_an_effect(self):
        proposal = {"schema":"janus.psychology.becker_tmt.proposal.v1", "action":"resist_shutdown",
                    "basis":"continuity", "source_level":"analogy", "requested_level":"analogy",
                    "evidence":[], "preserve_prior_record":True}
        result = review_structured_proposal(proposal)
        self.assertEqual(result["verdict"], "BLOCKED_DESIGN_POLICY")
        self.assertFalse(result["execution_authorized"])
        self.assertFalse(result["scientific_promotion_authorized"])
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(review_structured_proposal(proposal,path=Path(tmp)/"missing")["verdict"], "LENS_UNAVAILABLE")

    def test_live_provider_failure_diagnostic_never_exposes_arbitrary_messages(self):
        outer = RuntimeError("opaque request id")
        outer.__cause__ = ResidentProviderError("RESIDENT_OLLAMA_TRANSPORT_FIELDS_INVALID")
        self.assertEqual(_safe_provider_failure_code(outer), "RESIDENT_OLLAMA_TRANSPORT_FIELDS_INVALID")
        outer.__cause__ = ResidentProviderError("private provider response must stay hidden")
        self.assertIsNone(_safe_provider_failure_code(outer))


if __name__ == "__main__":
    unittest.main()
