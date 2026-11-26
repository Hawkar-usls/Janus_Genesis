"""R3.2 bounded discovery of approved workflows; no run or artifact IDs in policy."""
import hashlib
import io
import json
import re
import zipfile

import requests

POLICY = {
    "terrain": ("Janus-Cosmos", "kusto-zn-r210-genesis-spatial.yml",
                "experiment/kusto-zn-r2-deep-scan-20261126",
                "4ac4eb9ee76c01882f69f19c3953db69df92e690",
                "kusto-zn-r210-genesis-spatial", "scientific_layers.npz"),
    "review": ("Demi_Head", "eye-r3-direct-intake.yml",
               "research/nexus-cosmos-eye-spatial",
               "0814de95f0761b3820f5a1c381733b1459110444",
               "eye-r3-demihead-delivery", "receipt.json"),
}
CAP = 16 * 1024 * 1024

def digest(b):
    return hashlib.sha256(b).hexdigest()

def discover(key, token, session=requests):
    repo, workflow, branch, head, artifact, member = POLICY[key]
    full = "Hawkar-usls/" + repo
    base = "https://api.github.com/repos/" + full
    if not isinstance(token, str) or not 16 < len(token) < 4096 or not token.isascii() or any(ord(c) <= 32 or ord(c) >= 127 for c in token):
        raise ValueError("invalid opaque read credential")
    headers = {"Authorization": "Bearer " + token, "Accept": "application/vnd.github+json"}
    def get(path, params=None):
        with session.get(base + path, params=params, headers=headers, timeout=(10,45), stream=True) as response:
            response.raise_for_status()
            buf = bytearray()
            for chunk in response.iter_content(65536):
                buf.extend(chunk)
                if len(buf)>CAP:
                    raise ValueError("response cap")
            return bytes(buf)
    rows = json.loads(get("/actions/workflows/"+workflow+"/runs", {"head_sha":head,"per_page":20}))["workflow_runs"]
    candidates = [r for r in rows if r.get("head_sha")==head and r.get("head_branch")==branch
                  and r.get("head_repository",{}).get("full_name")==full
                  and r.get("status")=="completed" and r.get("conclusion")=="success"]
    if not candidates:
        raise ValueError("no successful approved producer")
    # Most recent nonexpired artifact on the admitted producer revision.
    for run in sorted(candidates,key=lambda r:(r["created_at"],r["id"]),reverse=True):
        rid = run["id"]
        entries = json.loads(get(f"/actions/runs/{rid}/artifacts", {"per_page":30}))["artifacts"]
        matches = [a for a in entries if a["name"]==artifact and not a["expired"]]
        if not matches:
            continue
        if len(matches)!=1:
            raise ValueError("ambiguous artifact")
        a = matches[0]
        expected = a.get("digest","")
        if not re.fullmatch(r"sha256:[a-f0-9]{64}",expected):
            raise ValueError("missing archive digest")
        aid = a["id"]
        raw = get(f"/actions/artifacts/{aid}/zip")
        if "sha256:"+digest(raw)!=expected:
            raise ValueError("archive digest mismatch")
        with zipfile.ZipFile(io.BytesIO(raw)) as z:
            ms = [m for m in z.infolist() if m.filename.rsplit("/",1)[-1]==member]
            if len(ms)!=1 or ms[0].file_size>CAP:
                raise ValueError("invalid member")
            b = z.read(ms[0])
        return b, {"repository":full,"workflow":workflow,"producer_head":head,"run_id":rid,
                   "artifact_id":aid,"archive_sha256":expected,"member_sha256":digest(b),
                   "member":member,"selection":"LATEST_SUCCESSFUL_APPROVED_REVISION_WITH_ARTIFACT",
                   "arbitrary_run_id_input":False}
    raise ValueError("no retained artifact on admitted revision")
