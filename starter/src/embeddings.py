"""Real local embedding provider (Sentence-Transformers). No mock fallback."""
from typing import Protocol


class Embedder(Protocol):
    model_name: str
    dimensions: int

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        """Return one vector per input text, in the same order."""
        ...

    def embed_query(self, question: str) -> list[float]:
        """Return a query vector compatible with the stored document vectors."""
        ...


class SentenceTransformerEmbedder:
    """Local Sentence-Transformers adapter.

    E5-family models expect "query: " / "passage: " prefixes; vectors are
    L2-normalised so cosine distance in pgvector is meaningful.
    Any loading/encoding error is raised -- never replaced by random vectors.
    """

    E5_PREFIXES = ("query: ", "passage: ")

    def __init__(self, model_name: str, device: str | None = None, batch_size: int = 32) -> None:
        if not model_name:
            raise ValueError("EMBEDDING_MODEL is empty; set it in starter/.env")
        import torch
        from sentence_transformers import SentenceTransformer

        self.model_name = model_name
        self.device = device or ("cuda" if torch.cuda.is_available() else "cpu")
        self.batch_size = batch_size
        self._model = SentenceTransformer(model_name, device=self.device)
        dims = self._model.get_sentence_embedding_dimension()
        if not dims:
            raise RuntimeError(f"Cannot determine embedding dimension for {model_name}")
        self.dimensions = int(dims)
        self.uses_e5_prefix = "e5" in model_name.lower()

    def _prefix(self, kind: str) -> str:
        if not self.uses_e5_prefix:
            return ""
        return self.E5_PREFIXES[0] if kind == "query" else self.E5_PREFIXES[1]

    def _encode(self, texts: list[str]) -> list[list[float]]:
        vectors = self._model.encode(
            texts,
            batch_size=self.batch_size,
            normalize_embeddings=True,
            convert_to_numpy=True,
            show_progress_bar=False,
        )
        return [v.astype(float).tolist() for v in vectors]

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        prefix = self._prefix("passage")
        return self._encode([prefix + t for t in texts])

    def embed_query(self, question: str) -> list[float]:
        return self._encode([self._prefix("query") + question])[0]
