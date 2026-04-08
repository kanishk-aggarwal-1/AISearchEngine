import re
from datetime import datetime, timezone
from typing import Dict, List

from backend.app.models import ComparisonResult, ResearchMetadata, SourceDoc, SportsMetadata, TimelinePoint


class EnrichmentService:
    SOURCE_CREDIBILITY: Dict[str, float] = {
        "arXiv": 0.83,
        "TechCrunch": 0.72,
        "The Verge": 0.71,
        "NewsAPI": 0.65,
        "TheSportsDB": 0.68,
    }

    def enrich(self, query: str, docs: List[SourceDoc]) -> List[SourceDoc]:
        for doc in docs:
            doc.credibility_score = self._credibility(doc.source)
            doc.citation_snippet = self._citation_snippet(query, doc.summary)
            doc.freshness_label = self._freshness(doc.published_at)
            doc.entity_tags = self._extract_entities(doc)
            doc.bias_label = self._infer_bias(doc)
            doc.research_metadata = self._enrich_research(doc)
            doc.sports_metadata = self._enrich_sports(doc)
        return docs

    def contradictions(self, docs: List[SourceDoc]) -> List[str]:
        if len(docs) < 2:
            return []

        positives = {"rise", "gain", "win", "surge", "beat", "growth"}
        negatives = {"fall", "loss", "drop", "decline", "miss", "down"}

        contradictions: List[str] = []
        joined = []
        for doc in docs[:8]:
            words = set(re.findall(r"[a-zA-Z]+", f"{doc.title} {doc.summary}".lower()))
            joined.append((doc, positives.intersection(words), negatives.intersection(words)))

        for i in range(len(joined)):
            for j in range(i + 1, len(joined)):
                left = joined[i]
                right = joined[j]
                shared_entities = set(left[0].entity_tags).intersection(right[0].entity_tags)
                if not shared_entities:
                    continue
                if (left[1] and right[2]) or (left[2] and right[1]):
                    entity = sorted(shared_entities)[0]
                    contradictions.append(f"Conflicting directional claims detected around '{entity}'.")
                    if len(contradictions) >= 3:
                        return contradictions
        return contradictions

    def timeline(self, docs: List[SourceDoc], max_points: int = 8) -> List[TimelinePoint]:
        points: List[TimelinePoint] = []
        dated = [doc for doc in docs if doc.published_at]
        dated.sort(key=lambda item: item.published_at or datetime.min.replace(tzinfo=timezone.utc), reverse=True)

        for doc in dated[:max_points]:
            points.append(
                TimelinePoint(
                    date=(doc.published_at.date().isoformat() if doc.published_at else "unknown"),
                    event=doc.title,
                    source=doc.source,
                    category=doc.category,
                )
            )
        return points

    def compare(self, query_a: str, docs_a: List[SourceDoc], query_b: str, docs_b: List[SourceDoc]) -> ComparisonResult:
        topics_a = self._topic_words(docs_a)
        topics_b = self._topic_words(docs_b)
        overlap = sorted(topics_a.intersection(topics_b))[:8]
        divergence = sorted((topics_a.symmetric_difference(topics_b)))[:8]

        return ComparisonResult(
            baseline_query=query_a,
            compared_query=query_b,
            baseline_summary=self._short_summary(docs_a),
            compared_summary=self._short_summary(docs_b),
            overlap_topics=overlap,
            divergence_topics=divergence,
        )

    def claim_confidence(self, docs: List[SourceDoc], contradictions: List[str]) -> float:
        if not docs:
            return 0.0
        avg_cred = sum(doc.credibility_score for doc in docs[:5]) / min(len(docs), 5)
        source_diversity = len({doc.source for doc in docs[:6]}) / max(1, min(len(docs), 6))
        penalty = 0.18 * len(contradictions)
        return max(0.05, min(0.98, (0.55 * avg_cred) + (0.45 * source_diversity) - penalty))

    def _credibility(self, source: str) -> float:
        if source in self.SOURCE_CREDIBILITY:
            return self.SOURCE_CREDIBILITY[source]
        return 0.62

    def _citation_snippet(self, query: str, summary: str) -> str:
        if not summary:
            return ""
        sentences = [part.strip() for part in re.split(r"(?<=[.!?])\s+", summary) if part.strip()]
        query_tokens = {token.lower() for token in query.split() if token.strip()}
        for sentence in sentences:
            low = sentence.lower()
            if any(token in low for token in query_tokens):
                return sentence[:220]
        return (sentences[0][:220] if sentences else summary[:220])

    def _freshness(self, published_at: datetime | None) -> str:
        if not published_at:
            return "unknown"
        now = datetime.now(timezone.utc)
        ts = published_at if published_at.tzinfo else published_at.replace(tzinfo=timezone.utc)
        hours = (now - ts).total_seconds() / 3600
        if hours < 4:
            return "just now"
        if hours < 24:
            return f"{int(hours)}h ago"
        days = int(hours // 24)
        return f"{days}d ago"

    def _extract_entities(self, doc: SourceDoc) -> List[str]:
        raw = f"{doc.title} {doc.summary}"
        candidates = re.findall(r"\b[A-Z][A-Za-z0-9\-]{2,}\b", raw)
        unique = []
        for token in candidates:
            if token.lower() in {"the", "and", "for", "with", "from"}:
                continue
            if token not in unique:
                unique.append(token)
            if len(unique) >= 8:
                break
        return unique

    def _infer_bias(self, doc: SourceDoc) -> str:
        text = f"{doc.title} {doc.summary}".lower()
        if doc.source_type == "research":
            return "research"
        if any(word in text for word in ["opinion", "editorial", "think piece"]):
            return "opinion"
        if any(word in text for word in ["rumor", "leak", "speculation"]):
            return "speculative"
        if any(word in text for word in ["analysis", "forecast", "outlook"]):
            return "analysis"
        return "reporting"

    def _enrich_research(self, doc: SourceDoc):
        if doc.category != "research":
            return doc.research_metadata
        theme = self._research_theme(f"{doc.title} {doc.summary}")
        meta = doc.research_metadata or ResearchMetadata()
        meta.theme = meta.theme or theme
        if meta.code_available is None:
            low = f"{doc.title} {doc.summary}".lower()
            meta.code_available = "github" in low or "code" in low
        if meta.venue is None:
            meta.venue = "arXiv preprint" if doc.source == "arXiv" else None
        return meta

    def _enrich_sports(self, doc: SourceDoc):
        if doc.category != "sports":
            return doc.sports_metadata
        meta = doc.sports_metadata or SportsMetadata()
        text = f"{doc.title} {doc.summary}".lower()
        impact = "No injury or trade signal detected."
        if any(word in text for word in ["injury", "out", "questionable"]):
            impact = "Potential lineup impact due to injury status mentions."
        if any(word in text for word in ["trade", "transferred", "deal"]):
            impact = "Roster change context may alter near-term performance."
        meta.injury_trade_impact = impact
        if not meta.trend:
            meta.trend = "Momentum unclear"
        return meta

    def _research_theme(self, text: str) -> str:
        low = text.lower()
        if any(key in low for key in ["agent", "autonomous", "tool use"]):
            return "AI Agents"
        if any(key in low for key in ["quantum", "qubit"]):
            return "Quantum Computing"
        if any(key in low for key in ["security", "threat", "malware"]):
            return "Cybersecurity"
        if any(key in low for key in ["vision", "image", "multimodal"]):
            return "Computer Vision"
        return "General Research"

    def _topic_words(self, docs: List[SourceDoc]) -> set[str]:
        stop = {"the", "and", "for", "with", "from", "that", "this", "are", "was", "have"}
        words = set()
        for doc in docs[:8]:
            for token in re.findall(r"[A-Za-z]{4,}", f"{doc.title} {doc.summary}".lower()):
                if token in stop:
                    continue
                words.add(token)
        return words

    def _short_summary(self, docs: List[SourceDoc]) -> str:
        if not docs:
            return "No strong retrieval signal."
        titles = [doc.title for doc in docs[:3]]
        return " | ".join(titles)
