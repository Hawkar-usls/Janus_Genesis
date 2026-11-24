"""R6.6 lossless Git-backed lineage and historical recovery.
Fixed reviewed archive; fixture generations cannot enter live ESSENCE.
No Git writes or model changes at runtime. Recovery is a read-only view.
"""
import argparse, copy, json, os, tempfile, unittest
from pathlib import Path
try:
    from . import registry_update_r65 as u
except ImportError:
    import registry_update_r65 as u
b=u.b
ARCHIVE=".janus/essence/registry_lineage_r66_archive.json"
PINS={
    "Hawkar-usls/Janus-Demiurge":"045f47971f20bf5e520fbcd42d5e950011d47a2c236c4594dea217dc8f37ad04",
    "Hawkar-usls/Janus_Genesis":"ffbb38186bccd21781e28c4f86d7c22eba5667a1a496cd5b789a5aca7b610c78"}
def req(x,tag):u.req(x,tag)
def restore(p,a,pin):
    b.checked(a,pin)
    req(a["schema"]=="janus.registry.r66.archived_lineage.v1" and a["repository"]==p["repository"] and a["base_pin"]==p["receipt_sha256"],"ARCHIVE_SCOPE")
    mode="CONTROLLED_FIXTURE"
    live=u.initial(p,"LIVE_OBSERVATION")
    req(live["receipt_sha256"]==a["live_g0_pin"],"LIVE_G0")
    prev=u.initial(p,mode)
    req(prev["receipt_sha256"]==a["fixture_g0_pin"],"FIXTURE_G0")
    chain=[prev]
    req(len(a["generations"])==2,"GENERATION_COUNT")
    for n in a["generations"]:
        k=next(k for k in u.IDENTITY if u.key(k)==n["dependency"])
        req(n["generation"]==len(chain),"GENERATION")
        fields=u.rows(p,k);seen=set()
        for row in fields:
            row["source_blob"]=n["blob"]
            patch=n["patches"].get(row["pointer"],{})
            req(set(patch)<={"json_preview","value_sha256","truncated"},"PATCH_SCOPE")
            row.update(patch)
            if patch:seen.add(row["pointer"])
        req(seen==set(n["patches"]),"PATCH_POINTER")
        nxt=copy.deepcopy(prev);nxt.pop("receipt_sha256")
        nxt.update(generation=n["generation"],previous_pin=prev["receipt_sha256"])
        nxt["dependencies"][n["dependency"]]=n["blob"]
        nxt["overlays"][n["dependency"]]={"blob":n["blob"],"fields":fields}
        nxt=b.seal(nxt)
        u.accept(p,prev,prev["receipt_sha256"],nxt,n["pin"],mode)
        chain.append(nxt);prev=nxt
    return live,chain
def load(repo,root="."):
    p=u.seed(repo,root);a=b.read((Path(root)/ARCHIVE).read_bytes())
    live,chain=restore(p,a,PINS[repo])
    return p,a,live,chain
def index(p,a,live,chain,view=2):
    req(type(view) is int and 0<=view<len(chain),"VIEW")
    return b.seal({"schema":"janus.registry.r66.recovery_index.v1","repository":p["repository"],"archive_pin":a["receipt_sha256"],"live_pin":live["receipt_sha256"],"live_generation":0,"fixture_head":chain[-1]["receipt_sha256"],"fixture_high_water":chain[-1]["generation"],"fixture_view":view,"fixture_view_pin":chain[view]["receipt_sha256"],"status":"HISTORICAL_VIEW_ONLY","fixture_activation":False,"action_authority":False,"model_promotion":False})
def verify_index(x,p,a,live,chain,expected):
    b.checked(x,expected)
    req(x==index(p,a,live,chain,x["fixture_view"]),"INDEX_MISMATCH")
    return x
def recover(p,a,live,chain,prior,prior_pin,target):
    verify_index(prior,p,a,live,chain,prior_pin)
    # Recovery never lowers high-water or changes the reviewed live pin.
    req(type(target) is int and 0<=target<prior["fixture_high_water"],"RECOVERY_TARGET")
    nxt=index(p,a,live,chain,target)
    context=u.materialize_context(p,chain[target])
    return nxt,context
def cli_report(x,context):
    return {"repository":x["repository"],"live_generation":x["live_generation"],"live_pin":x["live_pin"],"fixture_high_water":x["fixture_high_water"],"fixture_view":x["fixture_view"],"fixture_view_pin":x["fixture_view_pin"],"context_fields":sum(map(len,context.values())),"registry_document_reads":0,"fixture_activation":False,"action_authority":False}
