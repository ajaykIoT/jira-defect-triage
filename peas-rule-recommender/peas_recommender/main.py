"""CLI entry point.

Usage:
  python -m peas_recommender.main seed                 # load synthetic data
  python -m peas_recommender.main run --once           # one daily cycle now
  python -m peas_recommender.main run --daemon         # run every 24h
  python -m peas_recommender.main list                 # pending recommendations
  python -m peas_recommender.main accept <id> --operator <who> [--comment ...]
  python -m peas_recommender.main reject <id> --operator <who> [--comment ...]
"""
import argparse
import time
from pathlib import Path

from . import db, synthetic, engine, feedback

BASE = Path(__file__).resolve().parent.parent
DB_PATH = BASE / "data" / "gpe.db"
RULES_PATH = BASE / "rules" / "peas_rules.dsl"


def main(argv=None):
    p = argparse.ArgumentParser(prog="peas-recommender")
    p.add_argument("--db", default=str(DB_PATH))
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("seed")
    runp = sub.add_parser("run")
    runp.add_argument("--once", action="store_true")
    runp.add_argument("--daemon", action="store_true")
    sub.add_parser("list")
    for name in ("accept", "reject"):
        sp = sub.add_parser(name)
        sp.add_argument("rec_id", type=int)
        sp.add_argument("--operator", required=True)
        sp.add_argument("--comment", default="")
    args = p.parse_args(argv)

    Path(args.db).parent.mkdir(parents=True, exist_ok=True)
    conn = db.connect(args.db)

    if args.cmd == "seed":
        n = synthetic.generate(conn)
        print(f"[seed] inserted {n} synthetic repair records into new_journal")

    elif args.cmd == "run":
        while True:
            stats = engine.run_cycle(conn, RULES_PATH)
            print(f"[done] fetched={stats['fetched']} clusters={stats['clusters']} "
                  f"recommended={stats['recommended']}")
            if not args.daemon:
                break
            time.sleep(24 * 3600)  # daily fetch

    elif args.cmd == "list":
        rows = conn.execute(
            "SELECT rec_id, rec_type, target_rule, confidence, cluster_size, status, rule_dsl "
            "FROM recommendations ORDER BY rec_id").fetchall()
        for r in rows:
            hdr = (f"#{r['rec_id']} [{r['status']}] {r['rec_type']}"
                   + (f" -> {r['target_rule']}" if r["target_rule"] else "")
                   + f"  confidence={r['confidence']:.0%} support={r['cluster_size']}")
            print(hdr)
            print("    " + r["rule_dsl"].replace("\n", "\n    "))

    else:  # accept / reject
        res = feedback.decide(conn, args.rec_id, args.cmd.upper(), args.operator, args.comment)
        print(f"[feedback] recommendation #{args.rec_id} {res['action']}ED by {args.operator}; "
              f"pattern weight -> {res['new_weight']} (used to refine future confidence)")


if __name__ == "__main__":
    main()
