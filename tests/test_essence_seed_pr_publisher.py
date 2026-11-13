"""Offline draft-PR publisher tests; no live GitHub writes."""
import json
from pathlib import Path
import tempfile
import unittest

from tools import essence_collective_seed as c
from tools import essence_seed_pr_publisher as p
from tests.test_essence_collective_seed import fixture, ROOT, BANK

TARGET="Hawkar-usls/new-lab"
class PublishContracts(unittest.TestCase):
    def setUp(self):
        self.ctx=tempfile.TemporaryDirectory()
        self.root=Path(self.ctx.name)
        repos,_,fetch=fixture()
        s=c.collect_snapshot(repos,fetch,ROOT,"2026-11-13")
        c.seed_bundle(s,TARGET,self.root,ROOT,BANK)
        self.calls=[]

    def tearDown(self):
        self.ctx.cleanup()

    def fake(self,method,path,token,payload=None):
        self.calls.append((method,path,payload))
        if method=="GET" and path=="/repos/"+TARGET:
            return {"full_name":TARGET,"archived":False,"disabled":False,
                    "fork":False,"default_branch":"main"}
        if method=="GET" and "/contents/" in path: return None
        if method=="GET" and "/git/ref/heads/" in path:
            return {"object":{"sha":"a"*40}}
        if method=="POST" and "/pulls" in path:
            return {"html_url":"https://github.com/"+TARGET+"/pull/1","number":1}
        return {}

    def test_produces_only_one_draft_pr_branch(self):
        r=p.publish_draft(TARGET,self.root,"scoped-test-token-123",self.fake)
        self.assertEqual(r["pr_number"],1)
        self.assertFalse(r["production_activated"])
        refs=[x for x in self.calls if x[0]=="POST" and "/git/refs" in x[1]]
        self.assertEqual(len(refs),1)
        writes=[x for x in self.calls if x[0]=="PUT"]
        self.assertEqual(len(writes),7)
        self.assertTrue(all("/contents/.janus/essence/" in x[1] for x in writes))
        self.assertEqual(self.calls[-1][2]["draft"],True)
        self.assertEqual(self.calls[-1][2]["base"],"main")

    def test_missing_explicit_token_blocks_all_remote_access(self):
        with self.assertRaisesRegex(PermissionError,"EXPLICIT_TARGET_SCOPED_TOKEN_REQUIRED"):
            p.publish_draft(TARGET,self.root,"",self.fake)
        self.assertEqual(self.calls,[])

    def test_refuses_second_root_before_writes(self):
        def existing(method,path,token,payload=None):
            if method=="GET" and "/contents/" in path:return {"sha":"b"*40}
            return self.fake(method,path,token,payload)
        with self.assertRaisesRegex(ValueError,"ALREADY_HAS_ROOT_NO_SECOND_ROOT"):
            p.publish_draft(TARGET,self.root,"scoped-test-token-123",existing)
        self.assertFalse(any(x[0] in ("PUT","POST") for x in self.calls))

    def test_fork_repository_rejected(self):
        def fork(method,path,token,payload=None):
            if method=="GET" and path=="/repos/"+TARGET:
                return {"full_name":TARGET,"fork":True,"default_branch":"main"}
            return self.fake(method,path,token,payload)
        with self.assertRaisesRegex(ValueError,"UNSAFE_TARGET_REPOSITORY"):
            p.publish_draft(TARGET,self.root,"scoped-test-token-123",fork)
        self.assertEqual(self.calls,[])

    def test_tampered_factory_rejected_before_remote_calls(self):
        (self.root/c.CANONICAL/"collective_seed.py").write_text("bad",encoding="utf-8")
        with self.assertRaisesRegex(ValueError,"FACTORY_HASH_MISMATCH"):
            p.publish_draft(TARGET,self.root,"scoped-test-token-123",self.fake)
        self.assertEqual(self.calls,[])

    def test_wrong_target_binding_rejected(self):
        with self.assertRaisesRegex(ValueError,"WRONG_REPOSITORY_BINDING"):
            p.bundle_files(self.root,"Hawkar-usls/another-target")

    def test_untrusted_target_rejected(self):
        with self.assertRaisesRegex(ValueError,"INVALID_REPOSITORY"):
            p.publish_draft("evil/other",self.root,"scoped-test-token-123",self.fake)

if __name__=="__main__":
    unittest.main()
