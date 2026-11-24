"""R6.9 read-only ESSENCE memory canary. No new execution or write authority."""
import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

PINS={
 "Hawkar-usls/Janus-Demiurge":("ee02a190e408ca065def1af65c6faba0d3b93122","5fdbcdc238ce6148017dcbe5b47bb3927381af3154b9fe53e3dc0778c76c4999","9fed5a9934544a77970d00dc5b752f04f77c61e8e78159820694ca018ea707c0",45406071270,138487219284),
 "Hawkar-usls/Janus_Genesis":("a4219ffb018849bb212e84b42263125be4973b9c","9ba22a80f045dcafab59371769ef3cb584a53a2c5f0bcb88bf8e5137d30bb3bf","458901bf74f4eab11a3ae02d37cc420e7974e90d2fc84ee6264155ebaf8cd8ba",45406098923,138487127938)}
META_COMMIT="ecf61e5aec2bc7ffb370c28b5a2f8cd7a277dd2c"
META_BLOB="aee43f5804d5c15a76c333fc9e020d7d619b28b8"
META_PATH="data/autonomy_map/JANUS-R69-LIVING-MEMORY-EVIDENCE.json"
def req(ok,msg):
    if not ok:raise ValueError(msg)
def head(root):
    return subprocess.check_output(["git","-C",str(root),"rev-parse","HEAD"],text=True,timeout=5).strip()
def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--verified",required=True,type=Path)
    ap.add_argument("--evidence",required=True,type=Path)
    args=ap.parse_args()
    repo=os.environ["GITHUB_REPOSITORY"]
    commit,pin,prev,run,job=PINS[repo]
    req(head(args.verified)==commit and head(args.evidence)==META_COMMIT,"SOURCE_COMMIT")
    sys.path.insert(0,str((args.verified/"tools").resolve()))
    import registry_continuity_r68 as c
    b=c.b;u=c.u
    p,prior,current,ptr=c.load(repo,args.verified)
    req(ptr==c.expected(repo,prior,current,2),"CURRENT_POINTER")
    req(current["receipt_sha256"]==pin and prior["receipt_sha256"]==prev,"RECEIPT")
    c.check_transition(c.expected(repo,prior,current,1),ptr,repo,prior,current)
    b.checked(current,pin)
    # A fresh runner can rebuild an ephemeral cache solely from the reviewed Git snapshot.
    def cached(path):
        try:
            x=b.read(path.read_bytes(),131072);b.checked(x,pin)
            req(x==current,"CACHE_CONTEXT")
            return x,"REUSED"
        except (OSError,ValueError,KeyError,TypeError):
            x=c.wake(repo,args.verified)
            b.checked(x,pin)
            tmp=path.with_suffix(".tmp");tmp.write_bytes(b.canonical(x));os.replace(tmp,path)
            return x,"RESTORED"
    with tempfile.TemporaryDirectory() as d:
        cache=Path(d)/"cache.json"
        first,s1=cached(cache);second,s2=cached(cache)
        cache.write_bytes(b'{"corrupt":true}')
        third,s3=cached(cache)
        req((s1,s2,s3)==("RESTORED","REUSED","RESTORED") and first==second==third==current,"CACHE_RECOVERY")
        cache.write_bytes(b.canonical(prior))
        fourth,s4=cached(cache)
        req(s4=="RESTORED" and fourth==current,"STALE_CACHE")
    # Check only the known scientific dependency metadata; never replace reviewed data silently.
    observed=b.observe(p)
    status=b.classify(p,observed)
    raw=(args.evidence/META_PATH).read_bytes()
    req(len(raw)<=65536 and u.blob(raw)==META_BLOB,"EVIDENCE_BLOB")
    ev=b.read(raw)
    req(ev["schema"]=="janus.registry.r69.reviewed_evidence.v1" and ev["scope"]=="FIRST_PARTY_HISTORICAL_ENGINEERING_ONLY" and ev["action_authority"] is False and ev["science_changed"] is False and ev["production_deployed"] is False,"EVIDENCE_SCOPE")
    rows=[r for r in ev["organs"] if r["repository"]==repo]
    req(rows==[{"repository":repo,"run":run,"job":job,"source_commit":commit,"generation":2,"receipt":pin,"previous":prev}],"EVIDENCE_ROW")
    req(ev["result"]=={"transition_pass":2,"planner_reopen_pass":2,"registry_document_reads":0,"production_jobs_skipped":True},"EVIDENCE_RESULT")
    candidate=b.seal({"schema":"janus.registry.r69.candidate.v1","repository":repo,"generation":3,"previous_receipt":pin,"evidence_commit":META_COMMIT,"evidence_blob":META_BLOB,"engineering_evidence":rows[0],"status":"REVIEW_REQUIRED","action_authority":False,"model_promotion":False})
    result={"repository":repo,"event":os.environ.get("GITHUB_EVENT_NAME","unknown"),"run":os.environ.get("GITHUB_RUN_ID","unknown"),"generation":2,"active_receipt":pin,"previous_receipt":prev,"candidate_generation":3,"candidate_receipt":candidate["receipt_sha256"],"candidate_activated":False,"cache_recovery":"PASS","stale_cache_rejected":True,"scientific_metadata":status,"registry_scientific_document_reads":0,"engineering_evidence_reads":1,"production_model_changed":False,"action_authority":False}
    print("R69_CANARY "+json.dumps(result,sort_keys=True))
    print("R69_CANDIDATE "+json.dumps(candidate,sort_keys=True))
    summary=os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary,"a",encoding="utf-8") as f:f.write("### R6.9 read-only memory canary\n\n"+json.dumps(result,sort_keys=True)+"\n")
    return 0
if __name__=="__main__":raise SystemExit(main())
