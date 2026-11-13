"""Aggregate the manual-audit sheets into results/audit/audit_summary.json."""
import csv
import json
from collections import Counter, defaultdict

from . import config

AUDIT = config.RESULTS / "audit"


def _rows(name):
    with open(AUDIT / name, encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def _is(value, flag: bool) -> bool:
    """Spreadsheet-tolerant boolean check: Excel rewrites True/False as TRUE/FALSE."""
    return str(value).strip().lower() == str(flag).lower()


def main() -> None:
    out: dict = {"labeled_by": sorted({r.get("labeled_by", "") for n in
                                      ("coherence.csv", "grounding.csv", "metadata_audit.csv") for r in _rows(n)})}
    coh = defaultdict(list)
    for r in _rows("coherence.csv"):
        if r["score_0_1_2"] != "":
            coh[r["strategy"][0]].append(int(r["score_0_1_2"]))
    coh["C"] = coh["B"]  # C uses B's chunks
    out["coherence"] = {s: {"n": len(v), "mean_of_2": round(sum(v) / len(v), 2), "counts": dict(Counter(v))}
                        for s, v in sorted(coh.items()) if v}

    grd = defaultdict(list)
    for r in _rows("grounding.csv"):
        if r["grounding_0_1_2"] != "":
            grd[r["strategy"]].append(int(r["grounding_0_1_2"]))
    out["grounding"] = {s: {"n": len(v), "mean_of_2": round(sum(v) / len(v), 2),
                            "counts_0_1_2": [v.count(0), v.count(1), v.count(2)]} for s, v in sorted(grd.items())}

    meta = defaultdict(lambda: {"records": 0, "all_correct": 0, "filter_questions": set(), "filter_violations": set()})
    for r in _rows("metadata_audit.csv"):
        m = meta[r["strategy"]]
        m["records"] += 1
        m["all_correct"] += _is(r["all_correct"], True)
        if r["question_filter"] != "null":
            m["filter_questions"].add(r["question_id"])
            if _is(r["auto_filter_ok"], False):
                m["filter_violations"].add(r["question_id"])
    out["metadata"] = {s: {"correct_str": f"{m['all_correct']}/{m['records']}",
                           "filter_compliance_str": f"{len(m['filter_questions']) - len(m['filter_violations'])}/{len(m['filter_questions'])}",
                           "filter_violations": sorted(m["filter_violations"])} for s, m in sorted(meta.items())}
    (AUDIT / "audit_summary.json").write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(out, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
