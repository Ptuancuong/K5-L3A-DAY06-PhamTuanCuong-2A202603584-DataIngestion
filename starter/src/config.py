"""Single place for paths, corpus definition and the three strategies."""
import os
from pathlib import Path

from dotenv import load_dotenv

STARTER = Path(__file__).resolve().parents[1]
REPO = STARTER.parent
load_dotenv(STARTER / ".env")

DATA_DIR = REPO / "data"
MANIFEST = DATA_DIR / "manifest.json"
PAGES_JSONL = DATA_DIR / "pages.jsonl"
BENCHMARK = REPO / "benchmark" / "questions.jsonl"
RESULTS = REPO / "results"
ERRORS_LOG = RESULTS / "errors.log"

DATABASE_URL = os.getenv("DATABASE_URL", "")
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "")
TOP_K = 3

# A page inside the chosen section ranges counts as a content page if its normalised
# text has at least this many characters (filters figure-only / near-empty pages).
MIN_CONTENT_CHARS = 1000

SOURCES = [
    {
        "source_id": "openstax-intro-cs",
        "title": "Introduction to Computer Science (OpenStax)",
        "source_path_or_url": "https://assets.openstax.org/oscms-prodcms/media/documents/Introduction_To_Computer_Science_-_WEB.pdf",
        "book_page": "https://openstax.org/details/books/introduction-computer-science",
        "local_path": STARTER / "data" / "raw" / "intro_cs.pdf",
        "license_or_permission": "CC BY-NC-SA 4.0 (Creative Commons Attribution-NonCommercial-ShareAlike), "
                                 "as stated by the OpenStax CMS API license_name field",
        "attribution": "Access for free at openstax.org. Introduction to Computer Science, OpenStax, Rice University.",
        "version": "OpenStax web PDF; book first published 2024-10-29 (CMS API); last_updated_pdf not provided",
        "accessed_at": "2026-11-13T03:20:25Z",
        # Body pages of the two chosen chapters (PDF page numbers, 1-based).
        # Excluded by structure: chapter opener pages 203 & 249 (chapter outline + cover figure)
        # and Chapter Review / exercises (240-248, 295-306).
        "candidate_ranges": {5: (204, 239), 6: (250, 294)},
        "structural_exclusions": {
            "203": "Chapter 5 opener: chapter outline (table of contents) + cover figure",
            "240-248": "Chapter 5 Review: key terms, summary, review questions (not lesson content)",
            "249": "Chapter 6 opener: chapter outline (table of contents) + cover figure",
            "295-306": "Chapter 6 Review: key terms, summary, review questions (not lesson content)",
        },
    }
]

# Strategies. C reuses B's index (identical chunks and vectors) and differs ONLY in
# applying the question's metadata filter.
STRATEGIES = {
    "A": {"index": "A", "chunker": "fixed", "size": 500, "overlap": 50, "use_filter": False},
    "B": {"index": "B", "chunker": "paragraph", "max_size": 1000, "use_filter": False},
    "C": {"index": "B", "chunker": "paragraph", "max_size": 1000, "use_filter": True},
}
INDEXES = ["A", "B"]
