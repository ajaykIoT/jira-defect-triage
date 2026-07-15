"""Operator feedback loop.

Operators accept or reject each recommendation. Decisions are stored in
operator_actions and folded into feedback_weights, which scale the confidence
of future recommendations for the same repair pattern (model refinement).
"""
from datetime import datetime

ACCEPT_BOOST = 0.05   # each accept nudges the pattern weight up
REJECT_PENALTY = 0.15  # each reject pushes it down harder
WEIGHT_MIN, WEIGHT_MAX = 0.4, 1.2


def decide(conn, rec_id: int, action: str, operator_id: str,
           comment: str = "", now: datetime | None = None) -> dict:
    action = action.upper()
    assert action in ("ACCEPT", "REJECT")
    now = now or datetime.utcnow()

    rec = conn.execute("SELECT * FROM recommendations WHERE rec_id=?", (rec_id,)).fetchone()
    if rec is None:
        raise ValueError(f"recommendation {rec_id} not found")
    if rec["status"] != "PENDING":
        raise ValueError(f"recommendation {rec_id} already {rec['status']}")

    conn.execute(
        "INSERT INTO operator_actions (rec_id, action, operator_id, comment, acted_at) "
        "VALUES (?,?,?,?,?)",
        (rec_id, action, operator_id, comment, now.isoformat(timespec="seconds")),
    )
    conn.execute(
        "UPDATE recommendations SET status=?, decided_by=?, decided_at=? WHERE rec_id=?",
        ("ACCEPTED" if action == "ACCEPT" else "REJECTED", operator_id,
         now.isoformat(timespec="seconds"), rec_id),
    )

    # --- model refinement ---
    key = rec["cluster_key"]
    row = conn.execute("SELECT * FROM feedback_weights WHERE cluster_key=?", (key,)).fetchone()
    weight, accepts, rejects = (row["weight"], row["accepts"], row["rejects"]) if row else (1.0, 0, 0)
    if action == "ACCEPT":
        weight, accepts = min(weight + ACCEPT_BOOST, WEIGHT_MAX), accepts + 1
    else:
        weight, rejects = max(weight - REJECT_PENALTY, WEIGHT_MIN), rejects + 1
    conn.execute(
        """INSERT INTO feedback_weights (cluster_key, weight, accepts, rejects, updated_at)
           VALUES (?,?,?,?,?)
           ON CONFLICT(cluster_key) DO UPDATE SET
             weight=excluded.weight, accepts=excluded.accepts,
             rejects=excluded.rejects, updated_at=excluded.updated_at""",
        (key, round(weight, 3), accepts, rejects, now.isoformat(timespec="seconds")),
    )
    conn.commit()
    return {"rec_id": rec_id, "action": action, "new_weight": round(weight, 3)}
