"""PEaS rule DSL model.

Rules follow a WHEN <conditions> THEN <action> form applied to fixed-format
payment messages, e.g.:

    RULE enrich_intermediary_usd_gb
    WHEN msg.repaired_field_missing('receiver_bic') AND msg.currency == 'USD' AND msg.sender_country == 'GB'
    THEN SET msg.receiver_bic = 'CHASUS33'
    CONFIDENCE 0.92
"""
from dataclasses import dataclass, field


@dataclass
class Rule:
    name: str
    conditions: list[str] = field(default_factory=list)
    action: str = ""
    confidence: float = 0.0

    def to_dsl(self) -> str:
        cond = "\n  AND ".join(self.conditions) if self.conditions else "TRUE"
        return (
            f"RULE {self.name}\n"
            f"WHEN {cond}\n"
            f"THEN {self.action}\n"
            f"CONFIDENCE {self.confidence:.2f}"
        )

    @property
    def condition_key(self) -> str:
        """Canonical key used to match against clusters/existing rules."""
        return "|".join(sorted(c.replace(" ", "") for c in self.conditions))


def parse_rules(text: str) -> list[Rule]:
    """Parse a .dsl file with one or more RULE blocks."""
    rules: list[Rule] = []
    cur: Rule | None = None
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("RULE "):
            if cur:
                rules.append(cur)
            cur = Rule(name=line[5:].strip())
        elif cur is None:
            continue
        elif line.startswith("WHEN "):
            cur.conditions = [c.strip() for c in line[5:].split(" AND ")]
        elif line.startswith("AND "):
            cur.conditions.append(line[4:].strip())
        elif line.startswith("THEN "):
            cur.action = line[5:].strip()
        elif line.startswith("CONFIDENCE "):
            cur.confidence = float(line[11:].strip())
    if cur:
        rules.append(cur)
    return rules
