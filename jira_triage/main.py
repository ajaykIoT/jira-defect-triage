"""CLI entry point: run once, poll continuously, or triage specific issues."""

import argparse
import logging
import time

from .config import load_config
from .engine import TriageEngine


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="jira-triage",
        description="Auto-triage Jira defects: duplicates, past resolutions, root cause.",
    )
    parser.add_argument("-c", "--config", default="config.yaml", help="path to config.yaml")
    parser.add_argument("--once", action="store_true", help="run a single cycle and exit")
    parser.add_argument("--poll", action="store_true", help="poll continuously (default)")
    parser.add_argument("--issues", nargs="+", metavar="KEY", help="triage specific issue keys, e.g. PROJ-123")
    parser.add_argument("--dry-run", action="store_true", help="analyze but write nothing to Jira")
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    cfg = load_config(args.config)
    if args.dry_run:
        cfg.dry_run = True

    engine = TriageEngine(cfg)

    if args.issues:
        engine.run_keys(args.issues)
        return
    if args.once:
        engine.run_cycle()
        return

    # default: poll forever
    logging.info("Polling every %d seconds. Ctrl+C to stop.", cfg.interval_seconds)
    while True:
        try:
            engine.run_cycle()
        except KeyboardInterrupt:
            raise
        except Exception as e:  # noqa: BLE001 - keep the poller alive
            logging.error("Cycle failed: %s", e)
        time.sleep(cfg.interval_seconds)


if __name__ == "__main__":
    main()
