#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import ast
import copy
import json
import tempfile
import unittest
from pathlib import Path

from tools.janus_beacon_predictive_witness import BeaconPredictionError, JanusBeaconPredictiveWitness
from tools.janus_nas_no_delete_gateway import BeaconNasMemoryAdapter, NasGatewayError, NasJanusNoDeleteGateway


class BeaconPredictiveWitnessTests(unittest.TestCase):
    def setUp(self):
        self.beacon = JanusBeaconPredictiveWitness()
        self.context = {"face": "DEMIURGE", "gate": "UNIT", "objective_family": "BUILD", "recent_failures": 0}
        self.actions = ["PROPOSE", "VERIFY", "WAIT"]

    def forecast(self, idx=1, fid="f1", exposed=False):
        return self.beacon.forecast(forecast_id=fid, context=self.context, candidates=self.actions, event_index=idx, forecast_exposed_to_selector=exposed)

    def test_cold_start_is_bounded_distribution(self):
        result = self.forecast()
        self.assertAlmostEqual(sum(result["next_action_distribution"].values()), 1.0)
        self.assertEqual(set(result["success_forecast"]), set(self.actions))
        for row in result["success_forecast"].values():
            self.assertGreater(row["raw_probability"], 0.0)
            self.assertLess(row["raw_probability"], 1.0)
        self.assertFalse(result["prediction_is_command"])
        self.assertFalse(result["prediction_is_permission"])
        self.assertFalse(result["prediction_is_truth"])

    def test_forecast_idempotent_but_rebinding_rejected(self):
        first = self.forecast()
        self.assertEqual(first, self.forecast())
        changed = dict(self.context)
        changed["gate"] = "OTHER"
        with self.assertRaisesRegex(BeaconPredictionError, "different input"):
            self.beacon.forecast(forecast_id="f1", context=changed, candidates=self.actions, event_index=1)

    def test_outcome_must_follow_forecast(self):
        self.forecast(idx=10)
        with self.assertRaisesRegex(BeaconPredictionError, "after forecast"):
            self.beacon.settle(forecast_id="f1", outcome_event_index=10, actual_action="VERIFY", success=True)

    def test_success_learning_moves_probability_up(self):
        initial = self.forecast(fid="warmup")
        p0 = initial["success_forecast"]["VERIFY"]["raw_probability"]
        self.beacon.settle(forecast_id="warmup", outcome_event_index=2, actual_action="VERIFY", success=True)
        for i in range(2, 12):
            fid = f"f{i}"
            self.beacon.forecast(forecast_id=fid, context=self.context, candidates=self.actions, event_index=i * 2)
            self.beacon.settle(forecast_id=fid, outcome_event_index=i * 2 + 1, actual_action="VERIFY", success=True)
        after = self.beacon.forecast(forecast_id="final", context=self.context, candidates=self.actions, event_index=30)
        self.assertGreater(after["success_forecast"]["VERIFY"]["raw_probability"], p0)

    def test_next_action_learning_moves_transition_probability(self):
        cold = self.forecast(fid="cold")
        p0 = cold["next_action_distribution"]["WAIT"]
        self.beacon.settle(forecast_id="cold", outcome_event_index=2, actual_action="WAIT", success=False)
        for i in range(2, 8):
            fid = f"w{i}"
            self.beacon.forecast(forecast_id=fid, context=self.context, candidates=self.actions, event_index=i * 2)
            self.beacon.settle(forecast_id=fid, outcome_event_index=i * 2 + 1, actual_action="WAIT", success=bool(i % 2))
        later = self.beacon.forecast(forecast_id="later", context=self.context, candidates=self.actions, event_index=20)
        self.assertGreater(later["next_action_distribution"]["WAIT"], p0)

    def test_wrong_predictions_are_preserved_and_calibrated(self):
        for i in range(8):
            fid = f"miss{i}"
            self.beacon.forecast(forecast_id=fid, context=self.context, candidates=self.actions, event_index=i * 2)
            self.beacon.settle(forecast_id=fid, outcome_event_index=i * 2 + 1, actual_action="PROPOSE", success=False)
        state = self.beacon.export_state()
        self.assertEqual(len(state["outcomes"]), 8)
        self.assertEqual(self.beacon.metrics()["settled_forecasts"], 8)
        self.assertIsNotNone(self.beacon.metrics()["mean_raw_brier"])
        self.assertIsNotNone(self.beacon.metrics()["expected_calibration_error"])

    def test_exposed_forecast_is_marked_to_avoid_clean_predictive_claim(self):
        forecast = self.forecast(exposed=True)
        outcome = self.beacon.settle(forecast_id="f1", outcome_event_index=2, actual_action="PROPOSE", success=True)
        self.assertTrue(forecast["forecast_exposed_to_selector"])
        self.assertTrue(outcome["forecast_exposed_to_selector"])

    def test_out_of_support_action_updates_history_without_fake_scoring(self):
        self.forecast()
        result = self.beacon.settle(forecast_id="f1", outcome_event_index=2, actual_action="OTHER_ACTION", success=True)
        self.assertFalse(result["actual_action_in_forecast_support"])
        self.assertIsNone(result["metrics_delta"]["raw_brier"])
        self.assertEqual(self.beacon.global_action_counts["OTHER_ACTION"], 1)

    def test_state_roundtrip_and_tamper_rejection(self):
        self.forecast()
        self.beacon.settle(forecast_id="f1", outcome_event_index=2, actual_action="VERIFY", success=True)
        state = self.beacon.export_state()
        restored = JanusBeaconPredictiveWitness.from_state(state)
        self.assertEqual(restored.export_state(), state)
        tampered = copy.deepcopy(state)
        tampered["global_success"]["successes"] = 0
        with self.assertRaisesRegex(BeaconPredictionError, "receipt mismatch"):
            JanusBeaconPredictiveWitness.from_state(tampered)

    def test_raw_context_is_not_persisted(self):
        secretish = dict(self.context)
        secretish["project_local_marker"] = "DO_NOT_PERSIST_THIS_RAW_VALUE"
        result = self.beacon.forecast(forecast_id="privacy", context=secretish, candidates=self.actions, event_index=1)
        state_text = json.dumps(self.beacon.export_state(), sort_keys=True)
        self.assertNotIn("DO_NOT_PERSIST_THIS_RAW_VALUE", state_text)
        self.assertIn(result["context_sha256"], state_text)


class NasNoDeleteGatewayTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / "janus"
        self.root.mkdir()
        (self.root / "beacon").mkdir()
        (self.root / "existing.txt").write_text("source", encoding="utf-8")
        self.gateway = NasJanusNoDeleteGateway(self.root, write_prefix="beacon")

    def tearDown(self):
        self.tmp.cleanup()

    def test_read_root_and_existing_file(self):
        rows = self.gateway.list_dir(".")
        self.assertIn("existing.txt", {row["name"] for row in rows})
        self.assertEqual(self.gateway.read_bytes("existing.txt"), b"source")

    def test_writes_restricted_to_beacon_prefix(self):
        with self.assertRaisesRegex(NasGatewayError, "restricted"):
            self.gateway.create_new("outside.txt", b"x")
        with self.assertRaisesRegex(NasGatewayError, "restricted"):
            self.gateway.append("outside.txt", b"x")

    def test_create_is_exclusive_and_append_never_truncates(self):
        self.gateway.create_new("beacon/history.jsonl", b"one\n")
        with self.assertRaises(FileExistsError):
            self.gateway.create_new("beacon/history.jsonl", b"replace\n")
        self.gateway.append("beacon/history.jsonl", b"two\n")
        self.assertEqual(self.gateway.read_bytes("beacon/history.jsonl"), b"one\ntwo\n")

    def test_symlink_leaf_is_not_followed(self):
        target = self.root / "secret.txt"
        target.write_text("secret", encoding="utf-8")
        link = self.root / "beacon" / "link.txt"
        try:
            link.symlink_to(target)
        except OSError:
            self.skipTest("symlink unavailable")
        with self.assertRaises(OSError):
            self.gateway.read_bytes("beacon/link.txt")
        with self.assertRaises(OSError):
            self.gateway.append("beacon/link.txt", b"x")

    def test_path_escape_rejected(self):
        for path in ["../x", "/tmp/x", "beacon/../existing.txt", r"beacon\evil"]:
            with self.assertRaises(NasGatewayError, msg=path):
                self.gateway.read_bytes(path)

    def test_capability_surface_explicitly_has_no_delete_or_command(self):
        caps = self.gateway.capabilities()
        self.assertFalse(caps["delete"])
        self.assertFalse(caps["rename"])
        self.assertFalse(caps["replace"])
        self.assertFalse(caps["truncate"])
        self.assertFalse(caps["arbitrary_command"])
        self.assertFalse(caps["network_transport"])

    def test_versioned_json_is_create_only(self):
        receipt = self.gateway.create_versioned_json("state", {"n": 1})
        self.assertEqual(receipt["operation"], "CREATE_NEW")
        files = [row["name"] for row in self.gateway.list_dir("beacon") if row["name"].startswith("state.")]
        self.assertEqual(len(files), 1)
        with self.assertRaises(FileExistsError):
            self.gateway.create_versioned_json("state", {"n": 1})

    def test_beacon_nas_memory_roundtrip(self):
        beacon = JanusBeaconPredictiveWitness()
        adapter = BeaconNasMemoryAdapter(self.gateway)
        forecast = beacon.forecast(forecast_id="persist-1", context={"face": "CORE", "gate": "P0"}, candidates=["VERIFY", "WAIT"], event_index=1)
        adapter.persist_forecast(forecast)
        outcome = beacon.settle(forecast_id="persist-1", outcome_event_index=2, actual_action="VERIFY", success=True)
        adapter.persist_outcome(outcome)
        state = beacon.export_state()
        adapter.checkpoint(state)
        loaded = adapter.load_latest_state()
        restored = JanusBeaconPredictiveWitness.from_state(loaded)
        self.assertEqual(restored.export_state(), state)
        self.assertIn(b"persist-1", self.gateway.read_bytes("beacon/beacon_forecasts.jsonl"))
        self.assertIn(b"persist-1", self.gateway.read_bytes("beacon/beacon_outcomes.jsonl"))

    def test_gateway_source_has_no_delete_rename_truncate_surface(self):
        path = Path("tools/janus_nas_no_delete_gateway.py")
        tree = ast.parse(path.read_text(encoding="utf-8"))
        forbidden_attrs = {"remove", "unlink", "rmdir", "removedirs", "rename", "renames", "replace", "truncate", "ftruncate", "chmod", "chown", "symlink", "link"}
        seen = {node.attr for node in ast.walk(tree) if isinstance(node, ast.Attribute)}
        self.assertTrue(seen.isdisjoint(forbidden_attrs), sorted(seen & forbidden_attrs))
        forbidden_imports = {"subprocess", "socket", "requests", "httpx", "aiohttp", "paramiko"}
        imported = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module.split(".")[0])
        self.assertTrue(imported.isdisjoint(forbidden_imports), imported)


if __name__ == "__main__":
    unittest.main()
