"""Clean and validate a contact export: one CSV in, one CSV out, nothing guessed.

The tool normalises the columns it is told about, rejects every row it cannot
prove correct, and writes a machine-readable report. It never drops a row
silently and never leaves a half-written output file.

Run:
    python clean_contacts.py --input raw.csv --output clean.csv
        --rejects rejects.csv --report report.json
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import re
import sys
import tempfile
from collections import Counter
from datetime import date

REQUIRED_COLUMNS = ("id", "name", "email", "phone", "signup_date", "amount")

EMAIL_RE = re.compile(r"^[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(\.[A-Za-z0-9-]+)+$")
SPACES_RE = re.compile(r"\s+")
NON_DIGIT_RE = re.compile(r"[^\d]")
ISO_DATE_RE = re.compile(r"^(\d{4})-(\d{2})-(\d{2})$")
DOTTED_DATE_RE = re.compile(r"^(\d{2})\.(\d{2})\.(\d{4})$")
SLASH_DATE_RE = re.compile(r"^(\d{1,2})/(\d{1,2})/(\d{4})$")
AMOUNT_ALLOWED_RE = re.compile("^[\\d.,\\s ]+$")
CURRENCY_CHARS = "$€£₽ "


class RowError(ValueError):
    """One row failed validation for one stated reason."""


def clean_text(value):
    return SPACES_RE.sub(" ", (value or "").strip())


def clean_email(value):
    email = clean_text(value).lower().replace(" ", "")
    if not email:
        raise RowError("email is empty")
    if not EMAIL_RE.match(email):
        raise RowError("email is not a valid address: %r" % email)
    return email


def clean_phone(value):
    raw = clean_text(value)
    if not raw:
        raise RowError("phone is empty")
    international = raw.startswith("+") or raw.startswith("00")
    digits = NON_DIGIT_RE.sub("", raw)
    if digits.startswith("00"):
        digits = digits[2:]
    if not 8 <= len(digits) <= 15:
        raise RowError("phone has %d digits, expected 8-15: %r" % (len(digits), raw))
    return ("+" if international else "") + digits


def clean_date(value):
    """Return an ISO date. An ambiguous day/month order is rejected, not guessed."""
    raw = clean_text(value)
    if not raw:
        raise RowError("signup_date is empty")

    match = ISO_DATE_RE.match(raw)
    if match:
        year, month, day = (int(part) for part in match.groups())
    else:
        match = DOTTED_DATE_RE.match(raw)
        if match:
            day, month, year = (int(part) for part in match.groups())
        else:
            match = SLASH_DATE_RE.match(raw)
            if not match:
                raise RowError("signup_date has an unsupported format: %r" % raw)
            first, second, year = (int(part) for part in match.groups())
            if first <= 12 and second <= 12 and first != second:
                raise RowError(
                    "signup_date %r is ambiguous: %d and %d can both be the month"
                    % (raw, first, second)
                )
            day, month = (first, second) if second <= 12 else (second, first)

    try:
        return date(year, month, day).isoformat()
    except ValueError as exc:
        raise RowError("signup_date is not a real date: %r (%s)" % (raw, exc)) from exc


def clean_amount(value):
    raw = clean_text(value)
    if not raw:
        raise RowError("amount is empty")
    body = raw.strip(CURRENCY_CHARS)
    if not AMOUNT_ALLOWED_RE.match(body):
        raise RowError("amount contains unexpected characters: %r" % raw)
    body = body.replace(" ", "").replace(" ", "")
    if "," in body and "." in body:
        if body.rindex(".") > body.rindex(","):
            body = body.replace(",", "")
        else:
            body = body.replace(".", "").replace(",", ".")
    elif body.count(",") == 1 and len(body.split(",")[1]) != 3:
        body = body.replace(",", ".")
    else:
        body = body.replace(",", "")
    try:
        number = float(body)
    except ValueError as exc:
        raise RowError("amount is not a number: %r" % raw) from exc
    if number < 0:
        raise RowError("amount is negative: %r" % raw)
    return "%.2f" % number


def clean_row(row):
    return {
        "id": clean_text(row.get("id", "")),
        "name": clean_text(row.get("name", "")),
        "email": clean_email(row.get("email", "")),
        "phone": clean_phone(row.get("phone", "")),
        "signup_date": clean_date(row.get("signup_date", "")),
        "amount": clean_amount(row.get("amount", "")),
    }


def write_csv(path, fieldnames, rows):
    """Write atomically: a crash leaves the previous file, never half a new one."""
    directory = os.path.dirname(os.path.abspath(path)) or "."
    handle, temporary = tempfile.mkstemp(dir=directory, suffix=".tmp")
    os.close(handle)
    try:
        with open(temporary, "w", encoding="utf-8", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)
        os.replace(temporary, path)
    except BaseException:
        if os.path.exists(temporary):
            os.remove(temporary)
        raise


def clean_file(input_path, dedup_key="email"):
    with open(input_path, "r", encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        if reader.fieldnames is None:
            raise SystemExit("input file is empty: expected a header row")
        header = [clean_text(name) for name in reader.fieldnames]
        missing = [name for name in REQUIRED_COLUMNS if name not in header]
        if missing:
            raise SystemExit("input is missing required column(s): %s" % ", ".join(missing))
        raw_rows = list(reader)

    cleaned = []
    rejected = []
    seen = {}
    reasons = Counter()

    for offset, row in enumerate(raw_rows, start=2):  # row 1 is the header
        original = dict((name, row.get(name) or "") for name in REQUIRED_COLUMNS)
        try:
            values = clean_row(row)
        except RowError as error:
            reasons[str(error).split()[0]] += 1
            rejected.append(dict(source_row=offset, reason=str(error), **original))
            continue
        key = values[dedup_key].lower()
        if key in seen:
            reasons["duplicate"] += 1
            rejected.append(
                dict(
                    source_row=offset,
                    reason="duplicate %s of row %d" % (dedup_key, seen[key]),
                    **original
                )
            )
            continue
        seen[key] = offset
        cleaned.append(values)

    report = {
        "input": os.path.basename(input_path),
        "rows_read": len(raw_rows),
        "rows_written": len(cleaned),
        "rows_rejected": len(rejected),
        "dedup_key": dedup_key,
        "reject_reasons": dict(sorted(reasons.items())),
    }
    return cleaned, rejected, report


def main(argv=None):
    parser = argparse.ArgumentParser(description="Clean and validate a contact CSV export.")
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--rejects", required=True)
    parser.add_argument("--report", required=True)
    parser.add_argument("--dedup-key", default="email", choices=("email", "phone", "id"))
    parser.add_argument("--force", action="store_true", help="overwrite existing output files")
    args = parser.parse_args(argv)

    for path in (args.output, args.rejects, args.report):
        directory = os.path.dirname(os.path.abspath(path))
        if not os.path.isdir(directory):
            raise SystemExit("output directory does not exist: %s" % directory)
        if os.path.exists(path) and not args.force:
            raise SystemExit("refusing to overwrite existing file: %s (use --force)" % path)

    cleaned, rejected, report = clean_file(args.input, args.dedup_key)

    write_csv(args.output, list(REQUIRED_COLUMNS), cleaned)
    write_csv(args.rejects, ["source_row", "reason"] + list(REQUIRED_COLUMNS), rejected)
    with open(args.report, "w", encoding="utf-8") as stream:
        json.dump(report, stream, indent=2, ensure_ascii=False)
        stream.write("\n")

    print(json.dumps(report, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
