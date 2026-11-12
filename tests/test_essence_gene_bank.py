"""ESSENCE v0.2 archival JSON provenance, policy and legal-source admission checks."""
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / ".janus" / "essence"))
import gene_bank
import kernel


class GeneBankTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.reg = self.root / "registry"
        self.arc = self.root / "archive"
        self.reg.mkdir()
        self.arc.mkdir()
        self.manifest = kernel.load_json(
            Path(__file__).resolve().parents[1] / ".janus" / "essence" / "manifest.json")
        self.catalog = kernel.load_json(
            Path(__file__).resolve().parents[1] / ".janus" / "essence" / "legal_sources.json")
        self.ref = "a" * 40

    def create_sources(self):
        for origin, path in gene_bank.SRC:
            data = {"artifact_id": "synthetic_unit_test"}
            if path.endswith("GENOME-RESEARCH-2026-11-12-v1.json"):
                data["gene_candidates"] = [
                    {"gene": "autodiff_attention", "donors": ["MicroGPT"]},
                    {"gene": "gradient_guard", "donors": ["Yaksa+12"]},
                    {"gene": "not_a_real_gene", "donors": []}]
            elif path.endswith("JANUS_GPT_MODEL_ZOO_ARCHAEOLOGY_2026-08-25.json"):
                data["core_lineage"] = [
                    {"name": "MicroGPT", "sha256": "c" * 64}]
                data["hash_bound_model_zoo"] = [
                    {"name": "CatGPT", "sha256": "d" * 64}]
            elif path.endswith("JANUS_GPT_MICROMODEL_FAMILY_LINEAGE_2026-08-25.json"):
                data["members"] = [{"name": "FractalGPT(5).py", "sha256": "e" * 64}]
            elif path.endswith("JANUS_JGPT_TRI_BRAIN_GEX_LINEAGE_2026-08-25.json"):
                data["content_identities"] = [{"source": "JGPT1.py", "sha256": "f" * 64}]
            else:
                data["selected_patterns"] = [{"source": "Yaksa+12"}]
            root = self.reg if origin == "registry" else self.arc
            target = root / path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(json.dumps(data), encoding="utf-8")

    def evaluate(self, catalog=None):
        return gene_bank.evaluate(
            self.manifest, self.reg, self.arc, self.catalog if catalog is None else catalog,
            registry_sha=self.ref, archive_sha="b"*40,
            expected_repo=self.manifest["repository"])

    def test_reads_archive_and_matches_microkernel_roles_without_execution(self):
        self.create_sources()
        result = self.evaluate()
        self.assertEqual(result["gate"], "RESEARCH_READY_PROPOSAL_ONLY")
        self.assertEqual(len(result["archive_inventory"]), len(gene_bank.SRC))
        self.assertGreater(result["historical_gene_count"], 3)
        self.assertTrue(any(x["role"] == "recovery" and x["gene"] == "gradient_guard"
                            for x in result["proposals"]))
        self.assertTrue(all(x["state"] == "PROPOSED_ONLY" for x in result["proposals"]))
        self.assertFalse(result["weights_updated"])
        self.assertFalse(result["production_promotion"])
        self.assertTrue(gene_bank.verify(result))
        self.assertTrue(all(e["status"] == "METADATA_MATCH_REVIEW_REQUIRED"
                            for e in result["external_repository_license_review"]))

    def test_missing_archive_remains_hold_not_fabricated_success(self):
        self.create_sources()
        (self.reg / gene_bank.SRC[0][1]).unlink()
        result = self.evaluate()
        self.assertEqual(result["gate"], "HOLD_INCOMPLETE_ARCHIVE")
        self.assertEqual(len(result["missing_sources"]), 1)
        self.assertTrue(gene_bank.verify(result))

    def test_unlicensed_external_repo_fails_closed(self):
        self.create_sources()
        catalog = json.loads(json.dumps(self.catalog))
        catalog["repositories"][0]["observed_spdx"] = "NOASSERTION"
        result = self.evaluate(catalog)
        self.assertEqual(result["external_repository_license_review"][0]["status"], "LICENSE_HOLD")
        catalog["repositories"][1]["auto_fetch_code"] = True
        with self.assertRaisesRegex(ValueError, "UNTRUSTED_EXECUTION"):
            self.evaluate(catalog)

    def test_cross_repo_identity_and_source_sha_required(self):
        self.create_sources()
        with self.assertRaisesRegex(ValueError, "repository identity mismatch"):
            gene_bank.evaluate(self.manifest, self.reg, self.arc, self.catalog,
                               registry_sha=self.ref, archive_sha=self.ref,
                               expected_repo="attacker/unrelated")
        with self.assertRaisesRegex(ValueError, "UNPINNED_SOURCE_REF"):
            gene_bank.evaluate(self.manifest, self.reg, self.arc, self.catalog,
                               registry_sha="main", archive_sha=self.ref,
                               expected_repo=self.manifest["repository"])

    def test_unsafe_json_paths_and_oversize_rejected(self):
        self.create_sources()
        with self.assertRaisesRegex(ValueError, "UNSAFE_JSON_PATH"):
            gene_bank.load_bounded(self.reg, "../archive/" + gene_bank.SRC[3][1])
        huge = self.reg / "data/huge.json"
        huge.write_text('{"padding":"' + 'A' * (gene_bank.MAX_FILE_BYTES + 2) + '"}')
        with self.assertRaisesRegex(ValueError, "BOUNDED_JSON_REQUIRED"):
            gene_bank.load_bounded(self.reg, "data/huge.json")

    def test_receipt_tamper_and_privilege_escalation_rejected(self):
        self.create_sources()
        result = self.evaluate()
        result["proposals"][0]["action_authority"] = True
        with self.assertRaisesRegex(ValueError, "REPORT_DIGEST"):
            gene_bank.verify(result)
        result["report_sha256"] = gene_bank.sha(gene_bank.canonical(
            {k:v for k,v in result.items() if k != "report_sha256"}))
        with self.assertRaisesRegex(ValueError, "ACTIVE_CHILD_FORBIDDEN"):
            gene_bank.verify(result)

    def test_alias_deduplication_does_not_count_copies_twice(self):
        self.create_sources()
        original = self.evaluate()
        item = self.arc / gene_bank.SRC[4][1]
        obj = json.loads(item.read_text())
        obj["members"].append({"name": "FractalGPT(6).py", "sha256": "e" * 64})
        item.write_text(json.dumps(obj))
        duplicated = self.evaluate()
        self.assertEqual(original["historical_gene_count"], duplicated["historical_gene_count"])
        p1 = next(x for x in original["proposals"] if x["gene"] == "multiscale_forecast")
        p2 = next(x for x in duplicated["proposals"] if x["gene"] == "multiscale_forecast")
        self.assertEqual(p1["distinct_historical_source_hashes"], p2["distinct_historical_source_hashes"])


if __name__ == "__main__":
    unittest.main()
