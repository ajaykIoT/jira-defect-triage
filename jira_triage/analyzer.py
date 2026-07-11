"""OpenAI-powered analysis: image reading, duplicate confirmation, root cause, resolution."""

import base64
import json
import logging
import re
from dataclasses import dataclass, field

import openai

from .jira_client import Defect, IMAGE_MIMES
from .similarity import Candidate

log = logging.getLogger(__name__)


@dataclass
class TriageResult:
    key: str
    is_duplicate: bool = False
    duplicate_of: str = ""              # issue key of the original
    duplicate_confidence: float = 0.0
    duplicate_reason: str = ""
    past_resolution: str = ""           # resolution taken on the duplicate/similar issue
    root_cause: str = ""
    suggested_resolution: str = ""
    severity_assessment: str = ""
    similar_issues: list = field(default_factory=list)   # [{key, score}]
    image_findings: str = ""


def _extract_json(text: str) -> dict:
    """Pull the first JSON object out of a model response."""
    m = re.search(r"\{.*\}", text, re.DOTALL)
    if not m:
        raise ValueError(f"No JSON found in model response: {text[:200]}")
    return json.loads(m.group(0))


def _defect_snippet(d: Defect, max_desc: int = 1500, include_comments: int = 3) -> str:
    parts = [
        f"Key: {d.key}",
        f"Summary: {d.summary}",
        f"Status: {d.status} | Resolution: {d.resolution or 'Unresolved'} | Priority: {d.priority}",
        f"Components: {', '.join(d.components) or '-'}",
        f"Description: {d.description[:max_desc]}",
    ]
    if include_comments and d.comments:
        tail = d.comments[-include_comments:]
        parts.append("Recent comments:")
        parts += [f"  - {c['author']}: {c['body'][:400]}" for c in tail]
    return "\n".join(parts)


class Analyzer:
    def __init__(self, api_key: str, model: str, max_tokens: int = 2048):
        self.client = openai.OpenAI(api_key=api_key)
        self.model = model
        self.max_tokens = max_tokens

    def _call(self, content) -> str:
        resp = self.client.chat.completions.create(
            model=self.model,
            max_completion_tokens=self.max_tokens,
            messages=[{"role": "user", "content": content}],
        )
        return resp.choices[0].message.content or ""

    # ---------- image attachments ----------

    def analyze_images(self, defect: Defect, images: list) -> str:
        """images: list of (filename, mime, bytes). Returns extracted findings text."""
        if not images:
            return ""
        content = [{
            "type": "text",
            "text": (
                "These screenshots are attached to a software defect report.\n"
                f"Defect summary: {defect.summary}\n\n"
                "Extract every technically useful detail: exact error messages, stack traces, "
                "error codes, URLs, UI state, log lines, timestamps. Be concise and factual. "
                "Output plain text findings only."
            ),
        }]
        for filename, mime, data in images:
            if mime not in IMAGE_MIMES:
                continue
            content.append({"type": "text", "text": f"Attachment: {filename}"})
            b64 = base64.standard_b64encode(data).decode()
            content.append({
                "type": "image_url",
                "image_url": {"url": f"data:{mime};base64,{b64}"},
            })
        return self._call(content).strip()

    # ---------- duplicate confirmation + root cause + resolution ----------

    def triage(self, defect: Defect, candidates: list, image_findings: str = "") -> TriageResult:
        result = TriageResult(
            key=defect.key,
            image_findings=image_findings,
            similar_issues=[{"key": c.defect.key, "score": c.score} for c in candidates],
        )

        cand_block = "\n\n".join(
            f"--- CANDIDATE {i+1} (fuzzy score {c.score}) ---\n{_defect_snippet(c.defect)}"
            for i, c in enumerate(candidates)
        ) or "(no similar existing defects found)"

        img_block = f"\nEvidence extracted from attached screenshots:\n{image_findings}\n" if image_findings else ""

        prompt = f"""You are an expert software defect triage engineer.

NEW DEFECT UNDER TRIAGE:
{_defect_snippet(defect)}
{img_block}
EXISTING DEFECTS (duplicate candidates):
{cand_block}

Tasks:
1. Decide if the new defect is a DUPLICATE of one of the candidates (same underlying fault, not merely same area).
2. If duplicate and the original was resolved, summarize the past resolution from its resolution/comments.
3. Identify the most likely ROOT CAUSE of the new defect based on all evidence.
4. Propose a concrete SUGGESTED RESOLUTION (what to fix/check, next steps).
5. Assess severity briefly.

Respond with ONLY a JSON object:
{{
  "is_duplicate": true/false,
  "duplicate_of": "<issue key or empty string>",
  "duplicate_confidence": <0.0-1.0>,
  "duplicate_reason": "<one sentence>",
  "past_resolution": "<how the original was resolved, or empty string>",
  "root_cause": "<most likely root cause, 1-3 sentences>",
  "suggested_resolution": "<concrete next steps, 1-4 sentences>",
  "severity_assessment": "<one sentence>"
}}"""

        raw = self._call([{"type": "text", "text": prompt}])
        try:
            data = _extract_json(raw)
        except (ValueError, json.JSONDecodeError) as e:
            log.error("Failed to parse triage JSON for %s: %s", defect.key, e)
            result.root_cause = "Analysis failed: could not parse model output."
            return result

        result.is_duplicate = bool(data.get("is_duplicate"))
        result.duplicate_of = data.get("duplicate_of") or ""
        result.duplicate_confidence = float(data.get("duplicate_confidence") or 0.0)
        result.duplicate_reason = data.get("duplicate_reason") or ""
        result.past_resolution = data.get("past_resolution") or ""
        result.root_cause = data.get("root_cause") or ""
        result.suggested_resolution = data.get("suggested_resolution") or ""
        result.severity_assessment = data.get("severity_assessment") or ""

        # Guard: duplicate_of must actually be one of the candidates
        valid_keys = {c.defect.key for c in candidates}
        if result.is_duplicate and result.duplicate_of not in valid_keys:
            result.is_duplicate = False
            result.duplicate_of = ""
        return result
