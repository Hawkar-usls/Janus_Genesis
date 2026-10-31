"""Archived Genesis JSON syntax and no-credential guard."""
import json
from pathlib import Path
import re
import unittest
ROOT=Path(__file__).resolve().parents[1]/"archaeology"/"nas_genesis_20261031"
NAMES=("janus_rpg_schema.json","janus_history.json","MANIFEST.json")
class NASGenesisHistoricalArtifacts(unittest.TestCase):
    def test_valid_no_private_keys(self):
        for name in NAMES:
            with self.subTest(file=name):
                text=(ROOT/name).read_text(encoding="utf-8")
                value=json.loads(text)
                self.assertIsInstance(value,dict)
                self.assertNotRegex(text,r"-----BEGIN .*PRIVATE KEY-----")
                self.assertNotRegex(text,r"github_pat_[a-zA-Z0-9_]{15}")
                self.assertNotRegex(text,r"ghp_[A-Za-z0-9]{15}")
                self.assertNotRegex(text,r"192[.]168[.][0-9]+[.][0-9]+")
    def test_only_curated_archives(self):
        self.assertEqual({p.name for p in ROOT.glob("*.json")},set(NAMES))
if __name__=="__main__":
    unittest.main()
