"""Prepare manual-audit sheets (CSV, UTF-8 with BOM for Excel). Label columns are left
blank for the human grader; only clearly-named `auto_*` columns are computed.

  results/audit/coherence.csv       10 fixed source positions x strategies (A, B; C == B)
  results/audit/metadata_audit.csv  test questions x top-3 x A/B/C
  results/audit/grounding.csv       test questions x A/B/C

Coherence positions are chosen BEFORE looking at scores: the first 10 counted page IDs
in sorted order; on each page the position is the midpoint of the first paragraph with
>= 200 characters.
"""
import csv
import json
import re

from pypdf import PdfReader

from . import config
from .evaluation import _as_list, norm_for_match
from .run import build_chunks, load_pages

AUDIT = config.RESULTS / "audit"


def _write_csv(path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    print(f"{path.relative_to(config.REPO)}: {len(rows)} rows")


def coherence() -> None:
    pages = sorted(load_pages(), key=lambda p: p.page)[:10]
    chunks = {i: build_chunks(i, pages) for i in config.INDEXES}
    rows = []
    for n, p in enumerate(pages, 1):
        m = next(m for m in re.finditer(r"[^\n](?:.|\n(?!\n))*", p.text) if len(m.group()) >= 200)
        pos = (m.start() + m.end()) // 2
        for idx in config.INDEXES:
            c = next(c for c in chunks[idx] if c.page == p.page
                     and c.metadata["char_start"] <= pos < c.metadata["char_end"])
            rows.append({
                "position_id": f"pos{n:02d}", "page": p.page, "position_char": pos,
                "source_paragraph_start": m.group()[:160],
                "strategy": idx + (" (also C)" if idx == "B" else ""), "chunk_id": c.chunk_id,
                "chunk_len": len(c.text), "chunk_text": c.text,
                "score_0_1_2": "", "reason": "",
            })
    _write_csv(AUDIT / "coherence.csv", rows)


def _pypdf_pages() -> dict[int, str]:
    src = config.SOURCES[0]
    reader = PdfReader(src["local_path"])
    return {p: norm_for_match(reader.pages[p - 1].extract_text() or "") for p in range(1, len(reader.pages) + 1)}


def _on_page_independent(text: str, page_text: str) -> bool:
    """Independent check with pypdf: some 6-word window of the chunk appears on the page."""
    words = norm_for_match(text).replace("•", " ").split()
    windows = [" ".join(words[i:i + 6]) for i in range(0, max(1, len(words) - 5), 3)]
    return any(w in page_text for w in windows)


def metadata_and_grounding() -> None:
    raw = _pypdf_pages()
    meta_rows, ground_rows = [], []
    for s in config.STRATEGIES:
        path = config.RESULTS / f"traces_{s}_test.jsonl"
        for t in map(json.loads, open(path, encoding="utf-8")):
            top = []
            for r in t["results"]:
                filt_ok = (all(r.get(k) == v for k, v in t["filter"].items()) if t.get("filter") else "N/A")
                meta_rows.append({
                    "strategy": s, "question_id": t["id"], "rank": r["rank"], "chunk_id": r["chunk_id"],
                    "document_id": r["document_id"], "source": r["source"], "page": r["page"],
                    "chapter": r["chapter"], "section": r["section"], "section_title": r["section_title"],
                    "question_filter": json.dumps(t.get("filter")), "filter_applied": json.dumps(t.get("filter_applied")),
                    "auto_filter_ok": filt_ok,
                    "auto_text_found_on_page_by_pypdf": _on_page_independent(r["text"], raw[r["page"]]),
                    "text_excerpt": r["text"][:200],
                    "source_ok": "", "page_ok": "", "chapter_ok": "", "section_ok": "",
                    "all_correct": "", "note": "",
                })
                top.append(f"#{r['rank']} p{r['page']} ch{r['chapter']} §{r['section']} :: {r['text']}")
            ground_rows.append({
                "strategy": s, "question_id": t["id"], "question": t["question"],
                "filter_applied": json.dumps(t.get("filter_applied")),
                "expected_answer": t["expected_answer"], "evidence_quote": " || ".join(_as_list(t["evidence_quote"])),
                "gold_page": json.dumps(t["gold_page"]), "auto_evidence_hit_at_3": t["hit_at_3"],
                "auto_hit_rank": t["hit_rank"], "top3": "\n\n".join(top),
                "grounding_0_1_2": "", "reason": "",
            })
    _write_csv(AUDIT / "metadata_audit.csv", meta_rows)
    _write_csv(AUDIT / "grounding.csv", ground_rows)


if __name__ == "__main__":
    coherence()
    metadata_and_grounding()
