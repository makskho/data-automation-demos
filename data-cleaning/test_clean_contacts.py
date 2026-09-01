"""Output-level tests: realistic input, boundaries, and failures that must stay closed.

Run:
    python -m unittest discover -s portfolio/data-cleaning -v
"""

import csv
import json
import os
import shutil
import tempfile
import unittest

import clean_contacts as tool

HERE = os.path.dirname(os.path.abspath(__file__))
FIXTURES = os.path.join(HERE, "fixtures")


def read_text(path):
    with open(path, "r", encoding="utf-8") as stream:
        return stream.read()


def read_json(path):
    with open(path, "r", encoding="utf-8") as stream:
        return json.load(stream)


def read_csv(path):
    with open(path, "r", encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream))


class FieldRules(unittest.TestCase):
    def test_text_is_trimmed_and_collapsed(self):
        self.assertEqual(tool.clean_text("  Anna   Petrova "), "Anna Petrova")

    def test_email_is_lowercased(self):
        self.assertEqual(tool.clean_email(" ANNA.Petrova@Example.COM "), "anna.petrova@example.com")

    def test_invalid_email_is_rejected(self):
        with self.assertRaises(tool.RowError):
            tool.clean_email("emilie@")

    def test_phone_keeps_international_prefix_and_drops_formatting(self):
        self.assertEqual(tool.clean_phone("+66 81 234 5678"), "+66812345678")
        self.assertEqual(tool.clean_phone("0066812345679"), "+66812345679")
        self.assertEqual(tool.clean_phone("+1 (415) 555-0142"), "+14155550142")

    def test_short_phone_is_rejected(self):
        with self.assertRaises(tool.RowError):
            tool.clean_phone("12345")

    def test_supported_date_formats_become_iso(self):
        self.assertEqual(tool.clean_date("2026-01-15"), "2026-01-15")
        self.assertEqual(tool.clean_date("15.01.2026"), "2026-01-15")
        self.assertEqual(tool.clean_date("25/12/2026"), "2026-12-25")

    def test_ambiguous_date_is_rejected_not_guessed(self):
        with self.assertRaises(tool.RowError) as caught:
            tool.clean_date("03/04/2026")
        self.assertIn("ambiguous", str(caught.exception))

    def test_impossible_date_is_rejected(self):
        with self.assertRaises(tool.RowError):
            tool.clean_date("2026-02-30")

    def test_amount_separators_and_currency(self):
        self.assertEqual(tool.clean_amount("1 234,56"), "1234.56")
        self.assertEqual(tool.clean_amount("€ 89.90"), "89.90")
        self.assertEqual(tool.clean_amount("1,234.50"), "1234.50")
        self.assertEqual(tool.clean_amount("50"), "50.00")

    def test_non_numeric_and_negative_amounts_are_rejected(self):
        for bad in ("about 40", "-5", ""):
            with self.assertRaises(tool.RowError):
                tool.clean_amount(bad)


