// API type definitions — mirrors the Pydantic models in backend/app/models.py

export type Category = 'tech' | 'research' | 'sports' | 'general';
export type ExplanationMode = 'tldr' | 'beginner' | 'deep' | 'analyst';
export type ExplanationFormat = 'standard' | 'bullet' | 'pros_cons' | 'timeline' | 'fact_check';
export type SourceType = 'news' | 'research' | 'sports' | 'api' | 'community';
export type BiasLabel = 'reporting' | 'research' | 'analysis' | 'opinion' | 'speculative';
export type SortBy = 'relevance' | 'latest';
export type DigestMode = 'instant' | 'daily';
export type DeliveryMode = 'preview' | 'smtp' | 'none';

export interface ResearchMetadata {
  citations?: number;
  venue?: string;
  code_available?: boolean;
  code_url?: string;
  theme?: string;
  authors: string[];
  paper_id?: string;
}

export interface SportsMetadata {
  league?: string;
  status?: string;
  scoreline?: string;
  trend?: string;
  injury_trade_impact?: string;
  team?: string;
  opponent?: string;
}

export interface SourceDoc {
  title: string;
  summary: string;
  url: string;
  source: string;
  category: Category;
  published_at?: string;
  source_type: SourceType;
  bias_label: BiasLabel;
  credibility_score: number;
  confidence_score: number;
  citation_snippet: string;
  freshness_label: string;
  semantic_score: number;
  lexical_score: number;
  recency_score: number;
  personalization_score: number;
  total_score: number;
  entity_tags: string[];
  research_metadata?: ResearchMetadata;
  sports_metadata?: SportsMetadata;
}

export interface TimelinePoint {
  date: string;
  event: string;
  source: string;
  category: Category;
}

export interface ComparisonResult {
  baseline_query: string;
  compared_query: string;
  baseline_summary: string;
  compared_summary: string;
  overlap_topics: string[];
  divergence_topics: string[];
}

export interface AppliedFilters {
  recency_days?: number;
  source_filter: string[];
  source_type_filter: SourceType[];
  sort_by: SortBy;
}

export interface SearchResponse {
  query: string;
  explanation_provider: string;
  explanation: string;
  key_takeaways: string[];
  why_it_matters: string;
  what_changed_last_week: string;
  claim_confidence: number;
  contradictions: string[];
  sources: SourceDoc[];
  timeline: TimelinePoint[];
  comparison?: ComparisonResult;
  context_id: string;
  applied_filters: AppliedFilters;
  suggested_queries: string[];
  search_mode: "semantic" | "keyword";
}

export interface FollowUpResponse {
  context_id: string;
  response: string;
  key_points: string[];
}

export interface AuthUser {
  user_id: string;
  email: string;
  display_name: string;
  created_at: string;
  is_admin: boolean;
  email_verified: boolean;
}

export interface AuthSession {
  token: string;
  user: AuthUser;
}

export interface AuthFormState {
  email: string;
  password: string;
  display_name: string;
}

export interface TokenPreviewResponse {
  ok: boolean;
  message: string;
  token_preview: string;
  expires_at?: string;
  email_sent: boolean;
  delivery_mode: DeliveryMode;
  recipient: string;
}

export interface AlertRule {
  id?: number;
  user_id: string;
  query: string;
  categories: Category[];
  enabled: boolean;
}

export interface AlertDeliverySettings {
  user_id: string;
  webhook_url: string;
  digest_mode: DigestMode;
  enabled: boolean;
}

export interface BookmarkItem {
  id?: number;
  user_id: string;
  source: SourceDoc;
  saved_at?: string;
}

export interface FollowResponse {
  user_id: string;
  entities: string[];
}

export interface UserProfile {
  user_id: string;
  preferred_categories: Category[];
  explanation_mode: ExplanationMode;
}

export interface SearchHistoryItem {
  id?: number;
  user_id: string;
  query: string;
  categories: Category[];
  context_id: string;
  created_at: string;
}

export interface SavedSessionItem {
  id?: number;
  user_id: string;
  context_id: string;
  label: string;
  created_at: string;
}

export interface SourceStatus {
  source_name: string;
  category: string;
  enabled: boolean;
  success_count: number;
  failure_count: number;
  last_success_at?: string;
  last_attempt_at?: string;
  last_error: string;
  last_error_at?: string;
  last_item_count: number;
  average_latency_ms?: number;
  updated_at?: string;
}

export interface IngestionRunRecord {
  id?: number;
  trigger_type: string;
  query: string;
  categories: Category[];
  status: string;
  inserted_count: number;
  source_count: number;
  error_count: number;
  error_message: string;
  started_at: string;
  completed_at?: string;
}

export interface AdminData {
  snapshot: {
    counts: Record<string, number>;
    source_freshness: {
      healthy_sources: number;
      stale_sources: number;
      errored_sources: number;
    };
    recent_ingestion_runs: IngestionRunRecord[];
  };
  metrics: {
    counters: Record<string, number>;
  };
}

export interface SportsInsight {
  query: string;
  top_leagues: Record<string, number>;
  status_breakdown: Record<string, number>;
  trend_summary: string[];
  injury_trade_impacts: string[];
  sample_events: SourceDoc[];
}

export interface SportsDashboard {
  team: string;
  news: SourceDoc[];
  latest_scores: SourceDoc[];
  upcoming: SourceDoc[];
  top_leagues: [string, number][];
}

export interface ResearchInsight {
  query: string;
  theme_clusters: Record<string, number>;
  top_venues: Record<string, number>;
  code_available_count: number;
  sample_papers: SourceDoc[];
}

export interface HeadlinesResponse {
  updated_at: string;
  categories: Record<Category, SourceDoc[]>;
  recency_days: number;
}

export interface DeliveryTestResult {
  ok: boolean;
  preview_only?: boolean;
  status_code?: number;
  error?: string;
  preview: unknown;
}
