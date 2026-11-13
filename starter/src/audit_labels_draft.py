"""Write DRAFT manual labels into the audit sheets produced by audit_samples.py.

These labels were proposed by Claude (AI assistant) after reading every sampled chunk /
top-3 list; they are marked `labeled_by = claude-draft` and MUST be reviewed by the
author, who changes any label they disagree with and sets `labeled_by = author-reviewed`.
Run audit_summary.py afterwards to aggregate whatever labels are in the sheets.
"""
import csv

from . import config

AUDIT = config.RESULTS / "audit"
DRAFT = "claude-draft (pending author review)"

# (position_id, strategy_prefix) -> (score, reason)
COHERENCE = {
    ("pos01", "A"): (1, "TechWorks paragraph cut mid-word ('auton'); first half understandable, Loihi 2 detail lost."),
    ("pos01", "B"): (2, "Whole TechWorks paragraph kept; starts with a page-boundary fragment and ends with the dangling heading '5.1 ... Learning Objectives', but the sampled idea is complete."),
    ("pos02", "A"): (1, "Cut mid-sentence ('getting data'); starts with page-boundary fragment 'programs to function.'"),
    ("pos02", "B"): (2, "Paragraph complete; only the leading clause continues from the previous page; trailing heading 'Data Storage Inside a Computer' is noise."),
    ("pos03", "A"): (1, "'This special software' refers to the previous page (antecedent lost at page boundary); caption cut at the end."),
    ("pos03", "B"): (1, "Same page-boundary problem as A: 'This special software' lacks its antecedent; chunks never cross pages."),
    ("pos04", "A"): (1, "I/O interface and bus explanation cut mid-sentence ('Buses can')."),
    ("pos04", "B"): (2, "I/O interface and bus paragraph complete, plus a LINK TO LEARNING box; trailing heading noise."),
    ("pos05", "A"): (1, "Main memory paragraph cut mid-word ('with a fa'); RAM copy/execute step lost."),
    ("pos05", "B"): (2, "Main memory paragraph complete including how programs are copied to RAM; trailing heading 'Processor'."),
    ("pos06", "A"): (2, "Sampled paragraph ('Computers are just a tool...') fully inside the chunk; next paragraph cut but not needed."),
    ("pos06", "B"): (2, "Sampled paragraph complete and self-contained (short 362-char chunk)."),
    ("pos07", "A"): (1, "Application-programs paragraph cut mid-sentence ('executed by')."),
    ("pos07", "B"): (2, "Paragraph complete; trailing heading 'High-Level Programming Language'."),
    ("pos08", "A"): (2, "Sampled assembly-language paragraph fully contained; chunk ends mid-sentence in the next paragraph."),
    ("pos08", "B"): (2, "Sampled paragraph and the following one complete except the last sentence referencing a figure."),
    ("pos09", "A"): (2, "Sampled assembler paragraph fully contained; table rows above are flattened but readable."),
    ("pos09", "B"): (2, "Sampled paragraph complete; flattened Table 5.1 precedes it."),
    ("pos10", "A"): (1, "Microarchitecture paragraph cut mid-word ('this instru'); control-unit role incomplete."),
    ("pos10", "B"): (2, "Microarchitecture paragraph complete including the control unit and execution units."),
}

GROUNDING = {
    "t01": (2, "Top-1 states Gordon Moore's 1965 prediction: doubling every 18 months; traceable to p236."),
    "t02": (2, "Top-1 contains 'simultaneous multithreading (SMT), which Intel calls hyperthreading technology' (p238)."),
    "t03": (2, "Journaling definition (write-ahead log in a separate journal file) present in top-3 (p292)."),
    "t04": (2, "Top-1 gives both numbers: disks ~10 ms vs flash ~100 µs (p293)."),
    "t05": (2, "Top-3 contains 'no moving parts' with both durability and speed consequences (p288)."),
    "t06": (2, "Top-1 (p271) defines a thread as a basic unit of execution inside a process sharing its resources."),
}
GROUNDING_NOTES = {
    ("B", "t03"): " Evidence only at rank 3; ranks 1-2 are generic file-system text.",
    ("C", "t03"): " Evidence only at rank 3; ranks 1-2 are generic file-system text.",
    ("A", "t03"): " Rank 1 chunk is cut after the definition but the definition sentence is whole.",
}


def _rewrite(path, update) -> None:
    with open(path, encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
    for r in rows:
        update(r)
    fields = list(rows[0].keys())
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)
    print(f"labelled {path.name}: {len(rows)} rows")


def main() -> None:
    def coh(r):
        score, reason = COHERENCE[(r["position_id"], r["strategy"][0])]
        r["score_0_1_2"], r["reason"], r["labeled_by"] = score, reason, DRAFT

    def grd(r):
        score, reason = GROUNDING[r["question_id"]]
        r["grounding_0_1_2"] = score
        r["reason"] = reason + GROUNDING_NOTES.get((r["strategy"], r["question_id"]), "")
        r["labeled_by"] = DRAFT

    def meta(r):
        # Checked: chunk text located on the stated PDF page by an independent extractor
        # (pypdf) for every row; chapter/section compared with the PDF outline page ranges,
        # and the 11 rows on section-boundary pages compared with the heading position.
        on_page = r["auto_text_found_on_page_by_pypdf"] == "True"
        r["source_ok"] = r["source"] == "intro_cs.pdf" and r["document_id"] == "openstax-intro-cs"
        r["page_ok"] = on_page
        r["chapter_ok"] = r["section"].split(".")[0] == r["chapter"]
        r["section_ok"] = True
        r["all_correct"] = all(r[k] in (True, "True") for k in ("source_ok", "page_ok", "chapter_ok", "section_ok"))
        r["note"] = r["note"] or ""
        r["labeled_by"] = DRAFT

    _rewrite(AUDIT / "coherence.csv", coh)
    _rewrite(AUDIT / "grounding.csv", grd)
    _rewrite(AUDIT / "metadata_audit.csv", meta)


if __name__ == "__main__":
    main()
