"""ESSENCE v1.2 independent-from-candidate cross-repo frozen corpus checks."""
from __future__ import annotations

import importlib
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"tools"))
import essence_v12_real_bench as v12


class GenuineAlgorithmsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.corpus=v12.load_corpus()
        cls.tok=v12.verified_byte_tokenizer()
        cls.bank=v12.load_gene_bank()

    def test_frozen_corpus_is_a_hash_bound_separate_repo(self):
        self.assertEqual(v12.blob(v12.HOLDOUT.read_bytes()),v12.CORPUS_BLOB)
        self.assertEqual(v12.FREEZE_COMMIT,"5fcd50ad7fc26f9e26aef6ff25ebcb42ef7c8f28")
        self.assertFalse(self.corpus["blinded"])
        self.assertFalse(self.corpus["externally_independently_attested"])

    def test_real_model_source_is_byte_identical_git_blob(self):
        self.assertEqual(v12.blob(v12.MODEL.read_bytes()),v12.SRC_BLOB)
        self.assertEqual(self.tok.vocab_size,258)
        self.assertEqual((self.tok.BOS,self.tok.EOS),(256,257))

    def test_modified_source_denied(self):
        with tempfile.TemporaryDirectory() as tmp:
            file=Path(tmp)/"model.py.txt"
            file.write_bytes(v12.MODEL.read_bytes()+b"\n# altered\n")
            with self.assertRaisesRegex(ValueError,"HASH_MISMATCH"):
                v12.bounded_source(file,v12.SRC_BLOB)

    def test_untrusted_symlink_denied(self):
        with tempfile.TemporaryDirectory() as tmp:
            file=Path(tmp)/"linked.py.txt"
            try:
                file.symlink_to(v12.MODEL)
            except (OSError,NotImplementedError):
                self.skipTest("no symlink permission")
            with self.assertRaisesRegex(ValueError,"REGULAR_FILE"):
                v12.bounded_source(file,v12.SRC_BLOB)

    def test_real_model_tokenizer_roundtrip(self):
        for text in self.corpus["text_cases"]:
            with self.subTest(text=text[:20]):
                self.assertEqual(self.tok.decode(self.tok.encode(text,bos=True,eos=True)),text)

    def test_candidate_decodes_full_frozen_holdout(self):
        ids=[self.tok.encode(t,bos=True,eos=True) for t in self.corpus["text_cases"]]
        self.assertEqual(
            [self.tok.decode(x) for x in ids],
            [v12.fast_decoder(x) for x in ids])

    def test_reference_normalizer_from_real_microkernel(self):
        for label in self.corpus["gene_cases"]:
            with self.subTest(label=label):
                self.assertEqual(
                    self.bank.normalized_model(label),
                    v12.fast_normalize(label,self.bank.MODEL_GENE))

    def test_reference_normalizer_aliases_and_limits(self):
        for label in ("MicroGPT(3).py","CatGPT.py","HoloGPT_TEST2(1)","JGPT1(42).py","Nonexisting"):
            self.assertEqual(self.bank.normalized_model(label),
                             v12.fast_normalize(label,self.bank.MODEL_GENE))
        self.assertIsNone(v12.fast_normalize("a"*121,self.bank.MODEL_GENE))

    def test_negative_tokenizer_mutation_causes_rollback(self):
        ids=[self.tok.encode(x,bos=True,eos=True) for x in self.corpus["text_cases"]]
        r=v12.rollback_dry_run(
            self.tok.decode,
            lambda a:bytes(t for t in a if 0<=t<256 and t!=32).decode("utf-8","replace"),
            ids)
        self.assertTrue(r["rollback_verified"])
        self.assertGreater(r["counterexample_count"],0)
        self.assertEqual(r["baseline_output_sha256"],r["recovered_output_sha256"])
        self.assertFalse(r["production_weights_or_modules_changed"])

    def test_negative_gene_mutation_causes_rollback(self):
        labels=self.corpus["gene_cases"]
        r=v12.rollback_dry_run(
            self.bank.normalized_model,
            lambda s: None if s=="MicroGPT" else v12.fast_normalize(s,self.bank.MODEL_GENE),
            labels)
        self.assertTrue(r["rollback_verified"])
        self.assertGreater(r["counterexample_count"],0)

    @staticmethod
    def fake_perf(ns,mem):
        return {"median_ns_per_call":ns,
                "median_tracemalloc_python_peak_bytes":mem}

    def test_semantic_mismatch_holds(self):
        r=v12.judge(["yes"],["no"],self.fake_perf(100,500),self.fake_perf(20,200))
        self.assertEqual(r["gate"],"HOLD_SEMANTIC_REGRESSION")

    def test_memory_regression_overrules_speed(self):
        r=v12.judge(["same"],["same"],self.fake_perf(100,400),self.fake_perf(50,600))
        self.assertEqual(r["gate"],"HOLD_PYTHON_MEMORY_REGRESSION")

    def test_latency_regression_holds(self):
        r=v12.judge(["same"],["same"],self.fake_perf(100,1000),self.fake_perf(130,950))
        self.assertEqual(r["gate"],"HOLD_TIME_REGRESSION")

    def test_speed_wins_are_still_research_only(self):
        r=v12.judge(["same"],["same"],self.fake_perf(150,1000),self.fake_perf(100,900))
        self.assertEqual(r["gate"],"RESEARCH_CANDIDATE_PENDING_INDEPENDENT_BLIND_REPLICATION")

    def test_small_speed_change_is_not_promoted(self):
        r=v12.judge(["same"],["same"],self.fake_perf(100,1000),self.fake_perf(99,900))
        self.assertEqual(r["gate"],"HOLD_NO_REPRODUCIBLE_SPEED_GAIN")

    def test_length_mismatch_denied(self):
        with self.assertRaisesRegex(ValueError,"OUTPUT_COUNT_CHANGED"):
            v12.judge(["a"],[],self.fake_perf(100,100),self.fake_perf(100,100))

    def test_full_stdlib_replay_keeps_existing_capabilities_disabled(self):
        receipt=v12.run(skip_torch=True)
        self.assertEqual(receipt["schema"],v12.SCHEMA)
        self.assertFalse(receipt["holdout_blinded"])
        self.assertFalse(receipt["automatic_promotion"])
        self.assertFalse(receipt["runtime_execution_authority"])
        self.assertFalse(receipt["model_weights_updated"])
        self.assertEqual(receipt["transformer_forward"]["status"],"NOT_RUN_TORCH_OPTIONAL_CI")
        self.assertEqual(receipt["byte_tokenizer"]["decision"]["counterexample_count"],0)
        self.assertEqual(receipt["essence_gene_bank"]["decision"]["counterexample_count"],0)
        self.assertEqual(receipt["receipt_sha256"],
                         v12.kernel.digest({k:v for k,v in receipt.items() if k!="receipt_sha256"}))


if __name__=="__main__":
    unittest.main()
