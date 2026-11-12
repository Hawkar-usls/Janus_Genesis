"""Fail-closed JSON contract for real Git-backed lease TTL/fencing proof."""
from __future__ import annotations

import copy
import json
from pathlib import Path
import tempfile
import unittest

from tools.janus_nexus_live_git_lease_expiry_v1 import (
    LeaseHold,base,seed,renew,takeover,validate_three,assert_holder,
    late_attempt,verify,save_once,read,sha256,TTL_MS,
)

RUN="43275243138"
SOURCE="a"*40
SEED_HEAD="b"*40
RENEW_HEAD="c"*40
TAKE_HEAD="d"*40
T=1_800_000_000_000


class RealGitLeaseExpiryTests(unittest.TestCase):
    def setUp(self):
        self.first=seed(RUN,1,SOURCE,T,"1"*32)
        self.next=renew(self.first,T+1000)
        self.successor=takeover(self.first,self.next,T+1000+TTL_MS+2000,
                                "2"*32)

    def late(self):
        return late_attempt(self.first,self.next,self.successor,
                            T+TTL_MS+3500,True,RENEW_HEAD,TAKE_HEAD)

    def test_real_wallclock_chain_with_renewal_and_epoch_takeover(self):
        validate_three(self.first,self.next,self.successor)
        self.assertEqual(self.next["lease_id"],self.first["lease_id"])
        self.assertEqual(self.next["fence_epoch"],1)
        self.assertEqual(self.successor["fence_epoch"],2)
        self.assertNotEqual(self.successor["lease_id"],self.first["lease_id"])
        self.assertTrue(self.successor["observed_ms"]>=self.next["expires_at_ms"])
        self.assertEqual(self.next["previous_digest"],sha256(self.first))

    def test_renew_after_expiry_and_takeover_before_expiry_hold(self):
        with self.assertRaisesRegex(LeaseHold,"OLD_LEASE_EXPIRED_BEFORE_RENEW"):
            renew(self.first,self.first["expires_at_ms"])
        with self.assertRaisesRegex(LeaseHold,"TAKEOVER_BEFORE_EXPIRE"):
            takeover(self.first,self.next,self.next["expires_at_ms"]-1,"2"*32)

    def test_stale_owner_and_expired_owner_rejected(self):
        with self.assertRaisesRegex(LeaseHold,"STALE_FENCING_TOKEN_REJECTED"):
            assert_holder(self.successor,self.next,self.successor["observed_ms"])
        with self.assertRaisesRegex(LeaseHold,"PRESENTED_LEASE_EXPIRED"):
            assert_holder(self.next,self.next,self.next["expires_at_ms"])
        assert_holder(self.successor,self.successor,self.successor["observed_ms"])

    def test_stale_git_nonforce_push_proof_required(self):
        with self.assertRaisesRegex(LeaseHold,"OLD_GIT_PUSH_NOT_REJECTED"):
            late_attempt(self.first,self.next,self.successor,T+TTL_MS+3500,
                         False,RENEW_HEAD,TAKE_HEAD)
        with self.assertRaisesRegex(LeaseHold,"GIT_FENCE_HEAD_INVALID"):
            late_attempt(self.first,self.next,self.successor,T+TTL_MS+3500,
                         True,RENEW_HEAD,RENEW_HEAD)

    def test_verified_one_run_chain_only(self):
        p=self.late()
        v=verify(self.first,self.next,self.successor,p,
                 SEED_HEAD,RENEW_HEAD,TAKE_HEAD,TAKE_HEAD)
        self.assertEqual(v["status"],
                         "PASS_SCOPED_REAL_WALLCLOCK_TTL_TAKEOVER_GIT_STALE_FENCE")
        self.assertTrue(v["late_owner_semantic_rejected"])
        self.assertTrue(v["late_owner_git_nonforce_rejected"])
        self.assertFalse(v["full_issue_162_acceptance"])
        self.assertFalse(v["external_effect_lease_fence_tested"])
        with self.assertRaisesRegex(LeaseHold,"DURABLE_GIT_LINEAGE_OR_HEAD_MISMATCH"):
            verify(self.first,self.next,self.successor,p,
                   SEED_HEAD,RENEW_HEAD,TAKE_HEAD,SEED_HEAD)

    def test_forged_late_or_successor_rejected(self):
        late=self.late()
        late["nonforce_git_push_rejected"]=False
        with self.assertRaises(LeaseHold):
            verify(self.first,self.next,self.successor,late,
                   SEED_HEAD,RENEW_HEAD,TAKE_HEAD,TAKE_HEAD)
        corrupt=copy.deepcopy(self.successor)
        corrupt["fence_epoch"]=1
        with self.assertRaisesRegex(LeaseHold,"TAKEOVER_CHAIN_INVALID"):
            validate_three(self.first,self.next,corrupt)

    def test_forged_source_or_history_rejected(self):
        bad=copy.deepcopy(self.next)
        bad["source_sha"]="f"*40
        with self.assertRaises(LeaseHold):
            validate_three(self.first,bad,self.successor)
        bad=copy.deepcopy(self.successor)
        bad["previous_digest"]="f"*64
        with self.assertRaisesRegex(LeaseHold,"TAKEOVER_CHAIN_INVALID"):
            validate_three(self.first,self.next,bad)

    def test_bad_inputs_fail_closed(self):
        with self.assertRaises(LeaseHold):
            seed("../escape",1,SOURCE,T,"1"*32)
        with self.assertRaises(LeaseHold):
            seed(RUN,True,SOURCE,T,"1"*32)
        with self.assertRaises(LeaseHold):
            seed(RUN,1,SOURCE,T,"1"*16)
        with self.assertRaises(LeaseHold):
            seed(RUN,1,SOURCE,True,"1"*32)
        with self.assertRaises(LeaseHold):
            renew(self.first,T-1)

    def test_immutable_write_and_symlink_fail_closed(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            folder=base(root,RUN,1)
            path=folder/"seed.json"
            save_once(path,self.first)
            save_once(path,self.first)
            self.assertEqual(read(path),self.first)
            with self.assertRaisesRegex(LeaseHold,"IMMUTABLE_RECEIPT_CONFLICT"):
                save_once(path,self.next)
            link=folder/"fake.json"
            link.symlink_to(path)
            with self.assertRaisesRegex(LeaseHold,"RECEIPT_UNAVAILABLE"):
                read(link)

    def test_expired_new_owner_not_late_write_permission(self):
        with self.assertRaisesRegex(LeaseHold,"PRESENTED_LEASE_EXPIRED"):
            assert_holder(self.successor,self.successor,
                          self.successor["expires_at_ms"])


if __name__=="__main__":
    unittest.main()
