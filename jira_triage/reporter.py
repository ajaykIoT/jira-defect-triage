"""Format the triage result into a Jira comment."""

from .analyzer import TriageResult


def build_report(r: TriageResult, confidence_min: float) -> str:
    lines = ["🤖 AUTO-TRIAGE REPORT", ""]

    if r.is_duplicate and r.duplicate_confidence >= confidence_min:
        lines += [
            f"DUPLICATE: Yes — duplicate of {r.duplicate_of} "
            f"(confidence {r.duplicate_confidence:.0%})",
            f"Reason: {r.duplicate_reason}",
        ]
        if r.past_resolution:
            lines += ["", f"Past resolution ({r.duplicate_of}): {r.past_resolution}"]
    else:
        lines.append("DUPLICATE: No confirmed duplicate found.")
        if r.similar_issues:
            sims = ", ".join(f"{s['key']} ({s['score']})" for s in r.similar_issues[:5])
            lines.append(f"Similar issues reviewed: {sims}")

    if r.root_cause:
        lines += ["", f"ROOT CAUSE: {r.root_cause}"]
    if r.suggested_resolution:
        lines += ["", f"SUGGESTED RESOLUTION: {r.suggested_resolution}"]
    if r.severity_assessment:
        lines += ["", f"SEVERITY: {r.severity_assessment}"]
    if r.image_findings:
        lines += ["", "EVIDENCE FROM ATTACHED SCREENSHOTS:", r.image_findings]

    lines += ["", "— Generated automatically by jira-triage."]
    return "\n".join(lines)
