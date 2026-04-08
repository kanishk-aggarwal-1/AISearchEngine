import asyncio
import hashlib
import re
from typing import List
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

from backend.app.config import settings
from backend.app.models import Category, SourceDoc
from backend.app.services.logging_service import get_logger

try:
    from qdrant_client import QdrantClient
    from qdrant_client.http import models as qmodels
except Exception:  # pragma: no cover
    QdrantClient = None
    qmodels = None


class VectorIndexService:
    def __init__(self) -> None:
        self.logger = get_logger("signalscope.vector")
        self.client = None
        self.enabled = False

        if settings.vector_backend.lower() == "qdrant" and settings.qdrant_url and QdrantClient is not None:
            try:
                self.client = QdrantClient(url=settings.qdrant_url, api_key=settings.qdrant_api_key or None)
                self.enabled = True
            except Exception as exc:
                self.logger.warning("vector_init_failed error=%s", exc)

    async def ensure_collection(self, vector_size: int) -> None:
        if not self.enabled or not self.client or not qmodels:
            return

        def _ensure() -> None:
            if not self.client.collection_exists(settings.qdrant_collection):
                self.client.create_collection(
                    collection_name=settings.qdrant_collection,
                    vectors_config=qmodels.VectorParams(size=vector_size, distance=qmodels.Distance.COSINE),
                )

        await asyncio.to_thread(_ensure)

    async def upsert_documents(self, docs: List[SourceDoc], embeddings: dict[str, List[float]]) -> int:
        if not self.enabled or not self.client or not qmodels:
            return 0

        points = []
        for doc in docs:
            canonical = self._canonical_key(doc)
            vector = embeddings.get(canonical)
            if not vector:
                continue

            payload = doc.model_dump(mode="json")
            payload["canonical_url"] = canonical
            payload["category"] = str(doc.category)
            payload["source"] = doc.source

            pid = int(hashlib.md5(canonical.encode("utf-8")).hexdigest()[:15], 16)
            points.append(qmodels.PointStruct(id=pid, vector=vector, payload=payload))

        if not points:
            return 0

        await self.ensure_collection(len(points[0].vector))

        def _upsert() -> None:
            self.client.upsert(collection_name=settings.qdrant_collection, points=points)

        await asyncio.to_thread(_upsert)
        return len(points)

    async def search(self, query_embedding: List[float], categories: List[Category], limit: int) -> List[SourceDoc]:
        if not self.enabled or not self.client or not qmodels or not query_embedding:
            return []

        cats = [str(item) for item in categories]

        def _search():
            query_filter = qmodels.Filter(
                must=[qmodels.FieldCondition(key="category", match=qmodels.MatchAny(any=cats))]
            )
            return self.client.search(
                collection_name=settings.qdrant_collection,
                query_vector=query_embedding,
                query_filter=query_filter,
                limit=limit,
                with_payload=True,
            )

        try:
            rows = await asyncio.to_thread(_search)
        except Exception as exc:
            self.logger.warning("vector_search_failed error=%s", exc)
            return []

        docs: List[SourceDoc] = []
        for row in rows:
            payload = row.payload or {}
            try:
                doc = SourceDoc.model_validate(payload)
                doc.semantic_score = float(row.score)
                docs.append(doc)
            except Exception:
                continue
        return docs

    def _canonical_key(self, doc: SourceDoc) -> str:
        raw = (doc.url or "").strip()
        if not raw:
            return f"urn:{doc.source}:{doc.title}".lower()
        parsed = urlparse(raw)
        netloc = parsed.netloc.lower().replace("www.", "")
        path = re.sub(r"/+", "/", parsed.path or "/")
        query_pairs = [(k, v) for k, v in parse_qsl(parsed.query, keep_blank_values=True) if not k.lower().startswith("utm_")]
        query = urlencode(sorted(query_pairs))
        return urlunparse((parsed.scheme or "https", netloc, path.rstrip("/") or "/", "", query, ""))
