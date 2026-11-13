"""Day 06 pipeline entry point.

Usage (from starter/):
    python -m src.run prepare                 # PDF -> data/pages.jsonl + data/manifest.json
    python -m src.run ingest [--index A|B]    # chunk, embed, upsert into pgvector
    python -m src.run reingest-check          # re-ingest and verify no duplicates
    python -m src.run query --split dev|test  # top-3 traces for strategies A, B, C
    python -m src.run evaluate                # Hit@1 / Evidence Hit@3 summary
"""
import argparse
import hashlib
import json
import platform
import statistics
import sys
import time
from datetime import datetime, timezone
from importlib.metadata import version

from . import config
from .chunking import by_paragraph, fixed_size
from .evaluation import evaluate_query, summarize
from .models import Chunk, DocumentPage


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _write_json(path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")


def _read_jsonl(path) -> list[dict]:
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def _write_jsonl(path, rows) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False, default=str) + "\n")


def _log_errors(errors: list[dict], stage: str) -> None:
    config.ERRORS_LOG.parent.mkdir(parents=True, exist_ok=True)
    with open(config.ERRORS_LOG, "a", encoding="utf-8") as f:
        for e in errors:
            f.write(json.dumps({"at": _now(), "stage": stage, **e}, ensure_ascii=False) + "\n")


# ---------------------------------------------------------------- prepare
def cmd_prepare(_args) -> None:
    from .ingestion import load_pdf

    manifest = {"generated_at": _now(), "counting_rule": (
        f"A page is counted when it lies in the lesson-body page range of a chosen chapter "
        f"(chapter opener and Chapter Review pages excluded) AND its normalised extracted text "
        f"has >= {config.MIN_CONTENT_CHARS} characters. Page numbers are 1-based physical PDF "
        f"page numbers (not the printed page labels)."), "sources": []}
    all_pages: list[dict] = []
    for src in config.SOURCES:
        path = src["local_path"]
        if not path.exists():
            sys.exit(f"Missing {path}. Download it from {src['source_path_or_url']}")
        sha = hashlib.sha256(path.read_bytes()).hexdigest()
        import pymupdf
        with pymupdf.open(path) as d:
            physical_pages = d.page_count
        counted, excluded, chars = [], [], {}
        for chapter, (first, last) in src["candidate_ranges"].items():
            errors: list[dict] = []
            pages = load_pdf(path, src["source_id"], path.name, list(range(first, last + 1)), errors)
            _log_errors(errors, "prepare")
            for p in pages:
                n = len(p.text)
                chars[str(p.page)] = n
                if p.metadata.get("chapter") != chapter:
                    excluded.append({"page": p.page, "reason": f"chapter metadata {p.metadata.get('chapter')} != {chapter}"})
                elif n < config.MIN_CONTENT_CHARS:
                    excluded.append({"page": p.page, "reason": f"only {n} chars after normalisation (< {config.MIN_CONTENT_CHARS})"})
                    _log_errors([{"document_id": p.document_id, "page": p.page, "error": "low_text",
                                  "detail": f"{n} chars; excluded from corpus"}], "prepare")
                else:
                    counted.append(p.page)
                    all_pages.append({"document_id": p.document_id, "source": p.source, "page": p.page,
                                      "text": p.text, "metadata": p.metadata})
        manifest["sources"].append({
            "source_id": src["source_id"], "title": src["title"],
            "source_path_or_url": src["source_path_or_url"], "book_page": src["book_page"],
            "local_file": str(path.relative_to(config.REPO)).replace("\\", "/"), "sha256": sha,
            "license_or_permission": src["license_or_permission"], "attribution": src["attribution"],
            "version": src["version"], "accessed_at": src["accessed_at"],
            "physical_pages": physical_pages,
            "chapters_used": {str(k): list(v) for k, v in src["candidate_ranges"].items()},
            "structural_exclusions": src["structural_exclusions"],
            "counted_pages": counted, "counted_page_total": len(counted),
            "excluded_pages_in_range": excluded,
            "chars_per_page": chars,
            "counted_chars_total": sum(chars[str(p)] for p in counted),
            "extraction": {"library": "PyMuPDF", "version": version("pymupdf"), "ocr": "not used (born-digital PDF)"},
        })
    _write_jsonl(config.PAGES_JSONL, all_pages)
    _write_json(config.MANIFEST, manifest)
    total = sum(s["counted_page_total"] for s in manifest["sources"])
    print(f"Counted content pages: {total} -> {config.PAGES_JSONL}")
    if total < 30:
        sys.exit("ERROR: fewer than 30 content pages")


