"use client";

import Link from "next/link";
import { whyThisSource } from "../lib/formatters";
import type { SourceDoc } from "../types/api";

interface Props {
  source: SourceDoc;
  index: number;
  onBookmark: (source: SourceDoc) => void;
  onCreateAlert: (title: string) => void;
  onExplainPaper: (source: SourceDoc) => void;
}

export default function SourceCard({ source, index, onBookmark, onCreateAlert, onExplainPaper }: Props) {
  const teamSlug = source.sports_metadata?.team ? encodeURIComponent(source.sports_metadata.team) : "";
  const paperId = source.research_metadata?.paper_id || "";
  return (
    <div key={`${source.url}-${index}`} className="source-item source-card-shell">
      <a href={source.url} target="_blank" rel="noreferrer" className="source-link-block">
        <p className="source-meta">{source.source} | {source.category} | {source.freshness_label} | {source.source_type}</p>
        <h3>{source.title}</h3>
        <p>{source.summary}</p>
        <div className="citation-box">
          <p className="muted source-label">Grounding snippet</p>
          <p>{source.citation_snippet || "No snippet stored; using article summary as fallback."}</p>
        </div>
        <p className="muted">Credibility {Math.round((source.credibility_score || 0) * 100)}% | Confidence {Math.round((source.confidence_score || 0) * 100)}% | Bias {source.bias_label}</p>
        <p className="muted">Why this source: {whyThisSource(source)}</p>
      </a>
      <div className="card-actions">
        <button type="button" className="mini-button" onClick={() => onBookmark(source)}>Save</button>
        <button type="button" className="mini-button" onClick={() => onCreateAlert(source.title)}>Alert similar</button>
        {paperId && <Link href={`/research/${encodeURIComponent(paperId)}`} className="mini-link">Paper page</Link>}
        {teamSlug && <Link href={`/sports/${teamSlug}`} className="mini-link">Team page</Link>}
        {source.category === "research" && <button type="button" className="mini-button" onClick={() => onExplainPaper(source)}>Explain paper</button>}
      </div>
    </div>
  );
}
