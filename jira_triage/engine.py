"""Orchestrates a full triage cycle: fetch -> analyze -> write back to Jira."""

import logging

from .analyzer import Analyzer, TriageResult
from .config import Config
from .jira_client import IMAGE_MIMES, Defect, JiraClient
from .reporter import build_report
from .similarity import rank_candidates
from .state import State

log = logging.getLogger(__name__)


class TriageEngine:
    def __init__(self, cfg: Config):
        self.cfg = cfg
        self.jira = JiraClient(cfg.base_url, cfg.email, cfg.api_token)
        self.analyzer = Analyzer(cfg.openai_api_key, cfg.model, cfg.max_tokens)
        self.state = State(cfg.state_file)
        self._corpus: list = []

    # ---------- corpus ----------

    def load_corpus(self) -> list:
        log.info("Loading defect corpus (max %d)...", self.cfg.corpus_max_issues)
        self._corpus = self.jira.search(self.cfg.corpus_jql, self.cfg.corpus_max_issues)
        log.info("Corpus: %d defects", len(self._corpus))
        return self._corpus

    # ---------- single defect ----------

    def _collect_images(self, defect: Defect) -> list:
        images = []
        if not self.cfg.analyze_image_attachments:
            return images
        for a in defect.attachments:
            if len(images) >= self.cfg.max_images_per_issue:
                break
            if a["mimeType"] not in IMAGE_MIMES:
                continue
            if a["size"] > self.cfg.max_image_bytes:
                log.info("%s: skipping oversized image %s", defect.key, a["filename"])
                continue
            try:
                data = self.jira.download_attachment(a["content_url"], self.cfg.max_image_bytes)
            except Exception as e:  # noqa: BLE001 - keep triaging on download failure
                log.warning("%s: failed to download %s: %s", defect.key, a["filename"], e)
                continue
            if data:
                images.append((a["filename"], a["mimeType"], data))
        return images

    def triage_one(self, defect: Defect) -> TriageResult:
        log.info("Triaging %s: %s", defect.key, defect.summary[:80])

        images = self._collect_images(defect)
        image_findings = ""
        if images:
            try:
                image_findings = self.analyzer.analyze_images(defect, images)
            except Exception as e:  # noqa: BLE001
                log.warning("%s: image analysis failed: %s", defect.key, e)

        candidates = rank_candidates(
            defect, self._corpus,
            top_k=self.cfg.top_k_candidates,
            score_cutoff=self.cfg.candidate_score_cutoff,
        )
        result = self.analyzer.triage(defect, candidates, image_findings)
        self._write_back(defect, result)
        return result

    # ---------- write back ----------

    def _write_back(self, defect: Defect, r: TriageResult) -> None:
        report = build_report(r, self.cfg.duplicate_confidence_min)
        confirmed_dup = r.is_duplicate and r.duplicate_confidence >= self.cfg.duplicate_confidence_min

        if self.cfg.dry_run:
            print(f"\n===== DRY RUN: {defect.key} =====\n{report}\n")
            return

        if self.cfg.add_comment:
            self.jira.add_comment(defect.key, report)
        if self.cfg.add_labels:
            labels = [self.cfg.triaged_label]
            if confirmed_dup:
                labels.append(self.cfg.duplicate_label)
            self.jira.add_labels(defect.key, labels)
        if confirmed_dup and self.cfg.link_duplicates and r.duplicate_of:
            if r.duplicate_of not in defect.linked_keys:
                try:
                    self.jira.link_duplicate(defect.key, r.duplicate_of)
                except Exception as e:  # noqa: BLE001
                    log.warning("%s: could not create duplicate link: %s", defect.key, e)
        log.info("%s: triage logged to Jira (duplicate=%s)", defect.key, confirmed_dup)

    # ---------- cycles ----------

    def run_cycle(self) -> list:
        """One polling cycle. Returns list of TriageResult."""
        self.load_corpus()
        pending = self.jira.search(self.cfg.triage_jql, self.cfg.max_results_per_poll)
        results = []
        for defect in pending:
            if not self.state.needs_triage(defect.key, defect.updated):
                continue
            try:
                results.append(self.triage_one(defect))
                self.state.mark(defect.key, defect.updated)
            except Exception as e:  # noqa: BLE001
                log.error("Triage failed for %s: %s", defect.key, e)
        log.info("Cycle done: %d triaged", len(results))
        return results

    def run_keys(self, keys: list) -> list:
        """Triage specific issue keys on demand."""
        self.load_corpus()
        results = []
        for key in keys:
            defect = self.jira.get_issue(key)
            results.append(self.triage_one(defect))
            self.state.mark(defect.key, defect.updated)
        return results
