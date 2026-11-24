"""R6.5 selective, source-bound context releases. Advisory data only.
Known JSON schemas only; changed routing index/Markdown require review.
No writes to Git, no model calls, no automatic authority or promotion.
"""
import argparse, base64, copy, hashlib, json, os, re, unittest, urllib.request
from pathlib import Path
try:
    from . import registry_boot_r64 as b
except ImportError:
    import registry_boot_r64 as b
SCHEMA="janus.registry.selective_release.r65.v1"
MAX_DOC=2*1024*1024
MAX_RELEASE=65536
INDEX=(b.META,"data/JANUS-CHAT-CONTEXT-INDEX.json")
CS=(b.META,"data/JANUS-COSMOS-SETI-CURRENT-STATE.json")
CJ=(b.META,"data/JANUS-COSMOS-SETI-DEVELOPMENT-JOURNAL.json")
TS=(b.FUND,"registry/TRUMP_CURRENT_STATE.json")
IDENTITY={CS:("schema","janus.context_bridge.current_state.v1"),CJ:("schema","janus.cosmos.seti.development_journal.v1"),TS:("artifact_id","JANUS-TRUMP-CURRENT-STATE-CONTINUITY-2026-09-14-v1.0")}
TYPES={"string":str,"object":dict,"array":list,"integer":int,"boolean":bool}
FLAGS={k:False for k in b.FLAGS}
def req(x,tag):b.require(x,tag)
def blob(raw):return hashlib.sha1(b"blob "+str(len(raw)).encode()+b"\0"+raw).hexdigest()
def key(k):return k[0]+":"+k[1]
def observed_map(m):return {key(k):v for k,v in sorted(m.items())}
def pointer(o,p):
    req(p.startswith("/"),"POINTER")
    for k in p[1:].split("/"):
        req(type(o) is dict and k in o,"FIELD_MISSING")
        o=o[k]
    return o
def rows(p,k):
    s=[x for x in p["sources"] if (x["repo"],x["path"])==k]
    req(len(s)==1,"SOURCE_SCOPE")
    return sorted([dict(x,group=g) for g,items in p["context"].items() for x in items if x["source_blob"]==s[0]["blob"]],key=lambda x:x["pointer"])
def seed(repo,root="."):
    return b.packet(b.read((Path(root)/b.SEED).read_bytes()),repo)
def initial(p,mode):
    req(mode in ("CONTROLLED_FIXTURE","LIVE_OBSERVATION"),"MODE")
    return b.seal({"schema":SCHEMA,"repository":p["repository"],"project":p["project"],"base_pin":p["receipt_sha256"],"mode":mode,"generation":0,"previous_pin":None,"dependencies":observed_map(b.dependencies(p)),"overlays":{},"source_text_is_data":True,**FLAGS})
def validate(x,p,pin,mode):
    b.checked(x,pin)
    req(x["schema"]==SCHEMA and (x["repository"],x["project"],x["base_pin"],x["mode"])==(p["repository"],p["project"],p["receipt_sha256"],mode),"SCOPE")
    req(set(x)=={"schema","repository","project","base_pin","mode","generation","previous_pin","dependencies","overlays","source_text_is_data","receipt_sha256",*FLAGS},"EXTRA_FIELD")
    req(all(x.get(k) is False for k in FLAGS) and x["source_text_is_data"] is True,"AUTHORITY")
    req(type(x["generation"]) is int and 0<=x["generation"]<=100 and len(b.canonical(x))<=MAX_RELEASE,"BUDGET")
    req((x["generation"]==0 and x["previous_pin"] is None) or (x["generation"]>0 and type(x["previous_pin"]) is str and re.fullmatch("[0-9a-f]{64}",x["previous_pin"])),"ANCESTRY")
    base=observed_map(b.dependencies(p));d=x["dependencies"];ov=x["overlays"]
    req(type(d) is dict and set(d)==set(base) and all(type(v) is str and re.fullmatch("[0-9a-f]{40}",v) for v in d.values()),"DEPS")
    allowed={key(k):k for k in IDENTITY if key(k) in base}
    req(type(ov) is dict and set(ov)=={k for k in d if d[k]!=base[k]} and set(ov)<=set(allowed),"OVERLAY_SCOPE")
    for name,v in ov.items():
        req(set(v)=={"blob","fields"} and v["blob"]==d[name],"OVERLAY_BLOB")
        originals=rows(p,allowed[name]);new=v["fields"]
        req(type(new) is list and len(new)==len(originals),"ROW_COUNT")
        for o,n in zip(originals,new):
            req(set(n)==set(o) and all(n[k]==o[k] for k in ("pointer","role","type","group")) and n["source_blob"]==v["blob"],"ROW_SCOPE")
            req(type(n["json_preview"]) is str and len(n["json_preview"])<=600 and type(n["truncated"]) is bool and re.fullmatch("[0-9a-f]{64}",n["value_sha256"]),"PREVIEW")
            if not n["truncated"]:
                val=json.loads(n["json_preview"],object_pairs_hook=b.unique,parse_constant=lambda _: (_ for _ in ()).throw(ValueError("NONFINITE")))
                req(type(val) is TYPES[n["type"]] and b.digest(val)==n["value_sha256"],"FIELD_HASH")
    return x
