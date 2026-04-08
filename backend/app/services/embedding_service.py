import hashlib
import math
from typing import List

from openai import AsyncOpenAI

from backend.app.config import settings

try:
    from google import genai
except Exception:  # pragma: no cover
    genai = None


class EmbeddingService:
    def __init__(self) -> None:
        self.openai_client = AsyncOpenAI(api_key=settings.openai_api_key) if settings.openai_api_key else None
        self.gemini_client = genai.Client(api_key=settings.gemini_api_key) if settings.gemini_api_key and genai else None
        self.dim = 64

    @property
    def real_embeddings_enabled(self) -> bool:
        return bool(self.gemini_client or self.openai_client)

    async def embed(self, text: str) -> List[float]:
        clean = (text or "").strip()
        if not clean:
            return [0.0] * self.dim

        if self.gemini_client:
            try:
                response = self.gemini_client.models.embed_content(
                    model="gemini-embedding-001",
                    contents=clean,
                )
                vector = list(response.embeddings[0].values)
                self.dim = len(vector)
                return vector
            except Exception:
                if settings.strict_real_embeddings:
                    raise

        if self.openai_client:
            try:
                response = await self.openai_client.embeddings.create(model=settings.embedding_model, input=clean)
                vector = response.data[0].embedding
                self.dim = len(vector)
                return vector
            except Exception:
                if settings.strict_real_embeddings:
                    raise

        if settings.strict_real_embeddings:
            raise RuntimeError("Strict real embeddings is enabled, but no embedding provider succeeded.")

        return self._hash_embedding(clean)

    def cosine(self, a: List[float], b: List[float]) -> float:
        if not a or not b:
            return 0.0
        n = min(len(a), len(b))
        dot = sum(a[i] * b[i] for i in range(n))
        na = math.sqrt(sum(a[i] * a[i] for i in range(n)))
        nb = math.sqrt(sum(b[i] * b[i] for i in range(n)))
        if na == 0 or nb == 0:
            return 0.0
        return max(-1.0, min(1.0, dot / (na * nb)))

    def _hash_embedding(self, text: str) -> List[float]:
        vec = [0.0] * self.dim
        tokens = [token.lower().strip(".,:;!?()[]{}\"'") for token in text.split() if token.strip()]
        if not tokens:
            return vec

        for token in tokens:
            digest = hashlib.sha256(token.encode("utf-8")).hexdigest()
            idx = int(digest[:8], 16) % self.dim
            sign = 1.0 if int(digest[8:10], 16) % 2 == 0 else -1.0
            vec[idx] += sign

        norm = math.sqrt(sum(x * x for x in vec)) or 1.0
        return [x / norm for x in vec]