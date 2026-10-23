import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
AUDIT = ROOT / "protocol" / "JANUS_GENESIS_CONSTELLATION_ROLE_AUDIT-v1.0.json"
MANIFEST = ROOT / "protocol" / "JANUS_GENESIS_ACTIVE_FACE_MANIFEST-v1.0.json"


class ConstellationRoleAuditV1Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.audit = json.loads(AUDIT.read_text(encoding="utf-8"))
        cls.manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))

    def test_complete_44_node_accounting(self):
        public = self.audit["public"]
        private = self.audit["private"]
        self.assertEqual(len(public), 41)
        self.assertEqual(len(private), 3)
        self.assertEqual(len(public) + len(private), 44)
        self.assertEqual(len({row["id"] for row in public}), 41)
        self.assertEqual(len({row["repository"] for row in public}), 41)
        self.assertEqual(len({row["id"] for row in private}), 3)
        self.assertEqual(self.audit["summary"]["TOTAL"], 44)

    def test_private_public_projection_is_opaque(self):
        for row in self.audit["private"]:
            self.assertEqual(set(row), {"id", "state"})
            self.assertEqual(row["state"], "PRIVATE_OPAQUE_HOLD")
            self.assertTrue(row["id"].isdigit())

    def test_face_tool_reference_separation(self):
        rows = {row["repository"]: row for row in self.audit["public"]}
        self.assertEqual(rows["Hawkar-usls/Janus-Demiurge"]["state"], "TOOL_ONLY")
        self.assertEqual(rows["Hawkar-usls/Simptomat"]["state"], "REFERENCE_ONLY")
        self.assertEqual(rows["Hawkar-usls/SLOT"]["state"], "REFERENCE_ONLY")
        self.assertEqual(rows["Hawkar-usls/SSlot"]["state"], "REFERENCE_ONLY")
        self.assertEqual(rows["Hawkar-usls/lineara.xyz"]["state"], "REFERENCE_ONLY")
        self.assertEqual(rows["Hawkar-usls/Linear-A-decipherment-programme"]["state"], "REFERENCE_ONLY")

    def test_summary_matches_public_rows(self):
        expected = {
            "ACTIVE_TYPED_FACE": 2,
            "ADMISSION_CANDIDATE": 9,
            "ADMISSION_CANDIDATE_HOLD": 6,
            "TOOL_ONLY": 11,
            "REFERENCE_ONLY_PUBLIC": 13,
        }
        observed = {}
        for row in self.audit["public"]:
            key = "REFERENCE_ONLY_PUBLIC" if row["state"] == "REFERENCE_ONLY" else row["state"]
            observed[key] = observed.get(key, 0) + 1
        self.assertEqual(observed, expected)
        self.assertEqual(self.audit["summary"]["PRIVATE_OPAQUE_HOLD"], 3)

    def test_manifest_contains_only_face_entries(self):
        faces = self.manifest["faces"]
        self.assertEqual(len(faces), 17)
        self.assertEqual(len({face["face_id"] for face in faces}), 17)
        self.assertEqual(len({face["source"] for face in faces}), 17)
        active = [f for f in faces if f["activation"].startswith("ACTIVE")]
        self.assertEqual(len(active), 2)
        self.assertEqual({f["source"] for f in active}, {
            "Hawkar-usls/Janus_Genesis",
            "Hawkar-usls/janus-meta-registry",
        })

    def test_no_face_gains_source_or_external_authority(self):
        for face in self.manifest["faces"]:
            self.assertFalse(face["can_mutate_source"])
            self.assertFalse(face["external_effect"])
            self.assertEqual(face["pin_policy"], "EXACT_GIT_COMMIT_SHA1_AT_ADMISSION")

    def test_candidates_map_to_audited_candidates_only(self):
        allowed_states = {"ACTIVE_TYPED_FACE", "ADMISSION_CANDIDATE", "ADMISSION_CANDIDATE_HOLD"}
        audit_rows = {row["repository"]: row for row in self.audit["public"]}
        for face in self.manifest["faces"]:
            self.assertIn(face["source"], audit_rows)
            self.assertIn(audit_rows[face["source"]]["state"], allowed_states)

    def test_core_constitutional_laws_are_pinned(self):
        laws = set(self.audit["laws"])
        for required in {
            "LINKED_REPOSITORY != ACTIVE_HABITAT_FACE",
            "TOOL != FACE",
            "ROLE != PERMISSION",
            "MANY_FACES != MORE_AUTHORITY",
            "AMBIGUITY_IS_A_FIRST_CLASS_STATE",
            "MEASURE_OR_EXTRACT_BEFORE_ROLE_ASSIGNMENT",
            "WRITE_BACK_DEFAULT = DENY",
            "PRIVATE_CONTENT != PUBLIC_HABITAT_PAYLOAD",
        }:
            self.assertIn(required, laws)


if __name__ == "__main__":
    unittest.main()
