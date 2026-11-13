"""Fixed-size and structure-aware chunking.

Chunks never cross a page boundary so `page` stays exact for traceability.
Page text is expected to be normalised with paragraphs separated by a blank line.
"""
import re

from .models import Chunk, DocumentPage

_SENTENCE_END = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9\"'(])")


def _make_chunk(page: DocumentPage, strategy: str, idx: int, text: str, start: int, end: int) -> Chunk:
    meta = {k: v for k, v in page.metadata.items() if k != "section_marks"}
    # Section in effect at the chunk start (a heading starting inside the chunk is
    # applied only if the chunk begins with that heading).
    for offset, section, title in page.metadata.get("section_marks", []):
        if offset <= start:
            meta["section"], meta["section_title"] = section, title
    return Chunk(
        chunk_id=f"{strategy}:{page.document_id}:p{page.page}:c{idx}",
        document_id=page.document_id,
        source=page.source,
        page=page.page,
        text=text,
        metadata={**meta, "char_start": start, "char_end": end},
    )


def fixed_size(page: DocumentPage, size: int, overlap: int, strategy: str = "A") -> list[Chunk]:
    """Sliding character window of `size` with `overlap`, ignoring structure."""
    if size <= 0 or not 0 <= overlap < size:
        raise ValueError("require size > 0 and 0 <= overlap < size")
    text = page.text
    chunks: list[Chunk] = []
    step = size - overlap
    start = 0
    while start < len(text):
        end = min(start + size, len(text))
        piece = text[start:end]
        if piece.strip():
            chunks.append(_make_chunk(page, strategy, len(chunks), piece.strip(), start, end))
        if end == len(text):
            break
        start += step
    return chunks


def _paragraph_spans(text: str) -> list[tuple[int, int]]:
    spans = []
    for m in re.finditer(r"[^\n](?:.|\n(?!\n))*", text):
        if m.group().strip():
            spans.append((m.start(), m.end()))
    return spans


def _split_long(text: str, start: int, end: int, max_size: int) -> list[tuple[int, int]]:
    """Split one oversized paragraph at sentence boundaries (hard cut as last resort)."""
    # sentence spans
    bounds = [start] + [start + m.start() for m in _SENTENCE_END.finditer(text[start:end])] + [end]
    sentences = []
    for s, e in zip(bounds, bounds[1:]):
        while e - s > max_size:  # single sentence too long: hard cut
            sentences.append((s, s + max_size))
            s += max_size
        if e > s:
            sentences.append((s, e))
    pieces: list[tuple[int, int]] = []
    seg_start, seg_end = sentences[0]
    for s, e in sentences[1:]:
        if e - seg_start <= max_size:
            seg_end = e
        else:
            pieces.append((seg_start, seg_end))
            seg_start, seg_end = s, e
    pieces.append((seg_start, seg_end))
    return pieces


def by_paragraph(page: DocumentPage, max_size: int, strategy: str = "B") -> list[Chunk]:
    """Greedily merge consecutive paragraphs (headings are their own paragraph) up to
    `max_size` chars; oversized paragraphs are split by sentence."""
    text = page.text
    units: list[tuple[int, int]] = []
    for s, e in _paragraph_spans(text):
        units.extend(_split_long(text, s, e, max_size) if e - s > max_size else [(s, e)])

    chunks: list[Chunk] = []
    cur_start = cur_end = None
    for s, e in units:
        if cur_start is None:
            cur_start, cur_end = s, e
        elif e - cur_start <= max_size:
            cur_end = e
        else:
            chunks.append(_make_chunk(page, strategy, len(chunks), text[cur_start:cur_end].strip(), cur_start, cur_end))
            cur_start, cur_end = s, e
    if cur_start is not None:
        chunks.append(_make_chunk(page, strategy, len(chunks), text[cur_start:cur_end].strip(), cur_start, cur_end))
    return chunks
