"""Recommendation engine.

Daily cycle:
  1. Fetch unprocessed repair cases from new_journal.
  2. Cluster them by repair pattern.
  3. For clusters with >= 5 records, generate a candidate rule in the PEaS DSL.
  4. Score confidence (action purity x operator-feedback weight); recommend if >= 70%.
  5. If a cluster's conditions match an existing PEaS rule but the action
     differs, recommend an UPDATE to that rule instead of a new one.
"""
from datetime import datetime
from pathlib import Path

from .clustering import build_clusters, MIN_CLUSTER_SIZE, Cluster
from .dsl import Rule, parse_rules

CONFIDENCE_THRESHOLD = 0.70


def _cluster_conditions_dsl(c: Cluster) -> list[str]:
    conds = [f"msg.field_missing('{c.repaired_field}')"
             if not any(r["old_value"] for r in c.records)
             else f"msg.reason == '{c.repair_reason}'"]
    for attr, val in sorted(c.conditions.items()):
        conds.append(f"msg.{attr} == '{val}'")
    return conds


def _candidate_rule(c: Cluster, confidence: float) -> Rule:
    name = f"auto_{c.repaired_field}_{c.repair_reason.lower()}"[:48]
    action = f"SET msg.{c.repaired_field} = '{c.dominant_action}'"
    return Rule(name=name, conditions=_cluster_conditions_dsl(c), action=action,
                confidence=confidence)


def _feedback_weight(conn, cluster_key: str) -> float:
    row = conn.execute("SELECT weight FROM feedback_weights WHERE cluster_key=?",
                       (cluster_key,)).fetchone()
    return row["weight"] if row else 1.0


def _match_existing(rule: Rule, existing: list[Rule]) -> Rule | None:
    """An existing rule whose conditions overlap the candidate's conditions."""
    cand = set(rule.conditions)
    for ex in existing:
        if set(ex.conditions) == cand and ex.action != rule.action:
            return ex
    return None


def run_cycle(conn, rules_path: str | Path, now: datetime | None = None,
              log=print) -> dict:
    now = now or datetime.utcnow()
    existing = parse_rules(Path(rules_path).read_text()) if Path(rules_path).exists() else []

    rows = conn.execute("SELECT * FROM new_journal WHERE processed=0").fetchall()
    log(f"[fetch] {len(rows)} unprocessed repair cases loaded from new_journal")

    clusters = build_clusters(rows)
    log(f"[cluster] {len(clusters)} repair-pattern clusters formed")

    recommended = 0
    for c in sorted(clusters, key=lambda x: -x.size):
        if c.size < MIN_CLUSTER_SIZE:
            log(f"[skip] {c.key}: cluster size {c.size} < {MIN_CLUSTER_SIZE}")
            continue
        weight = _feedback_weight(conn, c.key)
        confidence = round(min(c.purity * weight, 0.99), 2)
        rule = _candidate_rule(c, confidence)
        verdict = "PASS" if confidence >= CONFIDENCE_THRESHOLD else "FAIL"
        log(f"[score] {c.key}: size={c.size} purity={c.purity:.2f} "
            f"feedback_weight={weight:.2f} -> confidence={confidence:.2f} [{verdict}]")
        if confidence < CONFIDENCE_THRESHOLD:
            continue

        target = _match_existing(rule, existing)
        rec_type = "UPDATE_RULE" if target else "NEW_RULE"
        conn.execute(
            """INSERT INTO recommendations
               (rec_type, target_rule, rule_dsl, confidence, cluster_size,
                cluster_key, created_at) VALUES (?,?,?,?,?,?,?)""",
            (rec_type, target.name if target else None, rule.to_dsl(),
             confidence, c.size, c.key, now.isoformat(timespec="seconds")),
        )
        recommended += 1
        label = f"update to existing rule '{target.name}'" if target else "new rule"
        log(f"[recommend] {label}: {rule.name} (confidence {confidence:.0%}, "
            f"{c.size} supporting repairs)")

    conn.execute("UPDATE new_journal SET processed=1 WHERE processed=0")
    conn.execute("INSERT INTO run_log (ran_at, fetched, clusters, recommended) VALUES (?,?,?,?)",
                 (now.isoformat(timespec="seconds"), len(rows), len(clusters), recommended))
    conn.commit()
    return {"fetched": len(rows), "clusters": len(clusters), "recommended": recommended}