def load_pages() -> list[DocumentPage]:
    rows = _read_jsonl(config.PAGES_JSONL)
    return [DocumentPage(r["document_id"], r["source"], r["page"], r["text"], r["metadata"]) for r in rows]


# ---------------------------------------------------------------- ingest
def build_chunks(index: str, pages: list[DocumentPage]) -> list[Chunk]:
    s = config.STRATEGIES[index]
    out: list[Chunk] = []
    for p in pages:
        if s["chunker"] == "fixed":
            out.extend(fixed_size(p, s["size"], s["overlap"], strategy=index))
        else:
            out.extend(by_paragraph(p, s["max_size"], strategy=index))
    return out


def _embedder():
    from .embeddings import SentenceTransformerEmbedder
    return SentenceTransformerEmbedder(config.EMBEDDING_MODEL)


def _store(dims: int):
    from .store import PgVectorStore
    return PgVectorStore(config.DATABASE_URL, dims)


def ingest(indexes: list[str], embedder=None) -> dict:
    pages = load_pages()
    embedder = embedder or _embedder()
    store = _store(embedder.dimensions)
    store.create_schema()
    stats_path = config.RESULTS / "ingest_stats.json"
    stats = json.loads(stats_path.read_text(encoding="utf-8")) if stats_path.exists() else {}
    for index in indexes:
        t0 = time.perf_counter()
        chunks = build_chunks(index, pages)
        t_chunk = time.perf_counter() - t0
        vectors = embedder.embed_documents([c.text for c in chunks])
        t_embed = time.perf_counter() - t0 - t_chunk
        write = store.upsert(index, chunks, vectors, embedder.model_name)
        total = time.perf_counter() - t0
        lengths = [len(c.text) for c in chunks]
        stats[index] = {
            "run_at": _now(), "params": config.STRATEGIES[index],
            "pages": len(pages), "chunk_count": len(chunks), "rows_in_store": store.count(index),
            "chars_total": sum(lengths), "len_min": min(lengths), "len_median": statistics.median(lengths),
            "len_mean": round(statistics.mean(lengths), 1), "len_max": max(lengths),
            "approx_tokens_total": sum(lengths) // 4,
            "seconds_chunk": round(t_chunk, 3), "seconds_embed": round(t_embed, 3),
            "seconds_total": round(total, 3), "cost_usd": 0.0,
            "write": write, "model": embedder.model_name, "dimensions": embedder.dimensions,
            "device": embedder.device,
        }
        print(f"[{index}] {len(chunks)} chunks, {total:.1f}s, store rows={stats[index]['rows_in_store']}, {write}")
    stats["_environment"] = {
        "python": platform.python_version(), "torch": version("torch"),
        "sentence_transformers": version("sentence-transformers"), "psycopg": version("psycopg"),
        "pgvector_py": version("pgvector"), "pymupdf": version("pymupdf"),
    }
    _write_json(stats_path, stats)
    return stats


def cmd_ingest(args) -> None:
    ingest([args.index] if args.index else config.INDEXES)


def cmd_reingest_check(_args) -> None:
    embedder = _embedder()
    store = _store(embedder.dimensions)
    before = {i: store.count(i) for i in config.INDEXES}
    stats = ingest(config.INDEXES, embedder)
    after = {i: store.count(i) for i in config.INDEXES}
    expected = {i: stats[i]["chunk_count"] for i in config.INDEXES}
    writes = {i: stats[i]["write"] for i in config.INDEXES}
    ok = before == after == expected
    result = {"checked_at": _now(), "rows_before": before, "rows_after": after,
              "expected_chunks": expected, "second_run_writes": writes, "no_duplicates": ok}
    _write_json(config.RESULTS / "reingest_check.json", result)
    print(json.dumps(result, indent=2))
    if not ok:
        sys.exit("Re-ingest changed row counts: duplicates or missing rows")


