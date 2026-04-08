import re
from datetime import datetime, timezone
from typing import Dict, List
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

from backend.app.config import settings
from backend.app.models import SourceDoc, UserProfile
from backend.app.services.embedding_service import EmbeddingService


class RetrieverService:
    STOPWORDS = {
        "a",
        "an",
        "and",
        "are",
        "at",
        "for",
        "from",
        "happening",
        "how",
        "in",
        "is",
        "it",
        "latest",
        "me",
        "new",
        "news",
        "of",
        "on",
        "show",
        "the",
        "this",
        "to",
        "today",
        "what",
        "whats",
        "with",
    }

    WORLD_NEWS_TERMS = {
        "conflict",
        "crisis",
        "gaza",
        "geopolitics",
        "hamas",
        "iran",
        "iraq",
        "israel",
        "lebanon",
        "middle",
        "palestine",
        "saudi",
        "syria",
        "ukraine",
        "war",
        "world",
    }

    TECH_TERMS = {
        "ai",
        "apple",
        "coding",
        "developer",
        "github",
        "llm",
        "macbook",
        "nvidia",
        "openai",
        "software",
        "startup",
        "tech",
    }

    RESEARCH_TERMS = {
        "arxiv",
        "benchmark",
        "breakthrough",
        "method",
        "model",
        "paper",
        "preprint",
        "publication",
        "research",
        "study",
    }

    SPORTS_TERMS = {
        "basketball",
        "epl",
        "fifa",
        "football",
        "game",
        "match",
        "mlb",
        "nba",
        "nfl",
        "nhl",
        "player",
        "score",
        "sports",
        "team",
    }

    def __init__(self, embedding_service: EmbeddingService):
        self.embedding_service = embedding_service

    @staticmethod
    def _normalize_token(token: str) -> str:
        return token.strip(".,:;!?()[]{}\"'").lower()

    def _tokenize(self, text: str) -> set[str]:
        tokens = {self._normalize_token(token) for token in text.split() if self._normalize_token(token)}
        return {token for token in tokens if token not in self.STOPWORDS and len(token) > 1}

    def _detect_intent(self, query_tokens: set[str]) -> str:
        if query_tokens.intersection(self.WORLD_NEWS_TERMS):
            return "general"
        if query_tokens.intersection(self.SPORTS_TERMS):
            return "sports"
        if query_tokens.intersection(self.RESEARCH_TERMS):
            return "research"
        if query_tokens.intersection(self.TECH_TERMS):
            return "tech"
        return "mixed"

    async def rank(
        self,
        query: str,
        docs: List[SourceDoc],
        top_k: int,
        profile: UserProfile,
        follows: List[str],
        cached_embeddings: Dict[str, List[float]] | None = None,
    ) -> tuple[List[SourceDoc], Dict[str, List[float]], List[float]]:
        if not docs:
            return [], {}, []

        cached_embeddings = cached_embeddings or {}
        query_tokens = self._tokenize(query)
        intent = self._detect_intent(query_tokens)
        query_embedding = await self.embedding_service.embed(query)
        now = datetime.now(tz=timezone.utc)

        follows_lower = {item.lower() for item in follows}
        pref_categories = set(profile.preferred_categories)

        computed_embeddings: Dict[str, List[float]] = {}

        for doc in docs:
            text_tokens = self._tokenize(f"{doc.title} {doc.summary}")
            lexical = len(query_tokens.intersection(text_tokens))

            recency = 0.0
            if doc.published_at:
                published = doc.published_at
                if published.tzinfo is None:
                    published = published.replace(tzinfo=timezone.utc)
                days_old = max((now - published).days, 0)
                recency = max(0.0, 14.0 - min(days_old, 14)) / 14.0

            canonical = self._canonical(doc.url)
            doc_embedding = cached_embeddings.get(canonical)
            if not doc_embedding:
                doc_embedding = await self.embedding_service.embed(f"{doc.title}\n{doc.summary}")
                computed_embeddings[canonical] = doc_embedding
            semantic = (self.embedding_service.cosine(query_embedding, doc_embedding) + 1.0) / 2.0

            personalization = 0.0
            if doc.category in pref_categories:
                personalization += 0.5
            if follows_lower and any(tag.lower() in follows_lower for tag in doc.entity_tags):
                personalization += 0.5

            category_alignment = self._category_alignment(intent, doc.category)

            total = (
                (settings.semantic_weight * semantic)
                + (settings.lexical_weight * lexical)
                + (settings.recency_weight * recency)
                + (settings.credibility_weight * doc.credibility_score)
                + (settings.personalization_weight * personalization)
                + category_alignment
            )

            doc.semantic_score = round(float(semantic), 4)
            doc.lexical_score = round(float(lexical), 4)
            doc.recency_score = round(float(recency), 4)
            doc.personalization_score = round(float(personalization), 4)
            doc.total_score = round(float(total), 4)

        ranked = sorted(docs, key=lambda item: item.total_score, reverse=True)
        ranked = [doc for doc in ranked if self._is_relevant(doc, query_tokens, intent)]
        top_docs = ranked[:top_k]

        return top_docs, computed_embeddings, query_embedding

    def _category_alignment(self, intent: str, category: str) -> float:
        if intent == "mixed":
            return 0.0
        if intent == category:
            return 1.2
        return -0.4

    def _is_relevant(self, doc: SourceDoc, query_tokens: set[str], intent: str) -> bool:
        # Keep broad queries from falling back to unrelated fresh documents.
        if intent != "mixed" and doc.category != intent and doc.lexical_score < 2:
            return False
        if doc.lexical_score >= 1:
            return True
        if len(query_tokens) <= 2 and doc.semantic_score >= 0.78:
            return True
        if len(query_tokens) > 2 and doc.semantic_score >= 0.72:
            return True
        return False

    def _canonical(self, url: str) -> str:
        clean = (url or "").strip()
        if not clean:
            return "urn:missing"
        parsed = urlparse(clean)
        netloc = parsed.netloc.lower().replace("www.", "")
        path = re.sub(r"/+", "/", parsed.path or "/")
        query_pairs = [(k, v) for k, v in parse_qsl(parsed.query, keep_blank_values=True) if not k.lower().startswith("utm_")]
        query = urlencode(sorted(query_pairs))
        return urlunparse((parsed.scheme or "https", netloc, path.rstrip("/") or "/", "", query, ""))