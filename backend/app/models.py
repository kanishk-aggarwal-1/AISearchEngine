from datetime import datetime
from typing import List, Literal

from pydantic import BaseModel, Field


Category = Literal["tech", "research", "sports", "general"]
ExplanationMode = Literal["tldr", "beginner", "deep", "analyst"]
ExplanationFormat = Literal["standard", "bullet", "pros_cons", "timeline", "fact_check"]
SourceType = Literal["news", "research", "sports", "api", "community"]
BiasLabel = Literal["reporting", "research", "analysis", "opinion", "speculative"]
SortBy = Literal["relevance", "latest"]


class ResearchMetadata(BaseModel):
    citations: int | None = None
    venue: str | None = None
    code_available: bool | None = None
    code_url: str | None = None
    theme: str | None = None
    authors: List[str] = Field(default_factory=list)
    paper_id: str | None = None


class SportsMetadata(BaseModel):
    league: str | None = None
    status: str | None = None
    scoreline: str | None = None
    trend: str | None = None
    injury_trade_impact: str | None = None
    team: str | None = None
    opponent: str | None = None


class SourceDoc(BaseModel):
    title: str
    summary: str
    url: str
    source: str
    category: Category
    published_at: datetime | None = None

    source_type: SourceType = "news"
    bias_label: BiasLabel = "reporting"
    credibility_score: float = 0.5
    confidence_score: float = 0.5
    citation_snippet: str = ""
    freshness_label: str = "unknown"

    semantic_score: float = 0.0
    lexical_score: float = 0.0
    recency_score: float = 0.0
    personalization_score: float = 0.0
    total_score: float = 0.0

    entity_tags: List[str] = Field(default_factory=list)
    research_metadata: ResearchMetadata | None = None
    sports_metadata: SportsMetadata | None = None


class TimelinePoint(BaseModel):
    date: str
    event: str
    source: str
    category: Category


class ComparisonResult(BaseModel):
    baseline_query: str
    compared_query: str
    baseline_summary: str
    compared_summary: str
    overlap_topics: List[str]
    divergence_topics: List[str]


class AppliedFilters(BaseModel):
    recency_days: int | None = None
    source_filter: List[str] = Field(default_factory=list)
    source_type_filter: List[SourceType] = Field(default_factory=list)
    sort_by: SortBy = "relevance"


class UserProfile(BaseModel):
    user_id: str
    preferred_categories: List[Category] = Field(default_factory=list)
    explanation_mode: ExplanationMode = "beginner"


class AlertRule(BaseModel):
    id: int | None = None
    user_id: str
    query: str
    categories: List[Category]
    enabled: bool = True


class AlertDeliverySettings(BaseModel):
    user_id: str
    webhook_url: str = ""
    digest_mode: Literal["instant", "daily"] = "daily"
    enabled: bool = False


class BookmarkRequest(BaseModel):
    user_id: str
    source: SourceDoc


class BookmarkItem(BaseModel):
    id: int | None = None
    user_id: str
    source: SourceDoc
    saved_at: str | None = None


class SearchRequest(BaseModel):
    query: str = Field(min_length=3)
    top_k: int = Field(default=5, ge=1, le=20)
    categories: List[Category] = Field(default_factory=lambda: ["tech", "research", "general"], min_length=1)
    user_id: str = "default"
    explanation_mode: ExplanationMode = "beginner"
    explanation_format: ExplanationFormat = "standard"
    compare_against: str | None = None
    timeline: bool = True
    recency_days: int | None = Field(default=None, ge=1, le=30)
    source_filter: List[str] = Field(default_factory=list)
    source_type_filter: List[SourceType] = Field(default_factory=list)
    sort_by: SortBy = "relevance"


class SearchResponse(BaseModel):
    query: str
    explanation_provider: str
    explanation: str
    key_takeaways: List[str]
    why_it_matters: str
    what_changed_last_week: str
    claim_confidence: float
    contradictions: List[str]
    sources: List[SourceDoc]
    timeline: List[TimelinePoint] = Field(default_factory=list)
    comparison: ComparisonResult | None = None
    context_id: str
    applied_filters: AppliedFilters = Field(default_factory=AppliedFilters)


class FollowRequest(BaseModel):
    user_id: str
    entity: str = Field(min_length=2)


class FollowResponse(BaseModel):
    user_id: str
    entities: List[str]


class FollowUpRequest(BaseModel):
    user_id: str
    context_id: str
    question: str = Field(min_length=3)
    explanation_mode: ExplanationMode = "beginner"


class FollowUpResponse(BaseModel):
    context_id: str
    response: str
    key_points: List[str]


class CompareRequest(BaseModel):
    user_id: str = "default"
    query_a: str = Field(min_length=3)
    query_b: str = Field(min_length=3)
    categories: List[Category] = Field(default_factory=lambda: ["tech", "research", "general"])
    recency_days: int | None = Field(default=None, ge=1, le=30)
    source_filter: List[str] = Field(default_factory=list)
    source_type_filter: List[SourceType] = Field(default_factory=list)
    sort_by: SortBy = "relevance"
