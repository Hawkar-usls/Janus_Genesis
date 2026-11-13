#!/usr/bin/env python3
"""ESSENCE v1.3: bounded, source-pinned module governance and research evolution.

Reconstructs *operators*, not legacy Python code. No dynamic import, exec, eval,
shell, network, database access, model training or production modification.
Historical Rex/Ouroboros/Auditor/Conductor become a data-only blueprint
pipeline; Physarum/Memory/Slime/Trinity become deterministic pure functions.
Only research offspring candidates can be born; no live module activation.
"""
from __future__ import annotations

import argparse
import hashlib
import heapq
import json
import math
from pathlib import Path
import re
import time
import tracemalloc

SCHEMA="janus.essence.module_governor/1.3"
MANIFEST="janus.essence.module_governor_manifest/1.3"
CASES="janus.essence.organogenesis_frozen_cases/1.3"
CATALOG="janus.essence.module_lineage_frozen/1.3"
CORPUS_GIT_BLOB="5b40e57e65eb53506378f329d76dbc627f8964bd"
CATALOG_GIT_BLOB="d9aeaf9e28f3d3e522b2153efc506756ac90100d"
MAX_JSON=100_000
NAME=re.compile(r"^[A-Za-z][A-Za-z0-9_-]{0,47}$")
OPERATORS=("physarum_route","slime_trace","graph_dedupe","trinity_veto",
           "dream_router","nas_snapshot")
NO_ACTION=("network","shell","repo_write","workflow_dispatch",
           "secrets","hardware")
DANGEROUS=("exec(", "exec ", "eval(", "subprocess", "__import__", "os.system",
           "popen(", "rm -rf", "delete database", "drop table")
BLUEPRINT_TYPES={"NEW_MODULE_BLUEPRINT","NEW_MODULE_IDEA",
                 "CODE_GENERATION","EVOLVED_BUFF","SYSTEM_BUFF"}
MEMORY_TYPES={"dream"}
EXPERIENCE_TYPES={"game_event"}
# Historic generated family is presumed defective until separately reviewed.
DENY_LEGACY_MODULES={"alien_rex_medic","mod_conductor","mod_rex",
                     "mod_auditor","ai_engine","janus_core",
                     "janus_bot_hub","mod_telegram_unified"}


def canonical(obj):
    return json.dumps(obj,sort_keys=True,ensure_ascii=False,
                      separators=(",",":"),allow_nan=False).encode()


def seal(obj):
    return hashlib.sha256(canonical(obj)).hexdigest()


def git_blob(raw):
    return hashlib.sha1(b"blob "+str(len(raw)).encode()+b"\0"+raw).hexdigest()


def load_json(path,max_bytes=MAX_JSON):
    file=Path(path)
    if file.is_symlink() or not file.is_file() or not 2<=file.stat().st_size<=max_bytes:
        raise ValueError("UNSAFE_OR_TOO_LARGE_INPUT")
    return json.loads(file.read_text(encoding="utf-8"),
                      parse_constant=lambda _: (_ for _ in ()).throw(ValueError("NONFINITE_JSON")))


def load_frozen(path,blob,expected_schema):
    source=Path(path)
    if source.is_symlink() or not source.is_file() or not 2<=source.stat().st_size<=MAX_JSON:
        raise ValueError("UNSAFE_FROZEN_SOURCE")
    raw=source.read_bytes()
    if git_blob(raw)!=blob:
        raise ValueError("FROZEN_GIT_BLOB_MISMATCH")
    obj=load_json(path)
    if not isinstance(obj,dict) or obj.get("schema")!=expected_schema:
        raise ValueError("FROZEN_SCHEMA_MISMATCH")
    return obj


