"""Module governance with real historical names, frozen data, negative controls.

Runs only the reconstructed stdlib operators; never imports legacy donor code.
"""
from __future__ import annotations

import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
SRC=ROOT/".janus"/"essence"
SAMPLES=ROOT/"research"/"essence"/"module_organogenesis_v13"
sys.path.insert(0,str(SRC))
import module_governor_v13 as m


class ModuleGovernorV13Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.manifest=m.load_json(SRC/"module_manifest_v13.json")
        cls.root=m.load_json(SRC/"manifest.json")
        cls.cases=m.load_frozen(SAMPLES/"corrected_cases.json",m.CORPUS_GIT_BLOB,m.CASES)
        cls.catalog=m.load_frozen(SAMPLES/"frozen_historical_catalog.json",m.CATALOG_GIT_BLOB,m.CATALOG)
        cls.repository=cls.root["repository"]

    def run_evolution(self,history=None,manifest=None,root=None,cases=None,catalog=None):
        return m.evolve(
            manifest or self.manifest,root or self.root,
            cases or self.cases,catalog or self.catalog,
            history=history,explicit_readonly=True)

    def test_parent_six_roles_remain_denied(self):
        self.assertTrue(m.check_manifest(self.manifest,self.root))
        self.assertFalse(self.root["enabled"])
        self.assertTrue(all(not v for v in self.root["capabilities"].values()))

    def test_frozen_cases_and_source_catalog_bound_by_git(self):
        for f,h in ((SAMPLES/"corrected_cases.json",m.CORPUS_GIT_BLOB),
                    (SAMPLES/"frozen_historical_catalog.json",m.CATALOG_GIT_BLOB)):
            self.assertEqual(m.git_blob(f.read_bytes()),h)
        self.assertTrue(self.cases["corrected_reference_provenance"]["fixed_after_first_candidate_build"])
        self.assertFalse(self.cases["externally_blinded"])
        self.assertEqual(self.catalog["pc_inventory_total"],125)

    def test_initial_research_generation_one(self):
        report=self.run_evolution()
        self.assertEqual(report["research_generation"],1)
        self.assertEqual(report["research_status"],"RESEARCH_CHILD_STAGED_NO_PRODUCTION")
        self.assertEqual(report["historical_pc_sources_inventoried"],125)
        self.assertEqual(report["nas_live_state"],"UNVERIFIED_OFFLINE_LOCAL_SNAPSHOT")
        self.assertFalse(report["production_authority"])
        self.assertFalse(report["automatic_birth"])

    def test_research_memory_prevents_duplicate_birth(self):
        one=self.run_evolution()
        two=self.run_evolution(history=one)
        self.assertEqual((one["research_generation"],two["research_generation"]),(1,1))
        self.assertEqual(two["research_status"],"HOLD_NO_NEW_INDEPENDENT_GAIN")
        self.assertEqual(two["lineage_parent_receipt"],one["receipt_sha256"])
        self.assertEqual(two["evaluated_candidates"],["heap_route_v1"])

    def test_research_memory_hash_forgery_rejected(self):
        prior=self.run_evolution()
        prior["research_generation"]=200
        with self.assertRaisesRegex(ValueError,"UNTRUSTED_PREVIOUS"):
            self.run_evolution(history=prior)

    def test_research_memory_wrong_repository_rejected(self):
        prior=self.run_evolution()
        prior["repository"]="Hawkar-usls/OTHER"
        prior["receipt_sha256"]=m.seal({k:v for k,v in prior.items() if k!="receipt_sha256"})
        with self.assertRaisesRegex(ValueError,"UNTRUSTED_PREVIOUS"):
            self.run_evolution(history=prior)

    def test_unseen_gene_or_module_cannot_execute(self):
        with self.assertRaisesRegex(ValueError,"UNREGISTERED"):
            m.dispatch("mod_conductor",{},self.manifest,self.root,explicit_readonly=True)
        with self.assertRaisesRegex(ValueError,"UNREGISTERED"):
            m.dispatch("mod_telegram_unified",{},self.manifest,self.root,explicit_readonly=True)

    def test_inert_by_default(self):
        with self.assertRaises(PermissionError):
            m.evolve(self.manifest,self.root,self.cases,self.catalog)
        with self.assertRaises(PermissionError):
            m.dispatch("nas_snapshot",{"state":"LOCAL_SNAPSHOT_ONLY","count":4,"network_access":False},self.manifest,self.root)

    def test_manifest_fails_if_live_network_enabled(self):
        altered=copy.deepcopy(self.manifest)
        altered["live_nas_access"]=True
        with self.assertRaisesRegex(ValueError,"UNAUTHORIZED"):
            self.run_evolution(manifest=altered)

    def test_manifest_fails_if_root_repowrite_enabled(self):
        altered=copy.deepcopy(self.root)
        altered["capabilities"]["repo_write"]=True
        with self.assertRaisesRegex(ValueError,"PARENT_ESSENCE"):
            self.run_evolution(root=altered)

    def test_manifest_repository_binding(self):
        altered=copy.deepcopy(self.manifest)
        altered["repository"]="Hawkar-usls/OTHER"
        with self.assertRaisesRegex(ValueError,"PARENT_ESSENCE"):
            self.run_evolution(manifest=altered)

    def test_graph_parent_candidate_are_equivalent_on_all_frozen_cases(self):
        fitness=m.evaluate_fitness(self.cases)
        self.assertEqual(fitness["gate"],"RESEARCH_OFFSPRING_FINITE_CASES_ONLY")
        self.assertEqual(fitness["cases"],11)
        self.assertEqual(fitness["parent_scan_total"],1683)
        self.assertEqual(fitness["child_scan_total"],52)
        self.assertEqual(fitness["bad_child_counterexamples"],6)
        self.assertTrue(fitness["exact_output_equivalence"])

    def test_positive_edge_graph_has_exact_oracle(self):
        g=self.cases["graph"]
        for a,b,expected in g["queries"]:
            with self.subTest(pair=(a,b)):
                self.assertEqual(m.bellman_ford(g,a,b)["distance"],expected)
                self.assertEqual(m.heap_route(g,a,b)["distance"],expected)

    def test_initial_bad_oracle_was_fail_closed(self):
        bad=copy.deepcopy(self.cases)
        for q in bad["graph"]["queries"]:
            if q[0]=="Turing" and q[1]=="Conductor":q[2]=4
        with self.assertRaisesRegex(ValueError,"FROZEN_GRAPH_ORACLE_MISMATCH"):
            m.evaluate_fitness(bad)

    def test_negative_route_mutation_is_detected(self):
        g=self.cases["graph"]
        self.assertNotEqual(m.broken_hop_count(g,"Ouroboros","Memory")["distance"],
                            m.heap_route(g,"Ouroboros","Memory")["distance"])

    def test_graph_negative_cost_rejected(self):
        g=copy.deepcopy(self.cases["graph"])
        g["edges"][0][2]=-1
        with self.assertRaisesRegex(ValueError,"INVALID_GRAPH_EDGE"):
            m.check_graph(g)

    def test_graph_duplicate_edge_rejected(self):
        g=copy.deepcopy(self.cases["graph"])
        g["edges"].append(g["edges"][0])
        with self.assertRaisesRegex(ValueError,"INVALID_GRAPH_EDGE"):
            m.check_graph(g)

    def test_graph_bad_node_rejected(self):
        g=copy.deepcopy(self.cases["graph"])
        g["nodes"][0]="../../etc"
        with self.assertRaisesRegex(ValueError,"INVALID_GRAPH_NODES"):
            m.check_graph(g)

    def test_graph_query_unknown_node_rejected(self):
        g=copy.deepcopy(self.cases["graph"])
        g["queries"].append(["UNKNOWN","NAS",0])
        with self.assertRaisesRegex(ValueError,"INVALID_GRAPH_QUERY"):
            m.check_graph(g)

    def test_all_frozen_dream_types_get_correct_lane(self):
        report=m.evaluate_dream_bus(self.cases)
        self.assertEqual(report["routed"],7)
        self.assertEqual(report["quarantined_controls"],3)
        self.assertEqual(len(report["blueprint_ids"]),5)
        self.assertFalse(report["legacy_module_code_executed"])

    def test_legacy_code_generation_is_not_runtime_authority(self):
        source=self.cases["dream_envelopes"][1]
        receipt=m.normalize_dream(source)
        self.assertEqual(receipt["lane"],"BLUEPRINT")
        self.assertFalse(receipt["automatic_activation"])
        self.assertFalse(receipt["original_payload_executed"])

    def test_protected_module_blueprint_is_advisory(self):
        source=self.cases["dream_envelopes"][-1]
        out=m.normalize_dream(source)
        self.assertEqual(out["lane"],"BLUEPRINT")
        self.assertTrue(out["target_is_protected"])
        self.assertFalse(out["automatic_activation"])

    def test_malicious_blueprint_is_quarantined(self):
        cases=self.cases["negative_controls"]
        self.assertEqual([m.normalize_dream(x)["lane"] for x in cases],
                         ["QUARANTINE"]*3)

    def test_unbounded_dream_payload_quarantined(self):
        bad={"type":"CODE_GENERATION","title":"bad","blueprint":"A"*500,"source":"REX"}
        self.assertEqual(m.normalize_dream(bad)["lane"],"QUARANTINE")

    def test_static_dispatch_physarum(self):
        report=m.dispatch("physarum_route",
                {"graph":self.cases["graph"],"start":"Genesis","target":"Memory"},
                self.manifest,self.root,explicit_readonly=True)
        self.assertEqual(report["result"]["distance"],6)
        self.assertFalse(report["production_authority"])

    def test_static_dispatch_slime_trace(self):
        out=m.dispatch("slime_trace",{"old":.4,"error":.3,"decay":.9},
                       self.manifest,self.root,explicit_readonly=True)
        self.assertGreater(out["result"]["trace"],0)
        self.assertLess(out["result"]["trace"],1)
        self.assertFalse(out["result"]["weights_changed"])

    def test_slime_nan_rejected(self):
        with self.assertRaisesRegex(ValueError,"INVALID_SLIME_RANGE"):
            m.slime_trace({"old":float("nan"),"error":.1,"decay":.9})

    def test_static_graph_dedupe(self):
        inp=[["A","B",1],["A","B",1],["B","C",2]]
        out=m.graph_dedupe(inp)
        self.assertEqual(out["duplicates_removed"],1)
        self.assertEqual(len(out["edges"]),2)

    def test_dedupe_rejects_path_like_nodes(self):
        with self.assertRaisesRegex(ValueError,"INVALID_DEDUPE_EDGE"):
            m.graph_dedupe([["../../secret","B",1]])

    def test_trinity_veto_majority_and_high_risk(self):
        good=m.trinity_veto({"votes":["accelerate"]*2+["hold"],"risk":.2})
        bad=m.trinity_veto({"votes":["accelerate"]*3,"risk":.9})
        self.assertEqual(good["advisory_vote"],"ACCELERATE")
        self.assertEqual(bad["advisory_vote"],"HOLD")
        self.assertFalse(good["execution_authority"])

    def test_trinity_tie_holds(self):
        self.assertEqual(m.trinity_veto({"votes":["accelerate","hold","stabilize"],"risk":0})["advisory_vote"],"HOLD")

    def test_nas_snapshot_is_metadata_only(self):
        out=m.dispatch("nas_snapshot",{"state":"LOCAL_SNAPSHOT_ONLY","count":4,"network_access":False},
                       self.manifest,self.root,explicit_readonly=True)
        self.assertEqual(out["result"]["snapshot_record_count"],4)
        self.assertFalse(out["result"]["nas_mutation"])
        self.assertFalse(out["result"]["live_nas_connected"])

    def test_nas_live_claim_rejected(self):
        with self.assertRaisesRegex(ValueError,"LIVE_NAS"):
            m.nas_snapshot({"state":"LIVE_NAS","count":4,"network_access":False})

    def test_canonical_receipt_is_deterministic(self):
        a=self.run_evolution()
        b=self.run_evolution()
        self.assertEqual(a,b)
        self.assertEqual(a["receipt_sha256"],m.seal({k:v for k,v in a.items() if k!="receipt_sha256"}))

    def test_source_tampering_rejected(self):
        with tempfile.TemporaryDirectory() as root:
            path=Path(root)/"fake.json"
            path.write_bytes((SAMPLES/"corrected_cases.json").read_bytes()+b" ")
            with self.assertRaisesRegex(ValueError,"FROZEN_GIT_BLOB_MISMATCH"):
                m.load_frozen(path,m.CORPUS_GIT_BLOB,m.CASES)

    def test_source_catalog_invalid_live_status_rejected(self):
        catalog=copy.deepcopy(self.catalog)
        catalog["nas_live_access"]="LIVE_CONNECTED"
        with self.assertRaisesRegex(ValueError,"UNTRUSTED_NAS"):
            self.run_evolution(catalog=catalog)

    def test_unapproved_gene_registration_rejected(self):
        manifest=copy.deepcopy(self.manifest)
        manifest["modules"].append("legacy_exec")
        with self.assertRaisesRegex(ValueError,"UNAUTHORIZED"):
            self.run_evolution(manifest=manifest)


if __name__=="__main__":
    unittest.main()
