export function formatDateTime(value) {
  if (!value) return "n/a";
  try {
    return new Date(value).toLocaleString();
  } catch {
    return value;
  }
}

export function whyThisSource(source) {
  const reasons = [];
  if ((source.lexical_score || 0) >= 2) reasons.push("strong keyword overlap");
  if ((source.semantic_score || 0) >= 0.75) reasons.push("high semantic match");
  if ((source.recency_score || 0) >= 0.8) reasons.push("recent coverage");
  if ((source.credibility_score || 0) >= 0.8) reasons.push("high-trust outlet");
  if (source.citation_snippet) reasons.push("direct support passage");
  return reasons.length ? reasons.join(" | ") : "best available supporting source";
}
