"""ESSENCE v5.2 offline reciprocal six-role + adversarial shadow tuning suite."""
import copy
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

spec = importlib.util.spec_from_file_location(
    "essence_peer_mesh_v52",
    str(Path(__file__).resolve().parents[1]/".janus/essence/peer_mesh_v52.py"))
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)

def save(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)

class MeshTests(unittest.TestCase):
    def setUp(self):
        self.raw = {m.D: m.canonical_dummy_manifest(m.D),
                    m.G: m.canonical_dummy_manifest(m.G)}

    def test_all_six_cells_have_usable_crossrepo_contacts(self):
        for src in (m.D, m.G):
            for cell in m.CELLS:
                req = m.make_request(src, "a"*40, self.raw[src], cell, cell)
                self.assertEqual(req["source_cell"], cell)
                self.assertEqual(req["target_cell"], cell)
                self.assertIs(m.verify_request(req, m.PEERS[src]), req)
                reply = m.make_response(req, m.PEERS[src], "b"*40,
                                        self.raw[m.PEERS[src]])
                m.verify_response(req, reply, self.raw[m.PEERS[src]])
                self.assertFalse(reply["code_execution"])

    def test_six_cell_each_way_actual_queue_roundtrip_with_one_fetch(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            roots = {m.D: base/"D", m.G: base/"G"}
            states = {m.D: base/"stateD", m.G: base/"stateG"}
            for repo, raw in self.raw.items():
                save(roots[repo]/m.MANIFEST, raw)
            calls = []
            def fetch(repo, commit):
                calls.append((repo, commit))
                return self.raw[repo]
            first = m.process(roots[m.D], m.D, "a"*40, states[m.D],
                              states[m.G], fetch=fetch)
            self.assertEqual(first["new"]["requests"], 7)
            self.assertEqual(first["peer_input_count"], 0)
            second = m.process(roots[m.G], m.G, "b"*40, states[m.G],
                               states[m.D], fetch=fetch)
            self.assertEqual(second["peer_input_count"], 7)
            self.assertEqual(second["peer_manifest_read_calls"], 1)
            self.assertEqual(second["new"]["responses"], 7)
            self.assertTrue(second["shadow_tuning_only"])
            shadow = list((states[m.G]/m.BASE/"shadow_settings").glob("*.json"))
            self.assertEqual(len(shadow), 1)
            record = m.load(shadow[0])
            self.assertEqual(record["network_reads_saved_against_uncached_plan"], 6)
            self.assertFalse(record["production_change"])
            third = m.process(roots[m.D], m.D, "a"*40, states[m.D],
                              states[m.G], fetch=fetch)
            self.assertEqual(third["new"]["acks"], 7)
            self.assertEqual(third["new"]["responses"], 7)
            fourth = m.process(roots[m.G], m.G, "b"*40, states[m.G],
                               states[m.D], fetch=fetch)
            self.assertEqual(fourth["new"]["acks"], 7)
            again = m.process(roots[m.G], m.G, "b"*40, states[m.G],
                              states[m.D], fetch=fetch)
            self.assertEqual(again["new"]["requests"], 0)
            self.assertEqual(again["new"]["responses"], 0)
            self.assertEqual(again["new"]["acks"], 0)
            for repo in (m.D, m.G):
                self.assertEqual(len(list((states[repo]/m.BASE/"acks").glob("*.json"))), 7)

    def test_escalation_and_forged_peer_data_denied_even_when_resealed(self):
        req = m.make_request(m.D, "a"*40, self.raw[m.D],
                             "cell-planning-02", "cell-verification-03",
                             "PROPOSE_SHADOW_CACHE")
        for field, value in (("execute_code", True),
                             ("change_weights", True),
                             ("production_change", True),
                             ("sentinel_dispatch", True),
                             ("text_is_authority", True),
                             ("source_path", "../../secrets"),
                             ("target_cell", "cell-evil"),
                             ("proposal", {"setting": "workflow_dispatch", "value": True}),
                             ("target_repo", "Hawkar-usls/SkinGPT")):
            bad = copy.deepcopy(req)
            bad[field] = value
            bad = m.seal({k:v for k,v in bad.items() if k != "receipt_sha256"})
            with self.assertRaises(ValueError, msg=field):
                m.verify_request(bad, m.G)
        bad = copy.deepcopy(req)
        bad["extra_command"] = "echo owned"
        bad = m.seal({k:v for k,v in bad.items() if k != "receipt_sha256"})
        with self.assertRaisesRegex(ValueError, "UNEXPECTED_FIELDS"):
            m.verify_request(bad, m.G)

    def test_provenance_and_receipt_negative_controls(self):
        req = m.make_request(m.D, "a"*40, self.raw[m.D],
                             "cell-memory-01", "cell-memory-01")
        rep = m.make_response(req, m.G, "b"*40, self.raw[m.G])
        forged = copy.deepcopy(rep)
        forged["code_execution"] = True
        forged = m.seal({k:v for k,v in forged.items() if k != "receipt_sha256"})
        with self.assertRaisesRegex(ValueError, "UNVERIFIED_RESPONSE"):
            m.verify_response(req, forged, self.raw[m.G])
        with self.assertRaisesRegex(ValueError, "RESPONSE_ORIGIN_OR_SOURCE"):
            m.verify_response(req, rep, self.raw[m.D])
        broken = dict(req, receipt_sha256="0"*64)
        with self.assertRaisesRegex(ValueError, "BROKEN_RECEIPT"):
            m.verify_request(broken, m.G)
        with self.assertRaisesRegex(ValueError, "DUPLICATE_JSON_KEY"):
            m.decode(b'{"a":1,"a":2}')
        with self.assertRaisesRegex(ValueError, "NONFINITE_JSON"):
            m.decode(b'{"x":NaN}')
        wrong = json.loads(self.raw[m.D])
        wrong["capabilities"]["repo_write"] = True
        with self.assertRaisesRegex(ValueError, "ROOT_AUTHORITY"):
            m.verify_manifest(m.canonical(wrong), m.D)

    def test_source_hash_rejection_is_fail_closed(self):
        with tempfile.TemporaryDirectory() as td:
            base=Path(td)
            save(base/"d"/m.MANIFEST,self.raw[m.D])
            save(base/"g"/m.MANIFEST,self.raw[m.G])
            m.process(base/"d",m.D,"a"*40,base/"sd",base/"sg",
                      fetch=lambda repo,commit: self.raw[repo])
            with self.assertRaisesRegex(ValueError, "PIN_MISMATCH"):
                m.process(base/"g",m.G,"b"*40,base/"sg",base/"sd",
                          fetch=lambda repo,commit: self.raw[repo]+b' ')

    def test_parent_symlink_cannot_redirect_peer_state(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            outside = root / "outside"
            outside.mkdir()
            (root / "peer-link").symlink_to(outside, target_is_directory=True)
            save(outside / "existing.json", b'{"value": 1}')
            with self.assertRaisesRegex(ValueError, "SYMLINK_COMPONENT"):
                m.load(root / "peer-link" / "existing.json")
            with self.assertRaisesRegex(ValueError, "SYMLINK_COMPONENT"):
                m.put_once(root / "peer-link" / "new.json", {"value": 2})
            with self.assertRaisesRegex(ValueError, "SYMLINK_COMPONENT"):
                m.queue(root / "peer-link" / "requests")
            self.assertFalse((outside / "new.json").exists())

    def test_shadow_caching_needs_a_verified_peer_proposal(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            save(base / "d" / m.MANIFEST, self.raw[m.D])
            save(base / "g" / m.MANIFEST, self.raw[m.G])
            m.process(base / "d", m.D, "a" * 40, base / "sd", base / "sg",
                      fetch=lambda repo, commit: self.raw[repo])
            for path in (base / "sd" / m.BASE / "requests").glob("*.json"):
                if m.load(path)["intent"] == "PROPOSE_SHADOW_CACHE":
                    path.unlink()
            calls = []
            def fetching(repo, commit):
                calls.append((repo, commit))
                return self.raw[repo]
            result = m.process(base / "g", m.G, "b" * 40,
                               base / "sg", base / "sd", fetch=fetching)
            self.assertEqual(result["peer_input_count"], 6)
            self.assertEqual(result["peer_manifest_read_calls"], 6)
            self.assertFalse(result["shadow_tuning_only"])
            self.assertEqual(len(calls), 6)

    def test_old_reply_is_immutable_across_new_code_commits(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            save(base / "d" / m.MANIFEST, self.raw[m.D])
            save(base / "g" / m.MANIFEST, self.raw[m.G])
            fetch = lambda repo, commit: self.raw[repo]
            m.process(base / "d", m.D, "a" * 40,
                      base / "sd", base / "sg", fetch=fetch)
            first = m.process(base / "g", m.G, "b" * 40,
                              base / "sg", base / "sd", fetch=fetch)
            self.assertEqual(first["new"]["responses"], 7)
            folder = base / "sg" / m.BASE / "responses"
            before = {p.name: p.read_bytes() for p in folder.glob("*.json")}
            self.assertEqual(len(before), 7)
            second = m.process(base / "g", m.G, "c" * 40,
                               base / "sg", base / "sd", fetch=fetch)
            self.assertEqual(second["new"]["responses"], 0)
            self.assertEqual(
                before,
                {p.name: p.read_bytes() for p in folder.glob("*.json")}
            )
            # Preserve HOLD on actual manifest drift: the old pinned reply
            # cannot be silently reused for a new target manifest.
            one_reply = m.load(next(iter(folder.glob("*.json"))))
            one_request = m.load(
                base / "sd" / m.BASE / "requests"
                / (one_reply["request_id"] + ".json")
            )
            changed = json.loads(self.raw[m.G])
            changed["untrusted_audit_marker"] = "new-manifest"
            with self.assertRaisesRegex(
                ValueError, "MESH_RESPONSE_ORIGIN_OR_SOURCE"
            ):
                m.verify_response(one_request, one_reply, m.canonical(changed))

if __name__ == "__main__":
    unittest.main()