def overlay(p,k,sha,raw):
    req(len(raw)<=MAX_DOC and blob(raw)==sha,"BLOB_MISMATCH")
    o=b.read(raw,MAX_DOC);idk,idv=IDENTITY[k];req(o.get(idk)==idv,"SCHEMA_DRIFT")
    if k==TS:
        req(o.get("repository_authority")==b.FUND and o.get("journal")=="docs/TRUMP_DEVELOPMENT_JOURNAL.md","CONTINUITY_DRIFT")
    if k==CJ:
        req(type(o.get("events")) is list and 0<len(o["events"])<=5000 and all(type(e) is dict for e in o["events"]),"EVENTS")
    if k==CS: req(type(o.get("open_gates")) is list and len(o["open_gates"])<=200,"GATES")
    out=[]
    for r in rows(p,k):
        v=pointer(o,r["pointer"]);req(type(v) is TYPES[r["type"]],"TYPE_DRIFT")
        preview=b.canonical(v).decode()
        out.append({**r,"source_blob":sha,"value_sha256":b.digest(v),"json_preview":preview[:600],"truncated":len(preview)>600})
    req(out,"NO_REVIEWED_FIELDS")
    return {"blob":sha,"fields":out}
def advance(p,old,pin,observed,read_blob,mode):
    validate(old,p,pin,mode)
    target=observed_map({k:observed.get(k) for k in b.dependencies(p)})
    if any(v is None or not re.fullmatch("[0-9a-f]{40}",v) for v in target.values()):
        return "HOLD_SOURCE_UNAVAILABLE",old,0
    changes=[k for k in b.dependencies(p) if target[key(k)]!=old["dependencies"][key(k)]]
    if not changes:return "REUSE",old,0
    # No rollback to old source blobs without an explicit review.
    base=observed_map(b.dependencies(p))
    if any(k not in IDENTITY for k in changes):return "HOLD_ROUTE_OR_JOURNAL_REVIEW",old,0
    if any(target[key(k)]==base[key(k)] for k in changes):return "HOLD_RETURN_TO_BASE_REVIEW",old,0
    nxt=copy.deepcopy(old);nxt.pop("receipt_sha256")
    nread=0
    try:
        for k in changes:
            sha=target[key(k)];raw=read_blob(k,sha);nread+=1
            nxt["overlays"][key(k)]=overlay(p,k,sha,raw)
        nxt.update(generation=old["generation"]+1,previous_pin=pin,dependencies=target)
        nxt=b.seal(nxt);validate(nxt,p,nxt["receipt_sha256"],mode)
    except (ValueError,KeyError,TypeError,UnicodeError,OSError,RecursionError):
        return "HOLD_INVALID_SOURCE_OR_SCHEMA",old,nread
    return "CANDIDATE_READY",nxt,nread
def accept(p,old,oldpin,new,newpin,mode):
    validate(old,p,oldpin,mode);validate(new,p,newpin,mode)
    req(new["generation"]==old["generation"]+1 and new["previous_pin"]==oldpin,"REPLAY_OR_PARENT")
    req(new["dependencies"]!=old["dependencies"],"NO_CHANGE")
    changed=[k for k in old["dependencies"] if old["dependencies"][k]!=new["dependencies"][k]]
    req(all(k in {key(x) for x in IDENTITY} for k in changed),"ROUTE_DRIFT")
    base=observed_map(b.dependencies(p))
    req(all(new["dependencies"][k]!=base[k] for k in changed),"RETURN_TO_BASE_REVIEW")
    for k in set(old["overlays"])-set(changed):
        req(new["overlays"].get(k)==old["overlays"][k],"UNCHANGED_OVERLAY")
    # A producer pin authenticates only this trusted CI handoff, not scientific truth.
    return new
