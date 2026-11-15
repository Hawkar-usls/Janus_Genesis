import unittest
from datetime import datetime,timezone,timedelta
from tools import janus_sentinel_mesh as m
from tools import janus_sentinel_mesh_lease as z
NOW=datetime(2026,11,15,15,45,tzinfo=timezone.utc)

def observation(now=NOW):
    peers={k:{"status":"HEALTHY","last_run_id":10} for k in m.ROLES}
    peers["B"]={"status":"STALE_SILENT","last_run_id":20}
    plan=m.decide(m.ROLES["A"],now,peers)
    return m.seal({"schema":m.SCHEMA,"observed_utc":m.iso(now),
                   "repository":m.ROLES["A"],"run_id":"12345",
                   "role":"A","peers":peers,"plan":plan,
                   "outcome":"HOLD_NO_CROSS_REPO_ACTIONS_WRITE_TOKEN"})

def state():
    return {"schema":z.STATE,"epoch":0,"last_dispatch":{},
            "cooldown_seconds":1800,"production_authority":False,
            "shared_failure_domain":"GitHub","version":"1.0"}

def fresh(repo,token):
    return [{"id":20,"status":"completed","conclusion":"success",
             "event":"schedule","head_branch":"main",
             "created_at":m.iso(NOW-timedelta(hours=1))}]

class CrossRepoLeaseContract(unittest.TestCase):
    def test_atomic_claim_and_cooldown(self):
        o=observation();first=z.transition(state(),o,NOW)
        self.assertEqual(first["epoch"],1)
        self.assertEqual(first["last_dispatch"]["B"]["issuer"],"A")
        with self.assertRaises(ValueError):z.transition(first,o,NOW)
        with self.assertRaises(ValueError):
            z.transition(first,o,NOW+timedelta(minutes=31))
        second=z.transition(first,observation(NOW+timedelta(minutes=31)),
                            NOW+timedelta(minutes=31))
        self.assertEqual(second["epoch"],2)
    def test_forgery_and_privilege_are_denied(self):
        o=observation()
        o["plan"]["target"]="C"
        with self.assertRaises(ValueError):z.transition(state(),o,NOW)
        bad=state();bad["production_authority"]=True
        with self.assertRaises(ValueError):z.state_check(bad)
        bad=state();bad["last_dispatch"]["WORKER"]={}
        with self.assertRaises(ValueError):z.state_check(bad)
    def test_no_tokens_no_wake(self):
        called=[]
        x=z.execute(observation(),"","","x"*30,NOW,
                    claim_fn=lambda *a:called.append("lease"),
                    dispatch=lambda *a:called.append("dispatch"))
        self.assertEqual(x["status"],"HOLD_MISSING_TWO_NARROW_TOKENS")
        self.assertFalse(x["actual_recovery_verified"])
        self.assertFalse(called)
    def test_cas_race_never_dispatches(self):
        called=[]
        x=z.execute(observation(),"a"*50,"b"*50,"c"*50,NOW,fetch=fresh,
                    claim_fn=lambda *a:"HOLD_CAS_LOST_NO_DISPATCH",
                    dispatch=lambda *a:called.append("dispatch"))
        self.assertEqual(x["status"],"HOLD_CAS_LOST_NO_DISPATCH")
        self.assertFalse(x["claim_won"])
        self.assertFalse(called)
    def test_claim_then_one_dispatch_not_recovery_proof(self):
        called=[]
        x=z.execute(observation(),"a"*50,"b"*50,"c"*50,NOW,fetch=fresh,
                    claim_fn=lambda *a:"CAS_WON",
                    dispatch=lambda *a:
                       (called.append(a) or
                        "REMOTE_DISPATCH_SUBMITTED_NOT_RECOVERY_PROOF"))
        self.assertTrue(x["claim_won"])
        self.assertTrue(x["dispatch_accepted"])
        self.assertFalse(x["actual_recovery_verified"])
        self.assertEqual(len(called),1)
    def test_no_prior_success_does_not_trigger(self):
        def fail_only(repo,token):
            rows=fresh(repo,token)
            rows[0]["conclusion"]="failure"
            return rows
        x=z.execute(observation(),"a"*50,"b"*50,"c"*50,NOW,
                    fetch=fail_only,claim_fn=lambda *a:"CAS_WON")
        self.assertFalse(x["claim_won"])
        self.assertFalse(x["dispatch_accepted"])

if __name__=="__main__":unittest.main()
