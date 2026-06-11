#!/usr/bin/env python3
"""Score an agent trace against a weighted rubric.

A rubric is a JSON file of dimensions, each with a weight and a 0-5 scale
description. Scores live in a separate JSON file so multiple raters can score
the same trace independently and be compared for agreement.

Usage:
    python3 rubric.py rubric.json --template            # blank scoring sheet
    python3 rubric.py rubric.json --scores scores.json  # weighted total

Stdlib only.
"""

import argparse
import json
import sys

MAX_SCORE = 5


def load_rubric(path):
    with open(path, encoding="utf-8") as f:
        rubric = json.load(f)
    dims = rubric.get("dimensions")
    if not dims:
        raise ValueError("rubric has no dimensions")
    for name, dim in dims.items():
        if not 0 < dim.get("weight", 0) <= 1:
            raise ValueError(f"dimension '{name}': weight must be in (0, 1]")
    total_weight = sum(d["weight"] for d in dims.values())
    if abs(total_weight - 1.0) > 1e-6:
        raise ValueError(f"dimension weights sum to {total_weight}, expected 1.0")
    return rubric


def blank_sheet(rubric):
    return {
        "trace_id": "",
        "rater": "",
        "scores": {name: None for name in rubric["dimensions"]},
        "notes": {name: "" for name in rubric["dimensions"]},
    }


def score(rubric, scores):
    dims = rubric["dimensions"]
    missing = [name for name in dims if scores.get(name) is None]
    if missing:
        raise ValueError(f"missing scores for: {', '.join(missing)}")
    unknown = [name for name in scores if name not in dims]
    if unknown:
        raise ValueError(f"scores for unknown dimensions: {', '.join(unknown)}")
    for name, value in scores.items():
        if not 0 <= value <= MAX_SCORE:
            raise ValueError(f"dimension '{name}': score {value} outside 0-{MAX_SCORE}")
    weighted = sum(dims[name]["weight"] * scores[name] for name in dims)
    return weighted / MAX_SCORE  # normalized 0-1


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("rubric", help="rubric JSON file")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--template", action="store_true", help="emit a blank scoring sheet")
    group.add_argument("--scores", help="scoring sheet JSON to compute weighted total")
    args = parser.parse_args(argv)

    rubric = load_rubric(args.rubric)
    if args.template:
        json.dump(blank_sheet(rubric), sys.stdout, indent=2)
        print()
        return 0

    with open(args.scores, encoding="utf-8") as f:
        sheet = json.load(f)
    total = score(rubric, sheet["scores"])
    print(f"trace={sheet.get('trace_id', '?')} rater={sheet.get('rater', '?')} "
          f"weighted score: {total:.3f} (0-1 scale)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
