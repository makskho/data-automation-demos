"""Quality control for a labelled dataset: validate, measure agreement, compare to gold.

Annotation projects fail in three ways: labels that break the schema, annotators who
disagree, and a batch that looks finished but is wrong. This tool answers all three with
numbers instead of an opinion, and refuses to score a batch it cannot validate.

Run:
    python check_annotations.py --schema schema.json --annotations pass_a.jsonl pass_b.jsonl
        --gold gold.jsonl --report report.json --rejects rejects.jsonl
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from collections import Counter, defaultdict

REQUIRED_FIELDS = ("item_id", "text", "label", "annotator")


class ItemError(ValueError):
    """One annotation failed validation for one stated reason."""


def load_schema(path):
    with open(path, "r", encoding="utf-8") as stream:
        schema = json.load(stream)
    labels = schema.get("labels")
    if not isinstance(labels, list) or not labels:
        raise SystemExit("schema must contain a non-empty 'labels' list")
    if len(set(labels)) != len(labels):
        raise SystemExit("schema 'labels' contains duplicates")
    return {
        "labels": set(labels),
        "min_confidence": float(schema.get("min_confidence", 0.0)),
        "requires_span": bool(schema.get("requires_span", False)),
    }


def validate_item(raw, schema):
    for field in REQUIRED_FIELDS:
        if field not in raw or raw[field] in (None, ""):
            raise ItemError("missing required field %r" % field)

    label = raw["label"]
    if label not in schema["labels"]:
        raise ItemError("label %r is not in the schema" % label)

    confidence = raw.get("confidence")
    if confidence is not None:
        if not isinstance(confidence, (int, float)) or isinstance(confidence, bool):
            raise ItemError("confidence is not a number: %r" % confidence)
        if not 0.0 <= float(confidence) <= 1.0:
            raise ItemError("confidence %r is outside 0.0-1.0" % confidence)
        if float(confidence) < schema["min_confidence"]:
            raise ItemError(
                "confidence %.2f is below the schema minimum %.2f"
                % (float(confidence), schema["min_confidence"])
            )

    span = raw.get("span")
    if schema["requires_span"] and span is None:
        raise ItemError("schema requires a span and none is present")
    if span is not None:
        if (not isinstance(span, list)) or len(span) != 2:
            raise ItemError("span must be a two-element list: %r" % (span,))
        start, end = span
        if not all(isinstance(value, int) and not isinstance(value, bool) for value in (start, end)):
            raise ItemError("span bounds must be integers: %r" % (span,))
        if start < 0 or end <= start:
            raise ItemError("span %r is not a positive range" % (span,))
        if end > len(raw["text"]):
            raise ItemError("span %r runs past the end of the text (%d characters)" % (span, len(raw["text"])))

    return {
        "item_id": str(raw["item_id"]),
        "text": raw["text"],
        "label": label,
        "annotator": str(raw["annotator"]),
        "confidence": float(confidence) if confidence is not None else None,
        "span": list(span) if span is not None else None,
    }


def read_jsonl(path, schema):
    """Return accepted items and rejects. A malformed line is a reject, not a crash."""
    accepted, rejected = [], []
    seen = set()
    with open(path, "r", encoding="utf-8-sig") as stream:
        lines = stream.readlines()
    if not any(line.strip() for line in lines):
        raise SystemExit("annotation file has no records: %s" % path)

    for number, line in enumerate(lines, start=1):
        if not line.strip():
            continue
        try:
            raw = json.loads(line)
        except ValueError as exc:
            rejected.append({"source": os.path.basename(path), "line": number, "reason": "invalid JSON: %s" % exc})
            continue
        try:
            item = validate_item(raw, schema)
        except ItemError as error:
            rejected.append({
                "source": os.path.basename(path),
                "line": number,
                "item_id": str(raw.get("item_id", "")),
                "reason": str(error),
            })
            continue
        key = (item["annotator"], item["item_id"])
        if key in seen:
            rejected.append({
                "source": os.path.basename(path),
                "line": number,
                "item_id": item["item_id"],
                "reason": "annotator %s labelled item %s twice" % key,
            })
            continue
        seen.add(key)
        accepted.append(item)
    return accepted, rejected


def cohens_kappa(pairs):
    """Agreement corrected for chance. Returns None when it is not defined."""
    if not pairs:
        return None
    total = len(pairs)
    observed = sum(1 for first, second in pairs if first == second) / total
    first_counts = Counter(first for first, _ in pairs)
    second_counts = Counter(second for _, second in pairs)
    expected = sum(
        (first_counts[label] / total) * (second_counts[label] / total)
        for label in set(first_counts) | set(second_counts)
    )
    if expected >= 1.0:
        return None  # every item carries the same label: chance agreement is already total
    return round((observed - expected) / (1 - expected), 4)


def per_label_scores(gold_by_item, predicted_by_item, labels):
    scores = {}
    for label in sorted(labels):
        true_positive = sum(
            1 for item, value in predicted_by_item.items()
            if value == label and gold_by_item.get(item) == label
        )
        predicted = sum(1 for value in predicted_by_item.values() if value == label)
        actual = sum(
            1 for item, value in gold_by_item.items()
            if value == label and item in predicted_by_item
        )
        precision = round(true_positive / predicted, 4) if predicted else None
        recall = round(true_positive / actual, 4) if actual else None
        if precision and recall:
            f1 = round(2 * precision * recall / (precision + recall), 4)
        else:
            f1 = 0.0 if (precision is not None and recall is not None) else None
        scores[label] = {"precision": precision, "recall": recall, "f1": f1, "gold_items": actual}
    return scores


def analyse(schema, annotation_paths, gold_path=None):
    accepted, rejected = [], []
    for path in annotation_paths:
        items, bad = read_jsonl(path, schema)
        accepted.extend(items)
        rejected.extend(bad)

    by_annotator = defaultdict(dict)
    for item in accepted:
        by_annotator[item["annotator"]][item["item_id"]] = item["label"]

    agreement = []
    annotators = sorted(by_annotator)
    disagreements = []
    for index, first in enumerate(annotators):
        for second in annotators[index + 1:]:
            shared = sorted(set(by_annotator[first]) & set(by_annotator[second]))
            pairs = [(by_annotator[first][item], by_annotator[second][item]) for item in shared]
            matches = sum(1 for one, two in pairs if one == two)
            agreement.append({
                "annotators": [first, second],
                "shared_items": len(shared),
                "exact_match": round(matches / len(shared), 4) if shared else None,
                "cohens_kappa": cohens_kappa(pairs),
            })
            for item in shared:
                if by_annotator[first][item] != by_annotator[second][item]:
                    disagreements.append({
                        "item_id": item,
                        first: by_annotator[first][item],
                        second: by_annotator[second][item],
                    })

    gold_section = None
    if gold_path:
        gold_items, gold_rejects = read_jsonl(gold_path, schema)
        if gold_rejects:
            raise SystemExit(
                "gold file is not valid, so it cannot be a reference: %s" % gold_rejects[0]["reason"]
            )
        gold_by_item = {item["item_id"]: item["label"] for item in gold_items}
        gold_section = {}
        for annotator in annotators:
            predicted = {
                item: label for item, label in by_annotator[annotator].items() if item in gold_by_item
            }
            correct = sum(1 for item, label in predicted.items() if gold_by_item[item] == label)
            gold_section[annotator] = {
                "checked_items": len(predicted),
                "accuracy": round(correct / len(predicted), 4) if predicted else None,
                "per_label": per_label_scores(gold_by_item, predicted, schema["labels"]),
            }

    report = {
        "annotations_read": len(accepted) + len(rejected),
        "annotations_accepted": len(accepted),
        "annotations_rejected": len(rejected),
        "reject_reasons": dict(sorted(Counter(
            reject["reason"].split(":")[0].split(" is ")[0].split(" runs ")[0]
            for reject in rejected
        ).items())),
        "annotators": {name: len(items) for name, items in sorted(by_annotator.items())},
        "label_distribution": dict(sorted(Counter(item["label"] for item in accepted).items())),
        "agreement": agreement,
        "disagreements": disagreements,
        "against_gold": gold_section,
    }
    return report, rejected


def write_json(path, payload, lines=False):
    directory = os.path.dirname(os.path.abspath(path)) or "."
    handle, temporary = tempfile.mkstemp(dir=directory, suffix=".tmp")
    os.close(handle)
    try:
        with open(temporary, "w", encoding="utf-8", newline="\n") as stream:
            if lines:
                for record in payload:
                    stream.write(json.dumps(record, ensure_ascii=False) + "\n")
            else:
                json.dump(payload, stream, indent=2, ensure_ascii=False)
                stream.write("\n")
        os.replace(temporary, path)
    except BaseException:
        if os.path.exists(temporary):
            os.remove(temporary)
        raise


def main(argv=None):
    parser = argparse.ArgumentParser(description="Validate and score an annotated dataset.")
    parser.add_argument("--schema", required=True)
    parser.add_argument("--annotations", required=True, nargs="+")
    parser.add_argument("--gold")
    parser.add_argument("--report", required=True)
    parser.add_argument("--rejects", required=True)
    parser.add_argument("--min-kappa", type=float, default=None,
                        help="exit non-zero when any annotator pair falls below this agreement")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args(argv)

    for path in (args.report, args.rejects):
        directory = os.path.dirname(os.path.abspath(path))
        if not os.path.isdir(directory):
            raise SystemExit("output directory does not exist: %s" % directory)
        if os.path.exists(path) and not args.force:
            raise SystemExit("refusing to overwrite existing file: %s (use --force)" % path)

    schema = load_schema(args.schema)
    report, rejected = analyse(schema, args.annotations, args.gold)

    write_json(args.report, report)
    write_json(args.rejects, rejected, lines=True)
    print(json.dumps({key: report[key] for key in (
        "annotations_read", "annotations_accepted", "annotations_rejected", "agreement"
    )}, ensure_ascii=False))

    if args.min_kappa is not None:
        for pair in report["agreement"]:
            kappa = pair["cohens_kappa"]
            if kappa is None or kappa < args.min_kappa:
                print("agreement below the required minimum: %s -> %s" % (pair["annotators"], kappa),
                      file=sys.stderr)
                return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
