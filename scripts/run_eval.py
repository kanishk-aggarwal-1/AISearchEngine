import argparse
import asyncio
import json
import math
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.app.config import settings
from backend.app.models import SourceDoc, UserProfile
from backend.app.services.embedding_service import EmbeddingService
from backend.app.services.retriever import RetrieverService

DEFAULT_DATASET = ROOT / "eval" / "eval_queries.json"
DEFAULT_OUTPUT_DIR = ROOT / "eval" / "out"


@dataclass
class EvalScenario:
    name: str
    weights: dict[str, float]


SCENARIOS = [
    EvalScenario(
        name="lexical_only",
        weights={
            "semantic_weight": 0.0,
            "lexical_weight": 2.4,
            "recency_weight": 0.5,
            "credibility_weight": 0.4,
            "personalization_weight": 0.0,
            "chunk_weight": 0.0,
            "exact_phrase_weight": 0.0,
            "coverage_weight": 0.0,
            "title_match_weight": 0.0,
            "source_diversity_penalty": 0.0,
        },
    ),
    EvalScenario(
        name="semantic_only",
        weights={
            "semantic_weight": 2.4,
            "lexical_weight": 0.0,
            "recency_weight": 0.2,
            "credibility_weight": 0.2,
            "personalization_weight": 0.0,
            "chunk_weight": 0.0,
            "exact_phrase_weight": 0.0,
            "coverage_weight": 0.0,
            "title_match_weight": 0.0,
            "source_diversity_penalty": 0.0,
        },
    ),
    EvalScenario(
        name="hybrid",
        weights={
            "semantic_weight": 1.4,
            "lexical_weight": 1.4,
            "recency_weight": 0.6,
            "credibility_weight": 0.6,
            "personalization_weight": 0.0,
            "chunk_weight": 0.0,
            "exact_phrase_weight": 0.0,
            "coverage_weight": 0.0,
            "title_match_weight": 0.0,
            "source_diversity_penalty": 0.0,
        },
    ),
    EvalScenario(
        name="hybrid_reranked",
        weights={
            "semantic_weight": settings.semantic_weight,
            "lexical_weight": settings.lexical_weight,
            "recency_weight": settings.recency_weight,
            "credibility_weight": settings.credibility_weight,
            "personalization_weight": 0.0,
            "chunk_weight": settings.chunk_weight,
            "exact_phrase_weight": settings.exact_phrase_weight,
            "coverage_weight": settings.coverage_weight,
            "title_match_weight": settings.title_match_weight,
            "source_diversity_penalty": settings.source_diversity_penalty,
        },
    ),
    EvalScenario(
        name="hybrid_source_diversity",
        weights={
            "semantic_weight": settings.semantic_weight,
            "lexical_weight": settings.lexical_weight,
            "recency_weight": settings.recency_weight,
            "credibility_weight": settings.credibility_weight,
            "personalization_weight": 0.0,
            "chunk_weight": settings.chunk_weight,
            "exact_phrase_weight": settings.exact_phrase_weight,
            "coverage_weight": settings.coverage_weight,
            "title_match_weight": settings.title_match_weight,
            "source_diversity_penalty": max(settings.source_diversity_penalty, 0.7),
        },
    ),
]


def load_dataset(path: Path) -> list[dict[str, Any]]:
    return json.loads(path.read_text(encoding="utf-8"))


def relevance_gain(relevance: int) -> float:
    return float((2**relevance) - 1)


def ndcg_at_k(ranked_urls: list[str], relevance: dict[str, int], k: int) -> float:
    dcg = 0.0
    for idx, url in enumerate(ranked_urls[:k], start=1):
        rel = relevance.get(url, 0)
        dcg += relevance_gain(rel) / math.log2(idx + 1)

    ideal_rels = sorted(relevance.values(), reverse=True)[:k]
    idcg = 0.0
    for idx, rel in enumerate(ideal_rels, start=1):
        idcg += relevance_gain(rel) / math.log2(idx + 1)
    return round((dcg / idcg) if idcg else 0.0, 6)


def recall_at_k(ranked_urls: list[str], relevant_urls: set[str], k: int) -> float:
    if not relevant_urls:
        return 0.0
    hits = len(set(ranked_urls[:k]).intersection(relevant_urls))
    return round(hits / len(relevant_urls), 6)


def reciprocal_rank(ranked_urls: list[str], relevant_urls: set[str]) -> float:
    for idx, url in enumerate(ranked_urls, start=1):
        if url in relevant_urls:
            return round(1.0 / idx, 6)
    return 0.0


def source_diversity(ranked_docs: list[SourceDoc], k: int = 5) -> float:
    top_docs = ranked_docs[:k]
    if not top_docs:
        return 0.0
    unique_sources = {doc.source.lower() for doc in top_docs}
    return round(len(unique_sources) / len(top_docs), 6)


def citation_coverage(ranked_docs: list[SourceDoc], k: int = 5) -> float:
    top_docs = ranked_docs[:k]
    if not top_docs:
        return 0.0
    cited = sum(1 for doc in top_docs if (doc.citation_snippet or "").strip())
    return round(cited / len(top_docs), 6)


class SettingsOverride:
    def __init__(self, overrides: dict[str, float]) -> None:
        self.overrides = overrides
        self.originals: dict[str, Any] = {}

    def __enter__(self):
        for key, value in self.overrides.items():
            self.originals[key] = getattr(settings, key)
            setattr(settings, key, value)
        return self

    def __exit__(self, exc_type, exc, tb):
        for key, value in self.originals.items():
            setattr(settings, key, value)


