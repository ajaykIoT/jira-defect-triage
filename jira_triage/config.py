"""Load configuration from config.yaml + environment (.env)."""

import os
from dataclasses import dataclass, field
from pathlib import Path

import yaml
from dotenv import load_dotenv


@dataclass
class Config:
    # jira
    base_url: str = ""
    email: str = ""
    api_token: str = ""
    triage_jql: str = ""
    corpus_jql: str = ""
    corpus_max_issues: int = 1000
    max_results_per_poll: int = 25
    # triage
    top_k_candidates: int = 8
    candidate_score_cutoff: int = 40
    duplicate_confidence_min: float = 0.7
    analyze_image_attachments: bool = True
    max_images_per_issue: int = 4
    max_image_bytes: int = 4_718_592
    # output
    add_comment: bool = True
    add_labels: bool = True
    triaged_label: str = "auto-triaged"
    duplicate_label: str = "auto-dup"
    link_duplicates: bool = True
    dry_run: bool = False
    # llm
    openai_api_key: str = ""
    model: str = "gpt-4o"
    max_tokens: int = 2048
    # poll
    interval_seconds: int = 300
    state_file: str = ".triage_state.json"
    raw: dict = field(default_factory=dict)


def load_config(path: str = "config.yaml") -> Config:
    load_dotenv()
    data: dict = {}
    p = Path(path)
    if p.exists():
        data = yaml.safe_load(p.read_text(encoding="utf-8")) or {}

    j = data.get("jira", {})
    t = data.get("triage", {})
    o = data.get("output", {})
    l = data.get("llm", {})
    pl = data.get("poll", {})

    cfg = Config(
        base_url=os.environ.get("JIRA_BASE_URL", "").rstrip("/"),
        email=os.environ.get("JIRA_EMAIL", ""),
        api_token=os.environ.get("JIRA_API_TOKEN", ""),
        openai_api_key=os.environ.get("OPENAI_API_KEY", ""),
        triage_jql=j.get("triage_jql", Config.triage_jql),
        corpus_jql=j.get("corpus_jql", Config.corpus_jql),
        corpus_max_issues=j.get("corpus_max_issues", Config.corpus_max_issues),
        max_results_per_poll=j.get("max_results_per_poll", Config.max_results_per_poll),
        top_k_candidates=t.get("top_k_candidates", Config.top_k_candidates),
        candidate_score_cutoff=t.get("candidate_score_cutoff", Config.candidate_score_cutoff),
        duplicate_confidence_min=t.get("duplicate_confidence_min", Config.duplicate_confidence_min),
        analyze_image_attachments=t.get("analyze_image_attachments", True),
        max_images_per_issue=t.get("max_images_per_issue", Config.max_images_per_issue),
        max_image_bytes=t.get("max_image_bytes", Config.max_image_bytes),
        add_comment=o.get("add_comment", True),
        add_labels=o.get("add_labels", True),
        triaged_label=o.get("triaged_label", Config.triaged_label),
        duplicate_label=o.get("duplicate_label", Config.duplicate_label),
        link_duplicates=o.get("link_duplicates", True),
        dry_run=o.get("dry_run", False),
        model=l.get("model", Config.model),
        max_tokens=l.get("max_tokens", Config.max_tokens),
        interval_seconds=pl.get("interval_seconds", Config.interval_seconds),
        state_file=pl.get("state_file", Config.state_file),
        raw=data,
    )

    missing = [n for n, v in [
        ("JIRA_BASE_URL", cfg.base_url),
        ("JIRA_EMAIL", cfg.email),
        ("JIRA_API_TOKEN", cfg.api_token),
        ("OPENAI_API_KEY", cfg.openai_api_key),
    ] if not v]
    if missing:
        raise SystemExit(f"Missing required environment variables: {', '.join(missing)} (see .env.example)")
    return cfg
