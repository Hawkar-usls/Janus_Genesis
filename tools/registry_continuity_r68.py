"""R6.8 reviewed persistent engineering context; no runtime writes or authority."""
import argparse,json,os,unittest
from pathlib import Path
try:
    from . import registry_homeostasis_r67 as h
except ImportError:
    import registry_homeostasis_r67 as h
b=h.b;u=h.u
POINTER=".janus/essence/registry_continuity_r68_current.json"
EVIDENCE=".janus/essence/registry_continuity_r68_evidence.json"
EVIDENCE_BLOB="49cf923c44d3c9d92c255d4638adec433344ca2f"
SOURCE_COMMIT="eb82f0a13fac1db659b5eabdd5580068b68e0ccc"
BASE={
"Hawkar-usls/Janus-Demiurge":("9fed5a9934544a77970d00dc5b752f04f77c61e8e78159820694ca018ea707c0","5ab5f33ae6d71c9cdf671b215de807d558f32ab2969c5ea59cb067b6959ca06f",45403619237,[138478352765,138478821737,138479371554]),
"Hawkar-usls/Janus_Genesis":("458901bf74f4eab11a3ae02d37cc420e7974e90d2fc84ee6264155ebaf8cd8ba","d884e246b8e2f26e608f4a60569abbc9986207b41e62b68531ade8b272430ee8",45403624469,[138478370410,138479254522,138479347381])}
def req(x,tag):u.req(x,tag)
def versions(repo,root="."):
    p,live,_,ptr,records=h.load(repo,root)
    prior=h.capsule(p,live,ptr,records,1)
    old=h.capsule(p,live,ptr,records,0)
    pin,oldpin,run,jobs=BASE[repo]
    b.checked(prior,pin);b.checked(old,oldpin)
    ev=b.read(h.rawread(Path(root)/EVIDENCE,EVIDENCE_BLOB))
    req(ev["schema"]=="janus.registry.r68.engineering_evidence.v1" and ev["scope"]=="FIRST_PARTY_REVIEWED_HISTORICAL_ENGINEERING_ONLY" and ev["action_authority"] is False,"EVIDENCE")
    rs=[r for r in ev["organs"] if r["repository"]==repo]
    req(rs==[{"repository":repo,"run":run,"jobs":jobs,"tests":9,"current_receipt":pin,"recovered_receipt":oldpin}],"EVIDENCE_SCOPE")
    req(ev["result"]=={"jobs_pass":6,"tests_pass":18,"scientific_release_changed":False,"planner_policy_changed":False,"recovery_read_only":True,"registry_document_reads_at_consumer":0},"RESULT")
    new=b.seal({"schema":"janus.registry.r68.context.v1","repository":repo,"generation":2,"previous_receipt":pin,"prior_context":prior,"engineering_evidence":rs[0],"evidence_blob":EVIDENCE_BLOB,"evidence_commit":SOURCE_COMMIT,"scientific_pin":live["receipt_sha256"],"action_authority":False,"model_promotion":False,"live_state_verified":False})
    return p,prior,new
def expected(repo,prior,new,g):
    req(type(g) is int and g in (1,2),"GENERATION")
    return {"schema":"janus.registry.r68.current.v1","repository":repo,"generation":g,"high_water":g,"previous_receipt":None if g==1 else prior["receipt_sha256"],"context_receipt":(prior if g==1 else new)["receipt_sha256"],"evidence_blob":None if g==1 else EVIDENCE_BLOB,"action_authority":False,"mode":"REVIEWED_RESEARCH_ONLY"}
def load(repo,root="."):
    p,prior,new=versions(repo,root)
    ptr=b.read((Path(root)/POINTER).read_bytes())
    req(ptr==expected(repo,prior,new,ptr["generation"]),"POINTER_MISMATCH")
    return p,prior,new,ptr
def check_transition(old,new,repo,prior,candidate):
    req(old==expected(repo,prior,candidate,1) and new==expected(repo,prior,candidate,2),"REVIEWED_TRANSITION")
    req(new["previous_receipt"]==old["context_receipt"],"PARENT")
def wake(repo,root="."):
    p,prior,new,ptr=load(repo,root)
    context=prior if ptr["generation"]==1 else new
    b.checked(context,ptr["context_receipt"])
    # Context is historical data. No state mutation and no authority.
    result={"repository":repo,"generation":ptr["generation"],"high_water":ptr["high_water"],"context_receipt":ptr["context_receipt"],"previous_receipt":ptr["previous_receipt"],"candidate_receipt":new["receipt_sha256"],"registry_document_reads":0,"action_authority":False,"production_promotion":False}
    print("R68_WAKE "+json.dumps(result,sort_keys=True))
    return context
class Tests(unittest.TestCase):
    def setUp(self):
        self.repo=os.environ["GITHUB_REPOSITORY"];self.p,self.old,self.new,self.ptr=load(self.repo)
    def test_same_context(self):self.assertEqual(wake(self.repo),wake(self.repo))
    def test_forward(self):check_transition(expected(self.repo,self.old,self.new,1),expected(self.repo,self.old,self.new,2),self.repo,self.old,self.new)
    def test_rollback_rejected(self):
        with self.assertRaises(ValueError):check_transition(expected(self.repo,self.old,self.new,2),expected(self.repo,self.old,self.new,1),self.repo,self.old,self.new)
    def test_science_fixed(self):self.assertEqual(self.new["scientific_pin"],self.old["scientific_pin"])
    def test_forged(self):
        with self.assertRaises(ValueError):check_transition(expected(self.repo,self.old,self.new,1),{**expected(self.repo,self.old,self.new,2),"action_authority":True},self.repo,self.old,self.new)
    def test_wrong_parent(self):
        with self.assertRaises(ValueError):check_transition(expected(self.repo,self.old,self.new,1),{**expected(self.repo,self.old,self.new,2),"previous_receipt":"0"*64},self.repo,self.old,self.new)
def main():
    ap=argparse.ArgumentParser();ap.add_argument("mode",choices=("test","wake","transition"));ap.add_argument("--previous");a=ap.parse_args()
    repo=os.environ["GITHUB_REPOSITORY"]
    if a.mode=="test":return 0 if unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(Tests)).wasSuccessful() else 1
    if a.mode=="transition":
        p,old,new,ptr=load(repo);check_transition(b.read(Path(a.previous).read_bytes()),ptr,repo,old,new)
        print("R68_TRANSITION_PASS "+repo)
    wake(repo);return 0
if __name__=="__main__":raise SystemExit(main())
