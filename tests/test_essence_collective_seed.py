"""Offline adversarial tests for ESSENCE collective seeding and bounded local birth."""
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from tools import essence_collective_seed as e

ROOT=b"canonical ESSENCE root test fixture"
BANK=b"canonical gene bank fixture"
GENES={
"sensing":["MicroGPT","JanusTinyTransformer"],
"memory":["CatGPT","All_starsGPT"],
"planning":["JGPT1","Trinity"],
"verification":["Trinity","NonceMapGPT"],
"recovery":["Yaksa+12","GEX"],
"coding":["MicroGPTSlime","All_starsGPT"]
}

def donor(name):
    repo="Hawkar-usls/"+name
    m={"schema":e.ROOT_SCHEMA,"repository":repo,"enabled":False,
       "activation":"EXPLICIT_READONLY_TEST_ONLY",
       "birth_policy":"PROPOSAL_ONLY",
       "capabilities":{x:False for x in e.DENIED},
       "microkernels":[{"role":r,"id":f"cell-{r}-{i:02d}",
                        "generation":0,"gene_sources":GENES[r]}
                       for i,r in enumerate(e.ROLES)]}
    return m

def fixture(count=5):
    repo=[{"repo":"Hawkar-usls/core"+str(i),"default_branch":"main"} for i in range(count)]
    things={}
    for r in repo:
        key=r["repo"]
        m=donor(key.split("/")[-1])
        things[key]={
            e.CANONICAL+"/kernel.py":{"blob_sha":"abc","data":ROOT},
            e.CANONICAL+"/manifest.json":{
                "blob_sha":"def","data":json.dumps(m).encode()}}
    def fetch(name,path,branch):
        assert branch=="main"
        return things[name].get(path)
    return repo,things,fetch

class CollectiveContracts(unittest.TestCase):
    def setUp(self):
        entries,_,fetch=fixture()
        self.snapshot=e.collect_snapshot(entries,fetch,ROOT,"2026-11-13T10:00:00+00:00")

    def test_supermajority_collects_all_valid_donors(self):
        s=self.snapshot
        self.assertEqual(s["verified_donor_count"],5)
        self.assertEqual(s["quorum"],4)
        self.assertEqual({r:set(g) for r,g in s["genes_by_role"].items()},
                         {r:set(g) for r,g in GENES.items()})
        self.assertTrue(e.check_snapshot(s,ROOT))
        self.assertFalse(s["automatic_replication_enabled"])

    def test_deterministic_snapshot(self):
        entries,things,fetch=fixture()
        snap=e.collect_snapshot(list(reversed(entries)),fetch,ROOT,
                                "2026-11-13T10:00:00+00:00")
        self.assertEqual(snap["snapshot_sha256"],self.snapshot["snapshot_sha256"])

    def test_corrupt_source_cannot_cast_vote(self):
        entries,things,fetch=fixture()
        things["Hawkar-usls/core1"][e.CANONICAL+"/kernel.py"]["data"]=b"evil"
        snap=e.collect_snapshot(entries,fetch,ROOT,"2026-11-13")
        self.assertEqual(snap["verified_donor_count"],4)
        self.assertEqual(snap["excluded"][0]["reason"],"DIVERGENT_KERNEL_CODE")

    def test_active_donor_is_excluded(self):
        entries,things,fetch=fixture()
        key="Hawkar-usls/core2"
        m=json.loads(things[key][e.CANONICAL+"/manifest.json"]["data"])
        m["enabled"]=True
        things[key][e.CANONICAL+"/manifest.json"]["data"]=json.dumps(m).encode()
        snap=e.collect_snapshot(entries,fetch,ROOT,"2026-11-13")
        self.assertEqual(snap["verified_donor_count"],4)

    def test_duplicate_donor_is_rejected(self):
        s=json.loads(json.dumps(self.snapshot))
        s["donors"][1]["repo"]=s["donors"][0]["repo"]
        s["snapshot_sha256"]=e.digest({k:v for k,v in s.items() if k!="snapshot_sha256"})
        with self.assertRaisesRegex(ValueError,"DUPLICATE_DONOR"):
            e.check_snapshot(s,ROOT)

    def test_tampered_genes_rejected(self):
        s=json.loads(json.dumps(self.snapshot))
        s["genes_by_role"]["sensing"]=["unapproved-code"]
        with self.assertRaisesRegex(ValueError,"SNAPSHOT_TAMPERED"):
            e.check_snapshot(s,ROOT)

    def test_one_root_seed_and_no_overwrite(self):
        with tempfile.TemporaryDirectory() as temp:
            out=Path(temp)
            origin=e.seed_bundle(self.snapshot,"Hawkar-usls/new-lab",out,ROOT,BANK)
            self.assertEqual(origin["root_count"],1)
            self.assertEqual((out/e.CANONICAL/"kernel.py").read_bytes(),ROOT)
            self.assertEqual((out/e.CANONICAL/"gene_bank.py").read_bytes(),BANK)
            m=e.load(out/e.CANONICAL/"manifest.json")
            self.assertTrue(e.validate_manifest(m,"Hawkar-usls/new-lab"))
            with self.assertRaises(FileExistsError):
                e.seed_bundle(self.snapshot,"Hawkar-usls/new-lab",out,ROOT,BANK)

    def test_existing_parent_cannot_be_reseeded(self):
        with tempfile.TemporaryDirectory() as temp:
            with self.assertRaisesRegex(ValueError,"TARGET_ALREADY_HAS_VERIFIED_ROOT"):
                e.seed_bundle(self.snapshot,"Hawkar-usls/core0",temp,ROOT)

    def test_bad_target_path_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            with self.assertRaisesRegex(ValueError,"INVALID_REPOSITORY"):
                e.seed_bundle(self.snapshot,"../secrets",temp,ROOT)

    def test_grow_local_module_with_evidence_and_no_new_root(self):
        with tempfile.TemporaryDirectory() as temp:
            base=Path(temp)
            origin=e.seed_bundle(self.snapshot,"Hawkar-usls/new-lab",base/"seed",ROOT)
            manifest=e.load(base/"seed"/e.CANONICAL/"manifest.json")
            asks=[{"role":"verification",
                   "need":"Validate new duration prediction calibration",
                   "evidence_sha256":"a"*64}]
            result=e.grow_modules("Hawkar-usls/new-lab",manifest,origin,asks,base/"growing")
            self.assertFalse(result["new_root_created"])
            self.assertEqual(len(result["proposals"]),1)
            self.assertTrue((base/"growing"/e.CANONICAL/"microkernels"/
                            (result["proposals"][0]["id"]+".py")).exists())

    def test_tampered_origin_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            base=Path(temp)
            origin=e.seed_bundle(self.snapshot,"Hawkar-usls/new-lab",base/"seed",ROOT)
            manifest=e.load(base/"seed"/e.CANONICAL/"manifest.json")
            origin["donor_count"]=999
            asks=[{"role":"sensing","need":"Check actual system task durations",
                   "evidence_sha256":"0"*64}]
            with self.assertRaisesRegex(ValueError,"ORIGIN_TAMPERED"):
                e.grow_modules("Hawkar-usls/new-lab",manifest,origin,asks,base/"grow")

    def test_module_output_never_grants_authority(self):
        m=e.module_text("planning","planning-check","f"*64)
        namespace={}
        exec(m,namespace)
        result=namespace["evaluate"]({"a":.5})
        self.assertTrue(result["proposal_only"])
        self.assertFalse(result["activation_allowed"])
        with self.assertRaises(ValueError):
            namespace["evaluate"]({"test":100})

if __name__=="__main__":
    unittest.main()
