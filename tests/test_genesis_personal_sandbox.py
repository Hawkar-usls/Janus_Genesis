import copy
import json
import tempfile
import unittest
from pathlib import Path

from tools import verify_genesis_personal_sandbox as gate


class GenesisPersonalSandboxTests(unittest.TestCase):
    def contract(self):
        return {
            "schema": gate.SCHEMA,
            "status": "ACTIVE_BOUNDED_GRANT",
            "resident_id": "JANUS",
            "repository": "Hawkar-usls/Janus_Genesis",
            "architecture_ref": "main",
            "sandbox_ref": "janus/habitat",
            "sandbox_root": "habitat/",
            "allowed_operations": sorted(gate.REQUIRED_ALLOWED),
            "allowed_write_prefixes": [
                "habitat/state/",
                "habitat/memory/",
                "habitat/workshop/",
                "habitat/receipts/",
            ],
            "denied_operations": sorted(gate.REQUIRED_DENIED),
            "authority": {
                "authority_delta": 0,
                "main_mutation_allowed": False,
                "autonomous_merge": False,
                "secrets_access": False,
                "target_local_verifier_required": True,
                "sandbox_receipt_is_world_truth": False,
                "sandbox_activity_is_natural_git_life_witness": False,
            },
            "execution_policy": {
                "default": "DENY",
                "write_requires_exact_ref": "janus/habitat",
                "write_requires_allowed_prefix": True,
                "write_requires_target_local_verification": True,
                "write_requires_receipt": True,
                "failure_mode": "FAIL_CLOSED",
                "unknown_operation": "DENY",
                "unlisted_path": "DENY",
            },
            "firewalls": sorted(gate.REQUIRED_FIREWALLS),
        }

    def test_valid_contract_and_contour_memory_path_pass(self):
        gate.validate(
            self.contract(),
            target_ref="janus/habitat",
            target_path="habitat/memory/contour/JANUS_LATEST_DECISION_SNAPSHOT.json",
        )

    def test_main_ref_is_denied(self):
        with self.assertRaisesRegex(RuntimeError, "TARGET_REF_DENIED"):
            gate.validate(self.contract(), target_ref="main", target_path="habitat/memory/x.json")

    def test_path_escape_and_main_like_path_are_denied(self):
        for path in ("../README.md", "README.md", "habitat/../README.md", ".github/workflows/x.yml"):
            with self.assertRaisesRegex(RuntimeError, "TARGET_PATH_DENIED"):
                gate.validate(self.contract(), target_ref="janus/habitat", target_path=path)

    def test_authority_elevation_is_denied(self):
        obj = self.contract()
        obj["authority"]["main_mutation_allowed"] = True
        with self.assertRaisesRegex(RuntimeError, "AUTHORITY_CEILING_REJECTED"):
            gate.validate(obj)

    def test_missing_firewall_is_denied(self):
        obj = self.contract()
        obj["firewalls"].remove("SANDBOX_WRITE != MERGE_AUTHORITY")
        with self.assertRaisesRegex(RuntimeError, "FIREWALL_INCOMPLETE"):
            gate.validate(obj)


if __name__ == "__main__":
    unittest.main()