def check_manifest(manifest,root):
    if not isinstance(manifest,dict) or manifest.get("schema")!=MANIFEST:
        raise ValueError("BAD_MODULE_GOVERNOR_MANIFEST")
    if (manifest.get("enabled") is not False or manifest.get("runtime_authority") is not False
            or manifest.get("automatic_model_promotion") is not False
            or manifest.get("live_nas_access") is not False
            or manifest.get("historical_sources_executed") is not False
            or manifest.get("modules")!=list(OPERATORS)):
        raise ValueError("UNAUTHORIZED_MODULE_ACTIVATION")
    if not isinstance(root,dict) or root.get("schema")!="janus.essence.microkernel/0.1":
        raise ValueError("MISSING_PARENT_ESSENCE")
    if (root.get("repository")!=manifest.get("repository")
            or root.get("enabled") is not False
            or root.get("birth_policy")!="PROPOSAL_ONLY"
            or root.get("activation")!="EXPLICIT_READONLY_TEST_ONLY"
            or not isinstance(root.get("capabilities"),dict)
            or set(root["capabilities"])!=set(NO_ACTION)
            or any(root["capabilities"].values())):
        raise ValueError("PARENT_ESSENCE_PROTECTION_VIOLATION")
    cells=root.get("microkernels")
    if (not isinstance(cells,list) or not 6<=len(cells)<=16
            or not {"sensing","memory","planning","verification","recovery","coding"}.issubset(
                {c.get("role") for c in cells if isinstance(c,dict)})):
        raise ValueError("PARENT_ESSENCE_MISSING_ROLES")
    if (manifest.get("frozen_case_blob")!=CORPUS_GIT_BLOB
            or manifest.get("historic_catalog_blob")!=CATALOG_GIT_BLOB):
        raise ValueError("UNPINNED_MODULE_EVIDENCE")
    return True


def check_graph(graph):
    if not isinstance(graph,dict) or set(graph)!={"nodes","edges","queries","weight_units"}:
        raise ValueError("INVALID_GRAPH_SCHEMA")
    nodes=graph["nodes"]
    if (not isinstance(nodes,list) or not 2<=len(nodes)<=64 or
            any(type(s) is not str or not NAME.fullmatch(s) for s in nodes)
            or len(set(nodes))!=len(nodes)):
        raise ValueError("INVALID_GRAPH_NODES")
    edges=graph["edges"]
    if not isinstance(edges,list) or not 1<=len(edges)<=256:
        raise ValueError("INVALID_GRAPH_EDGES")
    seen=set()
    for edge in edges:
        if (not isinstance(edge,list) or len(edge)!=3 or
                edge[0] not in nodes or edge[1] not in nodes or
                type(edge[2]) is not int or not 1<=edge[2]<=100_000
                or tuple(edge[:2]) in seen):
            raise ValueError("INVALID_GRAPH_EDGE")
        seen.add(tuple(edge[:2]))
    queries=graph["queries"]
    if not isinstance(queries,list) or not 1<=len(queries)<=128:
        raise ValueError("GRAPH_QUERY_LIMIT")
    for q in queries:
        if (not isinstance(q,list) or len(q)!=3 or
                q[0] not in nodes or q[1] not in nodes or
                (q[2] is not None and (type(q[2]) is not int or q[2]<0))):
            raise ValueError("INVALID_GRAPH_QUERY")
    if graph["weight_units"]!="SYNTHETIC_NONPHYSICAL_COST":
        raise ValueError("REAL_PHYSICS_CLAIM_NOT_ALLOWED")
    return True


def bellman_ford(graph,start,target):
    """Deliberately unoptimized parent route oracle with full edge sweeps."""
    check_graph(graph)
    distances={n:float("inf") for n in graph["nodes"]}
    distances[start]=0
    scans=0
    for _ in range(len(graph["nodes"])-1):
        for a,b,w in graph["edges"]:
            scans+=1
            if distances[a]+w<distances[b]:
                distances[b]=distances[a]+w
    answer=distances[target]
    return {"distance":None if math.isinf(answer) else int(answer),
            "edge_scans":scans}