async def run_scenario(dataset: list[dict[str, Any]], scenario: EvalScenario, allow_provider_calls: bool = False) -> dict[str, Any]:
    embedding_service = EmbeddingService()
    if not allow_provider_calls:
        embedding_service.gemini_client = None
        embedding_service.openai_client = None
    retriever = RetrieverService(embedding_service)
    profile = UserProfile(user_id="eval", preferred_categories=[], explanation_mode="beginner")

    per_query: list[dict[str, Any]] = []
    recall5_scores: list[float] = []
    recall10_scores: list[float] = []
    mrr_scores: list[float] = []
    ndcg_scores: list[float] = []
    diversity_scores: list[float] = []
    citation_scores: list[float] = []
    no_result_count = 0

    with SettingsOverride(scenario.weights):
        for item in dataset:
            docs = [SourceDoc.model_validate(doc) for doc in item["documents"]]
            ranked, _, _ = await retriever.rank(
                item["query"],
                docs,
                top_k=min(10, max(5, len(docs))),
                profile=profile,
                follows=[],
                cached_embeddings={},
                chunk_hits_by_doc={},
                query_embedding=None,
            )

            ranked_urls = [doc.url for doc in ranked]
            relevance = {url: int(score) for url, score in item.get("relevance", {}).items()}
            relevant_urls = {url for url, rel in relevance.items() if rel > 0}

            if not ranked:
                no_result_count += 1

            recall5 = recall_at_k(ranked_urls, relevant_urls, 5)
            recall10 = recall_at_k(ranked_urls, relevant_urls, 10)
            mrr = reciprocal_rank(ranked_urls, relevant_urls)
            ndcg10 = ndcg_at_k(ranked_urls, relevance, 10)
            diversity = source_diversity(ranked, 5)
            citations = citation_coverage(ranked, 5)

            recall5_scores.append(recall5)
            recall10_scores.append(recall10)
            mrr_scores.append(mrr)
            ndcg_scores.append(ndcg10)
            diversity_scores.append(diversity)
            citation_scores.append(citations)

            per_query.append(
                {
                    "id": item["id"],
                    "query": item["query"],
                    "top_urls": ranked_urls[:5],
                    "recall_at_5": recall5,
                    "recall_at_10": recall10,
                    "mrr": mrr,
                    "ndcg_at_10": ndcg10,
                    "source_diversity_at_5": diversity,
                    "citation_coverage_at_5": citations,
                }
            )

    aggregate = {
        "query_count": len(dataset),
        "recall_at_5": round(sum(recall5_scores) / max(len(recall5_scores), 1), 6),
        "recall_at_10": round(sum(recall10_scores) / max(len(recall10_scores), 1), 6),
        "mrr": round(sum(mrr_scores) / max(len(mrr_scores), 1), 6),
        "ndcg_at_10": round(sum(ndcg_scores) / max(len(ndcg_scores), 1), 6),
        "source_diversity_at_5": round(sum(diversity_scores) / max(len(diversity_scores), 1), 6),
        "citation_coverage_at_5": round(sum(citation_scores) / max(len(citation_scores), 1), 6),
        "no_result_rate": round(no_result_count / max(len(dataset), 1), 6),
    }
    return {"scenario": scenario.name, "aggregate": aggregate, "queries": per_query}


def to_markdown(results: list[dict[str, Any]]) -> str:
    lines = [
        "# Retrieval Evaluation Report",
        "",
        "| Scenario | Recall@5 | Recall@10 | MRR | nDCG@10 | Source diversity@5 | Citation coverage@5 | No-result rate |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for result in results:
        agg = result["aggregate"]
        lines.append(
            f"| {result['scenario']} | {agg['recall_at_5']:.3f} | {agg['recall_at_10']:.3f} | "
            f"{agg['mrr']:.3f} | {agg['ndcg_at_10']:.3f} | {agg['source_diversity_at_5']:.3f} | "
            f"{agg['citation_coverage_at_5']:.3f} | {agg['no_result_rate']:.3f} |"
        )

    lines.extend(["", "## Per-query detail", ""])
    for result in results:
        lines.append(f"### {result['scenario']}")
        lines.append("")
        for item in result["queries"]:
            lines.append(
                f"- `{item['id']}`: Recall@5 `{item['recall_at_5']:.3f}`, "
                f"MRR `{item['mrr']:.3f}`, top URLs: {', '.join(item['top_urls']) or 'none'}"
            )
        lines.append("")
    return "\n".join(lines)


async def main() -> None:
    parser = argparse.ArgumentParser(description="Run offline retrieval evaluation for SignalScope AI.")
    parser.add_argument("--dataset", default=str(DEFAULT_DATASET), help="Path to eval JSON dataset.")
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR), help="Directory for JSON and Markdown reports.")
    parser.add_argument("--allow-provider-calls", action="store_true", help="Allow configured embedding providers instead of forcing fallback embeddings.")
    args = parser.parse_args()

    dataset_path = Path(args.dataset).resolve()
    output_dir = Path(args.output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    dataset = load_dataset(dataset_path)
    results = []
    for scenario in SCENARIOS:
        results.append(await run_scenario(dataset, scenario, allow_provider_calls=args.allow_provider_calls))

    json_path = output_dir / "retrieval_eval_report.json"
    md_path = output_dir / "retrieval_eval_report.md"
    json_path.write_text(json.dumps(results, indent=2), encoding="utf-8")
    md_path.write_text(to_markdown(results), encoding="utf-8")

    print(f"Wrote {json_path}")
    print(f"Wrote {md_path}")


if __name__ == "__main__":
    asyncio.run(main())
