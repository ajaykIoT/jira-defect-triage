# PEaS Rule Recommendation Engine

Learns PEaS enrichment rules from the manual repairs operators make on
non-STP payments.

## Background

PEaS enriches ~96% of payment messages. The ~3% that remain unenriched are
non-STP: operators repair them by hand, and every repair writes an audit
record (message details + repair reason) to the `new_journal` table of the
GPE database. Those audit records are a training signal — if operators keep
making the same fix under the same conditions, that fix should become a rule.

## How it works

1. **Daily fetch** — once per day the engine pulls unprocessed repair cases
   from `new_journal` (SQLite stands in for GPE; synthetic data included).
2. **Clustering** — cases are grouped by repair pattern
   (`repaired_field` + `repair_reason`); within each cluster the engine mines
   the dominant message conditions and the dominant repair action.
3. **Rule generation** — clusters with **≥ 5 records** produce a candidate
   rule in the PEaS rule DSL (`WHEN <conditions> THEN <action>`).
4. **Validation** — confidence = action purity × operator-feedback weight.
   Only candidates with **confidence ≥ 70%** are recommended.
5. **Update detection** — if a candidate's conditions match an existing PEaS
   rule (`rules/peas_rules.dsl`) but the action differs, the engine recommends
   an **update** to that rule instead of a new one.
6. **Operator review** — each recommendation is accepted or rejected; the
   decision is stored and folded into per-pattern feedback weights, refining
   future confidence scores (rejects push a pattern below the threshold).

## Quick start

```bash
python -m peas_recommender.main seed        # load synthetic new_journal data
python -m peas_recommender.main run --once  # run one daily cycle
python -m peas_recommender.main list        # view recommendations + DSL
python -m peas_recommender.main accept 1 --operator ops_amara
python -m peas_recommender.main reject 4 --operator ops_amara --comment "OUR not allowed for this corridor"
python -m peas_recommender.main run --daemon   # fetch automatically every 24h
python tests/test_engine.py                 # run the test suite
```

No third-party dependencies (Python 3.10+, stdlib only).

## Layout

```
peas_recommender/
  db.py          SQLite schema: new_journal, recommendations, operator_actions,
                 feedback_weights, run_log
  synthetic.py   synthetic repair-case generator (strong patterns + noise)
  clustering.py  repair-pattern clustering + condition/action mining
  dsl.py         PEaS rule DSL model, parser and serializer
  engine.py      daily cycle: fetch -> cluster -> generate -> validate -> recommend
  feedback.py    operator accept/reject + weight refinement
  main.py        CLI (seed / run / list / accept / reject)
rules/peas_rules.dsl   existing PEaS rules (update-detection target)
tests/test_engine.py   end-to-end tests
```