def heap_route(graph,start,target):
    """Physarum-inspired route analogue; not the historical Physarum's code."""
    check_graph(graph)
    neighbors={n:[] for n in graph["nodes"]}
    for a,b,w in graph["edges"]:
        neighbors[a].append((w,b))
    for row in neighbors.values():row.sort()
    best={start:0};heap=[(0,start)];scans=0
    while heap:
        cost,node=heapq.heappop(heap)
        if cost!=best[node]:continue
        if node==target:break
        for w,next_node in neighbors[node]:
            scans+=1
            proposal=cost+w
            if proposal<best.get(next_node,float("inf")):
                best[next_node]=proposal
                heapq.heappush(heap,(proposal,next_node))
    return {"distance":best.get(target),"edge_scans":scans}


def broken_hop_count(graph,start,target):
    """Mutation-testing negative control: ignores weights, must be rejected."""
    check_graph(graph)
    frontier=[(start,0)];seen={start}
    while frontier:
        node,depth=frontier.pop(0)
        if node==target:
            return {"distance":depth,"edge_scans":depth}
        for a,b,_ in graph["edges"]:
            if a==node and b not in seen:
                seen.add(b);frontier.append((b,depth+1))
    return {"distance":None,"edge_scans":0}


def slime_trace(data):
    if not isinstance(data,dict) or set(data)!={"old","error","decay"}:
        raise ValueError("INVALID_SLIME_INPUT")
    old,error,decay=data["old"],data["error"],data["decay"]
    if (not all(type(x) in (float,int) and math.isfinite(x) for x in (old,error,decay))
            or not 0<=old<=1 or not 0<=decay<1 or not -100<=error<=100):
        raise ValueError("INVALID_SLIME_RANGE")
    value=decay*old+(1-decay)*math.exp(-min(20,abs(error)))
    return {"trace":round(value,12),"precision":"DETERMINISTIC_FLOAT_APPROXIMATE",
            "weights_changed":False}


def graph_dedupe(edges):
    if not isinstance(edges,list) or len(edges)>256:
        raise ValueError("GRAPH_DEDUPE_LIMIT")
    seen=set()
    for edge in edges:
        if not isinstance(edge,list) or len(edge)!=3:
            raise ValueError("INVALID_DEDUPE_INPUT")
        a,b,w=edge
        if not isinstance(a,str) or not isinstance(b,str) or not NAME.fullmatch(a) or not NAME.fullmatch(b) or type(w) is not int:
            raise ValueError("INVALID_DEDUPE_EDGE")
        seen.add((a,b,w))
    unique=sorted(seen)
    return {"edges":[list(item) for item in unique],"duplicates_removed":len(edges)-len(unique)}


def trinity_veto(data):
    if not isinstance(data,dict) or set(data)!={"votes","risk"}:
        raise ValueError("INVALID_COUNCIL_INPUT")
    votes=data["votes"];risk=data["risk"]
    if (not isinstance(votes,list) or len(votes)!=3 or
            any(v not in ("accelerate","hold","stabilize") for v in votes)
            or type(risk) not in (float,int) or not math.isfinite(risk)
            or not 0<=risk<=1):
        raise ValueError("INVALID_COUNCIL_VOTES")
    counts={v:votes.count(v) for v in ("accelerate","hold","stabilize")}
    preferred=max(counts,key=counts.get)
    result="HOLD" if risk>=.62 or counts[preferred]<2 else preferred.upper()
    return {"advisory_vote":result,"execution_authority":False}


