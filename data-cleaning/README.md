# Contact list cleanup and validation

A messy contact export goes in. Three files come out: the rows that are provably correct, the rows
that are not with the exact reason for each, and a short report. Nothing is guessed and nothing is
dropped silently.

The data here is synthetic. No client file, name, or address appears in this repository.

## Run it

```bash
python clean_contacts.py \
  --input fixtures/contacts_raw.csv \
  --output sample-output/contacts_clean.csv \
  --rejects sample-output/contacts_rejects.csv \
  --report sample-output/report.json
```

Python 3.9+ and the standard library. No packages to install, nothing to configure.

## What it does to each column

| Column | Rule |
|---|---|
| `name` | trim, collapse repeated spaces, keep non-ASCII letters as they are |
| `email` | trim, lowercase, validate the address shape |
| `phone` | strip spaces, brackets and dashes; keep the international prefix; require 8–15 digits |
| `signup_date` | accept `2026-01-15`, `15.01.2026` and unambiguous `25/12/2026`, output ISO |
| `amount` | strip currency symbols and thousands separators, accept `1 234,56` and `1,234.50`, output two decimals |
| all rows | drop later duplicates of the same key, `--dedup-key email\|phone\|id` |

## The part that matters: what it refuses to do

`03/04/2026` could be 3 April or 4 March. The tool does not pick one. It rejects the row and says
why, because a silently wrong date is worse than a visibly missing one.

The same applies everywhere else. A row is rejected, never repaired by guesswork, when the email is
not a valid address, the phone is too short or too long, the date is impossible (`2026-02-30`), the
amount is negative or not a number, or the row duplicates an earlier one. Every rejected row keeps
its original values, its line number in the source file, and one sentence explaining the decision,
so the list can be fixed at the source and re-run.

## Before and after

Input row 2, as exported:

```csv
1,  Anna   Petrova ,ANNA.Petrova@Example.COM , +66 81 234 5678 ,2026-01-15,"1 234,56"
```

Output:

```csv
1,Anna Petrova,anna.petrova@example.com,+66812345678,2026-01-15,1234.56
```

From the same 12-row sample, four rows were clean, eight were rejected:

```json
{
  "input": "contacts_raw.csv",
  "rows_read": 12,
  "rows_written": 4,
  "rows_rejected": 8,
  "dedup_key": "email",
  "reject_reasons": {"amount": 3, "duplicate": 1, "email": 1, "phone": 1, "signup_date": 2}
}
```

The rejects file names each one:

```csv
source_row,reason,id,name,email,phone,signup_date,amount
5,duplicate email of row 2,4,Dmitri Sokolov,ANNA.PETROVA@example.com,...
8,signup_date '03/04/2026' is ambiguous: 3 and 4 can both be the month,7,Grace Okafor,...
```

Full artifacts are in [`sample-output/`](sample-output).

## Safety of the run

- Output files are written through a temporary file and renamed, so an interrupted run never leaves
  a half-written CSV.
- An existing output file is not overwritten unless `--force` is given.
- A missing required column, an empty file, or a missing output directory stops the run before
  anything is written.

## Tests

```bash
python -m unittest discover -s . -v
```

20 tests: field rules, the realistic sample, and the failure cases above — an ambiguous date, an
impossible date, a bad email, a short phone, a non-numeric and a negative amount, a case-different
duplicate, a UTF-8 byte-order mark, a header-only file, a missing column, an empty file, a missing
output directory, and a refused overwrite.

## Limits

Written for delimited exports with the six columns above. Extending it to a different schema, other
date or phone conventions, Excel workbooks, or multi-file merges is a change to the rules, not a
change to the approach — the rules live in one small file and each one is one function.
