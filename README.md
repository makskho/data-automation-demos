# Data and document automation — work samples

Small tools and samples that show how I work rather than describe it: what the rules are, what happens when
the input breaks them, and how the result is verified. Both run on Python 3.9+ with the standard
library, so there is nothing to install before trying them. A third folder holds Russian text samples
written to a synthetic brief.

All inputs here are synthetic. No client data appears in this repository.

| Sample | What it does | Proof included |
|---|---|---|
| [`data-cleaning/`](data-cleaning) | Cleans and validates a messy contact export: trims and normalises text, emails, international phones, dates and amounts, removes duplicates, and separates rows it cannot prove correct | 20 tests, sample before/after artifacts |
| [`annotation-qa/`](annotation-qa) | Quality-controls a labelled dataset: validates it against a declared schema, measures inter-annotator agreement with Cohen's kappa, and scores annotators against a gold set | 20 tests, sample report |
| [`copywriting/`](copywriting) | Three Russian texts written to a synthetic brief for an imaginary small business: a blog article, a social-media post and a landing-page offer | length and stock-phrase check with a failing self-test (`check_texts.py`) |
| [`telegram-bot/`](telegram-bot) | Telegram bot on aiogram 3: FAQ menu from an editable YAML file, lead form with phone validation and anti-flood, SQLite storage, admin notification, `/export` to .xlsx | 84 offline tests |
| [`web-parser/`](web-parser) | Catalogue crawler: pagination and product pages to a formatted Excel/CSV, polite delays, retries, resumable checkpoint, CLI; runs on the public books.toscrape.com sandbox | 38 tests, sample .xlsx/.csv output |
| [`nextjs-crm-api/`](nextjs-crm-api) | Mini-CRM REST API on Next.js, TypeScript and PostgreSQL/Drizzle: client CRUD and search, document upload/download with Cyrillic file names (RFC 5987), optimistic locking (409) | 18 tests on PGlite, type check |
| [`translation-editing/`](translation-editing) | RU↔EN translation samples (Wikipedia CC BY-SA, USGS public domain) and editing samples (Russian literary, English business) as side-by-side and tracked-changes DOCX | rebuilt and checked by `build_samples.py` (numbers, glossary, untranslated words) |

## The idea both samples share

An automation that guesses is worse than one that stops. `03/04/2026` can be 3 April or 4 March, so
the cleaner rejects that row and says why instead of picking one. A gold file that fails its own
schema is refused rather than used to compute an accuracy figure that looks like quality.

Every rejected record keeps its source line and one exact reason, so the input can be fixed and the
run repeated. Outputs are written through a temporary file and renamed, an existing output is never
overwritten silently, and a missing column, an empty file or a missing output directory stops the
run before anything is written.

## Running them

```bash
cd data-cleaning
python clean_contacts.py --input fixtures/contacts_raw.csv --output out.csv \
  --rejects rejects.csv --report report.json
python -m unittest discover -s . -v
```

```bash
cd annotation-qa
python check_annotations.py --schema fixtures/schema.json \
  --annotations fixtures/pass_a.jsonl fixtures/pass_b.jsonl --gold fixtures/gold.jsonl \
  --report report.json --rejects rejects.jsonl --min-kappa 0.75
python -m unittest discover -s . -v
```

Each folder's README states exactly what the sample covers and what it deliberately does not.

## How I work on a real task

The input, the expected output, and the acceptance check are agreed before implementation. Realistic
and invalid inputs are both tested. What the tool refuses to do is stated as plainly as what it does,
and the delivered result is one repeatable command with its limitations written down.
