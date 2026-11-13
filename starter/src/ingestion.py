"""Read and normalise PDF pages with PyMuPDF, keeping page numbers and section metadata.

Layout facts of the chosen OpenStax PDF (verified by inspecting font sizes):
  * body text: NotoSans-Regular 9.0pt
  * section heading "5.1 Computer Systems Organization": RobotoCondensed-Bold ~15.6pt
  * sub-heading: NotoSans-Bold ~13pt
  * running header/footer: 7.5pt bold at the top/bottom edge
"""
import logging
import re
import unicodedata
from pathlib import Path

import pymupdf

from .models import DocumentPage

log = logging.getLogger("ingestion")

SECTION_HEADING_MIN_SIZE = 14.5
SUBHEADING_MIN_SIZE = 11.5
EDGE_MARGIN = 45  # points from top/bottom treated as header/footer zone
_SECTION_RE = re.compile(r"^(\d+)\.(\d+)\s+(.+)$")
_CHAPTER_RE = re.compile(r"^Chapter\s+(\d+)\b")
_ATTRIBUTION_RE = re.compile(r"\s*\((?:attribution|credit)[^()]*(?:\([^()]*\)[^()]*)*\)", re.IGNORECASE)
_FOOTER_RE = re.compile(r"^(Access for free at openstax\.org|\d+\s+\d+\s*•.*|\d+\.\d+\s*•.*\s+\d+)$")
_LIGATURES = {"ﬀ": "ff", "ﬁ": "fi", "ﬂ": "fl", "ﬃ": "ffi", "ﬄ": "ffl"}


def normalize_text(text: str) -> str:
    """NFC-normalise, fix ligatures/odd spaces, de-hyphenate line breaks, collapse
    whitespace inside lines, keep blank lines as paragraph boundaries."""
    text = unicodedata.normalize("NFC", text)
    for k, v in _LIGATURES.items():
        text = text.replace(k, v)
    text = text.replace("­", "").replace(" ", " ").replace("​", "")
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    paragraphs = re.split(r"\n\s*\n", text)
    out = []
    for p in paragraphs:
        lines = [re.sub(r"[ \t]+", " ", ln).strip() for ln in p.split("\n")]
        lines = [ln for ln in lines if ln]
        if not lines:
            continue
        merged = lines[0]
        for ln in lines[1:]:
            if ln.startswith("•"):
                merged += "\n" + ln
            elif re.search(r"[A-Za-z]-$", merged) and ln[:1].islower():
                merged = merged[:-1] + ln  # de-hyphenate "compu-\nter"
            else:
                merged += " " + ln
        out.append(merged)
    return "\n\n".join(out)


def strip_attribution(para: str) -> str:
    """Remove figure image-licence credits, including fragments split across a page break:
    '(attribution: ... license)', a trailing '(attribution: ... under' and a leading
    '... CC BY NC-SA 4.0 license)' / 'Copyright Rice University ... license)'."""
    para = _ATTRIBUTION_RE.sub("", para)
    para = re.sub(r"\s*\((?:attribution|credit):[^()]*$", "", para, flags=re.IGNORECASE)
    para = re.sub(r"^[^()]*\blicense\)\s*", "", para) if re.match(r"^[^()]*\blicense\)", para) else para
    return para.strip()


def _block_text(block: dict) -> tuple[str, float, bool]:
    lines, sizes, bold = [], [], True
    for line in block["lines"]:
        spans = line["spans"]
        lines.append("".join(s["text"] for s in spans))
        for s in spans:
            if s["text"].strip():
                sizes.append(s["size"])
                bold = bold and ("Bold" in s["font"] or bool(s["flags"] & 16))
    return "\n".join(lines), (max(sizes) if sizes else 0.0), bold


def load_pdf(path: Path, document_id: str, source: str, pages: list[int] | None = None,
             errors: list[dict] | None = None) -> list[DocumentPage]:
    """Extract physical pages (1-based numbers). Records empty/failed pages in `errors`.

    Each page gets metadata `chapter`, `section`, `section_title` (the section in effect
    at the top of the page) plus `section_marks` = [(char_offset, section, title)] for
    headings that start on the page, so chunks can inherit the right section.
    """
    errors = errors if errors is not None else []
    doc = pymupdf.open(path)
    wanted = pages or list(range(1, doc.page_count + 1))
    toc = doc.get_toc()

    def section_before(pno: int) -> dict:
        """Section in effect at the top of page `pno`, from the PDF outline (entries that
        start on an earlier page). Sections starting on `pno` itself are detected from the
        heading in the page text so the in-page offset is known."""
        cur = {"chapter": None, "section": None, "section_title": None}
        for _level, title, start in toc:
            if start >= pno:
                break
            title = title.strip()
            cm = _CHAPTER_RE.match(title)
            sm = _SECTION_RE.match(title)
            if cm:
                ch = int(cm.group(1))
                cur = {"chapter": ch, "section": f"{ch}.0", "section_title": "Chapter Introduction"}
            elif sm:
                cur = {"chapter": int(sm.group(1)), "section": f"{sm.group(1)}.{sm.group(2)}",
                       "section_title": sm.group(3).strip()}
        return cur

    current = section_before(wanted[0])
    result: list[DocumentPage] = []
    prev_page = None
    for pno in wanted:
        if prev_page is not None and pno != prev_page + 1:
            current = section_before(pno)  # gap in page list
        prev_page = pno
        # A chapter always starts on a fresh page: apply its outline entry at the page top.
        for _level, title, start in toc:
            cm = _CHAPTER_RE.match(title.strip())
            if cm and start == pno:
                ch = int(cm.group(1))
                current = {"chapter": ch, "section": f"{ch}.0", "section_title": "Chapter Introduction"}
        try:
            page = doc[pno - 1]
            height = page.rect.height
            page_meta = dict(current)
            parts: list[str] = []
            marks: list[tuple[int, str, str]] = []
            offset = 0
            for block in page.get_text("dict")["blocks"]:
                if block["type"] != 0:
                    continue
                raw, size, bold = _block_text(block)
                one_line = " ".join(raw.split())
                if not one_line:
                    continue
                y0, y1 = block["bbox"][1], block["bbox"][3]
                if (y1 < EDGE_MARGIN or y0 > height - EDGE_MARGIN) and size < 8.5:
                    continue  # running header / footer
                if _FOOTER_RE.match(one_line):
                    continue
                para = strip_attribution(normalize_text(raw))
                if not para:
                    continue
                if size >= SECTION_HEADING_MIN_SIZE:
                    m = _SECTION_RE.match(one_line)
                    if m:
                        current = {"chapter": int(m.group(1)), "section": f"{m.group(1)}.{m.group(2)}",
                                   "section_title": m.group(3).strip()}
                        marks.append((offset, current["section"], current["section_title"]))
                if parts:
                    offset += 2  # "\n\n" separator
                parts.append(para)
                offset += len(para)
            text = "\n\n".join(parts)
            assert offset == len(text), "offset bookkeeping error"
            if not text.strip():
                errors.append({"document_id": document_id, "page": pno, "error": "empty_text",
                               "detail": "no extractable text (image-only page?)"})
            result.append(DocumentPage(document_id=document_id, source=source, page=pno, text=text,
                                       metadata={**page_meta, "section_marks": marks}))
        except Exception as exc:  # record and continue; caller decides whether this is fatal
            log.exception("page %s failed", pno)
            errors.append({"document_id": document_id, "page": pno, "error": type(exc).__name__,
                           "detail": str(exc)})
    doc.close()
    return result