class WholeFile(unittest.TestCase):
    def setUp(self):
        self.workdir = tempfile.mkdtemp()
        self.out = os.path.join(self.workdir, "clean.csv")
        self.rejects = os.path.join(self.workdir, "rejects.csv")
        self.report = os.path.join(self.workdir, "report.json")

    def tearDown(self):
        shutil.rmtree(self.workdir, ignore_errors=True)

    def run_tool(self, fixture, *extra):
        return tool.main([
            "--input", os.path.join(FIXTURES, fixture),
            "--output", self.out,
            "--rejects", self.rejects,
            "--report", self.report,
        ] + list(extra))

    def test_realistic_file_splits_into_clean_rows_and_stated_rejects(self):
        self.assertEqual(self.run_tool("contacts_raw.csv"), 0)
        clean = read_csv(self.out)
        rejects = read_csv(self.rejects)
        report = read_json(self.report)

        self.assertEqual(report["rows_read"], 12)
        self.assertEqual(report["rows_written"], len(clean))
        self.assertEqual(report["rows_rejected"], len(rejects))
        self.assertEqual(report["rows_read"], report["rows_written"] + report["rows_rejected"])

        # every surviving row is normalised
        for row in clean:
            self.assertEqual(row["email"], row["email"].lower().strip())
            self.assertEqual(len(row["signup_date"]), 10)
            self.assertEqual(row["amount"], "%.2f" % float(row["amount"]))

        by_id = dict((row["id"], row) for row in clean)
        self.assertEqual(by_id["1"]["name"], "Anna Petrova")
        self.assertEqual(by_id["1"]["email"], "anna.petrova@example.com")
        self.assertEqual(by_id["1"]["phone"], "+66812345678")
        self.assertEqual(by_id["1"]["amount"], "1234.56")
        # a quoted field containing commas survives the round trip
        self.assertEqual(by_id["3"]["name"], "Cole, Jr., Marcus")
        self.assertEqual(by_id["12"]["name"], "Lea Fischer")
        # a non-ASCII name survives unchanged into the rejects file
        self.assertIn("Émilie Dubois", [row["name"] for row in read_csv(self.rejects)])

    def test_every_reject_names_its_row_and_reason(self):
        self.run_tool("contacts_raw.csv")
        rejects = read_csv(self.rejects)
        reasons = dict((row["id"], row["reason"]) for row in rejects)

        self.assertIn("duplicate", reasons["4"])       # same email as row 2, different case
        self.assertIn("email", reasons["5"])           # emilie@
        self.assertIn("phone", reasons["6"])           # 12345
        self.assertIn("ambiguous", reasons["7"])       # 03/04/2026
        self.assertIn("signup_date", reasons["8"])     # 2026-02-30
        self.assertIn("amount", reasons["9"])          # -5
        self.assertIn("amount", reasons["10"])         # about 40
        self.assertIn("amount", reasons["11"])         # empty

        for row in rejects:
            self.assertTrue(int(row["source_row"]) >= 2)
            self.assertTrue(row["reason"])

    def test_duplicate_keeps_the_first_occurrence(self):
        self.run_tool("contacts_raw.csv")
        clean = read_csv(self.out)
        self.assertIn("anna.petrova@example.com", [row["email"] for row in clean])
        self.assertEqual(len([r for r in clean if r["email"] == "anna.petrova@example.com"]), 1)
        self.assertEqual([r for r in clean if r["email"] == "anna.petrova@example.com"][0]["id"], "1")

    def test_byte_order_mark_does_not_break_the_header(self):
        self.assertEqual(self.run_tool("contacts_bom.csv"), 0)
        self.assertEqual(len(read_csv(self.out)), 2)

    def test_header_only_file_produces_an_empty_but_valid_output(self):
        self.assertEqual(self.run_tool("header_only.csv"), 0)
        self.assertEqual(read_csv(self.out), [])
        report = read_json(self.report)
        self.assertEqual(report["rows_read"], 0)

    def test_missing_required_column_fails_closed(self):
        with self.assertRaises(SystemExit) as caught:
            self.run_tool("missing_column.csv")
        self.assertIn("signup_date", str(caught.exception))
        self.assertFalse(os.path.exists(self.out))

    def test_empty_file_fails_closed(self):
        with self.assertRaises(SystemExit):
            self.run_tool("empty.csv")
        self.assertFalse(os.path.exists(self.out))

    def test_existing_output_is_not_overwritten_without_force(self):
        self.run_tool("contacts_raw.csv")
        before = read_text(self.out)
        with self.assertRaises(SystemExit) as caught:
            self.run_tool("contacts_raw.csv")
        self.assertIn("refusing to overwrite", str(caught.exception))
        self.assertEqual(read_text(self.out), before)
        self.assertEqual(self.run_tool("contacts_raw.csv", "--force"), 0)

    def test_missing_output_directory_fails_closed(self):
        missing = os.path.join(self.workdir, "no-such-dir", "clean.csv")
        with self.assertRaises(SystemExit) as caught:
            tool.main([
                "--input", os.path.join(FIXTURES, "contacts_raw.csv"),
                "--output", missing,
                "--rejects", self.rejects,
                "--report", self.report,
            ])
        self.assertIn("output directory does not exist", str(caught.exception))
        self.assertFalse(os.path.exists(self.rejects))

    def test_dedup_key_can_be_switched(self):
        self.run_tool("contacts_raw.csv", "--dedup-key", "id")
        report = read_json(self.report)
        self.assertEqual(report["dedup_key"], "id")
        # with id as the key the case-different email is no longer a duplicate
        self.assertIn("4", [row["id"] for row in read_csv(self.out)])


if __name__ == "__main__":
    unittest.main()