def materialize_context(p,release):
    context=copy.deepcopy(p["context"])
    for k,v in release["overlays"].items():
        oldrows=rows(p,next(x for x in IDENTITY if key(x)==k))
        oldblob=oldrows[0]["source_blob"]
        for g in context:context[g]=[r for r in context[g] if r["source_blob"]!=oldblob]
        for r in v["fields"]:
            context[r["group"]].append({k:v for k,v in r.items() if k!="group"})
    return context
def load_reviewed_context(repo,root,previous_path,previous_pin,release_path,release_pin):
    # Explicit pins must come from a reviewed release/CI handoff, not candidate JSON.
    p=seed(repo,root);old=load(previous_path);new=load(release_path)
    accept(p,old,previous_pin,new,release_pin,"LIVE_OBSERVATION")
    context=materialize_context(p,new)
    print("R65_REVIEWED_PLANNER_CONTEXT "+json.dumps({"repository":repo,"generation":new["generation"],"pin":release_pin,"fields":sum(map(len,context.values())),"action_authority":False,"cortex_citations":"BASE_HISTORICAL_ONLY"},sort_keys=True))
    return context
def fetch(k,sha):
    req(k in IDENTITY and re.fullmatch("[0-9a-f]{40}",sha),"FETCH_SCOPE")
    reqobj=urllib.request.Request("https://api.github.com/repos/"+k[0]+"/git/blobs/"+sha,headers={"Accept":"application/vnd.github+json","User-Agent":"JANUS-R65"})
    if os.environ.get("GH_TOKEN"):reqobj.add_header("Authorization","Bearer "+os.environ["GH_TOKEN"])
    with urllib.request.build_opener(b.NoRedirect()).open(reqobj,timeout=15) as r:o=b.read(r.read(4*MAX_DOC+1),4*MAX_DOC)
    req(o.get("sha")==sha and o.get("encoding")=="base64" and type(o.get("size")) is int and o["size"]<=MAX_DOC,"REMOTE_BLOB")
    raw=base64.b64decode("".join(o["content"].split()),validate=True)
    req(len(raw)==o["size"] and blob(raw)==sha,"REMOTE_HASH")
    return raw
def write(path,obj):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    with path.open("xb") as f:f.write(b.canonical(obj))
def load(path):return b.read(Path(path).read_bytes(),MAX_RELEASE)
def fixture(p,raw,out):
    k=CS if p["project"]=="COSMOS" else TS
    dep=b.dependencies(p);req(blob(raw)==dep[k],"FIXTURE_ORIGINAL")
    obj=b.read(raw,MAX_DOC);mode="CONTROLLED_FIXTURE";old=initial(p,mode)
    write(out/"g0.json",old)
    expected=old
    for i in (1,2):
        x=copy.deepcopy(obj)
        if k==CS:x["next_allowed"]="R65 CONTROLLED FIXTURE "+str(i)+" — no execution authority"
        else:x["current_frontier"]["correct_question"]="R65 CONTROLLED FIXTURE "+str(i)+" — no execution authority"
        changed=b.canonical(x);obs={**dep,k:blob(changed)}
        status,new,n=advance(p,expected,expected["receipt_sha256"],obs,lambda a,s:changed,mode)
        req(status=="CANDIDATE_READY" and n==1,"FIXTURE_UPDATE")
        accept(p,expected,expected["receipt_sha256"],new,new["receipt_sha256"],mode)
        write(out/("g"+str(i)+".json"),new)
        status,same,n=advance(p,new,new["receipt_sha256"],obs,lambda *_: (_ for _ in ()).throw(AssertionError("UNEXPECTED_READ")),mode)
        req(status=="REUSE" and n==0 and same==new,"FIXTURE_REUSE")
        expected=new
    pins={str(i):load(out/("g"+str(i)+".json"))["receipt_sha256"] for i in range(3)}
    print("R65_FIXTURE "+json.dumps({"repository":p["repository"],"generations":2,"changed_document_reads":2,"unchanged_document_reads":0,"pins":pins,"fixture_only":True}))
    return pins
