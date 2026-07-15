"""End-to-end tests for the PEaS rule recommendation engine."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from peas_recommender import db, synthetic, engine, feedback
from peas_recommender.dsl import parse_rules

RULES = Path(__file__).resolve().parent.parent / "rules" / "peas_rules.dsl"


class TestEngine(unittest.TestCase):
    def setUp(self):
        self.conn = db.connect(":memory:")
        synthetic.generate(self.conn)
        self.stats = engine.run_cycle(self.conn, RULES, log=lambda *a: None)

    def recs(self):
        return self.conn.execute("SELECT * FROM recommendations ORDER BY rec_id").fetchall()

    def test_recommends_only_large_confident_clusters(self):
        keys = {r["cluster_key"] for r in self.recs()}
        self.assertFalse(any(k.startswith("value_date|") for k in keys))
        self.assertFalse(any(k.startswith("sender_ref|") for k in keys))
        self.assertTrue(any(k.startswith("receiver_bic|MISSING_INTERMEDIARY_BIC") for k in keys))
        self.assertIn("charge_code|INVALID_CHARGE_CODE|EUR|DE", keys)
        self.assertIn("charge_code|INVALID_CHARGE_CODE|GBP|HK", keys)

    def test_confidence_threshold(self):
        for r in self.recs():
            self.assertGreaterEqual(r["confidence"], engine.CONFIDENCE_THRESHOLD)

    def test_update_rule_detected(self):
        updates = [r for r in self.recs() if r["rec_type"] == "UPDATE_RULE"]
        self.assertEqual(len(updates), 1)
        self.assertEqual(updates[0]["target_rule"], "enrich_charge_code_gbp_hk")
        self.assertIn("'OUR'", updates[0]["rule_dsl"])

    def test_generated_dsl_parses(self):
        for r in self.recs():
            rules = parse_rules(r["rule_dsl"])
            self.assertEqual(len(rules), 1)
            self.assertTrue(rules[0].conditions and rules[0].action)

    def test_feedback_refines_weights(self):
        rec = self.recs()[0]
        res = feedback.decide(self.conn, rec["rec_id"], "REJECT", "ops_test")
        self.assertAlmostEqual(res["new_weight"], 1.0 - feedback.REJECT_PENALTY, places=3)
        row = self.conn.execute("SELECT status FROM recommendations WHERE rec_id=?",
                                (rec["rec_id"],)).fetchone()
        self.assertEqual(row["status"], "REJECTED")
        with self.assertRaises(ValueError):
            feedback.decide(self.conn, rec["rec_id"], "ACCEPT", "ops_test")

    def test_rejected_pattern_loses_confidence_next_cycle(self):
        rec = next(r for r in self.recs() if r["rec_type"] == "UPDATE_RULE")
        feedback.decide(self.conn, rec["rec_id"], "REJECT", "ops_test")
        self.conn.execute("UPDATE feedback_weights SET weight=0.5 WHERE cluster_key=?",
                          (rec["cluster_key"],))
        self.conn.execute(
            "UPDATE new_journal SET processed=0 "
            "WHERE repaired_field='charge_code' AND currency='GBP'")
        self.conn.commit()
        engine.run_cycle(self.conn, RULES, log=lambda *a: None)
        newest = self.conn.execute(
            "SELECT * FROM recommendations WHERE cluster_key=? ORDER BY rec_id DESC LIMIT 1",
            (rec["cluster_key"],)).fetchone()
        self.assertEqual(newest["rec_id"], rec["rec_id"])

    def test_daily_run_logged_and_idempotent(self):
        self.assertGreaterEqual(self.stats["fetched"], 40)
        stats2 = engine.run_cycle(self.conn, RULES, log=lambda *a: None)
        self.assertEqual(stats2["fetched"], 0)
        runs = self.conn.execute("SELECT COUNT(*) c FROM run_log").fetchone()["c"]
        self.assertEqual(runs, 2)


if __name__ == "__main__":
    unittest.main(verbosity=2)
