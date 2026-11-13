"""Automatic retrieval metrics (Hit@1, Evidence Hit@3) with full per-query traces.

Manual dimensions (coherence, grounding, metadata audit) are NOT inferred here;
see audit_samples.py which only prepares templates for a human grader.
"""
import re
import unicodedata
from typing import Any


def norm_for_match(text: str) -> str:
    """Lenient normalisation used only for evidence matching."""
    text = unicodedata.normalize("NFKC", text).lower()
    text = text.replace("’", "'").replace("‘", "'").replace("“", '"').replace("”", '"')
    text = text.replace("–", "-").replace("—", "-")
    return re.sub(r"\s+", " ", text).strip()


def _as_list(x: Any) -> list:
    if x is None:
        return []
    return x if isinstance(x, list) else [x]


def gold_locations(question: dict[str, Any]) -> set[tuple[str, int]]:
    return {(question["gold_source_id"], int(p)) for p in _as_list(question["gold_page"])}


def judge_hit(question: dict[str, Any], hit: dict[str, Any]) -> dict[str, Any]:
    on_gold_page = (hit["document_id"], int(hit["page"])) in gold_locations(question)
    chunk_text = norm_for_match(hit["text"])
    quotes = [norm_for_match(q) for q in _as_list(question["evidence_quote"])]
    full = any(q in chunk_text for q in quotes)
    # Partial: at least half the words of some quote appear as a contiguous 8-word window.
    partial = False
    if on_gold_page and not full:
        for q in quotes:
            words = q.split()
            for i in range(0, max(1, len(words) - 7)):
                if " ".join(words[i:i + 8]) in chunk_text:
                    partial = True
                    break
    return {
        "on_gold_page": on_gold_page,
        "contains_full_evidence": full,
        "is_hit": on_gold_page and full,
        "evidence_split": partial,
    }


def evaluate_query(question: dict[str, Any], hits: list[dict[str, Any]]) -> dict[str, Any]:
    judged = [judge_hit(question, h) for h in hits]
    hit_rank = next((i + 1 for i, j in enumerate(judged) if j["is_hit"]), None)
    return {
        "id": question["id"],
        "split": question["split"],
        "type": question.get("type"),
        "question": question["question"],
        "filter": question.get("filter"),
        "gold_source_id": question["gold_source_id"],
        "gold_page": question["gold_page"],
        "evidence_quote": question["evidence_quote"],
        "expected_answer": question.get("expected_answer"),
        "hit_at_1": hit_rank == 1,
        "hit_at_3": hit_rank is not None and hit_rank <= 3,
        "hit_rank": hit_rank,
        "evidence_split_on_gold_page": any(j["evidence_split"] for j in judged) and hit_rank is None,
        "results": [
            {"rank": i + 1, **{k: h[k] for k in h}, **j} for i, (h, j) in enumerate(zip(hits, judged))
        ],
    }


def summarize(traces: list[dict[str, Any]]) -> dict[str, Any]:
    """traces: list of {strategy, ...evaluate_query output}."""
    out: dict[str, Any] = {}
    for t in traces:
        key = f"{t['strategy']}/{t['split']}"
        s = out.setdefault(key, {"strategy": t["strategy"], "split": t["split"], "N": 0,
                                 "hit1": 0, "hit3": 0, "evidence_split": 0,
                                 "filter_N": 0, "filter_compliant": 0, "missed_ids": []})
        s["N"] += 1
        s["hit1"] += int(t["hit_at_1"])
        s["hit3"] += int(t["hit_at_3"])
        s["evidence_split"] += int(t["evidence_split_on_gold_page"])
        if t.get("filter"):
            s["filter_N"] += 1
            ok = all(all(r.get(k) == v for k, v in t["filter"].items()) for r in t["results"])
            s["filter_compliant"] += int(ok)
        if not t["hit_at_3"]:
            s["missed_ids"].append(t["id"])
    for s in out.values():
        s["hit1_str"] = f"{s['hit1']}/{s['N']}"
        s["hit3_str"] = f"{s['hit3']}/{s['N']}"
        s["filter_compliance_str"] = (
            f"{s['filter_compliant']}/{s['filter_N']}" if s["filter_N"] else "N/A"
        )
    return dict(sorted(out.items()))
