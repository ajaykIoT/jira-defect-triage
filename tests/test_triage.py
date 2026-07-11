"""Unit tests with mocked Jira and OpenAI — no network needed."""

import json
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).parent.parent))

from jira_triage.analyzer import TriageResult, _extract_json
from jira_triage.jira_client import Defect, _adf_to_text, text_to_adf
from jira_triage.reporter import build_report
from jira_triage.similarity import rank_candidates
from jira_triage.state import State


def make_defect(key, summary, description="", resolution="", updated="2026-01-01T00:00:00"):
    return Defect(key=key, summary=summary, description=description,
                  resolution=resolution, updated=updated)


class TestAdf(unittest.TestCase):
    def test_roundtrip_text(self):
        adf = text_to_adf("line one\nline two")
        self.assertEqual(adf["type"], "doc")
        self.assertEqual(len(adf["content"]), 2)

    def test_adf_to_text(self):
        adf = {"type": "doc", "content": [
            {"type": "paragraph", "content": [{"type": "text", "text": "hello"}]},
            {"type": "paragraph", "content": [{"type": "text", "text": "world"}]},
        ]}
        self.assertEqual(_adf_to_text(adf).strip(), "hello\nworld")


class TestSimilarity(unittest.TestCase):
    def test_ranks_similar_first(self):
        target = make_defect("P-10", "Login page crashes with NullPointerException on submit")
        corpus = [
            make_defect("P-1", "Login page crash NullPointerException when submitting form"),
            make_defect("P-2", "Export to CSV produces empty file"),
            make_defect("P-10", "self should be excluded"),
        ]
        cands = rank_candidates(target, corpus, top_k=5, score_cutoff=40)
        self.assertTrue(cands)
        self.assertEqual(cands[0].defect.key, "P-1")
        self.assertNotIn("P-10", [c.defect.key for c in cands])

    def test_cutoff_filters_noise(self):
        target = make_defect("P-10", "Payment gateway timeout on checkout")
        corpus = [make_defect("P-2", "zzz completely unrelated qqq")]
        self.assertEqual(rank_candidates(target, corpus, score_cutoff=60), [])


class TestAnalyzerParsing(unittest.TestCase):
    def test_extract_json(self):
        raw = 'Here you go:\n{"is_duplicate": true, "duplicate_of": "P-1"}\nthanks'
        self.assertTrue(_extract_json(raw)["is_duplicate"])

    def test_triage_parses_and_validates_duplicate_key(self):
        from jira_triage.analyzer import Analyzer
        with patch("jira_triage.analyzer.openai.OpenAI"):
            a = Analyzer("key", "model")
        payload = {
            "is_duplicate": True, "duplicate_of": "P-1", "duplicate_confidence": 0.9,
            "duplicate_reason": "same stack trace", "past_resolution": "fixed null check",
            "root_cause": "missing null check", "suggested_resolution": "add guard",
            "severity_assessment": "high",
        }
        a._call = MagicMock(return_value=json.dumps(payload))
        from jira_triage.similarity import Candidate
        cand = Candidate(defect=make_defect("P-1", "same bug", resolution="Fixed"), score=95.0)
        r = a.triage(make_defect("P-2", "same bug again"), [cand])
        self.assertTrue(r.is_duplicate)
        self.assertEqual(r.duplicate_of, "P-1")
        self.assertEqual(r.past_resolution, "fixed null check")

        # hallucinated key not in candidates -> rejected
        payload["duplicate_of"] = "P-999"
        a._call = MagicMock(return_value=json.dumps(payload))
        r = a.triage(make_defect("P-2", "same bug again"), [cand])
        self.assertFalse(r.is_duplicate)


class TestReporter(unittest.TestCase):
    def test_duplicate_report(self):
        r = TriageResult(key="P-2", is_duplicate=True, duplicate_of="P-1",
                         duplicate_confidence=0.9, duplicate_reason="same trace",
                         past_resolution="patched in v2.1", root_cause="race condition",
                         suggested_resolution="apply same patch", severity_assessment="medium")
        text = build_report(r, confidence_min=0.7)
        for expected in ["duplicate of P-1", "patched in v2.1", "ROOT CAUSE", "race condition"]:
            self.assertIn(expected, text)

    def test_low_confidence_not_marked_duplicate(self):
        r = TriageResult(key="P-2", is_duplicate=True, duplicate_of="P-1",
                         duplicate_confidence=0.4)
        self.assertIn("No confirmed duplicate", build_report(r, confidence_min=0.7))


class TestState(unittest.TestCase):
    def test_state_tracks_updates(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            path = str(Path(tmp) / "state.json")
            s = State(path)
            self.assertTrue(s.needs_triage("P-1", "t1"))
            s.mark("P-1", "t1")
            self.assertFalse(s.needs_triage("P-1", "t1"))
            self.assertTrue(s.needs_triage("P-1", "t2"))  # issue updated -> retriage
            s2 = State(path)  # persisted
            self.assertFalse(s2.needs_triage("P-1", "t1"))


class TestEngineWriteBack(unittest.TestCase):
    def _engine(self):
        from jira_triage.config import Config
        from jira_triage.engine import TriageEngine
        cfg = Config(base_url="https://x.atlassian.net", email="e", api_token="t",
                     openai_api_key="k", state_file="/tmp/_s.json")
        with patch("jira_triage.engine.JiraClient") as jc, \
             patch("jira_triage.engine.Analyzer"):
            eng = TriageEngine(cfg)
            eng.jira = jc.return_value
        return eng

    def test_confirmed_duplicate_writes_comment_labels_link(self):
        eng = self._engine()
        defect = make_defect("P-2", "bug")
        r = TriageResult(key="P-2", is_duplicate=True, duplicate_of="P-1",
                         duplicate_confidence=0.95)
        eng._write_back(defect, r)
        eng.jira.add_comment.assert_called_once()
        labels = eng.jira.add_labels.call_args[0][1]
        self.assertIn("auto-triaged", labels)
        self.assertIn("auto-dup", labels)
        eng.jira.link_duplicate.assert_called_once_with("P-2", "P-1")

    def test_non_duplicate_no_link(self):
        eng = self._engine()
        eng._write_back(make_defect("P-2", "bug"), TriageResult(key="P-2"))
        eng.jira.add_comment.assert_called_once()
        eng.jira.link_duplicate.assert_not_called()

    def test_dry_run_writes_nothing(self):
        eng = self._engine()
        eng.cfg.dry_run = True
        eng._write_back(make_defect("P-2", "bug"), TriageResult(key="P-2"))
        eng.jira.add_comment.assert_not_called()
        eng.jira.add_labels.assert_not_called()


if __name__ == "__main__":
    unittest.main()
