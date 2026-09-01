"""Output-level tests: a clean batch, a batch that breaks every rule, and the gates.

Run:
    python -m unittest discover -s portfolio/annotation-qa -v
"""

import json
import os
import shutil
import tempfile
import unittest

import check_annotations as tool

HERE = os.path.dirname(os.path.abspath(__file__))
FIXTURES = os.path.join(HERE, "fixtures")


def fixture(name):
    return os.path.join(FIXTURES, name)


def read_json(path):
    with open(path, "r", encoding="utf-8") as stream:
        return json.load(stream)


def read_jsonl(path):
    with open(path, "r", encoding="utf-8") as stream:
        return [json.loads(line) for line in stream if line.strip()]


class Kappa(unittest.TestCase):
    def test_total_agreement_is_one(self):
        self.assertEqual(tool.cohens_kappa([("a", "a"), ("b", "b"), ("a", "a"), ("b", "b")]), 1.0)

    def test_chance_level_agreement_is_about_zero(self):
        pairs = [("a", "a"), ("a", "b"), ("b", "a"), ("b", "b")]
        self.assertEqual(tool.cohens_kappa(pairs), 0.0)

    def test_systematic_disagreement_is_negative(self):
        self.assertLess(tool.cohens_kappa([("a", "b"), ("b", "a"), ("a", "b"), ("b", "a")]), 0)

    def test_single_label_everywhere_is_undefined_not_perfect(self):
        # every item carries one label, so chance agreement is already total
        self.assertIsNone(tool.cohens_kappa([("a", "a"), ("a", "a")]))

    def test_no_shared_items_is_undefined(self):
        self.assertIsNone(tool.cohens_kappa([]))


class Validation(unittest.TestCase):
    def setUp(self):
        self.schema = tool.load_schema(fixture("schema.json"))

    def test_valid_item_is_normalised(self):
        item = tool.validate_item({
            "item_id": 7, "text": "hello", "label": "spam", "annotator": "ann_a", "confidence": 0.9
        }, self.schema)
        self.assertEqual(item["item_id"], "7")
        self.assertEqual(item["confidence"], 0.9)

    def test_label_outside_schema_is_rejected(self):
        with self.assertRaises(tool.ItemError):
            tool.validate_item({"item_id": "1", "text": "t", "label": "refund", "annotator": "a"}, self.schema)

    def test_low_and_impossible_confidence_are_rejected(self):
        for confidence in (0.2, 1.6, -0.1, "high", True):
            with self.assertRaises(tool.ItemError):
                tool.validate_item({
                    "item_id": "1", "text": "t", "label": "spam", "annotator": "a", "confidence": confidence
                }, self.schema)

    def test_span_must_stay_inside_the_text(self):
        with self.assertRaises(tool.ItemError):
            tool.validate_item({
                "item_id": "1", "text": "short", "label": "spam", "annotator": "a", "span": [0, 99]
            }, self.schema)

    def test_span_must_be_a_forward_range(self):
        with self.assertRaises(tool.ItemError):
            tool.validate_item({
                "item_id": "1", "text": "abcdef", "label": "spam", "annotator": "a", "span": [3, 1]
            }, self.schema)

    def test_empty_schema_is_refused(self):
        with self.assertRaises(SystemExit):
            tool.load_schema(fixture("schema_empty.json"))


