"""Fast candidate retrieval: rank existing defects by textual similarity."""

from dataclasses import dataclass

from rapidfuzz import fuzz

from .jira_client import Defect


@dataclass
class Candidate:
    defect: Defect
    score: float  # 0-100


def rank_candidates(target: Defect, corpus: list, top_k: int = 8,
                    score_cutoff: float = 40.0) -> list:
    """Return top_k most similar defects from corpus (excluding target itself)."""
    t_summary = target.summary.lower()
    t_blob = target.text_blob().lower()

    scored = []
    for d in corpus:
        if d.key == target.key:
            continue
        s = max(
            fuzz.token_set_ratio(t_summary, d.summary.lower()),
            0.85 * fuzz.token_set_ratio(t_blob, d.text_blob().lower()),
            0.9 * fuzz.partial_ratio(t_summary, d.summary.lower()),
        )
        if s >= score_cutoff:
            scored.append(Candidate(defect=d, score=round(s, 1)))

    scored.sort(key=lambda c: c.score, reverse=True)
    return scored[:top_k]
