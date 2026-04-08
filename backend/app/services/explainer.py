import json
import re
from datetime import datetime, timedelta, timezone
from typing import Dict, List

from openai import AsyncOpenAI

from backend.app.config import settings
from backend.app.models import ExplanationFormat, ExplanationMode, SourceDoc
from backend.app.services.logging_service import get_logger

try:
    from google import genai
except Exception:  # pragma: no cover
    genai = None


class ExplainerService:
    def __init__(self) -> None:
        self.openai_client = AsyncOpenAI(api_key=settings.openai_api_key) if settings.openai_api_key else None
        self.gemini_client = genai.Client(api_key=settings.gemini_api_key) if settings.gemini_api_key and genai else None
        self.logger = get_logger("signalscope.explainer")

    async def explain(
        self,
        query: str,
        docs: List[SourceDoc],
        mode: ExplanationMode,
        contradictions: List[str],
        output_format: ExplanationFormat = "standard",
    ) -> Dict[str, object]:
        if not docs:
            return {
                "explanation": "I could not find enough relevant results yet. Try a narrower query or include different categories.",
                "key_takeaways": ["No high-confidence sources were retrieved."],
                "why_it_matters": "Reliable decisions need multiple corroborating sources.",
                "what_changed_last_week": "Insufficient retrieved context to compare with prior week.",
                "provider": "fallback",
            }

        if self.gemini_client:
            try:
                result = await self._gemini_explain(query, docs, mode, contradictions, output_format)
                result["provider"] = "gemini"
                return result
            except Exception as exc:
                self.logger.warning("gemini_explain_failed error=%s", exc)

        if self.openai_client:
            try:
                result = await self._openai_explain(query, docs, mode, contradictions, output_format)
                result["provider"] = "openai"
                return result
            except Exception as exc:
                self.logger.warning("openai_explain_failed error=%s", exc)

        result = self._fallback_explanation(query, docs, mode, contradictions, output_format)
        result["provider"] = "fallback"
        return result

    async def followup(
        self,
        query: str,
        docs: List[SourceDoc],
        question: str,
        mode: ExplanationMode,
    ) -> tuple[str, List[str]]:
        if not docs:
            return "No prior context is available for this follow-up.", ["Run a search first."]

        if self.gemini_client:
            try:
                context = self._context_block(docs[:8])
                prompt = (
                    "Answer follow-up questions strictly from the provided context. "
                    "Admit uncertainty when context is missing. "
                    "Return strict JSON with keys answer and key_points (max 4).\n\n"
                    f"Original query: {query}\n"
                    f"Mode: {mode}\n"
                    f"Follow-up question: {question}\n\n"
                    f"Context:\n{context}"
                )
                response = self.gemini_client.models.generate_content(model="gemini-2.5-flash", contents=prompt)
                payload = self._parse_json_response(response.text)
                answer = str(payload.get("answer", "")).strip() or "No follow-up answer generated."
                points = [str(item).strip() for item in payload.get("key_points", []) if str(item).strip()][:4]
                if not points:
                    points = ["Check listed sources for verification."]
                return answer, points
            except Exception as exc:
                self.logger.warning("gemini_followup_failed error=%s", exc)

        if self.openai_client:
            try:
                context = self._context_block(docs[:8])
                system = "Answer follow-up questions strictly from provided context. Admit uncertainty when missing."
                user = (
                    f"Original query: {query}\n"
                    f"Mode: {mode}\n"
                    f"Follow-up question: {question}\n\n"
                    f"Context:\n{context}\n\n"
                    "Return JSON with keys answer and key_points (max 4)."
                )
                resp = await self.openai_client.responses.create(
                    model=settings.explanation_model,
                    input=[{"role": "system", "content": system}, {"role": "user", "content": user}],
                    temperature=0.2,
                )
                payload = self._parse_json_response(resp.output_text or "")
                answer = str(payload.get("answer", "")).strip() or "No follow-up answer generated."
                points = [str(item).strip() for item in payload.get("key_points", []) if str(item).strip()][:4]
                if not points:
                    points = ["Check listed sources for verification."]
                return answer, points
            except Exception as exc:
                self.logger.warning("openai_followup_failed error=%s", exc)

        title_list = ", ".join(doc.title for doc in docs[:3])
        answer = f"Based on the current context, the strongest signals are around: {title_list}."
        return answer, ["This answer is derived from the saved search context."]

    async def _gemini_explain(self, query: str, docs: List[SourceDoc], mode: ExplanationMode, contradictions: List[str], output_format: ExplanationFormat) -> Dict[str, object]:
        context = self._context_block(docs[:10])
        prompt = (
            "You are an AI research and news assistant. Explain retrieved information clearly and truthfully. "
            "Do not fabricate facts. Use uncertainty language when evidence is mixed. Return strict JSON with keys: "
            "explanation (string), key_takeaways (array max 6), why_it_matters (string), what_changed_last_week (string).\n\n"
            f"User query: {query}\n"
            f"Explanation mode: {mode}\n"
            f"Output format: {output_format}\n"
            f"Known contradictions: {contradictions}\n\n"
            f"Retrieved context:\n{context}"
        )
        response = self.gemini_client.models.generate_content(model="gemini-2.5-flash", contents=prompt)
        return self._normalize_payload(self._parse_json_response(response.text))

    async def _openai_explain(self, query: str, docs: List[SourceDoc], mode: ExplanationMode, contradictions: List[str], output_format: ExplanationFormat) -> Dict[str, object]:
        context = self._context_block(docs[:10])
        system = (
            "You are an AI research and news assistant. Explain retrieved information clearly and truthfully. "
            "Do not fabricate facts. Use uncertainty language when evidence is mixed."
        )
        user = (
            f"User query: {query}\n"
            f"Explanation mode: {mode}\n"
            f"Output format: {output_format}\n"
            f"Known contradictions: {contradictions}\n\n"
            f"Retrieved context:\n{context}\n\n"
            "Return strict JSON with keys: explanation (string), key_takeaways (array max 6), why_it_matters (string), what_changed_last_week (string)."
        )
        resp = await self.openai_client.responses.create(
            model=settings.explanation_model,
            input=[{"role": "system", "content": system}, {"role": "user", "content": user}],
            temperature=0.2,
        )
        return self._normalize_payload(self._parse_json_response(resp.output_text or ""))

    def _normalize_payload(self, payload: Dict[str, object]) -> Dict[str, object]:
        return {
            "explanation": str(payload.get("explanation", "")).strip() or "No explanation generated.",
            "key_takeaways": [str(item).strip() for item in payload.get("key_takeaways", []) if str(item).strip()][:6],
            "why_it_matters": str(payload.get("why_it_matters", "")).strip() or "This topic influences near-term decisions.",
            "what_changed_last_week": str(payload.get("what_changed_last_week", "")).strip() or "The latest batch shows incremental change rather than a full trend reversal.",
        }

    def _fallback_explanation(self, query: str, docs: List[SourceDoc], mode: ExplanationMode, contradictions: List[str], output_format: ExplanationFormat) -> Dict[str, object]:
        top = docs[:4]
        source_names = ", ".join(sorted({doc.source for doc in top}))
        if mode == "tldr":
            base = f"Top signals for '{query}' come from {source_names}. Cross-source overlap suggests this trend is active."
        elif mode == "deep":
            base = f"For '{query}', ranked evidence converges across {source_names}. Scores combine semantic similarity, lexical overlap, recency, source credibility, and user personalization."
        elif mode == "analyst":
            base = f"For '{query}', the current evidence stack indicates directional momentum across {source_names}. Confidence should be discounted where contradiction signals appear."
        else:
            base = f"For '{query}', the strongest results come from {source_names}. Multiple sources report similar themes, so we can treat this as a credible snapshot."

        takeaways = [f"{doc.title} ({doc.source}, {doc.freshness_label})" for doc in top]
        if contradictions:
            takeaways.append(f"Caution: {contradictions[0]}")

        if output_format == "bullet":
            explanation = "\n".join(f"- {item}" for item in takeaways[:4])
        elif output_format == "pros_cons":
            pros = takeaways[:2] or ["Cross-source coverage exists."]
            cons = [contradictions[0]] if contradictions else ["Evidence remains source-limited."]
            explanation = f"Pros: {'; '.join(pros)}\nCons: {'; '.join(cons)}"
        elif output_format == "timeline":
            explanation = self._timeline_style(top)
        elif output_format == "fact_check":
            explanation = f"Verified claims are strongest in {source_names}. Uncertainty remains where sources do not fully agree."
        else:
            explanation = base

        return {
            "explanation": explanation,
            "key_takeaways": takeaways[:6],
            "why_it_matters": "This helps you separate durable trends from short-lived noise.",
            "what_changed_last_week": self._last_week_delta(docs),
        }

    def _timeline_style(self, docs: List[SourceDoc]) -> str:
        lines = []
        for doc in docs:
            stamp = doc.freshness_label or "recent"
            lines.append(f"{stamp}: {doc.title}")
        return "\n".join(lines) or "No recent milestones available."

    def _parse_json_response(self, text: str) -> Dict[str, object]:
        raw = (text or "").strip()
        if not raw:
            raise ValueError("Empty model response")
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            pass
        fenced = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw, flags=re.IGNORECASE | re.DOTALL).strip()
        try:
            return json.loads(fenced)
        except json.JSONDecodeError:
            pass
        match = re.search(r"\{.*\}", fenced, flags=re.DOTALL)
        if match:
            return json.loads(match.group(0))
        raise ValueError("Model response was not valid JSON")

    def _context_block(self, docs: List[SourceDoc]) -> str:
        lines = []
        for idx, doc in enumerate(docs, start=1):
            authors = ""
            if doc.research_metadata and doc.research_metadata.authors:
                authors = f" | Authors: {', '.join(doc.research_metadata.authors[:4])}"
            lines.append(
                f"[{idx}] {doc.title}\n"
                f"Source: {doc.source} | Category: {doc.category} | Freshness: {doc.freshness_label}{authors}\n"
                f"Citation: {doc.citation_snippet}\n"
                f"Summary: {doc.summary[:500]}"
            )
        return "\n\n".join(lines)

    def _last_week_delta(self, docs: List[SourceDoc]) -> str:
        now = datetime.now(timezone.utc)
        one_week_ago = now - timedelta(days=7)
        recent = 0
        older = 0
        for doc in docs[:15]:
            if not doc.published_at:
                continue
            ts = doc.published_at if doc.published_at.tzinfo else doc.published_at.replace(tzinfo=timezone.utc)
            if ts >= one_week_ago:
                recent += 1
            else:
                older += 1
        if recent > older:
            return "Coverage accelerated in the last 7 days versus the previous period."
        if recent == older:
            return "Coverage volume looks stable week over week."
        return "Coverage cooled relative to prior weeks, but key themes remain active."