class WholeRun(unittest.TestCase):
    def setUp(self):
        self.workdir = tempfile.mkdtemp()
        self.report = os.path.join(self.workdir, "report.json")
        self.rejects = os.path.join(self.workdir, "rejects.jsonl")

    def tearDown(self):
        shutil.rmtree(self.workdir, ignore_errors=True)

    def run_tool(self, *extra):
        return tool.main(["--schema", fixture("schema.json"),
                          "--report", self.report, "--rejects", self.rejects] + list(extra))

    def test_two_clean_passes_produce_agreement_and_gold_scores(self):
        code = self.run_tool("--annotations", fixture("pass_a.jsonl"), fixture("pass_b.jsonl"),
                             "--gold", fixture("gold.jsonl"))
        self.assertEqual(code, 0)
        report = read_json(self.report)

        self.assertEqual(report["annotations_accepted"], 20)
        self.assertEqual(report["annotations_rejected"], 0)
        self.assertEqual(report["annotators"], {"ann_a": 10, "ann_b": 10})

        pair = report["agreement"][0]
        self.assertEqual(pair["shared_items"], 10)
        self.assertEqual(pair["exact_match"], 0.8)
        self.assertAlmostEqual(pair["cohens_kappa"], 0.7436, places=3)

        # kappa is lower than raw agreement, which is the point of using it
        self.assertLess(pair["cohens_kappa"], pair["exact_match"])

        self.assertEqual(len(report["disagreements"]), 2)
        self.assertEqual({row["item_id"] for row in report["disagreements"]}, {"m-006", "m-008"})

        self.assertEqual(report["against_gold"]["ann_a"]["accuracy"], 1.0)
        self.assertEqual(report["against_gold"]["ann_b"]["accuracy"], 0.8)
        billing = report["against_gold"]["ann_b"]["per_label"]["billing"]
        self.assertEqual(billing["gold_items"], 3)  # gold marks m-001, m-006 and m-010 as billing
        self.assertLess(billing["precision"], 1.0)  # ann_b called m-008 billing, gold says cancellation

    def test_every_broken_row_is_rejected_with_its_line_and_reason(self):
        self.run_tool("--annotations", fixture("pass_broken.jsonl"))
        rejects = read_jsonl(self.rejects)
        reasons = {row["line"]: row["reason"] for row in rejects}

        self.assertEqual(len(rejects), 8)
        self.assertIn("not in the schema", reasons[1])
        self.assertIn("below the schema minimum", reasons[2])
        self.assertIn("outside 0.0-1.0", reasons[3])
        self.assertIn("missing required field", reasons[4])
        self.assertIn("past the end of the text", reasons[5])
        self.assertIn("not a positive range", reasons[6])
        self.assertIn("invalid JSON", reasons[7])
        self.assertIn("twice", reasons[9])

        report = read_json(self.report)
        self.assertEqual(report["annotations_read"], 9)
        self.assertEqual(report["annotations_accepted"], 1)

    def test_one_bad_row_does_not_discard_the_good_ones(self):
        self.run_tool("--annotations", fixture("pass_broken.jsonl"), fixture("pass_a.jsonl"))
        report = read_json(self.report)
        self.assertEqual(report["annotators"]["ann_a"], 10)

    def test_min_kappa_gate_fails_the_run(self):
        code = self.run_tool("--annotations", fixture("pass_a.jsonl"), fixture("pass_b.jsonl"),
                             "--min-kappa", "0.9")
        self.assertEqual(code, 2)

    def test_min_kappa_gate_passes_when_met(self):
        code = self.run_tool("--annotations", fixture("pass_a.jsonl"), fixture("pass_b.jsonl"),
                             "--min-kappa", "0.7")
        self.assertEqual(code, 0)

    def test_invalid_gold_is_refused_rather_than_scored(self):
        with self.assertRaises(SystemExit) as caught:
            self.run_tool("--annotations", fixture("pass_a.jsonl"), "--gold", fixture("gold_invalid.jsonl"))
        self.assertIn("gold file is not valid", str(caught.exception))

    def test_empty_annotation_file_fails_closed(self):
        with self.assertRaises(SystemExit):
            self.run_tool("--annotations", fixture("empty.jsonl"))
        self.assertFalse(os.path.exists(self.report))

    def test_existing_report_is_not_overwritten_without_force(self):
        self.run_tool("--annotations", fixture("pass_a.jsonl"))
        with self.assertRaises(SystemExit) as caught:
            self.run_tool("--annotations", fixture("pass_a.jsonl"))
        self.assertIn("refusing to overwrite", str(caught.exception))
        self.assertEqual(self.run_tool("--annotations", fixture("pass_a.jsonl"), "--force"), 0)

    def test_missing_output_directory_fails_closed(self):
        missing = os.path.join(self.workdir, "no-such-dir", "report.json")
        with self.assertRaises(SystemExit) as caught:
            tool.main(["--schema", fixture("schema.json"), "--annotations", fixture("pass_a.jsonl"),
                       "--report", missing, "--rejects", self.rejects])
        self.assertIn("output directory does not exist", str(caught.exception))


if __name__ == "__main__":
    unittest.main()
