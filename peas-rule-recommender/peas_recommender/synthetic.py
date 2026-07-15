"""Synthetic new_journal data generator.

Produces realistic manual-repair audit records: a handful of strong repeating
repair patterns (which the engine should learn), plus random noise repairs
(which it should ignore).
"""
import random
from datetime import datetime, timedelta

# Strong patterns:
# (repaired_field, repair_reason, condition attrs, old_value, dominant new_value, count)
PATTERNS = [
    ("receiver_bic", "MISSING_INTERMEDIARY_BIC",
     {"currency": "USD", "sender_country": "GB"}, "", "CHASUS33", 14),
    ("charge_code", "INVALID_CHARGE_CODE",
     {"currency": "EUR", "sender_country": "DE"}, "DEB", "SHA", 9),
    ("bene_account", "MISSING_IBAN_PREFIX",
     {"currency": "EUR", "sender_country": "FR"}, "", "PREPEND_FR76", 7),
    # Pattern that overlaps an existing rule but with a different action ->
    # should surface as an UPDATE_RULE recommendation.
    ("charge_code", "INVALID_CHARGE_CODE",
     {"currency": "GBP", "sender_country": "HK"}, "DEB", "OUR", 6),
    # Small cluster (< 5) -> must NOT generate a rule.
    ("value_date", "STALE_VALUE_DATE",
     {"currency": "JPY", "sender_country": "JP"}, "2026-03-14", "ROLL_NEXT_BUSINESS_DAY", 3),
]

NOISE_FIELDS = [
    ("sender_ref", "DUPLICATE_REFERENCE"),
    ("bene_name", "TRUNCATED_NAME"),
    ("remit_info", "INVALID_CHARSET"),
]
CURRENCIES = ["USD", "EUR", "GBP", "JPY", "HKD", "SGD"]
COUNTRIES = ["GB", "DE", "FR", "US", "HK", "SG", "JP"]
OPERATORS = ["ops_amara", "ops_wei", "ops_priya", "ops_tom"]


def _mid(i: int) -> str:
    return f"2631810{i:06d}SL00"


def generate(conn, days: int = 7, noise: int = 12, seed: int = 42) -> int:
    """Insert synthetic repair records spread over the past `days` days."""
    rng = random.Random(seed)
    now = datetime.utcnow()
    rows = []
    i = 0

    for field_, reason, attrs, old_value, new_value, count in PATTERNS:
        for _ in range(count):
            i += 1
            ts = now - timedelta(days=rng.uniform(0, days))
            # ~10% of records in a cluster disagree on the fix (operator variance)
            nv = new_value if rng.random() > 0.10 else new_value + "_ALT"
            rows.append((
                _mid(i), "MT103", attrs["currency"], round(rng.uniform(1e3, 5e6), 2),
                f"{rng.choice(['MIDL','HSBC','BARC'])}{attrs['sender_country']}22",
                attrs["sender_country"], "" if "bic" in field_ else "HSBCHKHH",
                field_, reason, old_value, nv, rng.choice(OPERATORS),
                ts.isoformat(timespec="seconds"),
            ))

    for _ in range(noise):
        i += 1
        field_, reason = rng.choice(NOISE_FIELDS)
        ts = now - timedelta(days=rng.uniform(0, days))
        rows.append((
            _mid(i), "MT103", rng.choice(CURRENCIES), round(rng.uniform(1e3, 5e6), 2),
            f"HSBC{rng.choice(COUNTRIES)}22", rng.choice(COUNTRIES), "HSBCHKHH",
            field_, reason, "OLD", f"FIX_{rng.randint(100,999)}",
            rng.choice(OPERATORS), ts.isoformat(timespec="seconds"),
        ))

    conn.executemany(
        """INSERT INTO new_journal
           (mid, msg_type, currency, amount, sender_bic, sender_country,
            receiver_bic, repaired_field, repair_reason, old_value, new_value,
            operator_id, repaired_at)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        rows,
    )
    conn.commit()
    return len(rows)
