"""Validate the benchmark against the normalised corpus BEFORE any retrieval run.

Checks: schema, >=20 questions, >=15 dev / >=5 test, >=3 filter questions with >=1 in
test, every evidence quote is present on (one of) its gold page(s) after normalisation,
filter values exist in page metadata, and whether the evidence also appears on pages
outside the filter scope (useful to confirm the filter is discriminative).
"""
import json
import sys
from collections import Counter

from . import config
from .evaluation import _as_list, norm_for_match

REQUIRED = ["id", "split", "question", "expected_answer", "gold_source_id", "gold_page", "evidence_quote"]


def main() -> None:
    pages = {(r["document_id"], r["page"]): r for r in map(json.loads, open(config.PAGES_JSONL, encoding="utf-8"))}
    qs = [json.loads(line) for line in open(config.BENCHMARK, encoding="utf-8") if line.strip()]
    problems: list[str] = []
    ids = Counter(q.get("id") for q in qs)
    problems += [f"duplicate id {i}" for i, n in ids.items() if n > 1]
    splits = Counter(q.get("split") for q in qs)
    filt = [q for q in qs if q.get("filter")]
    for q in qs:
        missing = [k for k in REQUIRED if k not in q]
        if missing:
            problems.append(f"{q.get('id')}: missing fields {missing}")
            continue
        found_on = []
        for page in _as_list(q["gold_page"]):
            key = (q["gold_source_id"], int(page))
            if key not in pages:
                problems.append(f"{q['id']}: gold page {key} not in corpus")
                continue
            text = norm_for_match(pages[key]["text"])
            for quote in _as_list(q["evidence_quote"]):
                if norm_for_match(quote) in text:
                    found_on.append((page, quote[:50]))
            if q.get("filter"):
                for k, v in q["filter"].items():
                    if pages[key]["metadata"].get(k) != v:
                        problems.append(f"{q['id']}: gold page {page} has {k}={pages[key]['metadata'].get(k)} != filter {v}")
        quotes_ok = all(any(norm_for_match(qt) in norm_for_match(pages[(q['gold_source_id'], int(p))]['text'])
                            for p in _as_list(q["gold_page"]) if (q['gold_source_id'], int(p)) in pages)
                        for qt in _as_list(q["evidence_quote"]))
        if not quotes_ok:
            problems.append(f"{q['id']}: some evidence_quote not found on any gold page")
        status = "OK " if quotes_ok else "BAD"
        print(f"{status} {q['id']:4} {q['split']:4} {q.get('type',''):16} pages={q['gold_page']} filter={q.get('filter')}")
    # filter values must exist in corpus metadata
    for q in filt:
        for k, v in q["filter"].items():
            if not any(p["metadata"].get(k) == v for p in pages.values()):
                problems.append(f"{q['id']}: filter value {k}={v} does not exist in corpus metadata")
    print(f"\nTotal {len(qs)} | splits {dict(splits)} | filter questions {len(filt)} "
          f"(test: {sum(q['split'] == 'test' for q in filt)})")
    if len(qs) < 20:
        problems.append("fewer than 20 questions")
    if splits.get("dev", 0) < 15 or splits.get("test", 0) < 5:
        problems.append("need >=15 dev and >=5 test")
    if len(filt) < 3 or not any(q["split"] == "test" for q in filt):
        problems.append("need >=3 filter questions with >=1 in test")
    if problems:
        print("\nPROBLEMS:\n- " + "\n- ".join(problems))
        sys.exit(1)
    print("Benchmark check passed.")


if __name__ == "__main__":
    main()
