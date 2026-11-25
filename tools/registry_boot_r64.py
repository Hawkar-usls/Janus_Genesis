"""R6.4 ESSENCE read-only historical boot cache, no training or task authority.
The reviewed seed is durable Git data. Only dependency metadata is polled.
Changed sources require a new reviewed R63 capsule; never silently repin.
"""
import argparse, base64, hashlib, json, os, re, tempfile, unittest, urllib.request, zlib
from pathlib import Path

SCHEMA="janus.registry.organ_boot.r63.v1"
SEED=".janus/essence/registry_boot_r64_seed.json"
MAX=65536
FLAGS=("action_authority","automatic_dispatch","production_writeback","model_promotion","live_state_verified","actual_neural_inference")
PINS={
 "Hawkar-usls/Janus-Demiurge":("demiurge","COSMOS","cdc480f0f3c5828cb4b604484ba33b887a6af628778d3a79f51a622656104e18"),
 "Hawkar-usls/Janus_Genesis":("genesis","TRUMP","badb4b57f72efebe805997f3c7307ad8f3ade63da9e2e6856aefc78ee5aafabe")}
META="Hawkar-usls/janus-meta-registry"
FUND="Hawkar-usls/Janus-Fundamentum"
def require(ok,tag):
    if not ok:raise ValueError(tag)
def canonical(x):return json.dumps(x,sort_keys=True,ensure_ascii=False,separators=(",",":"),allow_nan=False).encode()
def digest(x):return hashlib.sha256(canonical(x)).hexdigest()
def unique(pairs):
    d={}
    for k,v in pairs:
        require(k not in d,"DUPLICATE_KEY");d[k]=v
    return d
def read(raw,limit=MAX):
    require(len(raw)<=limit,"SIZE")
    x=json.loads(raw,object_pairs_hook=unique,parse_constant=lambda x: (_ for _ in ()).throw(ValueError("NONFINITE")))
    require(type(x) is dict,"OBJECT")
    return x
def seal(x):return {**x,"receipt_sha256":digest(x)}
def checked(x,pin):
    require(type(pin) is str and re.fullmatch("[0-9a-f]{64}",pin),"PIN")
    require(x.get("receipt_sha256")==pin==digest({k:v for k,v in x.items() if k!="receipt_sha256"}),"RECEIPT")
    return x
def packet(seed,repo,pin=None):
    organ,project,initial_pin=PINS[repo]
    pin=initial_pin if pin is None else pin # explicit reviewed pin, never inferred from seed
    require(seed["schema"]=="janus.essence.registry_boot_seed.r64.v1" and seed["encoding"]=="zlib+base64","SEED")
    require((seed["repository"],seed["organ"],seed["project"],seed["receipt_sha256"])==(repo,organ,project,pin),"SEED_SCOPE")
    d=zlib.decompressobj()
    raw=d.decompress(base64.b64decode(seed["capsule"],validate=True),MAX+1)
    require(d.eof and not d.unused_data and not d.unconsumed_tail and len(raw)<=MAX,"COMPRESSED_BUDGET")
    p=checked(read(raw),pin)
    require(p["schema"]==SCHEMA and (p["repository"],p["organ"],p["project"])==(repo,organ,project),"RECIPIENT")
    require(p["status"]=="BOOT_PACKET_READY__PINNED_HISTORY__LIVE_AUTHORITY_HOLD" and all(p.get(k) is False for k in FLAGS),"AUTHORITY")
    require(p["source_text_is_data"] is True and p["knowledge_gaps"]["fresh_primary_receipts_required"] is True,"HISTORICAL")
    return p
def dependencies(p):
    # The old organ map is a reviewed historical draft, not a live main path.
    # Check the actual project journal for TRUMP too, even though R63 only previewed its state.
    result={}
    for s in p["sources"]:
        k=(s["repo"],s["path"])
        if s["id"]=="organ_map":continue
        require(k not in result and re.fullmatch("[0-9a-f]{40}",s["blob"]),"SOURCE")
        result[k]=s["blob"]
    if p["project"]=="TRUMP":result[(FUND,"docs/TRUMP_DEVELOPMENT_JOURNAL.md")]="f060f1096aaf7b5e67f74846146fbe3837439267"
    allowed={(META,"data/JANUS-CHAT-CONTEXT-INDEX.json")}
    if p["project"]=="COSMOS":allowed|={(META,"data/JANUS-COSMOS-SETI-CURRENT-STATE.json"),(META,"data/JANUS-COSMOS-SETI-DEVELOPMENT-JOURNAL.json")}
    else:allowed|={(FUND,"registry/TRUMP_CURRENT_STATE.json"),(FUND,"docs/TRUMP_DEVELOPMENT_JOURNAL.md")}
    require(set(result)==allowed,"DEPENDENCY_SCOPE")
    return result