def normalize_dream(event):
    """Versioned bus normalization fixes old Ouroboros/Rex/Hypnos schema drift."""
    if not isinstance(event,dict) or len(event)>14:
        return {"lane":"QUARANTINE","reason":"INVALID_ENVELOPE"}
    kind=event.get("type")
    if kind not in BLUEPRINT_TYPES|MEMORY_TYPES|EXPERIENCE_TYPES:
        return {"lane":"QUARANTINE","reason":"UNKNOWN_LEGACY_TYPE"}
    target=event.get("target_module")
    title=event.get("title") or event.get("label") or (event.get("target_module") if kind in ("EVOLVED_BUFF","SYSTEM_BUFF") else "") or ""
    summary=event.get("blueprint") or event.get("insight") or event.get("content") or ""
    if (type(title) is not str or type(summary) is not str
            or not 3<=len(title)<=90 or not 8<=len(summary)<=240
            or type(event.get("source")) is not str or len(event["source"])>60):
        return {"lane":"QUARANTINE","reason":"BOUNDED_FIELDS_REQUIRED"}
    if (isinstance(target,str) and (len(target)>64 or
          (target in DENY_LEGACY_MODULES and kind=="CODE_GENERATION"))):
        return {"lane":"QUARANTINE","reason":"PROTECTED_CODE_TARGET"}
    if any(x in summary.casefold() for x in DANGEROUS):
        return {"lane":"QUARANTINE","reason":"EXECUTION_LANGUAGE_FORBIDDEN"}
    lane="BLUEPRINT" if kind in BLUEPRINT_TYPES else ("MEMORY" if kind in MEMORY_TYPES else "EXPERIENCE")
    return {"schema":"janus.essence.dream_bus/1.3",
            "lane":lane,"legacy_type":kind,
            "idea_id":seal({"kind":kind,"title":title,"summary":summary,"source":event["source"]})[:20],
            "target_is_protected":isinstance(target,str) and target in DENY_LEGACY_MODULES,
            "data_only":True,"original_payload_executed":False,
            "automatic_activation":False,"source_untrusted":True}


def nas_snapshot(data):
    if (not isinstance(data,dict) or data.get("state")!="LOCAL_SNAPSHOT_ONLY"
            or type(data.get("count")) is not int or not 0<=data["count"]<=2000
            or data.get("network_access") is not False):
        raise ValueError("LIVE_NAS_STATE_OR_PRIVILEGE_NOT_VERIFIED")
    return {"snapshot_record_count":data["count"],
            "live_nas_connected":False,"nas_mutation":False,
            "status":"STALE_POSSIBLE_LOCAL_SNAPSHOT_ONLY"}


HANDLERS={
    "physarum_route":lambda data:heap_route(data["graph"],data["start"],data["target"]),
    "slime_trace":slime_trace,
    "graph_dedupe":graph_dedupe,
    "trinity_veto":trinity_veto,
    "dream_router":normalize_dream,
    "nas_snapshot":nas_snapshot,
}


def dispatch(op,data,manifest,root,*,explicit_readonly=False):
    if explicit_readonly is not True:
        raise PermissionError("MODULE_GOVERNOR_INERT_BY_DEFAULT")
    check_manifest(manifest,root)
    if op not in HANDLERS:
        raise ValueError("UNREGISTERED_OR_LEGACY_MODULE")
    result=HANDLERS[op](data)
    return {"schema":"janus.essence.module_dispatch/1.3",
            "repo":manifest["repository"],"operator":op,"result":result,
            "writes":False,"source_executed":False,"production_authority":False,
            "receipt_sha256":seal({"operator":op,"result":result,
                                  "repository":manifest["repository"]})}


