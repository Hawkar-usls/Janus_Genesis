"""R6.7 reviewed engineering evidence lineage. Historical context only.
Scientific source G0 and model/dispatch authority are never changed here.
"""
import argparse, copy, json, os, unittest
from pathlib import Path
try:
    from . import registry_lineage_r66 as l
except ImportError:
    import registry_lineage_r66 as l
u=l.u
b=u.b
A=".janus/essence/registry_homeostasis_r67_evidence.json"
P=".janus/essence/registry_homeostasis_r67_current.json"
SOURCE="data/autonomy_map/JANUS-R67-CONTEXT-HEALTH-EVIDENCE.json"
META="Hawkar-usls/janus-meta-registry"
VERSIONS=(
 ("8d37b6da64c800dd723097323f16f8c23fe734f3","183d4930d1354d0971e3da316a7f93af201710aa"),
 ("1d447ea1e86ecd84c98a22c8597bf0100ac7d1af","33f6eae6c9c9b75429964cdeb9749d136203e9c4"))
PINS={
 "Hawkar-usls/Janus-Demiurge":("79620625ba270fa4a332a688de9c5a48fc740534","34547ad38543f8219abcb719a0d6ceb8307e4c88"),
 "Hawkar-usls/Janus_Genesis":("eb64e97cbe0b667c0261582331793f170a37648a","571093fbea5505ef714771551e4730d981b2f351")}
RUNS={"Hawkar-usls/Janus-Demiurge":(45392616619,45400644902),"Hawkar-usls/Janus_Genesis":(45392621220,45400655470)}
def req(x,tag):u.req(x,tag)
def rawread(path,sha):
    raw=Path(path).read_bytes()
    req(len(raw)<=65536 and u.blob(raw)==sha,"GIT_BLOB")
    return raw
def record(raw,repo,p,live,chain,i):
    d=b.read(raw)
    req(d["schema"]=="janus.registry.context_health_evidence.r67.v1" and d["revision"]==i,"SOURCE_SCHEMA")
    req(d["scope"]=="MEASURED_FIRST_PARTY_ENGINEERING_EVIDENCE_NOT_SCIENCE_OR_LIVE_AUTHORITY" and d["historical_snapshot"] is True and d["source_text_is_data"] is True and d["action_authority"] is False,"SOURCE_SCOPE")
    found=[x for x in d["organs"] if x["repository"]==repo]
    req(len(found)==1,"ORGAN")
    r=found[0]
    req(r["project"]==p["project"] and r["base_live_pin"]==live["receipt_sha256"],"BASE")
    r65,r66=RUNS[repo]
    req(r["r65"]=={"run":r65,"producer_consumer_pass":2,"controlled_updates":2,"unchanged_live_document_reads":0,"live_status":"REUSE"},"R65_EVIDENCE")
    expected=None if i==0 else {"run":r66,"jobs_pass":3,"tests_pass":10,"restored_fixture_generation":1,"retained_fixture_high_water":2,"restored_fixture_pin":chain[1]["receipt_sha256"],"live_generation":0,"registry_document_reads":0,"fixture_activation":False}
    req(r["recovery"]==expected,"R66_EVIDENCE")
    return r
def load(repo,root="."):
    root=Path(root);p,_,live,chain=l.load(repo,root)
    archive_pin,pointer_pin=PINS[repo]
    archive=b.read(rawread(root/A,archive_pin))
    pointer=b.read(rawread(root/P,pointer_pin))
    req(archive["schema"]=="janus.registry.context_homeostasis.r67.archive.v1" and (archive["repository"],archive["source_repository"],archive["source_path"])==(repo,META,SOURCE),"ARCHIVE")
    req(len(archive["versions"])==2,"VERSION_COUNT")
    records=[]
    for i,v in enumerate(archive["versions"]):
        commit,blob=VERSIONS[i]
        req((v["generation"],v["commit"],v["blob"])==(i,commit,blob),"SOURCE_PIN")
        raw=v["raw"].encode()
        req(u.blob(raw)==blob,"SOURCE_BYTES")
        records.append(record(raw,repo,p,live,chain,i))
    expected={"schema":"janus.registry.context_homeostasis.r67.pointer.v1","repository":repo,"archive_blob":archive_pin,"active_generation":1,"active_source_blob":VERSIONS[1][1],"previous_source_blob":VERSIONS[0][1],"high_water":1,"scope":"REVIEWED_RESEARCH_ENGINEERING_CONTEXT_ONLY","scientific_release_changed":False,"action_authority":False}
    req(pointer==expected,"POINTER")
    req(records[0]["r65"]==records[1]["r65"] and records[0]["recovery"] is None and records[1]["recovery"] is not None,"CHANGE")
    return p,live,archive,pointer,records
def capsule(p,live,pointer,records,i):
    req(type(i) is int and i in (0,1),"GENERATION")
    return b.seal({"schema":"janus.registry.context_homeostasis.r67.view.v1","repository":p["repository"],"project":p["project"],"scientific_pin":live["receipt_sha256"],"scientific_context":u.materialize_context(p,live),"engineering_evidence":records[i],"source_commit":VERSIONS[i][0],"source_blob":VERSIONS[i][1],"previous_source_blob":None if i==0 else VERSIONS[0][1],"view_generation":i,"current_generation":pointer["active_generation"],"high_water":pointer["high_water"],"status":"HISTORICAL_ENGINEERING_CONTEXT_ONLY","action_authority":False,"live_state_verified":False,"model_promotion":False})
