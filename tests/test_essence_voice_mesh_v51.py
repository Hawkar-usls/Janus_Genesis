"""Two-way ESSENCE v5.1 peer speech-link and task handoff, offline adversarial suite."""
import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

import importlib.util

_spec=importlib.util.spec_from_file_location("voice_mesh_v51",str(Path(__file__).resolve().parents[1]/".janus/essence/voice_mesh_v51.py"))
m=importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(m)


def local_manifest(repo):
    return {
        "schema":"janus.essence.microkernel/0.1",
        "repository":repo,"enabled":False,
        "activation":"EXPLICIT_READONLY_TEST_ONLY",
        "birth_policy":"PROPOSAL_ONLY",
        "capabilities":{"network":False,"shell":False,"repo_write":False,
                        "workflow_dispatch":False,"secrets":False,"hardware":False},
        "microkernels":[{"id":"cell-"+str(i)} for i in range(6)]
    }


def model_link(repo):
    return {
        "schema":m.MODEL_SCHEMA,
        "repository":repo,
        "shared_model":"Qwen/Qwen2.5-0.5B-Instruct",
        "model_role":"READ_ONLY_ASYNC_SPEAKER_LINK",
        "source_receipt_sha256":m.MODEL_RECEIPT,
        "source_packet_id":m.MODEL_PACKET,
        "original_model_answer":"HOLD",
        "local_model_inference_performed":False,
        "speaker_can_delegate_arbitrary_workflows":False,
        "production_or_sentinel_authority":False,
    }


def v49_source():
    return {
        "schema":"janus.essence.continual_prospective_first_trial_evidence/4.9",
        "status":"HOLD_REPLAY_DID_NOT_CLEAR_PREDECLARED_GATES",
        "deployment":{"production_admission":False},
        "interpretation":{"external_custodian":False},
        "results":{
            "fresh_unseen_legacy_oracle":{"replay_exact":16},
            "lapis_paraphrased_source":{"replay_exact":0}
        }
    }


def write(path,obj):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(obj,sort_keys=True))


class VoiceMeshTests(unittest.TestCase):
    def test_origins_and_model_are_limited(self):
        for repo in (m.D,m.G):
            m.validate_model_link(model_link(repo),repo)
            bad=copy.deepcopy(model_link(repo))
            bad["speaker_can_delegate_arbitrary_workflows"]=True
            with self.assertRaisesRegex(ValueError,"LINK_AUTHORITY"):
                m.validate_model_link(bad,repo)

    def test_tampered_task_and_reply_rejected(self):
        link=model_link(m.D)
        raw=m.canonical(v49_source())
        request=m.make_task(m.D,"a"*40,raw,link)
        m.validate_task(request,m.G)
        response=m.make_reply(request,m.G,raw)
        m.verify_reply(request,response,raw)
        self.assertEqual(response["status"],"VERIFIED_V49_HOLD_SOURCE_ONLY")
        tamper=copy.deepcopy(request)
        tamper["request_arbitrary_execution"]=True
        tamper["receipt_sha256"]=m.digest({
            k:v for k,v in tamper.items() if k!="receipt_sha256"})
        with self.assertRaisesRegex(ValueError,"ESCALATION"):
            m.validate_task(tamper,m.G)
        tamper=copy.deepcopy(response)
        tamper["evidence"]["model_admission"]=True
        tamper["receipt_sha256"]=m.digest({
            k:v for k,v in tamper.items() if k!="receipt_sha256"})
        with self.assertRaisesRegex(ValueError,"REPRODUCIBLE"):
            m.verify_reply(request,tamper,raw)
        with self.assertRaisesRegex(ValueError,"SHA_MISMATCH"):
            m.make_reply(request,m.G,raw+b" ")

    def test_relay_source_only_no_execute(self):
        raw=m.canonical(v49_source())
        task=m.make_task(m.D,"a"*40,raw,model_link(m.D))
        self.assertEqual(task["last_verified_model_statement"],"HOLD")
        self.assertFalse(task["fresh_model_speech_on_this_task"])
        self.assertFalse(task["request_arbitrary_execution"])
        self.assertEqual(m.assess_source(m.D,raw)[0],"VERIFIED_V49_HOLD_SOURCE_ONLY")
        with self.assertRaises(ValueError):
            m.verify_original_model_link(json.dumps({
                "schema":"janus.agency.qwen_research_task_proposal/5.0",
                "model_raw_response":"fake","receipt_sha256":"0"*64,
            }).encode())

    def test_two_way_task_request_reply_and_receipt(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            roots={m.D:root/"D",m.G:root/"G"}
            states={m.D:root/"stateD",m.G:root/"stateG"}
            sources={
                m.D:m.canonical(v49_source()),
                m.G:m.canonical(local_manifest(m.G)),
            }
            for repo in (m.D,m.G):
                r=roots[repo]
                write(r/".janus/essence/manifest.json",local_manifest(repo))
                write(r/".janus/essence/VOICE_MODEL_LINK.json",model_link(repo))
                source=r/m.TASKS[repo][1]
                source.parent.mkdir(parents=True,exist_ok=True)
                source.write_bytes(sources[repo])
            def mocked_fetch(repo,commit,path):
                self.assertEqual(path,m.TASKS[repo][1])
                self.assertRegex(commit,r"^[a-f0-9]{40}$")
                return sources[repo]
            first=m.process(roots[m.D],m.D,"a"*40,states[m.D],states[m.G],
                            fetch=mocked_fetch)
            self.assertEqual(first["new_tasks"],1)
            g=m.process(roots[m.G],m.G,"b"*40,states[m.G],states[m.D],
                        fetch=mocked_fetch)
            self.assertEqual(g["new_tasks"],1)
            self.assertEqual(g["new_replies"],1)
            d=m.process(roots[m.D],m.D,"c"*40,states[m.D],states[m.G],
                        fetch=mocked_fetch)
            self.assertEqual(d["new_tasks"],0)
            self.assertEqual(d["new_replies"],1)
            self.assertEqual(d["new_verified_peer_replies"],1)
            g=m.process(roots[m.G],m.G,"d"*40,states[m.G],states[m.D],
                        fetch=mocked_fetch)
            self.assertEqual(g["new_tasks"],0)
            self.assertEqual(g["new_verified_peer_replies"],1)
            for repo in (m.D,m.G):
                self.assertEqual(len(list(
                    (states[repo]/"research/essence/voice_v51/heard").glob("*.json"))),1)
                self.assertEqual(len(list(
                    (states[repo]/"research/essence/voice_v51/replies").glob("*.json"))),1)
                self.assertEqual(len(list(
                    (states[repo]/"research/essence/voice_v51/messages").glob("*.json"))),1)


if __name__=="__main__":
    unittest.main()