def relevance(p):
    # Includes all watched source hashes and the exact curated field content.
    return digest({"recipient":[p["repository"],p["project"]],"dependencies":[[a,b,v] for (a,b),v in sorted(dependencies(p).items())],"fields":p["context"],"next":p["next_check"]})
def classify(p,observed):
    deps=dependencies(p)
    if any(k not in observed or observed[k] is None for k in deps):return "HOLD_SOURCE_CHECK_UNAVAILABLE"
    if any(observed[k]!=v for k,v in deps.items()):return "REFRESH_REQUIRED__REVIEW_NEW_CAPSULE"
    return "REUSE_VERIFIED_HISTORICAL_CAPSULE"
def refresh_decision(old,new,observed):
    require((old["repository"],old["project"])==(new["repository"],new["project"]),"CANDIDATE_RECIPIENT")
    require(classify(new,observed)=="REUSE_VERIFIED_HISTORICAL_CAPSULE","CANDIDATE_STALE")
    return "REUSE_EXISTING" if relevance(old)==relevance(new) else "REPLACE_WITH_REVIEWED_CANDIDATE"
class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs):return None
def observe(p):
    """Read Git trees only, no document contents or external executable code."""
    dep=dependencies(p);out={};roots={};trees={}
    opener=urllib.request.build_opener(NoRedirect())
    def get(path):
        req=urllib.request.Request("https://api.github.com"+path,headers={"Accept":"application/vnd.github+json","User-Agent":"JANUS-R64-read-only"})
        tok=os.environ.get("GH_TOKEN")
        if tok:req.add_header("Authorization","Bearer "+tok)
        with opener.open(req,timeout=8) as r:return read(r.read(4*1024*1024+1),4*1024*1024)
    for repo,path in dep:
        try:
            require(repo in (META,FUND),"REPO")
            if repo not in roots:
                sha=get("/repos/"+repo+"/git/ref/heads/main")["object"]["sha"]
                require(re.fullmatch("[0-9a-f]{40}",sha),"COMMIT")
                roots[repo]=get("/repos/"+repo+"/git/commits/"+sha)["tree"]["sha"]
            tree=roots[repo]
            parts=path.split("/")
            for i,part in enumerate(parts):
                require(re.fullmatch("[0-9a-f]{40}",tree),"TREE")
                key=(repo,tree)
                if key not in trees:
                    x=get("/repos/"+repo+"/git/trees/"+tree);require(not x.get("truncated"),"TRUNCATED");trees[key]=x["tree"]
                matches=[e for e in trees[key] if e["path"]==part]
                require(len(matches)==1,"MISSING")
                e=matches[0];require(e["type"]==("blob" if i==len(parts)-1 else "tree") and e["mode"] in ("100644","100755","040000"),"TYPE")
                tree=e["sha"]
            require(re.fullmatch("[0-9a-f]{40}",tree),"BLOB")
            out[(repo,path)]=tree
        except (OSError,ValueError,KeyError,TypeError):out[(repo,path)]=None
    return out
def wake(p,observed):
    status=classify(p,observed)
    return seal({"schema":"janus.essence.boot_sidecar.r64.v1","repository":p["repository"],"project":p["project"],"status":status,"seed_pin":p["receipt_sha256"],"relevance_sha256":relevance(p),"watched_sources":len(dependencies(p)),"registry_document_reads":0,"capsule":p if status.startswith("REUSE") else None,"action_authority":False,"live_state_verified":False,"model_promotion":False})
