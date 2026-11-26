"""R3 fixed public artifact transport: bounded, read-only, no arbitrary locators."""
import hashlib
import io
import json
import zipfile

import requests

SOURCES = {
    "kusto": ("Janus-Cosmos", 45832385030, 15122838520,
              "1de7032febea4ebc12db315c2db5725831ad312d78b55ca20401efadb296cbc1",
              "scientific_layers.npz",
              "15bcc32c14a7e5a700bb3b05ff7aa039d9793426e7a2be0d7ed85916358ee442"),
    "eye": ("Janus-Cosmos", 45833030382, 15123013441,
            "b57022a2f7d359399bfc732947356310a6542d9f3ea02c4c60df3048f504ec2a",
            "scene_receipt.json", None),
    "review": ("Demi_Head", 45840986384, 15127419718,
               "10baf9fcf658ea3a065ee30e325b3d9aae0866e31d1bd20eda688c93803a74fe",
               "receipt.json", None),
}
CAP = 16 * 1024 * 1024

def digest(raw):
    return hashlib.sha256(raw).hexdigest()

def pull(key, token):
    repo, run, aid, expected, member, member_hash = SOURCES[key]
    if not isinstance(token, str) or not 16 < len(token) < 4096 or not token.isascii() or any(ord(ch) <= 32 or ord(ch) >= 127 for ch in token):
        raise ValueError("missing or invalid read token")
    base = "https://api.github.com/repos/Hawkar-usls/" + repo
    headers = {"Authorization": "Bearer " + token, "Accept": "application/vnd.github+json"}
    def get(url):
        with requests.get(url, headers=headers, timeout=(10,45), stream=True) as r:
            r.raise_for_status()
            buf = bytearray()
            for chunk in r.iter_content(65536):
                buf.extend(chunk)
                if len(buf) > CAP:
                    raise ValueError("response cap")
            return bytes(buf)
    run_meta = json.loads(get(base + "/actions/runs/" + str(run)))
    if run_meta["id"] != run or run_meta["status"] != "completed" or run_meta["conclusion"] != "success":
        raise ValueError("upstream run not successful")
    meta = json.loads(get(base + "/actions/artifacts/" + str(aid)))
    if (meta["id"] != aid or meta["workflow_run"]["id"] != run or meta["expired"]
            or meta.get("digest") != "sha256:"+expected):
        raise ValueError("artifact identity mismatch")
    raw = get(base + "/actions/artifacts/" + str(aid) + "/zip")
    if digest(raw) != expected:
        raise ValueError("archive byte mismatch")
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        entries = [i for i in z.infolist() if i.filename.rsplit("/",1)[-1] == member]
        if len(entries) != 1 or entries[0].file_size > CAP:
            raise ValueError("member missing or oversized")
        content = z.read(entries[0])
    if member_hash is not None and digest(content) != member_hash:
        raise ValueError("member byte mismatch")
    return content, {"repository":repo,"source_run_id":run,"artifact_id":aid,"archive_sha256":expected,
                     "member":member,"member_sha256":digest(content),"transport":"VERIFIED_ARTIFACT_BYTES",
                     "producer_head_sha":run_meta["head_sha"]}