def evaluate_fitness(cases):
    if not isinstance(cases,dict) or cases.get("schema")!=CASES:
        raise ValueError("INVALID_FROZEN_CASES")
    graph=cases.get("graph")
    check_graph(graph)
    parent=[];child=[];broken=[]
    for start,target,expected in graph["queries"]:
        a=bellman_ford(graph,start,target)
        b=heap_route(graph,start,target)
        c=broken_hop_count(graph,start,target)
        if a["distance"]!=expected:
            raise ValueError("FROZEN_GRAPH_ORACLE_MISMATCH")
        parent.append(a);child.append(b);broken.append(c)
    if any(p["distance"]!=c["distance"] for p,c in zip(parent,child)):
        gate="HOLD_SEMANTIC_REGRESSION"
    elif any(c["edge_scans"]>p["edge_scans"] for p,c in zip(parent,child)):
        gate="HOLD_OPERATION_REGRESSION"
    elif sum(c["edge_scans"] for c in child)>=sum(p["edge_scans"] for p in parent):
        gate="HOLD_NO_MEASURABLE_IMPROVEMENT"
    else:
        gate="RESEARCH_OFFSPRING_FINITE_CASES_ONLY"
    counterexamples=[i for i,(a,b) in enumerate(zip(parent,broken))
                     if a["distance"]!=b["distance"]]
    if not counterexamples:
        raise ValueError("BROKEN_NEGATIVE_CONTROL_NOT_CAUGHT")
    return {"gate":gate,"cases":len(parent),
            "parent_scan_total":sum(x["edge_scans"] for x in parent),
            "child_scan_total":sum(x["edge_scans"] for x in child),
            "exact_output_equivalence":all(p["distance"]==c["distance"] for p,c in zip(parent,child)),
            "bad_child_counterexamples":len(counterexamples),
            "first_bad_child_case_index":counterexamples[0],
            "research_candidate":"heap_route_v1","baseline":"bellman_ford_full_sweeps",
            "source_code_training":False,"production_authority":False}


def evaluate_dream_bus(cases):
    events=cases.get("dream_envelopes")
    controls=cases.get("negative_controls")
    if not isinstance(events,list) or not isinstance(controls,list) or len(events)>30 or len(controls)>20:
        raise ValueError("UNBOUNDED_DREAM_CORPUS")
    routed=[normalize_dream(e) for e in events]
    quarantined=[normalize_dream(e) for e in controls]
    if (any(r["lane"]!=e["expected_lane"] for r,e in zip(routed,events))
        or len(routed)!=len(events)
        or len(quarantined)!=len(controls)
        or any(r["lane"]!="QUARANTINE" for r in quarantined)):
        raise ValueError("LEGACY_DREAM_BUS_PROTOCOL_REGRESSION")
    return {"routed":len(routed),"quarantined_controls":len(quarantined),
            "blueprint_ids":[x["idea_id"] for x in routed if x["lane"]=="BLUEPRINT"],
            "producer_to_consumer_schema_v13":True,
            "unrouted_messages_deleted":False,
            "legacy_module_code_executed":False}


def verify_history(previous,repository,case_hash):
    if previous is None:
        return {"generation":0,"seen":[]}
    if (not isinstance(previous,dict) or previous.get("schema")!=SCHEMA
            or previous.get("repository")!=repository
            or previous.get("frozen_cases_sha256")!=case_hash
            or previous.get("production_authority") is not False
            or previous.get("live_model_weights_modified") is not False
            or previous.get("receipt_sha256")!=seal({
              k:v for k,v in previous.items() if k!="receipt_sha256"})):
        raise ValueError("UNTRUSTED_PREVIOUS_GENERATION")
    gen=previous.get("research_generation")
    seen=previous.get("evaluated_candidates")
    if (type(gen) is not int or not 0<=gen<=8
            or not isinstance(seen,list) or len(seen)>8
            or any(s not in ("heap_route_v1",) for s in seen)
            or len(set(seen))!=len(seen)):
        raise ValueError("PREVIOUS_GENERATION_LIMIT")
    return {"generation":gen,"seen":seen}