def consume_chain(p,folder,pins):
    req(set(pins)=={"0","1","2"},"PINS")
    mode="CONTROLLED_FIXTURE";prev=load(folder/"g0.json")
    req(prev==initial(p,mode) and prev["receipt_sha256"]==pins["0"],"BASE")
    for i in (1,2):
        new=load(folder/("g"+str(i)+".json"))
        accept(p,prev,pins[str(i-1)],new,pins[str(i)],mode)
        prev=new
    context=materialize_context(p,prev)
    target="recorded_next" if p["project"]=="COSMOS" else "goals"
    req(any("R65 CONTROLLED FIXTURE 2" in r["json_preview"] for r in context[target]),"CONTEXT_REPLACEMENT")
    print("R65_ESSENCE_CONSUMER "+json.dumps({"repository":p["repository"],"generation":2,"accepted_pin":pins["2"],"rollback_pin":pins["1"],"context_fields":sum(map(len,context.values())),"registry_document_reads":0,"fixture_only":True,"action_authority":False}))
    return context
class Tests(unittest.TestCase):
    def setUp(self):
        self.p=seed(os.environ["GITHUB_REPOSITORY"]);self.mode="CONTROLLED_FIXTURE";self.old=initial(self.p,self.mode);self.pin=self.old["receipt_sha256"];self.dep=b.dependencies(self.p)
    def step(self,obs,reader=lambda *_: (_ for _ in ()).throw(AssertionError("UNEXPECTED_READ"))):
        return advance(self.p,self.old,self.pin,obs,reader,self.mode)
    def test_no_change(self):self.assertEqual(self.step(self.dep),("REUSE",self.old,0))
    def test_unrelated(self):self.assertEqual(self.step({**self.dep,("other","x"):"a"*40}),("REUSE",self.old,0))
    def test_missing(self):self.assertEqual(self.step({})[0],"HOLD_SOURCE_UNAVAILABLE")
    def test_index_drift(self):self.assertEqual(self.step({**self.dep,INDEX:"a"*40})[0],"HOLD_ROUTE_OR_JOURNAL_REVIEW")
    def test_corrupt_blob(self):
        k=CS if self.p["project"]=="COSMOS" else TS
        self.assertEqual(self.step({**self.dep,k:"a"*40},lambda *_:b"{}")[0],"HOLD_INVALID_SOURCE_OR_SCHEMA")
    def test_schema_drift(self):
        k=CS if self.p["project"]=="COSMOS" else TS;raw=b'{"schema":"unexpected"}'
        self.assertEqual(self.step({**self.dep,k:blob(raw)},lambda *_:raw)[0],"HOLD_INVALID_SOURCE_OR_SCHEMA")
    def test_forged_authority(self):
        x=b.seal({**{k:v for k,v in self.old.items() if k!="receipt_sha256"},"action_authority":True})
        with self.assertRaises(ValueError):validate(x,self.p,x["receipt_sha256"],self.mode)
    def test_wrong_pin(self):
        with self.assertRaises(ValueError):validate(self.old,self.p,"0"*64,self.mode)
    def test_replay(self):
        with self.assertRaises(ValueError):accept(self.p,self.old,self.pin,self.old,self.pin,self.mode)
    def test_mode(self):
        with self.assertRaises(ValueError):validate(self.old,self.p,self.pin,"LIVE_OBSERVATION")
def main():
    a=argparse.ArgumentParser();a.add_argument("mode",choices=("test","live","fixture","consume"));a.add_argument("--source");a.add_argument("--out");a.add_argument("--pins");a.add_argument("--previous");a.add_argument("--previous-pin");x=a.parse_args()
    if x.mode=="test":return 0 if unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(Tests)).wasSuccessful() else 1
    p=seed(os.environ["GITHUB_REPOSITORY"]);out=Path(x.out)
    if x.mode=="fixture":
        pins=fixture(p,Path(x.source).read_bytes(),out)
        write(out/"pins.json",pins)
    elif x.mode=="consume":consume_chain(p,out,json.loads(x.pins))
    else:
        mode="LIVE_OBSERVATION";req(bool(x.previous)==bool(x.previous_pin),"PREVIOUS")
        old=load(x.previous) if x.previous else initial(p,mode);pin=x.previous_pin if x.previous else old["receipt_sha256"]
        status,new,n=advance(p,old,pin,b.observe(p),fetch,mode)
        write(out,{"status":status,"release":new,"document_reads":n,"publication":"REVIEW_REQUIRED","action_authority":False})
        print("R65_LIVE "+json.dumps({"repository":p["repository"],"status":status,"generation":new["generation"],"document_reads":n,"pin":new["receipt_sha256"],"publication":"REVIEW_REQUIRED"}))
    return 0
if __name__=="__main__":raise SystemExit(main())
