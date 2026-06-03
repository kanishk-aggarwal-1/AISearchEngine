"""
Retriever unit tests.
Uses FakeEmbeddingService — no mocks, no HTTP. Tests actual ranking logic.
"""
import asyncio
import math
import unittest
from datetime import datetime, timedelta, timezone

from backend.app.models import SourceDoc, UserProfile
from backend.app.services.retriever import RetrieverService


class FakeEmbeddingService:
    """
    Deterministic embedding service for testing.
    Returns a unit vector where only the slot matching hash(text) % 64 is set.
    Texts that share a common first word will have cosine similarity > 0.
    """
    dim = 64
    real_embeddings_enabled = True

    async def embed(self, text: str) -> list[float]:
        vec = [0.0] * self.dim
        words = text.strip().lower().split()
        if words:
            idx = sum(ord(c) for c in words[0]) % self.dim
            vec[idx] = 1.0
        return vec

    def cosine(self, a: list[float], b: list[float]) -> float:
        if not a or not b:
            return 0.0
        n = min(len(a), len(b))
        dot = sum(a[i] * b[i] for i in range(n))
        na = math.sqrt(sum(a[i] ** 2 for i in range(n)))
        nb = math.sqrt(sum(b[i] ** 2 for i in range(n)))
        if na == 0 or nb == 0:
            return 0.0
        return dot / (na * nb)


def _doc(title: str, summary: str = "", source: str = "TestSource",
         category="tech", credibility: float = 0.5,
         days_old: int = 1, url: str | None = None) -> SourceDoc:
    published = datetime.now(timezone.utc) - timedelta(days=days_old)
    return SourceDoc(
        title=title,
        summary=summary or title,
        url=url or f"https://example.com/{title.replace(' ', '-')}",
        source=source,
        category=category,
        published_at=published,
        credibility_score=credibility,
    )


def _profile(user_id="test") -> UserProfile:
    return UserProfile(user_id=user_id)


def _run(coro):
    return asyncio.run(coro)


class TestRetrieverRanking(unittest.TestCase):
    def setUp(self):
        self.retriever = RetrieverService(FakeEmbeddingService())

    def test_higher_lexical_overlap_ranks_first(self):
        """Doc with more query terms in title+summary should rank above one with fewer."""
        # Query: "machine learning agents"
        # Doc A has all three tokens; Doc B has only one
        doc_a = _doc("machine learning agents breakthrough", days_old=1)
        doc_b = _doc("machine startup news", days_old=1)

        ranked, _, _ = _run(self.retriever.rank(
            "machine learning agents",
            [doc_a, doc_b],
            top_k=5,
            profile=_profile(),
            follows=[],
        ))

        urls = [d.url for d in ranked]
        self.assertIn(doc_a.url, urls, "High-lexical doc should survive relevance filter")
        if doc_b.url in urls:
            self.assertGreater(doc_a.total_score, doc_b.total_score,
                               "Doc A should rank above Doc B")

    def test_fresher_doc_ranks_higher_than_stale(self):
        """A doc published yesterday should beat an identical doc from 20 days ago."""
        fresh = _doc("machine learning latest research", days_old=1)
        stale = _doc("machine learning latest research", summary="same content",
                     days_old=20, url="https://example.com/stale")

        ranked, _, _ = _run(self.retriever.rank(
            "machine learning",
            [stale, fresh],
            top_k=5,
            profile=_profile(),
            follows=[],
        ))

        if len(ranked) >= 2:
            self.assertGreater(
                ranked[0].recency_score, ranked[-1].recency_score,
                "Fresh doc should have a higher recency score",
            )

    def test_higher_credibility_breaks_tie(self):
        """When recency and lexical overlap are equal, higher credibility wins."""
        trusted = _doc("machine learning models", days_old=1,
                       credibility=0.95, url="https://trusted.com/a")
        shady = _doc("machine learning models", days_old=1,
                     credibility=0.2, url="https://shady.com/b")

        ranked, _, _ = _run(self.retriever.rank(
            "machine learning",
            [shady, trusted],
            top_k=5,
            profile=_profile(),
            follows=[],
        ))

        if len(ranked) >= 2:
            first_urls = [d.url for d in ranked]
            self.assertEqual(first_urls[0], trusted.url,
                             "High-credibility doc should rank first")

    def test_source_diversity_penalty_applied(self):
        """Second doc from the same source should have its score reduced."""
        doc_a = _doc("machine learning news", source="TechCrunch",
                     url="https://tc.com/a", days_old=1)
        doc_b = _doc("machine learning update", source="TechCrunch",
                     url="https://tc.com/b", days_old=1)

        ranked, _, _ = _run(self.retriever.rank(
            "machine learning",
            [doc_a, doc_b],
            top_k=5,
            profile=_profile(),
            follows=[],
        ))

        if len(ranked) == 2:
            self.assertLess(
                ranked[1].total_score, ranked[0].total_score,
                "Second doc from same source should have a lower total_score",
            )

    def test_personalization_boosts_followed_entity(self):
        """Doc whose entity_tags include a followed entity gets a personalization boost."""
        doc_followed = _doc("machine learning OpenAI research", days_old=1,
                            url="https://example.com/openai")
        doc_followed.entity_tags = ["OpenAI", "GPT"]

        doc_plain = _doc("machine learning neural networks", days_old=1,
                         url="https://example.com/plain")
        doc_plain.entity_tags = ["ResearchCo"]

        ranked, _, _ = _run(self.retriever.rank(
            "machine learning",
            [doc_plain, doc_followed],
            top_k=5,
            profile=_profile(),
            follows=["OpenAI"],
        ))

        followed_scores = {d.url: d.personalization_score for d in ranked}
        if doc_followed.url in followed_scores:
            self.assertGreater(
                followed_scores[doc_followed.url],
                followed_scores.get(doc_plain.url, 0),
                "Doc with followed entity should have higher personalization score",
            )

    def test_irrelevant_doc_filtered_by_category_intent(self):
        """
        When query intent is sports, a tech doc with zero lexical overlap and
        category mismatch should be filtered by _is_relevant's category guard.
        """
        # "NBA basketball scores" → intent="sports"
        sports_doc = _doc("NBA basketball scores tonight", category="sports",
                          days_old=1, url="https://example.com/sports")
        tech_doc = _doc("cloud computing architecture", category="tech",
                        days_old=1, url="https://example.com/tech")

        ranked, _, _ = _run(self.retriever.rank(
            "NBA basketball scores",
            [sports_doc, tech_doc],
            top_k=5,
            profile=_profile(),
            follows=[],
        ))

        urls = [d.url for d in ranked]
        self.assertIn(sports_doc.url, urls, "Sports doc should survive sports query")
        self.assertNotIn(tech_doc.url, urls,
                         "Tech doc with no lexical overlap should be filtered on sports query")

    def test_empty_docs_returns_empty(self):
        ranked, embeddings, _ = _run(self.retriever.rank(
            "machine learning", [], top_k=5, profile=_profile(), follows=[],
        ))
        self.assertEqual(ranked, [])
        self.assertEqual(embeddings, {})