class Tests(unittest.TestCase):
    def setUp(self):
        self.p,self.a,self.live,self.chain=load(os.environ["GITHUB_REPOSITORY"])
        self.x=index(self.p,self.a,self.live,self.chain)
    def test_all_exact(self):
        self.assertEqual([v["receipt_sha256"] for v in self.chain],[self.a["fixture_g0_pin"]]+[v["pin"] for v in self.a["generations"]])
    def test_live_separation(self):
        self.assertEqual(self.live["mode"],"LIVE_OBSERVATION")
        with self.assertRaises(ValueError):u.validate(self.chain[1],self.p,self.chain[1]["receipt_sha256"],"LIVE_OBSERVATION")
    def test_rollback(self):
        n,c=recover(self.p,self.a,self.live,self.chain,self.x,self.x["receipt_sha256"],1)
        self.assertEqual(n["fixture_view_pin"],self.chain[1]["receipt_sha256"])
        self.assertEqual(n["fixture_high_water"],2)
        self.assertEqual(n["live_pin"],self.x["live_pin"])
        self.assertTrue(any("R65 CONTROLLED FIXTURE 1" in r["json_preview"] for v in c.values() for r in v))
    def test_replay(self):
        with self.assertRaises(ValueError):u.accept(self.p,self.chain[2],self.chain[2]["receipt_sha256"],self.chain[1],self.chain[1]["receipt_sha256"],"CONTROLLED_FIXTURE")
    def test_bad_archive(self):
        a=copy.deepcopy(self.a);a["generations"][0]["blob"]="0"*40
        with self.assertRaises(ValueError):restore(self.p,a,PINS[self.p["repository"]])
    def test_resealed_archive(self):
        a=copy.deepcopy(self.a);a.pop("receipt_sha256");a["run"]=0
        with self.assertRaises(ValueError):restore(self.p,b.seal(a),PINS[self.p["repository"]])
    def test_corrupt_index(self):
        x={**self.x,"fixture_view":1}
        with self.assertRaises(ValueError):verify_index(x,self.p,self.a,self.live,self.chain,self.x["receipt_sha256"])
    def test_resealed_index(self):
        x=index(self.p,self.a,self.live,self.chain,1)
        with self.assertRaises(ValueError):verify_index(x,self.p,self.a,self.live,self.chain,self.x["receipt_sha256"])
    def test_recover_from_corrupt_cache(self):
        with tempfile.TemporaryDirectory() as d:
            f=Path(d)/"cache.json";f.write_text('{"corrupt":true}')
            # The cache is disposable. Rebuild from fixed Git archive and expected pin.
            p,a,l,c=load(self.p["repository"])
            n,ctx=recover(p,a,l,c,self.x,self.x["receipt_sha256"],1)
            self.assertEqual(n["fixture_view_pin"],c[1]["receipt_sha256"])
    def test_invalid_target(self):
        with self.assertRaises(ValueError):recover(self.p,self.a,self.live,self.chain,self.x,self.x["receipt_sha256"],3)
def main():
    ap=argparse.ArgumentParser();ap.add_argument("mode",choices=("test","snapshot","recover","verify-recovery"));ap.add_argument("--out");ap.add_argument("--prior");ap.add_argument("--pin");a=ap.parse_args()
    if a.mode=="test":return 0 if unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(Tests)).wasSuccessful() else 1
    p,arc,live,chain=load(os.environ["GITHUB_REPOSITORY"])
    if a.mode=="snapshot":
        x=index(p,arc,live,chain)
        u.write(a.out,x)
        print("R66_SNAPSHOT "+json.dumps(cli_report(x,u.materialize_context(p,chain[2])),sort_keys=True))
    elif a.mode=="recover":
        prev=u.load(a.prior);x,c=recover(p,arc,live,chain,prev,a.pin,1)
        u.write(a.out,x)
        print("R66_RECOVERY "+json.dumps(cli_report(x,c),sort_keys=True))
    else:
        x=u.load(a.prior);verify_index(x,p,arc,live,chain,a.pin)
        req(x["fixture_view"]==1 and x["fixture_high_water"]==2,"RECOVERY_STATE")
        c=u.materialize_context(p,chain[1])
        print("R66_FRESH_RUNNER_REOPEN "+json.dumps(cli_report(x,c),sort_keys=True))
    return 0
if __name__=="__main__":raise SystemExit(main())
