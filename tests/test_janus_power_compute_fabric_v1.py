# -*- coding: utf-8 -*-
from __future__ import annotations

import asyncio
import unittest

from tools.janus_power_compute_fabric import (
    ComputeTier,
    JanusPowerCore,
    TaskStatus,
)


class AsyncMemory:
    def __init__(self) -> None:
        self.events = []

    async def remember(self, source, content):
        self.events.append((source, content))


class Kernel:
    def __init__(self) -> None:
        self.memory = AsyncMemory()


class JanusPowerFabricTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.cores: list[JanusPowerCore] = []

    async def asyncTearDown(self) -> None:
        for core in reversed(self.cores):
            await core.shutdown()

    def make_core(self, **kwargs) -> JanusPowerCore:
        core = JanusPowerCore(Kernel(), **kwargs)
        self.cores.append(core)
        return core

    async def test_initial_capabilities_are_truthful_and_local_only(self) -> None:
        core = self.make_core()
        self.assertEqual(
            [tier.name for tier in core.available_tiers],
            ["LOCAL_CPU", "QUANTUM_SIM", "HYBRID"],
        )

    async def test_matrix_multiply_returns_real_result_and_metrics(self) -> None:
        core = self.make_core()
        await core.start(worker_count=1)
        task_id = await core.compute(
            {
                "type": "matrix_operations",
                "operation": "multiply",
                "data": {
                    "A": [[1, 2], [3, 4]],
                    "B": [[5, 6], [7, 8]],
                },
            }
        )
        response = await core.get_result(task_id, wait=True, timeout=2)
        self.assertEqual(response["result"], [[19.0, 22.0], [43.0, 50.0]])
        task = response["task"]
        self.assertEqual(task["status"], "completed")
        self.assertEqual(task["tier"], "LOCAL_CPU")
        self.assertGreaterEqual(task["metrics"]["execution_time_seconds"], 0.0)
        self.assertEqual(len(task["metrics"]["result_sha256"]), 64)

    async def test_solve_operation_is_implemented_not_silent_addition(self) -> None:
        core = self.make_core()
        await core.start(worker_count=1)
        task_id = await core.compute(
            {
                "type": "matrix_operations",
                "operation": "solve",
                "data": {"A": [[2, 1], [1, 3]], "B": [5, 7]},
            }
        )
        response = await core.get_result(task_id, wait=True, timeout=2)
        self.assertAlmostEqual(response["result"][0], 1.6, places=9)
        self.assertAlmostEqual(response["result"][1], 1.8, places=9)

    async def test_eigen_is_not_faked_without_registered_numerical_executor(self) -> None:
        core = self.make_core()
        await core.start(worker_count=1)
        task_id = await core.compute(
            {
                "type": "matrix_operations",
                "operation": "eigen",
                "data": {"A": [[1, 0], [0, 2]]},
            }
        )
        response = await core.get_result(task_id, wait=True, timeout=2)
        self.assertEqual(response["task"]["status"], "failed")
        self.assertIn("EIGEN_REQUIRES_REGISTERED_NUMERICAL_EXECUTOR", response["task"]["error"])

    async def test_cnot_is_real_and_bell_state_is_normalized(self) -> None:
        core = self.make_core()
        await core.start(worker_count=1)
        task_id = await core.compute(
            {
                "type": "quantum_simulation",
                "qubits": 2,
                "circuit": [
                    {"gate": "H", "target": 0},
                    {"gate": "CNOT", "control": 0, "target": 1},
                ],
                "seed": 7,
            }
        )
        response = await core.get_result(task_id, wait=True, timeout=2)
        result = response["result"]
        self.assertAlmostEqual(result["probabilities"][0], 0.5, places=9)
        self.assertAlmostEqual(result["probabilities"][1], 0.0, places=9)
        self.assertAlmostEqual(result["probabilities"][2], 0.0, places=9)
        self.assertAlmostEqual(result["probabilities"][3], 0.5, places=9)
        self.assertAlmostEqual(sum(result["probabilities"]), 1.0, places=9)
        self.assertFalse(result["quantum_hardware"])
        self.assertFalse(result["quantum_speedup_claimed"])
        self.assertIn(result["measurement"], {"00", "11"})

    async def test_cnot_requires_explicit_valid_control(self) -> None:
        core = self.make_core()
        await core.start(worker_count=1)
        task_id = await core.compute(
            {
                "type": "quantum_simulation",
                "qubits": 2,
                "circuit": [{"gate": "CNOT", "target": 1}],
            }
        )
        response = await core.get_result(task_id, wait=True, timeout=2)
        self.assertEqual(response["task"]["status"], "failed")
        self.assertIn("CNOT control required", response["task"]["error"])

    async def test_priority_queue_processes_high_before_preexisting_low(self) -> None:
        core = self.make_core()
        observed = []

        async def echo(request):
            observed.append(request.blueprint["label"])
            return {"label": request.blueprint["label"]}

        core.register_executor(
            name="priority-test",
            tier=ComputeTier.LOCAL_GPU,
            capabilities={"echo"},
            handler=echo,
            external_effect=False,
            cancellation_note="COOPERATIVE_ASYNC",
        )
        low = await core.compute({"type": "echo", "label": "low"}, priority="low")
        high = await core.compute({"type": "echo", "label": "high"}, priority="high")
        await core.start(worker_count=1)
        await core.get_result(low, wait=True, timeout=2)
        await core.get_result(high, wait=True, timeout=2)
        self.assertEqual(observed, ["high", "low"])

    async def test_wait_true_tracks_running_task_until_terminal(self) -> None:
        core = self.make_core()
        entered = asyncio.Event()

        async def slow(request):
            entered.set()
            await asyncio.sleep(0.05)
            return {"ok": True}

        core.register_executor(
            name="slow-local",
            tier=ComputeTier.LOCAL_GPU,
            capabilities={"slow"},
            handler=slow,
            external_effect=False,
        )
        await core.start(worker_count=1)
        task_id = await core.compute({"type": "slow"})
        await asyncio.wait_for(entered.wait(), timeout=1)
        self.assertEqual(core.tasks[task_id].status, TaskStatus.RUNNING)
        response = await core.get_result(task_id, wait=True, timeout=1)
        self.assertEqual(response["task"]["status"], "completed")
        self.assertTrue(response["result"]["ok"])

    async def test_queued_cancel_is_terminal_and_never_executes(self) -> None:
        core = self.make_core()
        observed = []

        async def echo(request):
            observed.append(request.task_id)
            return {"ok": True}

        core.register_executor(
            name="cancel-test",
            tier=ComputeTier.LOCAL_GPU,
            capabilities={"echo"},
            handler=echo,
            external_effect=False,
        )
        task_id = await core.compute({"type": "echo"})
        self.assertTrue(await core.cancel(task_id))
        await core.start(worker_count=1)
        response = await core.get_result(task_id, wait=True, timeout=1)
        self.assertEqual(response["task"]["status"], "cancelled")
        self.assertEqual(observed, [])

    async def test_timeout_is_real_terminal_state(self) -> None:
        core = self.make_core(max_task_seconds=0.05)

        async def too_slow(request):
            await asyncio.sleep(1)
            return {"should": "not complete"}

        core.register_executor(
            name="timeout-test",
            tier=ComputeTier.LOCAL_GPU,
            capabilities={"slow"},
            handler=too_slow,
            external_effect=False,
        )
        await core.start(worker_count=1)
        task_id = await core.compute(
            {"type": "slow", "constraints": {"max_time": 0.02}}
        )
        response = await core.get_result(task_id, wait=True, timeout=1)
        self.assertEqual(response["task"]["status"], "timeout")
        self.assertEqual(response["task"]["error"], "TASK_TIMEOUT")

    async def test_cloud_tier_exists_only_after_real_executor_registration(self) -> None:
        core = self.make_core()
        self.assertNotIn(ComputeTier.CLOUD, core.available_tiers)

        async def cloud_echo(request):
            return {"remote": True}

        core.register_executor(
            name="test-cloud",
            tier=ComputeTier.CLOUD,
            capabilities={"cloud_echo"},
            handler=cloud_echo,
            external_effect=True,
            cancellation_note="ASYNC_REMOTE_NO_ROLLBACK_CLAIM",
        )
        self.assertIn(ComputeTier.CLOUD, core.available_tiers)
        await core.start(worker_count=1)

        denied = await core.compute(
            {"type": "cloud_echo", "preferred_tier": "CLOUD"}
        )
        denied_response = await core.get_result(denied, wait=True, timeout=1)
        self.assertEqual(denied_response["task"]["status"], "failed")
        self.assertIn("EXTERNAL_COMPUTE_REQUIRES_REQUEST_ADMISSION", denied_response["task"]["error"])

        admitted = await core.compute(
            {
                "type": "cloud_echo",
                "preferred_tier": "CLOUD",
                "effects": {"allow_external_compute": True},
            }
        )
        admitted_response = await core.get_result(admitted, wait=True, timeout=1)
        self.assertEqual(admitted_response["task"]["status"], "completed")
        self.assertTrue(admitted_response["result"]["remote"])

    async def test_effectful_sync_executor_is_rejected_at_registration(self) -> None:
        core = self.make_core()

        def sync_remote(request):
            return {"remote": True}

        with self.assertRaises(TypeError):
            core.register_executor(
                name="unsafe-sync-cloud",
                tier=ComputeTier.CLOUD,
                capabilities={"cloud_echo"},
                handler=sync_remote,
                external_effect=True,
            )

    async def test_predict_future_does_not_train_on_random_fake_labels(self) -> None:
        core = self.make_core()
        await core.start(worker_count=1)
        response = await core.summon_power(
            {"spell": "predict_future", "parameters": {"question": "tomorrow?"}}
        )
        self.assertFalse(response["success"])
        self.assertEqual(response["task"]["status"], "failed")
        self.assertIn("NO_EXECUTOR_FOR_predict_future", response["task"]["error"])

    async def test_create_universe_is_not_fake_local_gravity_loop(self) -> None:
        core = self.make_core()
        await core.start(worker_count=1)
        response = await core.summon_power(
            {"spell": "create_universe", "parameters": {"size": 1000}}
        )
        self.assertFalse(response["success"])
        self.assertIn("NO_EXECUTOR_FOR_physics_simulation", response["task"]["error"])

    async def test_async_memory_logging_is_awaited(self) -> None:
        kernel = Kernel()
        core = JanusPowerCore(kernel)
        self.cores.append(core)
        await core.start(worker_count=1)
        task_id = await core.compute(
            {
                "type": "matrix_operations",
                "operation": "add",
                "data": {"A": [[1]], "B": [[2]]},
            }
        )
        await core.get_result(task_id, wait=True, timeout=1)
        event_names = [event[1]["event"] for event in kernel.memory.events]
        self.assertEqual(event_names, ["COMPUTE_QUEUED", "COMPUTE_TERMINAL"])

    async def test_equal_blueprints_have_equal_provenance_digest(self) -> None:
        core = self.make_core()
        blueprint = {
            "type": "matrix_operations",
            "operation": "add",
            "data": {"A": [[1]], "B": [[2]]},
        }
        first = await core.compute(blueprint)
        second = await core.compute(
            {"data": {"B": [[2]], "A": [[1]]}, "operation": "add", "type": "matrix_operations"}
        )
        self.assertEqual(
            core.tasks[first].blueprint_sha256,
            core.tasks[second].blueprint_sha256,
        )


if __name__ == "__main__":
    unittest.main()
