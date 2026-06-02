"use client";

import type { AuthSession, SearchResponse, SourceDoc } from "../types/api";
import SourceCard from "./SourceCard";

interface Props {
  result: SearchResponse | null;
  appliedFiltersText: string;
  session: AuthSession | null;
  followUpQuestion: string; setFollowUpQuestion: (v: string) => void;
  followUpResponse: { response: string; key_points: string[] } | null;
  sessionLabel: string; setSessionLabel: (v: string) => void;
  onSaveSession: (contextId: string | undefined, token: string | null) => void;
  onCreateAlert: (q?: string) => void;
  onSetFollowEntity: () => void;
  onBookmark: (source: SourceDoc) => void;
  onExplainPaper: (source: SourceDoc) => void;
  onResetFilters: () => void;
  onExpandRecency: () => void;
  onSuggestedQuery: (q: string) => void;
  onRunFollowUp: () => void;
}

export default function SearchResults({
  result, appliedFiltersText, session,
  followUpQuestion, setFollowUpQuestion, followUpResponse,
  sessionLabel, setSessionLabel, onSaveSession,
  onCreateAlert, onSetFollowEntity, onBookmark, onExplainPaper,
  onResetFilters, onExpandRecency, onSuggestedQuery, onRunFollowUp,
}: Props) {
  if (!result) return null;
  return (
    <>
      <section className="result-grid">
        <article className="explanation-card">
          <h2>Explanation</h2>
          <p className="muted">Provider: {result.explanation_provider}</p>
          <p className="muted">{appliedFiltersText}</p>
          <p className="formatted-block">{result.explanation}</p>
          <div className="hero-action-strip">
            <button type="button" className="mini-button" onClick={() => onSaveSession(result.context_id, session?.token ?? null)} disabled={!result.context_id || !session?.token}>Save context</button>
            <button type="button" className="mini-button" onClick={() => onCreateAlert()}>Alert on this query</button>
            <button type="button" className="mini-button" onClick={onSetFollowEntity}>Follow this topic</button>
            {result.sources?.[0] && <button type="button" className="mini-button" onClick={() => onBookmark(result.sources[0])}>Save top source</button>}
          </div>
          <h3>Why it matters</h3><p>{result.why_it_matters}</p>
          <h3>What changed last week</h3><p>{result.what_changed_last_week}</p>
          <h3>Claim confidence</h3><p>{Math.round((result.claim_confidence || 0) * 100)}%</p>
          {result.comparison && (
            <div className="comparison-card">
              <h3>Comparison snapshot</h3>
              <p><strong>{result.comparison.baseline_query}</strong>: {result.comparison.baseline_summary}</p>
              <p><strong>{result.comparison.compared_query}</strong>: {result.comparison.compared_summary}</p>
              <p className="muted">Overlap: {(result.comparison.overlap_topics || []).join(", ") || "None detected"}</p>
              <p className="muted">Divergence: {(result.comparison.divergence_topics || []).join(", ") || "None detected"}</p>
            </div>
          )}
          <h3>Key takeaways</h3>
          <ul>{(result.key_takeaways || []).map((item, i) => <li key={`${item}-${i}`}>{item}</li>)}</ul>
          {!result.sources?.length && (
            <div className="empty-state">
              <h3>No strong results yet</h3>
              <p className="muted">Try broadening the time window, clearing filters, or using one of these suggestions.</p>
              <div className="card-actions">
                <button type="button" className="mini-button" onClick={onResetFilters}>Clear filters</button>
                <button type="button" className="mini-button" onClick={onExpandRecency}>Expand to 30 days</button>
              </div>
              <div className="chips">{(result.suggested_queries || []).map((item) => <button type="button" key={item} className="chip active" onClick={() => onSuggestedQuery(item)}>{item}</button>)}</div>
            </div>
          )}
          {result.context_id && (
            <div className="followup-box">
              <h3>Follow-up chat</h3>
              <input value={followUpQuestion} onChange={(e) => setFollowUpQuestion(e.target.value)} placeholder="Ask a follow-up about this context" />
              <button type="button" onClick={onRunFollowUp}>Ask</button>
              {followUpResponse && (
                <div className="followup-answer">
                  <p>{followUpResponse.response}</p>
                  <ul>{(followUpResponse.key_points || []).map((point, idx) => <li key={`${point}-${idx}`}>{point}</li>)}</ul>
                </div>
              )}
            </div>
          )}
        </article>
        <article className="sources-card">
          <h2>Sources</h2>
          <div className="sources-list">
            {result.sources.map((source, index) => (
              <SourceCard key={`${source.url}-${index}`} source={source} index={index} onBookmark={onBookmark} onCreateAlert={onCreateAlert} onExplainPaper={onExplainPaper} />
            ))}
          </div>
        </article>
      </section>
      {result.timeline?.length > 0 && (
        <section className="query-card">
          <h2>Timeline</h2>
          <div className="timeline-list">
            {result.timeline.map((point, idx) => (
              <div className="timeline-item" key={`${point.date}-${point.event}-${idx}`}>
                <p className="source-meta">{point.date} | {point.source} | {point.category}</p>
                <p>{point.event}</p>
              </div>
            ))}
          </div>
        </section>
      )}
    </>
  );
}