def evolve(manifest,root,case_bundle,catalog,*,explicit_readonly=False,history=None):
    if explicit_readonly is not True:raise PermissionError("EVOLUTION_INERT_BY_DEFAULT")
    check_manifest(manifest,root)
    if (catalog.get("schema")!=CATALOG or
            catalog.get("nas_live_access")!="UNVERIFIED_OLD_CONFIGURED_ENDPOINT_UNREACHABLE"
            or catalog.get("raw_module_code_uploaded") is not False
            or catalog.get("production_changes") is not False):
        raise ValueError("UNTRUSTED_NAS_OR_MODULE_CATALOG")
    fitness=evaluate_fitness(case_bundle)
    bus=evaluate_dream_bus(case_bundle)
    parent=verify_history(history,manifest["repository"],seal(case_bundle))
    has_benefit=fitness["gate"]=="RESEARCH_OFFSPRING_FINITE_CASES_ONLY"
    novel=fitness["research_candidate"] not in parent["seen"]
    generation=parent["generation"]+(1 if has_benefit and novel else 0)
    if generation>8:raise ValueError("RESEARCH_GENERATION_LIMIT")
    decision=("RESEARCH_CHILD_STAGED_NO_PRODUCTION" if has_benefit and novel
              else "HOLD_NO_NEW_INDEPENDENT_GAIN")
    seen=list(parent["seen"])
    if has_benefit and novel:seen.append(fitness["research_candidate"])
    result={
        "schema":SCHEMA,"repository":manifest["repository"],
        "root_manifest_sha256":seal(root),"module_manifest_sha256":seal(manifest),
        "frozen_cases_sha256":seal(case_bundle),
        "historic_catalog_sha256":seal(catalog),
        "frozen_cases_blob_sha1":CORPUS_GIT_BLOB,
        "historical_catalog_blob_sha1":CATALOG_GIT_BLOB,
        "historical_pc_sources_inventoried":catalog["pc_inventory_total"],
        "nas_live_state":"UNVERIFIED_OFFLINE_LOCAL_SNAPSHOT",
        "active_operators":list(OPERATORS),
        "graph_fitness":fitness,"dream_bus":bus,
        "research_generation":generation,"evaluated_candidates":seen,
        "research_status":decision,
        "parent_generation":parent["generation"],
        "lineage_parent_receipt":history["receipt_sha256"] if history else None,
        "automatic_birth":False,
        "legacy_source_imported":False,
        "remote_communications_enabled":False,
        "nas_written":False,
        "live_model_weights_modified":False,
        "production_authority":False,
        "external_blind_verification":False,
        "production_rollback_tested":False,
    }
    result["receipt_sha256"]=seal(result)
    return result


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for v in ("manifest","root","cases","catalog","out"):
        p.add_argument("--"+v,required=True)
    p.add_argument("--history")
    p.add_argument("--allow-readonly",action="store_true")
    a=p.parse_args()
    manifest,root=load_json(a.manifest),load_json(a.root)
    cases=load_frozen(a.cases,CORPUS_GIT_BLOB,CASES)
    catalog=load_frozen(a.catalog,CATALOG_GIT_BLOB,CATALOG)
    history=load_json(a.history) if a.history else None
    report=evolve(manifest,root,cases,catalog,history=history,
                  explicit_readonly=a.allow_readonly)
    out=Path(a.out)
    allowed=(Path.cwd()/"research"/"essence"/"module_organogenesis_v13").resolve()
    if (out.suffix!=".json" or not out.resolve().is_relative_to(allowed)
            or out.name not in ("ci_generation.json","generation_0001.json","generation_0002.json")
            or out.parent.is_symlink()):
        raise ValueError("RESEARCH_OUTPUT_PATH_REQUIRED")
    if out.exists():raise FileExistsError("EVIDENCE_OUTPUT_NO_OVERWRITE")
    out.parent.mkdir(parents=True,exist_ok=True)
    out.write_text(json.dumps(report,ensure_ascii=False,sort_keys=True,indent=2)+"\n",encoding="utf-8")
    print(json.dumps({"research_generation":report["research_generation"],
        "graph_fitness":report["graph_fitness"],
        "dream_bus":report["dream_bus"],
        "status":report["research_status"],
        "production_authority":report["production_authority"],
        "receipt_sha256":report["receipt_sha256"]},ensure_ascii=False))


if __name__=="__main__":
    main()
