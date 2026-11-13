"""Store and search vectors using PostgreSQL + pgvector (exact cosine search)."""
import hashlib
from typing import Any

import psycopg
from pgvector.psycopg import register_vector
import numpy as np

from .models import Chunk

# Metadata columns that may be used as filters (whitelist -> no SQL injection via keys).
FILTER_COLUMNS = {"chapter": "chapter", "section": "section", "document_id": "document_id"}


def content_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


class PgVectorStore:
    def __init__(self, database_url: str, dimensions: int, table: str = "chunks") -> None:
        if not database_url:
            raise ValueError("DATABASE_URL missing")
        if dimensions <= 0:
            raise ValueError("dimensions must be positive")
        if not table.isidentifier():
            raise ValueError("invalid table name")
        self.database_url = database_url
        self.dimensions = dimensions
        self.table = table

    def _connect(self) -> psycopg.Connection:
        # Raises psycopg.OperationalError if the backend is down; caller must not fall back.
        conn = psycopg.connect(self.database_url, connect_timeout=5)
        register_vector(conn)
        return conn

    def create_schema(self) -> None:
        with self._connect() as conn:
            conn.execute("CREATE EXTENSION IF NOT EXISTS vector")
            conn.execute(
                f"""
                CREATE TABLE IF NOT EXISTS {self.table} (
                    chunk_id      TEXT PRIMARY KEY,
                    strategy      TEXT NOT NULL,
                    document_id   TEXT NOT NULL,
                    source        TEXT NOT NULL,
                    page          INTEGER NOT NULL,
                    chapter       INTEGER,
                    section       TEXT,
                    section_title TEXT,
                    char_start    INTEGER,
                    char_end      INTEGER,
                    text          TEXT NOT NULL,
                    content_hash  TEXT NOT NULL,
                    model         TEXT NOT NULL,
                    embedding     vector({self.dimensions}) NOT NULL,
                    updated_at    TIMESTAMPTZ NOT NULL DEFAULT now()
                )
                """
            )
            conn.execute(
                f"CREATE INDEX IF NOT EXISTS {self.table}_strategy_chapter_idx "
                f"ON {self.table} (strategy, chapter)"
            )
            # Detect dimension mismatch with an existing table.
            row = conn.execute(
                "SELECT atttypmod FROM pg_attribute WHERE attrelid = %s::regclass AND attname = 'embedding'",
                (self.table,),
            ).fetchone()
            if row and row[0] != self.dimensions:
                raise RuntimeError(f"Table {self.table} has vector({row[0]}), model gives {self.dimensions}")

    def upsert(self, strategy: str, chunks: list[Chunk], vectors: list[list[float]], model: str) -> dict[str, int]:
        """Idempotent write: stable IDs, update only changed rows, delete obsolete chunks
        of the re-ingested documents for this strategy."""
        if len(chunks) != len(vectors):
            raise ValueError(f"{len(chunks)} chunks but {len(vectors)} vectors")
        for v in vectors:
            if len(v) != self.dimensions:
                raise ValueError(f"vector has {len(v)} dims, expected {self.dimensions}")
        ids = [c.chunk_id for c in chunks]
        if len(set(ids)) != len(ids):
            raise ValueError("duplicate chunk_id in batch")

        inserted_or_updated = 0
        with self._connect() as conn:
            with conn.cursor() as cur:
                for c, v in zip(chunks, vectors):
                    cur.execute(
                        f"""
                        INSERT INTO {self.table} (chunk_id, strategy, document_id, source, page, chapter,
                            section, section_title, char_start, char_end, text, content_hash, model, embedding)
                        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                        ON CONFLICT (chunk_id) DO UPDATE SET
                            source = EXCLUDED.source, page = EXCLUDED.page, chapter = EXCLUDED.chapter,
                            section = EXCLUDED.section, section_title = EXCLUDED.section_title,
                            char_start = EXCLUDED.char_start, char_end = EXCLUDED.char_end,
                            text = EXCLUDED.text, content_hash = EXCLUDED.content_hash,
                            model = EXCLUDED.model, embedding = EXCLUDED.embedding, updated_at = now()
                        WHERE {self.table}.content_hash IS DISTINCT FROM EXCLUDED.content_hash
                           OR {self.table}.model IS DISTINCT FROM EXCLUDED.model
                        """,
                        (
                            c.chunk_id, strategy, c.document_id, c.source, c.page,
                            c.metadata.get("chapter"), c.metadata.get("section"),
                            c.metadata.get("section_title"), c.metadata.get("char_start"),
                            c.metadata.get("char_end"), c.text, content_hash(c.text), model,
                            np.asarray(v, dtype=np.float32),
                        ),
                    )
                    inserted_or_updated += cur.rowcount
                doc_ids = sorted({c.document_id for c in chunks})
                cur.execute(
                    f"DELETE FROM {self.table} WHERE strategy = %s AND document_id = ANY(%s) "
                    f"AND NOT (chunk_id = ANY(%s))",
                    (strategy, doc_ids, ids),
                )
                deleted = cur.rowcount
        return {"written": inserted_or_updated, "deleted_obsolete": deleted, "batch": len(chunks)}

    def count(self, strategy: str) -> int:
        with self._connect() as conn:
            return conn.execute(
                f"SELECT COUNT(*) FROM {self.table} WHERE strategy = %s", (strategy,)
            ).fetchone()[0]

    def search(self, strategy: str, query_vector: list[float], top_k: int = 3,
               filters: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        if len(query_vector) != self.dimensions:
            raise ValueError("query vector dimension mismatch")
        where = ["strategy = %s"]
        params: list[Any] = [strategy]
        for key, value in (filters or {}).items():
            if key not in FILTER_COLUMNS:
                raise ValueError(f"filter field not allowed: {key}")
            where.append(f"{FILTER_COLUMNS[key]} = %s")
            params.append(value)
        qv = np.asarray(query_vector, dtype=np.float32)
        sql = (
            f"SELECT chunk_id, document_id, source, page, chapter, section, section_title, "
            f"char_start, char_end, text, 1 - (embedding <=> %s) AS score "
            f"FROM {self.table} WHERE {' AND '.join(where)} "
            f"ORDER BY embedding <=> %s LIMIT %s"
        )
        with self._connect() as conn:
            rows = conn.execute(sql, [qv, *params, qv, top_k]).fetchall()
        cols = ["chunk_id", "document_id", "source", "page", "chapter", "section", "section_title",
                "char_start", "char_end", "text", "score"]
        return [dict(zip(cols, r)) | {"score": float(r[-1])} for r in rows]
