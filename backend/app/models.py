from datetime import datetime
from typing import List, Literal

import re

from pydantic import BaseModel, EmailStr, Field, field_validator


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
    language: str = "en"
    region: str = "global"
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


class ChunkHit(BaseModel):
    canonical_url: str
    chunk_id: str
    chunk_index: int
    text: str
    source: str
    category: Category
    published_at: datetime | None = None
    semantic_score: float = 0.0
    lexical_score: float = 0.0
    total_score: float = 0.0


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
    domain_filter: List[str] = Field(default_factory=list)
    author_filter: List[str] = Field(default_factory=list)
    min_credibility: float | None = None
    language_filter: List[str] = Field(default_factory=list)
    region_filter: List[str] = Field(default_factory=list)
    date_from: datetime | None = None
    date_to: datetime | None = None


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
    email_enabled: bool = False
    timezone: str = "UTC"
    delivery_hour: int = Field(default=9, ge=0, le=23)


class BookmarkRequest(BaseModel):
    user_id: str
    source: SourceDoc
    folder: str = Field(default="", max_length=100)
    tags: List[str] = Field(default_factory=list)
    notes: str = Field(default="", max_length=2000)


class BookmarkMetadataRequest(BaseModel):
    folder: str = Field(default="", max_length=100)
    tags: List[str] = Field(default_factory=list)
    notes: str = Field(default="", max_length=2000)


class BookmarkItem(BaseModel):
    id: int | None = None
    user_id: str
    source: SourceDoc
    saved_at: str | None = None
    folder: str = ""
    tags: List[str] = Field(default_factory=list)
    notes: str = ""


_PASSWORD_RE = re.compile(r"^(?=.*[a-z])(?=.*[A-Z])(?=.*\d).+$")


def _check_password_complexity(v: str) -> str:
    if not _PASSWORD_RE.match(v):
        raise ValueError("Password must contain at least one uppercase letter, one lowercase letter, and one digit")
    return v


class AuthRegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=10, max_length=128)
    display_name: str = Field(min_length=2, max_length=80)

    @field_validator("password")
    @classmethod
    def password_complexity(cls, v: str) -> str:
        return _check_password_complexity(v)


class AuthLoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)
    otp_code: str = Field(default="", max_length=8)


class AuthUser(BaseModel):
    user_id: str
    email: str
    display_name: str
    created_at: str
    is_admin: bool = False
    email_verified: bool = False
    mfa_enabled: bool = False


class AuthSessionResponse(BaseModel):
    token: str
    user: AuthUser


class AuthMessage(BaseModel):
    ok: bool = True
    message: str


class PasswordResetRequest(BaseModel):
    email: EmailStr


class PasswordResetConfirmRequest(BaseModel):
    token: str
    new_password: str = Field(min_length=10, max_length=128)

    @field_validator("new_password")
    @classmethod
    def password_complexity(cls, v: str) -> str:
        return _check_password_complexity(v)


class ChangePasswordRequest(BaseModel):
    current_password: str = Field(min_length=1, max_length=128)
    new_password: str = Field(min_length=10, max_length=128)

    @field_validator("new_password")
    @classmethod
    def new_password_complexity(cls, v: str) -> str:
        return _check_password_complexity(v)


class UpdateAccountRequest(BaseModel):
    display_name: str = Field(min_length=2, max_length=80)


class MfaCodeRequest(BaseModel):
    code: str = Field(min_length=6, max_length=8)


class OAuthGoogleRequest(BaseModel):
    id_token: str = Field(min_length=20, max_length=8192)


class PasskeyAuthenticationBeginRequest(BaseModel):
    email: EmailStr


class PasskeyFinishRequest(BaseModel):
    challenge_id: str = Field(min_length=16, max_length=200)
    credential: dict
    name: str = Field(default="Passkey", max_length=100)


class EmailChangeRequest(BaseModel):
    new_email: EmailStr


class TokenConfirmRequest(BaseModel):
    token: str


class TokenPreviewResponse(BaseModel):
    ok: bool = True
    message: str
    token_preview: str = ""
    expires_at: str | None = None
    email_sent: bool = False
    delivery_mode: Literal["preview", "smtp", "none"] = "preview"
    recipient: str = ""


class SearchHistoryItem(BaseModel):
    id: int | None = None
    user_id: str
    query: str
    categories: List[Category] = Field(default_factory=list)
    context_id: str
    created_at: str


class SavedSessionItem(BaseModel):
    id: int | None = None
    user_id: str
    context_id: str
    label: str = ""
    created_at: str


class SaveSessionRequest(BaseModel):
    label: str = ""


class SourceStatus(BaseModel):
    source_name: str
    category: str
    enabled: bool = True
    success_count: int = 0
    failure_count: int = 0
    last_success_at: str | None = None
    last_attempt_at: str | None = None
    last_error: str = ""
    last_error_at: str | None = None
    last_item_count: int = 0
    average_latency_ms: float | None = None
    updated_at: str | None = None


class IngestionRunRecord(BaseModel):
    id: int | None = None
    trigger_type: str
    query: str = ""
    categories: List[Category] = Field(default_factory=list)
    status: str = "running"
    inserted_count: int = 0
    source_count: int = 0
    error_count: int = 0
    error_message: str = ""
    started_at: str
    completed_at: str | None = None


class SourceToggleRequest(BaseModel):
    enabled: bool


class SearchRequest(BaseModel):
    query: str = Field(min_length=1, max_length=1000)
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
    domain_filter: List[str] = Field(default_factory=list)
    author_filter: List[str] = Field(default_factory=list)
    min_credibility: float | None = Field(default=None, ge=0, le=1)
    language_filter: List[str] = Field(default_factory=list)
    region_filter: List[str] = Field(default_factory=list)
    date_from: datetime | None = None
    date_to: datetime | None = None


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
    suggested_queries: List[str] = Field(default_factory=list)
    # "semantic" when real embeddings rank results, "keyword" when the
    # hash-based lexical fallback is in use. Lets the UI be honest about mode.
    search_mode: str = "keyword"
    citation_warnings: List[str] = Field(default_factory=list)


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


class SearchFeedbackRequest(BaseModel):
    context_id: str = Field(min_length=8, max_length=128)
    helpful: bool
    comment: str = Field(default="", max_length=1000)


class ConversationCreateRequest(BaseModel):
    context_id: str
    title: str = Field(default="", max_length=200)


class ConversationMessageRequest(BaseModel):
    question: str = Field(min_length=3, max_length=2000)
    explanation_mode: ExplanationMode = "beginner"
