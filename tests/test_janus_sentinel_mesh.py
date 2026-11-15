import unittest
from datetime import datetime,timezone,timedelta
from tools import janus_sentinel_mesh as m
NOW=datetime(2026,11,15,12,0,tzinfo=timezone.utc)
def row(identity=1,age=1,status="completed",conclusion="success"):
    return {"id":identity,"event":"schedule","head_branch":"main",
            "status":status,"conclusion":conclusion,
            "created_at":(NOW-timedelta(minutes=age)).isoformat()}
class MeshContract(unittest.TestCase):
    def test_stale_requires_previous_success(self):
        self.assertEqual(m.health([row(age=55)],NOW)["status"],"STALE_SILENT")
        self.assertEqual(m.health([row(conclusion="failure",age=55)],NOW)["status"],"UNKNOWN_NO_PRIOR_SUCCESS")
        self.assertEqual(m.health([row(3,7,conclusion="failure"),row(2,9)],NOW)["status"],"STALE_FAILED")
        self.assertEqual(m.health([row(3,4,conclusion="failure"),row(2,9)],NOW)["status"],"HEALTHY")
        self.assertEqual(m.health([row(3,70,status="in_progress",conclusion=None),row(2,80)],NOW)["status"],"BUSY_OR_PENDING_HOLD")
    def test_main_only_and_unique(self):
        x=row();x["head_branch"]="untrusted"
        with self.assertRaises(ValueError):m.health([x],NOW)
        with self.assertRaises(ValueError):m.health([row(),row()],NOW)
        x=row();x["event"]="pull_request"
        self.assertEqual(m.health([x],NOW)["status"],"UNKNOWN_NO_PEER_EVIDENCE")
    def test_primary_and_recovery_only(self):
        ok={x:{"status":"HEALTHY","last_run_id":3} for x in m.ROLES}
        ok["B"]={"status":"STALE_SILENT","last_run_id":2}
        self.assertEqual(m.decide(m.ROLES["A"],NOW,ok)["target"],"B")
        self.assertIsNone(m.decide(m.ROLES["C"],NOW,ok)["target"])
        self.assertIsNone(m.decide(m.ROLES["A"],NOW,ok,recovery_only=True)["target"])
        ok["A"]={"status":"STALE_FAILED","last_run_id":1}
        self.assertEqual(m.decide(m.ROLES["C"],NOW,ok)["target"],"A")
    def test_missing_credential(self):
        called=[]
        def fetch(repo,token):return [row(age=62)] if repo.endswith("Janus_Genesis") else [row()]
        rec=m.run(m.ROLES["A"],"1234","x"*30,"",now=NOW,fetch=fetch,dispatch=lambda *args:called.append(args))
        self.assertEqual(rec["plan"]["target"],"B")
        self.assertEqual(rec["outcome"],"HOLD_NO_CROSS_REPO_ACTIONS_WRITE_TOKEN")
        self.assertFalse(rec["actual_recovery_verified"])
        self.assertFalse(called)
        rec2=m.run(m.ROLES["A"],"1234","x"*30,"secret"*10,now=NOW,fetch=fetch,
                   dispatch=lambda *args:"REMOTE_DISPATCH_SUBMITTED_NOT_RECOVERY_PROOF")
        self.assertEqual(rec2["outcome"],"REMOTE_DISPATCH_SUBMITTED_NOT_RECOVERY_PROOF")
        self.assertFalse(rec2["actual_recovery_verified"])
    def test_unknown_and_loop(self):
        unknown={x:{"status":"UNKNOWN_PEER_API_HOLD"} for x in m.ROLES}
        self.assertIsNone(m.decide(m.ROLES["A"],NOW,unknown)["target"])
        with self.assertRaises(ValueError):m.decide("attacker/repository",NOW,unknown)
        with self.assertRaises(ValueError):m.send("A",m.ROLES["A"],"123","x"*50)
if __name__=="__main__":unittest.main()
