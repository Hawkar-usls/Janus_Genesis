"""ESSENCE GitHub peer-inbox origin/permission tests."""
from __future__ import annotations
import copy
from pathlib import Path
import sys
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
SRC=ROOT/".janus"/"essence"
DATA=ROOT/"research"/"essence"/"peer_v13"
sys.path.insert(0,str(SRC))
import peer_inbox_v13 as peer

class PeerInboxV13Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root=peer.read_json(SRC/"manifest.json")
        cls.ledger=peer.read_ledger(DATA/"source_ledger.json")
        cls.inbox=peer.read_json(DATA/"inbox.json")

    def check(self,inbox=None,ledger=None,root=None):
        return peer.review(inbox if inbox is not None else self.inbox,
                           ledger if ledger is not None else self.ledger,
                           root if root is not None else self.root)

    def test_input_from_real_github_src(self):
        self.assertEqual(peer.git_blob((DATA/"source_ledger.json").read_bytes()),
                         peer.LEDGER_GIT_BLOB)
        self.assertEqual(len(self.ledger["peers"]),6)

    def test_incoming_peer_idea_is_research_only(self):
        result=self.check()
        self.assertEqual(result["repository"],self.root["repository"])
        self.assertNotEqual(result["source_repo"],result["repository"])
        self.assertEqual(result["status"],"GITHUB_PEER_IDEA_RECEIVED_REQUIRES_INDEPENDENT_TEST")
        self.assertEqual(result["research_generation"],1)
        self.assertFalse(result["new_candidate_proven"])
        self.assertFalse(result["production_authority"])

    def test_hash_self_check(self):
        result=self.check()
        self.assertEqual(result["receipt_sha256"],peer.sha256({
            k:v for k,v in result.items() if k!="receipt_sha256"}))

    def test_no_code_from_other_repo_executed(self):
        self.assertFalse(self.check()["foreign_code_executed"])
        self.assertFalse(self.inbox["executable"])

    def test_change_offer_hash_fails(self):
        bad=copy.deepcopy(self.inbox)
        bad["offer"]["offer_sha256"]="0"*64
        with self.assertRaisesRegex(ValueError,"UNTRUSTED_SOURCE_OFFER"):
            self.check(inbox=bad)

    def test_resealed_forged_origin_fails(self):
        bad=copy.deepcopy(self.inbox)
        bad["offer"]["source_commit_sha1"]="0"*40
        bad["offer"]["offer_sha256"]=peer.sha256({
            k:v for k,v in bad["offer"].items() if k!="offer_sha256"})
        with self.assertRaisesRegex(ValueError,"ORIGIN_MISMATCH"):
            self.check(inbox=bad)

    def test_resealed_forged_replay_fails(self):
        bad=copy.deepcopy(self.inbox)
        bad["offer"]["source_replay_receipt_sha256"]="1"*64
        bad["offer"]["offer_sha256"]=peer.sha256({
            k:v for k,v in bad["offer"].items() if k!="offer_sha256"})
        with self.assertRaisesRegex(ValueError,"ORIGIN_MISMATCH"):
            self.check(inbox=bad)

    def test_wrong_target_repository_fails(self):
        bad=copy.deepcopy(self.inbox)
        bad["offer"]["target_repo"]="Hawkar-usls/fake"
        bad["offer"]["offer_sha256"]=peer.sha256({
            k:v for k,v in bad["offer"].items() if k!="offer_sha256"})
        with self.assertRaisesRegex(ValueError,"UNTRUSTED_SOURCE_OFFER"):
            self.check(inbox=bad)

    def test_foreign_code_execution_claim_rejected(self):
        bad=copy.deepcopy(self.inbox)
        bad["offer"]["foreign_code_imported"]=True
        bad["offer"]["offer_sha256"]=peer.sha256({
            k:v for k,v in bad["offer"].items() if k!="offer_sha256"})
        with self.assertRaisesRegex(ValueError,"UNTRUSTED_SOURCE_OFFER"):
            self.check(inbox=bad)

    def test_production_authority_never_accepted(self):
        bad=copy.deepcopy(self.inbox)
        bad["production_authority"]=True
        with self.assertRaisesRegex(ValueError,"INBOX_IDENTITY"):
            self.check(inbox=bad)

    def test_modified_parent_capabilities_denied(self):
        bad=copy.deepcopy(self.root)
        bad["capabilities"]["repo_write"]=True
        with self.assertRaises(PermissionError):
            self.check(root=bad)

    def test_unauthenticated_ledger_replacement_denied(self):
        with tempfile.TemporaryDirectory() as folder:
            p=Path(folder)/"ledger.json"
            p.write_bytes((DATA/"source_ledger.json").read_bytes()+b" ")
            with self.assertRaisesRegex(ValueError,"META_LEDGER_SOURCE_GIT_BLOB_MISMATCH"):
                peer.read_ledger(p)

    def test_repository_roster_has_unique_peers(self):
        bad=copy.deepcopy(self.ledger)
        bad["peers"][1]["repository"]=bad["peers"][0]["repository"]
        with self.assertRaisesRegex(ValueError,"UNTRUSTED_PEER_ROSTER"):
            # read_ledger re-checks blob too; direct reviewer is required to reject
            # an invalid roster even without the source-loading gate.
            peer.review(self.inbox,bad,self.root)

if __name__=="__main__":
    unittest.main()
