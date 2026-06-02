"use client";

import Link from "next/link";
import type { ResearchInsight, SourceDoc } from "../types/api";

interface PaperComparison { left_title: string; right_title: string; same_theme: boolean; shared_authors: string[] }

interface Props {
  researchInsight: ResearchInsight | null;
  researchPapers: SourceDoc[];
  explainedPaper: { summary: string; key_takeaways: string[] } | null;
  paperComparison: PaperComparison | null;
  comparePapers: SourceDoc[];
  onExplainPaper: (paper: SourceDoc) => void;
  onToggleComparePaper: (paper: SourceDoc) => void;
}

export default function ResearchWorkspace({ researchInsight, researchPapers, explainedPaper, paperComparison, comparePapers, onExplainPaper, onToggleComparePaper }: Props) {
  return (
    <article className="query-card">
      <h2>Research Workspace</h2>
      {researchInsight && <p className="muted">Themes: {Object.entries(researchInsight.theme_clusters || {}).map(([k, v]) => `${k} (${v})`).join(", ") || "n/a"}</p>}
      {researchPapers.length ? (
        <div className="compact-list research-list">
          {researchPapers.slice(0, 6).map((paper, idx) => (
            <div key={`${paper.url}-${idx}`} className="research-row">
              <div>
                <p className="bookmark-title">{paper.title}</p>
                <p className="muted">{paper.research_metadata?.authors?.slice(0, 3).join(", ") || "Unknown authors"}</p>
              </div>
              <div className="card-actions">
                {paper.research_metadata?.paper_id && <Link href={`/research/${encodeURIComponent(paper.research_metadata.paper_id)}`} className="mini-link">Open paper</Link>}
                <button type="button" className="mini-button" onClick={() => onExplainPaper(paper)}>Explain</button>
                <button type="button" className={comparePapers.find((p) => p.url === paper.url) ? "mini-button active-mini" : "mini-button"} onClick={() => onToggleComparePaper(paper)}>Compare</button>
              </div>
            </div>
          ))}
        </div>
      ) : <p className="muted">Load research papers to inspect detail pages and compare papers.</p>}
      {explainedPaper && (
        <div className="followup-answer">
          <h3>Paper Explainer</h3>
          <p>{explainedPaper.summary}</p>
          <ul>{(explainedPaper.key_takeaways || []).map((item, idx) => <li key={`${item}-${idx}`}>{item}</li>)}</ul>
        </div>
      )}
      {paperComparison && (
        <div className="followup-answer">
          <h3>Paper Compare</h3>
          <p>{paperComparison.left_title} vs {paperComparison.right_title}</p>
          <p className="muted">Same theme: {String(paperComparison.same_theme)}</p>
          <p className="muted">Shared authors: {(paperComparison.shared_authors || []).join(", ") || "None"}</p>
        </div>
      )}
    </article>
  );
}