def consume_boot(path,repo,root="."):
    # Called by real plan entrypoint; sidecar cannot alter its decision or model.
    s=read(Path(path).read_bytes(),2*MAX);checked(s,s["receipt_sha256"])
    p=packet(read((Path(root)/SEED).read_bytes()),repo)
    require(s["schema"]=="janus.essence.boot_sidecar.r64.v1" and s["repository"]==repo and s["project"]==p["project"] and s["seed_pin"]==p["receipt_sha256"] and s["relevance_sha256"]==relevance(p),"SIDECAR_SCOPE")
    require(all(s.get(k) is False for k in ("action_authority","live_state_verified","model_promotion")),"SIDECAR_AUTHORITY")
    if s["status"]=="REUSE_VERIFIED_HISTORICAL_CAPSULE":require(s["capsule"]==p,"SIDECAR_CAPSULE")
    else:require(s["status"] in ("HOLD_SOURCE_CHECK_UNAVAILABLE","REFRESH_REQUIRED__REVIEW_NEW_CAPSULE") and s["capsule"] is None,"SIDECAR_HOLD")
    # Only reviewed historical context is exposed, no instructions are executed.
    print("R64_PLANNER_BOOT "+json.dumps({"repository":repo,"status":s["status"],"project":p["project"],"goal_fields":len(p["context"]["goals"]) if s["capsule"] else 0,"next_check":p["next_check"] if s["capsule"] else None,"seed_pin":p["receipt_sha256"],"registry_document_reads":0,"planning_authority_changed":False},sort_keys=True))
    return s
class Tests(unittest.TestCase):
    def setUp(self):
        self.repo=os.environ["GITHUB_REPOSITORY"];self.p=packet(read(Path(SEED).read_bytes()),self.repo);self.d=dependencies(self.p)
    def test_seed(self):self.assertEqual(self.p["receipt_sha256"],PINS[self.repo][2])
    def test_reuse(self):self.assertEqual(classify(self.p,self.d),"REUSE_VERIFIED_HISTORICAL_CAPSULE")
    def test_unrelated(self):self.assertEqual(classify(self.p,{**self.d,("other","irrelevant"):"f"*40}),classify(self.p,self.d))
    def test_changed(self):
        d={**self.d,next(iter(self.d)):"f"*40};self.assertIsNone(wake(self.p,d)["capsule"])
    def test_missing(self):self.assertEqual(classify(self.p,{}),"HOLD_SOURCE_CHECK_UNAVAILABLE")
    def test_same_candidate(self):self.assertEqual(refresh_decision(self.p,self.p,self.d),"REUSE_EXISTING")
    def test_candidate_stale(self):
        with self.assertRaises(ValueError):refresh_decision(self.p,self.p,{})
    def test_tamper(self):
        x={**self.p,"action_authority":True}
        with self.assertRaises(ValueError):checked(x,self.p["receipt_sha256"])
    def test_wrong_pin(self):
        with self.assertRaises(ValueError):packet(read(Path(SEED).read_bytes()),self.repo,"0"*64)
    def test_sidecar(self):
        with tempfile.TemporaryDirectory() as d:
            f=Path(d)/"b.json";f.write_bytes(canonical(wake(self.p,self.d)));self.assertEqual(consume_boot(f,self.repo)["capsule"],self.p)
    def test_wrong_recipient(self):
        other=next(k for k in PINS if k!=self.repo)
        with self.assertRaises(ValueError):packet(read(Path(SEED).read_bytes()),other)
def main():
    a=argparse.ArgumentParser();a.add_argument("mode",choices=("test","wake","replay"));a.add_argument("--root",default=".");a.add_argument("--out");x=a.parse_args()
    if x.mode=="test":return 0 if unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(Tests)).wasSuccessful() else 1
    repo=os.environ["GITHUB_REPOSITORY"];p=packet(read((Path(x.root)/SEED).read_bytes()),repo)
    result=wake(p,observe(p) if x.mode=="wake" else dependencies(p))
    out=Path(x.out);out.parent.mkdir(parents=True,exist_ok=True)
    with out.open("x") as f:json.dump(result,f,ensure_ascii=False,sort_keys=True,allow_nan=False)
    print("R64_WAKE "+json.dumps({k:result[k] for k in ("repository","project","status","seed_pin","relevance_sha256","watched_sources","registry_document_reads")},sort_keys=True))
    return 0
if __name__=="__main__":raise SystemExit(main())
