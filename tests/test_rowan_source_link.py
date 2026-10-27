"""Genesis authoritative Rowan link is reference-only, never an action."""
import json
import pathlib
import unittest

class RowanSourceLinkTests(unittest.TestCase):
    def test_frozen_read_only_capability(self):
        p=pathlib.Path(__file__).resolve().parents[1]/'.janus'/'ROWAN_RESEARCH_SOURCE_LINK.json'
        obj=json.loads(p.read_text(encoding='utf-8'))
        self.assertEqual(obj['schema'],'janus.genesis.rowan_evidence_source_link.v1')
        self.assertEqual(obj['mode'],'READ_ONLY_CANONICAL_META_REGISTRY_SOURCE')
        self.assertEqual(obj['observation']['currentVerifiedCompletedMutants'],8)
        self.assertEqual(obj['observation']['runAtContractCreation'],40520611650)
        self.assertTrue(obj['links']['canonical'].endswith('/data/rowan/CANONICAL_STATE.json'))
        self.assertTrue(all(val is False for val in obj['authority'].values()))
        self.assertEqual(obj['status'],'REFERENCE_AVAILABLE_NOT_EXECUTABLE_AGENT_OR_AUTONOMY_PERMIT')
        self.assertIn('source hashes',obj['observation']['coordinationCheck'])
if __name__ == '__main__':
    unittest.main()
