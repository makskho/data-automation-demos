# Annotation quality control

Labelling projects fail in three ways: labels that break the schema, annotators who quietly disagree
with each other, and a delivered batch that looks finished but is wrong. This tool answers all three
with numbers, and refuses to score a batch it cannot validate first.

The data here is synthetic support messages. No client dataset appears in this repository.

## Run it

```bash
python check_annotations.py \
  --schema fixtures/schema.json \
  --annotations fixtures/pass_a.jsonl fixtures/pass_b.jsonl \
  --gold fixtures/gold.jsonl \
  --report sample-output/report.json \
  --rejects sample-output/rejects.jsonl
```

Python 3.9+ and the standard library. Add `--min-kappa 0.75` to make the run exit non-zero when any
annotator pair falls below the agreement you agreed with the client — that turns quality into a
build step instead of an opinion.

## 1. Validation against the schema

The label set, the minimum confidence, and whether spans are required come from `schema.json`, not
from the code. Every record must carry `item_id`, `text`, `label` and `annotator`. A record is
rejected, with its file, line number and one exact reason, when the label is not in the schema, the
confidence is outside 0–1 or below the agreed floor, a span is reversed or runs past the end of the
text, a required field is missing, the line is not valid JSON, or one annotator labelled the same
item twice.

A malformed line never stops the run and never silently disappears:

```json
{"source": "pass_broken.jsonl", "line": 5, "item_id": "m-005", "reason": "span [0, 99] runs past the end of the text (5 characters)"}
{"source": "pass_broken.jsonl", "line": 7, "reason": "invalid JSON: Expecting ',' delimiter: line 1 column 21 (char 20)"}
{"source": "pass_broken.jsonl", "line": 9, "item_id": "m-008", "reason": "annotator ann_c labelled item m-008 twice"}
```

## 2. Agreement between annotators

Raw match rate flatters a dataset whose labels are unevenly distributed, so the report gives both it
and Cohen's kappa, which subtracts the agreement you would expect by chance:

```json
{"annotators": ["ann_a", "ann_b"], "shared_items": 10, "exact_match": 0.8, "cohens_kappa": 0.7436}
```

Every disagreement is listed by item, so a reviewer sees the actual conflicts rather than a summary:

```json
{"item_id": "m-006", "ann_a": "billing", "ann_b": "cancellation"}
{"item_id": "m-008", "ann_a": "cancellation", "ann_b": "billing"}
```

Kappa is reported as undefined, never as a perfect score, when it is not defined — no shared items,
or one label used everywhere.

## 3. Accuracy against a gold set

When a reviewed gold file is supplied, each annotator gets an accuracy figure plus per-label
precision, recall and F1, which is what shows whether one specific label is the weak point:

```json
{"ann_a": {"checked_items": 10, "accuracy": 1.0}, "ann_b": {"checked_items": 10, "accuracy": 0.8}}
```

An invalid gold file is refused outright. Scoring a batch against a broken reference produces a
number that looks like quality and is not.

## Safety of the run

Report and rejects are written through a temporary file and renamed, an existing output is not
overwritten without `--force`, and an empty input, an empty schema or a missing output directory
stops the run before anything is written.

## Tests

```bash
python -m unittest discover -s . -v
```

20 tests: kappa on total, chance-level, systematic-disagreement and undefined cases; each validation
rule; the full two-pass run with gold scoring; every rejection reason with its line number; the
`--min-kappa` gate in both directions; an invalid gold file; an empty file; a missing output
directory; and a refused overwrite.

## Limits

Single-label classification per item, with optional character spans. Not written for multi-label
sets, hierarchical ontologies, bounding boxes, audio or video timelines, or more than pairwise
agreement — those change the metric, and the metric is the part worth agreeing on before work
starts.