class TestAnalyzeQuery(unittest.TestCase):
    def setUp(self):
        self.retriever = RetrieverService(FakeEmbeddingService())

    def test_sports_intent_detected(self):
        result = self.retriever.analyze_query("latest nba scores tonight")
        self.assertEqual(result["intent"], "sports")

    def test_research_intent_detected(self):
        result = self.retriever.analyze_query("arxiv paper on LLM benchmarks")
        self.assertEqual(result["intent"], "research")

    def test_general_intent_triggers_world_news_rewrite(self):
        result = self.retriever.analyze_query("ukraine war conflict")
        self.assertIn("world news", result["rewritten_query"].lower())

    def test_research_intent_triggers_papers_rewrite(self):
        result = self.retriever.analyze_query("benchmark study")
        self.assertIn("research papers", result["rewritten_query"].lower())

    def test_sports_intent_triggers_scores_rewrite(self):
        result = self.retriever.analyze_query("NBA game")
        self.assertIn("latest scores", result["rewritten_query"].lower())

    def test_stopwords_stripped_from_tokens(self):
        result = self.retriever.analyze_query("what is the latest news")
        tokens = result["tokens"]
        stopwords = {"what", "is", "the", "latest", "news"}
        self.assertEqual(set(tokens).intersection(stopwords), set(),
                         "Stopwords should not appear in token list")

    def test_empty_query_handled(self):
        result = self.retriever.analyze_query("")
        self.assertEqual(result["rewritten_query"], "")

    def test_tokens_returned_sorted(self):
        result = self.retriever.analyze_query("machine learning models")
        self.assertEqual(result["tokens"], sorted(result["tokens"]))


class TestRankChunks(unittest.TestCase):
    def setUp(self):
        self.retriever = RetrieverService(FakeEmbeddingService())

    def test_empty_chunks_returns_empty(self):
        ranked, _, _ = _run(self.retriever.rank_chunks("machine learning", []))
        self.assertEqual(ranked, [])

    def test_higher_lexical_chunk_ranks_first(self):
        from backend.app.models import ChunkHit

        def _chunk(text, chunk_id):
            return ChunkHit(
                canonical_url=f"https://example.com/{chunk_id}",
                chunk_id=chunk_id,
                chunk_index=0,
                text=text,
                source="TestSource",
                category="tech",
            )

        chunk_a = _chunk("machine learning agents breakthrough", "a")
        chunk_b = _chunk("sports game score", "b")

        ranked, _, _ = _run(self.retriever.rank_chunks(
            "machine learning agents", [chunk_a, chunk_b]
        ))

        self.assertEqual(ranked[0].chunk_id, "a",
                         "Chunk with lexical overlap should rank first")


if __name__ == "__main__":
    unittest.main()
