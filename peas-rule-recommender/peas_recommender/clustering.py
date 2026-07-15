"""Clustering of repair cases.

Two-level clustering: repair cases are first grouped by repair pattern
(repaired_field + repair_reason), then split by message context (currency,
sender country) so that distinct corridors with distinct fixes form distinct
clusters. Within each cluster the engine mines the dominant message
conditions (shared attribute values) and the dominant repair action. Purity
of the dominant action is the base confidence signal.
"""
from collections import Counter
from dataclasses import dataclass

MIN_CLUSTER_SIZE = 5
CONDITION_SUPPORT = 0.8  # attribute value must appear in >=80% of the cluster


@dataclass
class Cluster:
    key: str                    # "field|reason|currency|country"
    repaired_field: str
    repair_reason: str
    records: list
    conditions: dict            # attr -> dominant value
    dominant_action: str
    action_support: int

    @property
    def size(self) -> int:
        return len(self.records)

    @property
    def purity(self) -> float:
        return self.action_support / self.size if self.size else 0.0


def build_clusters(rows: list) -> list["Cluster"]:
    groups: dict[str, list] = {}
    for r in rows:
        key = (f"{r['repaired_field']}|{r['repair_reason']}"
               f"|{r['currency'] or '?'}|{r['sender_country'] or '?'}")
        groups.setdefault(key, []).append(r)

    clusters = []
    for key, records in groups.items():
        field_, reason = key.split("|", 2)[:2]
        conditions = {}
        for attr in ("currency", "sender_country", "msg_type"):
            vals = Counter(r[attr] for r in records if r[attr])
            if vals:
                val, n = vals.most_common(1)[0]
                if n / len(records) >= CONDITION_SUPPORT:
                    conditions[attr] = val
        actions = Counter(r["new_value"] for r in records)
        dominant, support = actions.most_common(1)[0]
        clusters.append(Cluster(key, field_, reason, records, conditions,
                                dominant, support))
    return clusters
