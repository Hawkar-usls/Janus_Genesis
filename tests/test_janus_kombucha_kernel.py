"""Offline failure-injection tests for the JANUS Kombucha microkernel."""
import asyncio
import unittest
from tools import janus_kombucha_kernel as k


def ok(module):
    return {"module": module, "reachable": len(k.GROUPS[module]), "failures": 0}


class KombuchaTests(unittest.IsolatedAsyncioTestCase):
    async def test_two_bounded_cycles_all_organs(self):
        async def fixture(module):
            return ok(module)
        result = await k.circulate(fixture=fixture)
        self.assertEqual(result["gate"], "PASS_OBSERVATION_ONLY")
        self.assertEqual(len(result["journal"]), 12)
        self.assertFalse(result["claim_of_full_autonomy"])
        self.assertEqual(result["cross_repository_dispatches"], 0)
        self.assertFalse(result["recursive_self_dispatch"])

    async def test_optional_organ_failure_does_not_stop_others(self):
        async def fixture(module):
            if module == "bio":
                raise RuntimeError("simulated crash")
            return ok(module)
        result = await k.circulate(fixture=fixture)
        self.assertEqual(result["gate"], "HOLD")
        self.assertEqual(result["module_states"]["bio"], "ISOLATED_FAILURE")
        self.assertEqual(result["module_states"]["brain"], "OBSERVED")
        self.assertEqual(len(result["journal"]), 12)

    async def test_hung_critical_organ_is_isolated(self):
        async def fixture(module):
            if module == "sensing":
                await asyncio.sleep(.2)
            return ok(module)
        result = await k.circulate(fixture=fixture, seconds=.01)
        self.assertEqual(result["gate"], "HOLD")
        self.assertEqual(result["module_states"]["brain"], "OBSERVED")

    async def test_unknown_modules_and_unbounded_cycles_denied(self):
        for cycles in (0, 3, -1):
            with self.assertRaises(ValueError):
                await k.circulate(cycles=cycles)
        with self.assertRaises(ValueError):
            await k.circulate(modules=("python-from-the-internet",))

    async def test_critical_modules_required_for_observation_gate(self):
        async def fixture(module):
            return ok(module)
        result = await k.circulate(modules=("bio",), fixture=fixture)
        self.assertEqual(result["gate"], "HOLD")

    async def test_private_repositories_are_not_public_probe_targets(self):
        all_repos = {repo for values in k.GROUPS.values() for repo in values}
        self.assertFalse({"SkinGPT", "janus-io", "JanusMMORPG"} & all_repos)
        with self.assertRaises(ValueError):
            k.read_public_run("SkinGPT")


if __name__ == "__main__":
    unittest.main()