def select(p,live,pointer,records,observed):
    current=capsule(p,live,pointer,records,1)
    if observed!=b.dependencies(p):return "HOLD_SCIENTIFIC_SOURCE_DRIFT",None
    return "REUSE_REVIEWED_CONTEXT",current
def recover(p,live,pointer,records,prior,pin):
    b.checked(prior,pin)
    req(prior==capsule(p,live,pointer,records,1),"CURRENT_VIEW")
    # Recovery returns prior knowledge but never lowers the committed current pointer.
    return capsule(p,live,pointer,records,0)
def consume_current(path,pin,repo,root="."):
    p,live,_,pointer,records=load(repo,root)
    x=u.load(path);b.checked(x,pin)
    req(x==capsule(p,live,pointer,records,1),"CURRENT_REVIEWED_CONTEXT")
    print("R67_PLANNER_CONTEXT "+json.dumps(report(x),sort_keys=True))
    return x
def report(x):
    return {"repository":x["repository"],"view_generation":x["view_generation"],"current_generation":x["current_generation"],"high_water":x["high_water"],"scientific_pin":x["scientific_pin"],"source_blob":x["source_blob"],"recovery_evidence_available":x["engineering_evidence"]["recovery"] is not None,"registry_document_reads_at_consumer":0,"receipt":x["receipt_sha256"],"action_authority":False}
class Tests(unittest.TestCase):
    def setUp(self):self.p,self.live,self.a,self.ptr,self.r=load(os.environ["GITHUB_REPOSITORY"])
    def current(self):return capsule(self.p,self.live,self.ptr,self.r,1)
    def test_real_evidence(self):self.assertIsNotNone(self.current()["engineering_evidence"]["recovery"])
    def test_previous(self):
        x=self.current();y=recover(self.p,self.live,self.ptr,self.r,x,x["receipt_sha256"])
        self.assertIsNone(y["engineering_evidence"]["recovery"])
        self.assertEqual((y["current_generation"],y["high_water"],y["view_generation"]),(1,1,0))
        self.assertEqual(x["scientific_pin"],y["scientific_pin"])
    def test_reuse(self):self.assertEqual(select(self.p,self.live,self.ptr,self.r,b.dependencies(self.p)),("REUSE_REVIEWED_CONTEXT",self.current()))
    def test_drift(self):self.assertEqual(select(self.p,self.live,self.ptr,self.r,{}),("HOLD_SCIENTIFIC_SOURCE_DRIFT",None))
    def test_tamper(self):
        x=self.current();pin=x["receipt_sha256"];x["action_authority"]=True
        with self.assertRaises(ValueError):recover(self.p,self.live,self.ptr,self.r,x,pin)
    def test_replay(self):
        x=capsule(self.p,self.live,self.ptr,self.r,0)
        with self.assertRaises(ValueError):recover(self.p,self.live,self.ptr,self.r,x,x["receipt_sha256"])
    def test_source_bytes(self):
        raw=self.a["versions"][1]["raw"].encode()
        self.assertNotEqual(u.blob(raw+b" "),VERSIONS[1][1])
    def test_no_fixture_activation(self):
        x=self.current();self.assertFalse(x["engineering_evidence"]["recovery"]["fixture_activation"]);self.assertFalse(x["action_authority"])
def main():
    ap=argparse.ArgumentParser();ap.add_argument("mode",choices=("test","produce","wake","recover","reopen"));ap.add_argument("--out");ap.add_argument("--old-source");ap.add_argument("--new-source");ap.add_argument("--prior");ap.add_argument("--pin");a=ap.parse_args()
    if a.mode=="test":return 0 if unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(Tests)).wasSuccessful() else 1
    repo=os.environ["GITHUB_REPOSITORY"];p,live,arc,ptr,rs=load(repo)
    if a.mode=="produce":
        for i,path in enumerate((a.old_source,a.new_source)):
            req(rawread(path,VERSIONS[i][1])==arc["versions"][i]["raw"].encode(),"SOURCE_COPY")
        x=capsule(p,live,ptr,rs,1);u.write(a.out,x);print("R67_REAL_EVIDENCE_UPDATE "+json.dumps(report(x),sort_keys=True))
    elif a.mode=="wake":
        status,x=select(p,live,ptr,rs,b.observe(p))
        print("R67_LIVE_METADATA "+json.dumps({"repository":repo,"status":status,"source_document_reads":0,"scientific_state_changed":False}))
        if x is not None:u.write(a.out,x)
    elif a.mode=="recover":
        x=recover(p,live,ptr,rs,u.load(a.prior),a.pin);u.write(a.out,x);print("R67_RECOVER "+json.dumps(report(x),sort_keys=True))
    else:
        x=u.load(a.prior);b.checked(x,a.pin);req(x==capsule(p,live,ptr,rs,0),"REOPEN")
        print("R67_REOPEN "+json.dumps(report(x),sort_keys=True))
    return 0
if __name__=="__main__":raise SystemExit(main())
