"""JANUS Kombucha: bounded, read-only, subprocess-isolated repository sensor mesh."""
from __future__ import annotations
import argparse
import asyncio
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sys
import urllib.error
import urllib.request

OWNER = "Hawkar-usls"
GROUPS = {
    "brain": ("Janus_Genesis", "Janus-Demiurge", "Demi_Head", "janus-distributed-ai-swarm"),
    "memory": ("janus-meta-registry", "Hrain", "iNaiHR", "Janus-Fundamentum"),
    "sensing": ("TOPA", "janus-lapis", "aura-oracle-tg", "Janus-Cosmos"),
    "bio": ("SCOBY-D0", "Simptomat"),
    "io": ("Hawkar-usls", "-Terminal-for-Janus", "janus-first-followers-club-"),
    "markets": ("JANUS-MACHINE-MARKET", "Janus-HELIOS", "AIFC"),
}
CRITICAL = ("brain", "memory", "sensing")
MAX_CYCLES = 2
MAX_PARALLEL = 3
MAX_SECONDS = 36


def utcnow():
    return datetime.now(timezone.utc).isoformat()


def read_public_run(repo):
    if repo not in {p for group in GROUPS.values() for p in group}:
        raise ValueError("REPO_NOT_ADMITTED")
    req = urllib.request.Request(
        f"https://api.github.com/repos/{OWNER}/{repo}/actions/runs?per_page=6",
        headers={"Accept": "application/vnd.github+json",
                 "User-Agent": "JANUS-Kombucha-ReadOnly/1.0",
                 "X-GitHub-Api-Version": "2022-11-28"})
    with urllib.request.urlopen(req, timeout=7) as stream:
        data = json.load(stream)
    runs = data.get("workflow_runs") or []
    newest = next((r for r in runs if r.get("event") != "dynamic"), None)
    return {"repository": repo, "run_id": newest.get("id") if newest else None,
            "status": newest.get("status") if newest else None,
            "conclusion": newest.get("conclusion") if newest else None,
            "head_sha": newest.get("head_sha") if newest else None,
            "url": newest.get("html_url") if newest else None}


def child(module):
    if module not in GROUPS:
        raise ValueError("MODULE_NOT_ADMITTED")
    results = []
    for repo in GROUPS[module]:
        try:
            results.append(read_public_run(repo))
        except (OSError, ValueError, urllib.error.URLError) as err:
            results.append({"repository": repo, "error": type(err).__name__})
    return {"module": module, "observed_at": utcnow(), "repositories": results,
            "reachable": sum("error" not in x for x in results),
            "failures": sum(x.get("conclusion") == "failure" for x in results)}


async def isolate(module, seconds=MAX_SECONDS, fixture=None):
    if fixture is not None:
        return await asyncio.wait_for(fixture(module), timeout=seconds)
    proc = await asyncio.create_subprocess_exec(
        sys.executable, str(Path(__file__).resolve()), "--child", module,
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
        env={"PATH": os.environ.get("PATH", ""), "PYTHONUNBUFFERED": "1"})
    try:
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=seconds)
    except asyncio.TimeoutError:
        proc.kill()
        await proc.communicate()
        raise TimeoutError("MODULE_TIMEOUT")
    if proc.returncode != 0 or len(stdout) > 100000:
        raise RuntimeError("MODULE_PROCESS_FAILURE: " + stderr.decode("utf-8", "replace")[-200:])
    result = json.loads(stdout)
    if result.get("module") != module:
        raise RuntimeError("MODULE_IDENTITY_MISMATCH")
    return result


async def circulate(modules=tuple(GROUPS), cycles=MAX_CYCLES, fixture=None, seconds=MAX_SECONDS):
    if not 1 <= cycles <= MAX_CYCLES:
        raise ValueError("UNBOUNDED_CYCLES_DENIED")
    if len(set(modules)) != len(modules) or set(modules) - set(GROUPS):
        raise ValueError("UNADMITTED_MODULE")
    sem = asyncio.Semaphore(MAX_PARALLEL)
    fail_counts = {m: 0 for m in modules}
    journal = []
    for cycle in range(1, cycles + 1):
        async def one(module):
            if fail_counts[module] >= 2:
                return {"module": module, "state": "QUARANTINED", "cycle": cycle}
            async with sem:
                try:
                    result = await isolate(module, seconds, fixture)
                    fail_counts[module] = 0
                    return {"module": module, "state": "OBSERVED", "cycle": cycle, "result": result}
                except (TimeoutError, asyncio.TimeoutError, RuntimeError, ValueError, OSError) as err:
                    fail_counts[module] += 1
                    return {"module": module, "state": "ISOLATED_FAILURE", "cycle": cycle,
                            "error": type(err).__name__}
        journal.extend(await asyncio.gather(*(one(m) for m in modules)))
    latest = {row["module"]: row for row in journal[-len(modules):]} if modules else {}
    def healthy(row):
        result = row.get("result", {})
        return (row["state"] == "OBSERVED" and
                result.get("reachable") == len(GROUPS[row["module"]]) and
                not result.get("failures"))
    critical_healthy = set(CRITICAL).issubset(latest) and all(healthy(latest[m]) for m in CRITICAL)
    all_observed = bool(latest) and all(x["state"] == "OBSERVED" for x in latest.values())
    return {"schema": "janus.kombucha.microkernel.v1", "timestamp": utcnow(),
            "mode": "OBSERVATION_ONLY", "cycle_count": cycles, "modules": list(modules),
            "parallel_limit": MAX_PARALLEL, "journal": journal,
            "module_states": {m: latest[m]["state"] for m in latest},
            "gate": "PASS_OBSERVATION_ONLY" if critical_healthy and all_observed else "HOLD",
            "critical_healthy": critical_healthy,
            "claim_of_full_autonomy": False, "cross_repository_dispatches": 0,
            "untrusted_code_executed": False, "production_writes": 0,
            "recursive_self_dispatch": False}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--child", choices=GROUPS)
    parser.add_argument("--out", type=Path)
    parser.add_argument("--cycles", type=int, default=MAX_CYCLES)
    args = parser.parse_args()
    if args.child:
        print(json.dumps(child(args.child), sort_keys=True))
        return
    result = asyncio.run(circulate(cycles=args.cycles))
    print(json.dumps({"gate": result["gate"], "modules": result["module_states"],
                      "cycles": result["cycle_count"]}, sort_keys=True))
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(result, indent=2, ensure_ascii=False, sort_keys=True) + "\n")


if __name__ == "__main__":
    main()
