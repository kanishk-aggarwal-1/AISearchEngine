import re
from datetime import datetime, timezone
from typing import Dict, List
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

from backend.app.config import settings
from backend.app.models import ChunkHit, SourceDoc, UserProfile
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

    QUERY_EXPANSIONS = {
        "ai": {"artificial", "intelligence", "llm", "model"},
        "llm": {"ai", "model", "language"},
        "nba": {"basketball", "sports"},
        "nfl": {"football", "sports"},
        "mlb": {"baseball", "sports"},
        "research": {"paper", "study", "method"},
        "paper": {"research", "study", "preprint"},
        "war": {"conflict", "crisis"},
        "conflict": {"war", "crisis"},
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

    def _expanded_tokens(self, tokens: set[str]) -> set[str]:
        expanded = set(tokens)
        for token in list(tokens):
            expanded.update(self.QUERY_EXPANSIONS.get(token, set()))
        return expanded

    def analyze_query(self, query: str, categories: List[str] | None = None) -> dict[str, object]:
        raw = " ".join((query or "").split()).strip()
        query_tokens = self._tokenize(raw)
        intent = self._detect_intent(query_tokens)
        rewritten = raw

        if raw:
            compact_tokens = [token for token in raw.split() if self._normalize_token(token) not in self.STOPWORDS]
            compact = " ".join(compact_tokens).strip() or raw
            rewritten = compact

            if intent == "general" and "world" not in compact.lower() and "news" not in compact.lower():
                rewritten = f"{compact} world news"
            elif intent == "research" and "paper" not in compact.lower() and "research" not in compact.lower():
                rewritten = f"{compact} research papers"
            elif intent == "sports" and "score" not in compact.lower() and "sports" not in compact.lower():
                rewritten = f"{compact} latest scores"
            elif categories and categories == ["tech"] and "tech" not in compact.lower():
                rewritten = f"{compact} tech updates"

        return {
            "raw_query": raw,
            "rewritten_query": rewritten.strip() or raw,
            "tokens": sorted(query_tokens),
            "intent": intent,
        }

    async def rank(
        self,
        query: str,
        docs: List[SourceDoc],
        top_k: int,
        profile: UserProfile,
        follows: List[str],
        cached_embeddings: Dict[str, List[float]] | None = None,
        chunk_hits_by_doc: Dict[str, ChunkHit] | None = None,
        query_embedding: List[float] | None = None,
    ) -> tuple[List[SourceDoc], Dict[str, List[float]], List[float]]:
        if not docs:
            return [], {}, []

        cached_embeddings = cached_embeddings or {}
        chunk_hits_by_doc = chunk_hits_by_doc or {}
        query_tokens = self._tokenize(query)
        expanded_query_tokens = self._expanded_tokens(query_tokens)
        intent = self._detect_intent(query_tokens)
        query_embedding = query_embedding or await self.embedding_service.embed(query)
        now = datetime.now(tz=timezone.utc)

        follows_lower = {item.lower() for item in follows}
        pref_categories = set(profile.preferred_categories)

        computed_embeddings: Dict[str, List[float]] = {}

        for doc in docs:
            text_tokens = self._tokenize(f"{doc.title} {doc.summary}")
            expanded_text_tokens = self._expanded_tokens(text_tokens)
            lexical = len(expanded_query_tokens.intersection(expanded_text_tokens))
            coverage = 0.0
            if expanded_query_tokens:
                coverage = len(expanded_query_tokens.intersection(expanded_text_tokens)) / max(len(expanded_query_tokens), 1)
            title_tokens = self._tokenize(doc.title)
            title_overlap = len(query_tokens.intersection(title_tokens))
            query_phrase = " ".join(query.lower().split())
            phrase_boost = 1.0 if query_phrase and query_phrase in f"{doc.title} {doc.summary}".lower() else 0.0

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
            top_chunk = chunk_hits_by_doc.get(canonical)
            chunk_bonus = 0.0
            if top_chunk:
                lexical = max(lexical, top_chunk.lexical_score)
                semantic = max(semantic, top_chunk.semantic_score)
                chunk_bonus = top_chunk.total_score
                if top_chunk.text:
                    doc.citation_snippet = top_chunk.text[:280]

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
                + (settings.chunk_weight * chunk_bonus)
                + (settings.coverage_weight * coverage)
                + (settings.exact_phrase_weight * phrase_boost)
                + (settings.title_match_weight * min(title_overlap, 2))
                + category_alignment
            )

            doc.semantic_score = round(float(semantic), 4)
            doc.lexical_score = round(float(lexical), 4)
            doc.recency_score = round(float(recency), 4)
            doc.personalization_score = round(float(personalization), 4)
            doc.total_score = round(float(total), 4)

        ranked = sorted(docs, key=lambda item: item.total_score, reverse=True)
        ranked = [doc for doc in ranked if self._is_relevant(doc, query_tokens, intent)]
        ranked = self._diversify_sources(ranked)
        top_docs = ranked[:top_k]

        return top_docs, computed_embeddings, query_embedding

    async def rank_chunks(
        self,
        query: str,
        chunks: List[ChunkHit],
        cached_embeddings: Dict[str, List[float]] | None = None,
        query_embedding: List[float] | None = None,
    ) -> tuple[List[ChunkHit], Dict[str, List[float]], List[float]]:
        if not chunks:
            return [], {}, query_embedding or []

        cached_embeddings = cached_embeddings or {}
        query_tokens = self._tokenize(query)
        query_embedding = query_embedding or await self.embedding_service.embed(query)
        computed_embeddings: Dict[str, List[float]] = {}

        for chunk in chunks:
            chunk_tokens = self._tokenize(chunk.text)
            lexical = len(query_tokens.intersection(chunk_tokens))
            chunk_embedding = cached_embeddings.get(chunk.chunk_id)
            if not chunk_embedding:
                chunk_embedding = await self.embedding_service.embed(chunk.text)
                computed_embeddings[chunk.chunk_id] = chunk_embedding
            semantic = (self.embedding_service.cosine(query_embedding, chunk_embedding) + 1.0) / 2.0
            total = (settings.semantic_weight * semantic) + (settings.lexical_weight * lexical)
            chunk.semantic_score = round(float(semantic), 4)
            chunk.lexical_score = round(float(lexical), 4)
            chunk.total_score = round(float(total), 4)

        ranked = sorted(chunks, key=lambda item: item.total_score, reverse=True)
        return ranked[: settings.chunk_top_k], computed_embeddings, query_embedding

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

    def _diversify_sources(self, docs: List[SourceDoc]) -> List[SourceDoc]:
        seen_sources: dict[str, int] = {}
        diversified: List[SourceDoc] = []
        rescored: List[SourceDoc] = []
        for doc in docs:
            count = seen_sources.get(doc.source.lower(), 0)
            doc.total_score = round(float(doc.total_score - (settings.source_diversity_penalty * count)), 4)
            rescored.append(doc)
            seen_sources[doc.source.lower()] = count + 1
        rescored.sort(key=lambda item: item.total_score, reverse=True)
        for doc in rescored:
            if any(existing.url == doc.url for existing in diversified):
                continue
            diversified.append(doc)
        return diversified

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