def cmd_change_check(_args) -> None:
    """Simulate a changed source document in a scratch table: obsolete chunks must be
    deleted and changed chunks rewritten, unchanged chunks untouched."""
    from .store import PgVectorStore

    embedder = _embedder()
    store = PgVectorStore(config.DATABASE_URL, embedder.dimensions, table="chunks_change_test")
    store.create_schema()
    pages = load_pages()[:3]
    v1 = build_chunks("B", pages)
    w1 = store.upsert("B", v1, embedder.embed_documents([c.text for c in v1]), embedder.model_name)
    # "New version": page 2 shortened to its first paragraph, page 3 text edited.
    changed = [pages[0],
               DocumentPage(pages[1].document_id, pages[1].source, pages[1].page,
                            pages[1].text.split("\n\n")[0], pages[1].metadata),
               DocumentPage(pages[2].document_id, pages[2].source, pages[2].page,
                            pages[2].text.replace("computer", "COMPUTER", 1), pages[2].metadata)]
    v2 = build_chunks("B", changed)
    w2 = store.upsert("B", v2, embedder.embed_documents([c.text for c in v2]), embedder.model_name)
    rows = store.count("B")
    with store._connect() as conn:
        conn.execute("DROP TABLE chunks_change_test")
    result = {"checked_at": _now(), "pages": [p.page for p in pages], "v1_chunks": len(v1),
              "v1_write": w1, "v2_chunks": len(v2), "v2_write": w2, "rows_after_v2": rows,
              "ok": rows == len(v2) and w2["deleted_obsolete"] == len(v1) - len(v2)}
    _write_json(config.RESULTS / "change_check.json", result)
    print(json.dumps(result, indent=2))
    if not result["ok"]:
        sys.exit("change-check failed")


# ---------------------------------------------------------------- query / evaluate
def cmd_query(args) -> None:
    questions = [q for q in _read_jsonl(config.BENCHMARK) if q["split"] == args.split]
    if not questions:
        sys.exit(f"No questions for split {args.split}")
    embedder = _embedder()
    store = _store(embedder.dimensions)
    qvecs = {q["id"]: embedder.embed_query(q["question"]) for q in questions}
    for name, s in config.STRATEGIES.items():
        traces = []
        t0 = time.perf_counter()
        for q in questions:
            filters = q.get("filter") if s["use_filter"] else None
            hits = store.search(s["index"], qvecs[q["id"]], config.TOP_K, filters or None)
            trace = evaluate_query(q, hits)
            traces.append({"strategy": name, "index": s["index"], "filter_applied": filters or None,
                           "model": embedder.model_name, "run_at": _now(), **trace})
        out = config.RESULTS / f"traces_{name}_{args.split}.jsonl"
        _write_jsonl(out, traces)
        h1 = sum(t["hit_at_1"] for t in traces)
        h3 = sum(t["hit_at_3"] for t in traces)
        print(f"[{name}/{args.split}] Hit@1 {h1}/{len(traces)}  Hit@3 {h3}/{len(traces)}  "
              f"({time.perf_counter() - t0:.2f}s) -> {out.name}")


def cmd_evaluate(_args) -> None:
    traces = []
    for f in sorted(config.RESULTS.glob("traces_*_*.jsonl")):
        traces.extend(_read_jsonl(f))
    summary = summarize(traces)
    _write_json(config.RESULTS / "summary.json", {"generated_at": _now(), "metrics": summary})
    print(f"{'strategy/split':<14} {'Hit@1':>7} {'Hit@3':>7} {'split-ev':>8} {'filter':>7}  missed")
    for k, s in summary.items():
        print(f"{k:<14} {s['hit1_str']:>7} {s['hit3_str']:>7} {s['evidence_split']:>8} "
              f"{s['filter_compliance_str']:>7}  {','.join(s['missed_ids'])}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Day 06 data ingestion pipeline")
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("prepare").set_defaults(func=cmd_prepare)
    p = sub.add_parser("ingest")
    p.add_argument("--index", choices=config.INDEXES)
    p.set_defaults(func=cmd_ingest)
    sub.add_parser("reingest-check").set_defaults(func=cmd_reingest_check)
    sub.add_parser("change-check").set_defaults(func=cmd_change_check)
    p = sub.add_parser("query")
    p.add_argument("--split", choices=["dev", "test"], required=True)
    p.set_defaults(func=cmd_query)
    sub.add_parser("evaluate").set_defaults(func=cmd_evaluate)
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
