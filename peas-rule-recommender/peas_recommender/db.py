"""Database layer.

SQLite stands in for the GPE database. The `new_journal` table mirrors the
audit records written by operators when they manually repair non-STP payments.
"""
import sqlite3
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS new_journal (
    journal_id      INTEGER PRIMARY KEY AUTOINCREMENT,
    mid             TEXT NOT NULL,              -- message id
    msg_type        TEXT NOT NULL,              -- e.g. MT103
    currency        TEXT,
    amount          REAL,
    sender_bic      TEXT,
    sender_country  TEXT,
    receiver_bic    TEXT,
    repaired_field  TEXT NOT NULL,              -- field fixed by the operator
    repair_reason   TEXT NOT NULL,              -- reason code recorded in audit
    old_value       TEXT,                       -- value before repair (may be empty)
    new_value       TEXT NOT NULL,              -- value after repair
    operator_id     TEXT,
    repaired_at     TEXT NOT NULL,
    processed       INTEGER DEFAULT 0           -- consumed by the recommender
);

CREATE TABLE IF NOT EXISTS recommendations (
    rec_id          INTEGER PRIMARY KEY AUTOINCREMENT,
    rec_type        TEXT NOT NULL,              -- NEW_RULE | UPDATE_RULE
    target_rule     TEXT,                       -- existing rule name for updates
    rule_dsl        TEXT NOT NULL,
    confidence      REAL NOT NULL,
    cluster_size    INTEGER NOT NULL,
    cluster_key     TEXT NOT NULL,
    status          TEXT DEFAULT 'PENDING',     -- PENDING | ACCEPTED | REJECTED
    decided_by      TEXT,
    decided_at      TEXT,
    created_at      TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS operator_actions (
    action_id       INTEGER PRIMARY KEY AUTOINCREMENT,
    rec_id          INTEGER NOT NULL REFERENCES recommendations(rec_id),
    action          TEXT NOT NULL,              -- ACCEPT | REJECT
    operator_id     TEXT NOT NULL,
    comment         TEXT,
    acted_at        TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS feedback_weights (
    cluster_key     TEXT PRIMARY KEY,           -- (repaired_field|repair_reason)
    weight          REAL NOT NULL DEFAULT 1.0,
    accepts         INTEGER DEFAULT 0,
    rejects         INTEGER DEFAULT 0,
    updated_at      TEXT
);

CREATE TABLE IF NOT EXISTS run_log (
    run_id          INTEGER PRIMARY KEY AUTOINCREMENT,
    ran_at          TEXT NOT NULL,
    fetched         INTEGER,
    clusters        INTEGER,
    recommended     INTEGER
);
"""


def connect(db_path: str | Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    return conn
