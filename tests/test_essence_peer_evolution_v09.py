"""ESSENCE v0.9 tests: real factory in isolated staging; never execution rights."""
import copy
import json
from pathlib import Path
import tempfile
import unittest

from tests.test_essence_collective_seed import fixture, ROOT
from tools import essence_collective_seed as g
from tools import essence_peer_evolution_v09 as v

def inputs():
    entries,things,fetch=fixture(count=5)
    repo=entries[0]["repo"]
    for i,role in ((1,"memory"),(2,"recovery")):
        donor=entries[i]["repo"]
        item={
          "id": f"idea-peer-{role}-{i}", "role":role,
          "idea":f"Preserve unique independent {role} research after provenance checks.",
          "evidence_sha256":str(i)*64,
          "precommit_sha256":str(i+1)*64,
          "origin_receipt_sha256":str(i+2)*64,
        }
        package=g.empty_innovations(donor)
        package["entries"].append(item)
        g.validate_innovations(package,donor)
        things[donor][g.CANONICAL+"/innovations.json"]={
            "data":json.dumps(package).encode(),"blob_sha":"local-test"}
    snapshot=g.collect_snapshot(entries,fetch,ROOT,"2026-11-13T18:30:00+00:00")
    manifest_raw=things[repo][g.CANONICAL+"/manifest.json"]["data"]
    manifest=json.loads(manifest_raw)
    return snapshot,repo,manifest,manifest_raw

def reseal(snapshot):
    snapshot["snapshot_sha256"]=g.digest({
        k:value for k,value in snapshot.items() if k!="snapshot_sha256"})

class PeerEvolutionContracts(unittest.TestCase):
    def test_born_children_are_REAL_static_python_proposals(self):
        snapshot,repo,manifest,raw=inputs()
        with tempfile.TemporaryDirectory() as d:
            out=Path(d)/"new"
            rec=v.run(snapshot,repo,manifest,ROOT,out,raw)
            self.assertEqual(rec["new_microcore_proposals"],2)
            self.assertEqual(rec["peer_offers"],2)
            self.assertEqual(rec["learning_generation"],0)
            self.assertEqual(rec["independent_evaluations"],0)
            self.assertFalse(rec["production_authority"])
            self.assertFalse(rec["automatic_child_activation"])
            self.assertFalse(rec["foreign_weights_or_code_executed"])
            children=list((out/g.CANONICAL/"microkernels").glob("*.py"))
            self.assertEqual(len(children),2)
            for child in children:
                self.assertIn("research", child.read_text().lower())
            msgs=json.loads((out/"peer_messages.json").read_text())
            self.assertEqual(len(msgs["local_unsent_responses"]),2)
            self.assertFalse(msgs["published_to_other_repositories"])
            for x in msgs["local_unsent_responses"]:
                offer=x["offer"];reply=x["reply"]
                self.assertEqual(offer["offer_sha256"],g.digest({
                    k:q for k,q in offer.items() if k!="offer_sha256"}))
                self.assertEqual(reply["reply_sha256"],g.digest({
                    k:q for k,q in reply.items() if k!="reply_sha256"}))
                self.assertEqual(reply["in_reply_to_sha256"],offer["offer_sha256"])
                self.assertFalse(reply["production_authority"])
            prior=json.loads((out/"learning_state.json").read_text())
            self.assertEqual(prior["generation"],0)

    def test_live_manifest_bytes_are_mandatory(self):
        snapshot,repo,manifest,raw=inputs()
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaisesRegex(ValueError,"LOCAL_MANIFEST_NOT_LIVE_DONOR_VERSION"):
                v.run(snapshot,repo,manifest,ROOT,Path(d)/"out",b"modified")

    def test_root_bytes_altered_rejected(self):
        snapshot,repo,manifest,raw=inputs()
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaisesRegex(ValueError,"CANONICAL_ROOT_CHANGED"):
                v.run(snapshot,repo,manifest,b"modified",Path(d)/"out",raw)

    def test_snapshot_modified_digest_rejected(self):
        snapshot,repo,manifest,raw=inputs()
        snapshot["verified_donor_count"]=100
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaisesRegex(ValueError,"SNAPSHOT_TAMPERED"):
                v.run(snapshot,repo,manifest,ROOT,Path(d)/"out",raw)

    def test_foreign_repo_not_a_donor_rejected(self):
        snapshot,repo,manifest,raw=inputs()
        snapshot["innovation_candidates"][0]["repo"]="Hawkar-usls/UnknownRepo"
        reseal(snapshot)
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaisesRegex(ValueError,"PEER_NOT_INDEPENDENT_VERIFIED_DONOR"):
                v.run(snapshot,repo,manifest,ROOT,Path(d)/"out",raw)

    def test_forged_independent_performance_not_authority(self):
        snapshot,repo,manifest,raw=inputs()
        snapshot["innovation_candidates"][0]["performance_gain"]=999
        reseal(snapshot)
        with tempfile.TemporaryDirectory() as d:
            rec=v.run(snapshot,repo,manifest,ROOT,Path(d)/"out",raw)
            self.assertFalse(rec["production_authority"])
            self.assertEqual(rec["learning_generation"],0)

    def test_duplicate_peer_cannot_multiply(self):
        snapshot,repo,manifest,raw=inputs()
        snapshot["innovation_candidates"].append(
            copy.deepcopy(snapshot["innovation_candidates"][0]))
        reseal(snapshot)
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaisesRegex(ValueError,"DUPLICATE_ORIGIN_ID"):
                v.run(snapshot,repo,manifest,ROOT,Path(d)/"out",raw)

    def test_bad_sha_is_rejected(self):
        snapshot,repo,manifest,raw=inputs()
        snapshot["innovation_candidates"][0]["origin_receipt_sha256"]="fake"
        reseal(snapshot)
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaisesRegex(ValueError,"MISSING_PINNED_SOURCE"):
                v.run(snapshot,repo,manifest,ROOT,Path(d)/"out",raw)

    def test_proposals_never_overwrite(self):
        snapshot,repo,manifest,raw=inputs()
        with tempfile.TemporaryDirectory() as d:
            out=Path(d)/"out"
            v.run(snapshot,repo,manifest,ROOT,out,raw)
            with self.assertRaisesRegex(FileExistsError,"NO_STAGING_OVERWRITE"):
                v.run(snapshot,repo,manifest,ROOT,out,raw)

    def test_no_peer_means_no_birth(self):
        snapshot,repo,manifest,raw=inputs()
        snapshot["innovation_candidates"]=[]
        reseal(snapshot)
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaisesRegex(ValueError,"NO_OTHER_REPO_IDEAS"):
                v.run(snapshot,repo,manifest,ROOT,Path(d)/"out",raw)

    def test_self_origin_is_not_external_peer(self):
        snapshot,repo,manifest,raw=inputs()
        foreign=copy.deepcopy(snapshot["innovation_candidates"][0])
        foreign["repo"]=repo
        snapshot["innovation_candidates"]=[foreign]
        reseal(snapshot)
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaisesRegex(ValueError,"NO_OTHER_REPO_IDEAS"):
                v.run(snapshot,repo,manifest,ROOT,Path(d)/"out",raw)

    def test_malicious_unknown_role_rejected(self):
        snapshot,repo,manifest,raw=inputs()
        snapshot["innovation_candidates"][0]["role"]="shell"
        reseal(snapshot)
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaisesRegex(ValueError,"BAD_IDEA_PROVENANCE"):
                v.run(snapshot,repo,manifest,ROOT,Path(d)/"out",raw)

if __name__=="__main__":
    unittest.main()
