"""Minimal Jira Cloud REST v3 client for defect triage."""

import logging
from dataclasses import dataclass, field
from typing import Optional

import requests

log = logging.getLogger(__name__)

IMAGE_MIMES = {"image/png", "image/jpeg", "image/gif", "image/webp"}

FIELDS = [
    "summary", "description", "status", "resolution", "resolutiondate",
    "priority", "labels", "components", "created", "updated",
    "attachment", "comment", "issuelinks", "issuetype",
]


@dataclass
class Defect:
    key: str
    summary: str = ""
    description: str = ""
    status: str = ""
    resolution: str = ""
    resolution_date: str = ""
    priority: str = ""
    labels: list = field(default_factory=list)
    components: list = field(default_factory=list)
    created: str = ""
    updated: str = ""
    comments: list = field(default_factory=list)          # [{author, body}]
    attachments: list = field(default_factory=list)       # [{id, filename, mimeType, size, content_url}]
    linked_keys: list = field(default_factory=list)

    @property
    def is_resolved(self) -> bool:
        return bool(self.resolution) and self.resolution.lower() != "unresolved"

    def text_blob(self) -> str:
        return f"{self.summary}\n{self.description}"


def _adf_to_text(node) -> str:
    """Flatten Atlassian Document Format (or plain string) to text."""
    if node is None:
        return ""
    if isinstance(node, str):
        return node
    if isinstance(node, list):
        return "".join(_adf_to_text(n) for n in node)
    if isinstance(node, dict):
        t = node.get("type")
        if t == "text":
            return node.get("text", "")
        if t == "hardBreak":
            return "\n"
        if t == "mention":
            return node.get("attrs", {}).get("text", "")
        inner = _adf_to_text(node.get("content", []))
        if t in {"paragraph", "heading", "listItem", "codeBlock", "blockquote"}:
            return inner + "\n"
        return inner
    return ""


def text_to_adf(text: str) -> dict:
    """Wrap plain text (with newlines) into a minimal ADF document."""
    paragraphs = []
    for para in text.split("\n"):
        content = [{"type": "text", "text": para}] if para else []
        paragraphs.append({"type": "paragraph", "content": content})
    return {"type": "doc", "version": 1, "content": paragraphs}


class JiraClient:
    def __init__(self, base_url: str, email: str, api_token: str, timeout: int = 30):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.session = requests.Session()
        self.session.auth = (email, api_token)
        self.session.headers.update({"Accept": "application/json"})

    # ---------- read ----------

    def search(self, jql: str, max_issues: int = 100) -> list["Defect"]:
        """Run JQL and return parsed defects (paginated)."""
        issues, token = [], None
        while len(issues) < max_issues:
            payload = {
                "jql": jql,
                "maxResults": min(100, max_issues - len(issues)),
                "fields": FIELDS,
            }
            if token:
                payload["nextPageToken"] = token
            r = self.session.post(f"{self.base_url}/rest/api/3/search/jql",
                                  json=payload, timeout=self.timeout)
            r.raise_for_status()
            data = r.json()
            issues.extend(self._parse_issue(i) for i in data.get("issues", []))
            token = data.get("nextPageToken")
            if not token or data.get("isLast", True):
                break
        return issues

    def get_issue(self, key: str) -> "Defect":
        r = self.session.get(f"{self.base_url}/rest/api/3/issue/{key}",
                             params={"fields": ",".join(FIELDS)}, timeout=self.timeout)
        r.raise_for_status()
        return self._parse_issue(r.json())

    def download_attachment(self, content_url: str, max_bytes: int) -> Optional[bytes]:
        r = self.session.get(content_url, timeout=self.timeout, stream=True)
        r.raise_for_status()
        buf = b""
        for chunk in r.iter_content(chunk_size=65536):
            buf += chunk
            if len(buf) > max_bytes:
                log.warning("Attachment exceeds %d bytes, skipping", max_bytes)
                return None
        return buf

    # ---------- write ----------

    def add_comment(self, key: str, text: str) -> None:
        r = self.session.post(f"{self.base_url}/rest/api/3/issue/{key}/comment",
                              json={"body": text_to_adf(text)}, timeout=self.timeout)
        r.raise_for_status()

    def add_labels(self, key: str, labels: list) -> None:
        r = self.session.put(
            f"{self.base_url}/rest/api/3/issue/{key}",
            json={"update": {"labels": [{"add": lb} for lb in labels]}},
            timeout=self.timeout)
        r.raise_for_status()

    def link_duplicate(self, dup_key: str, original_key: str) -> None:
        """Create a 'Duplicate' link: dup_key duplicates original_key."""
        r = self.session.post(
            f"{self.base_url}/rest/api/3/issueLink",
            json={
                "type": {"name": "Duplicate"},
                "inwardIssue": {"key": original_key},   # "is duplicated by"
                "outwardIssue": {"key": dup_key},       # "duplicates"
            },
            timeout=self.timeout)
        r.raise_for_status()

    # ---------- parsing ----------

    def _parse_issue(self, raw: dict) -> "Defect":
        f = raw.get("fields", {})
        comments = [{
            "author": (c.get("author") or {}).get("displayName", "unknown"),
            "body": _adf_to_text(c.get("body")).strip(),
        } for c in (f.get("comment") or {}).get("comments", [])]

        attachments = [{
            "id": a.get("id"),
            "filename": a.get("filename", ""),
            "mimeType": a.get("mimeType", ""),
            "size": a.get("size", 0),
            "content_url": a.get("content", ""),
        } for a in (f.get("attachment") or [])]

        linked = []
        for ln in f.get("issuelinks") or []:
            other = ln.get("inwardIssue") or ln.get("outwardIssue") or {}
            if other.get("key"):
                linked.append(other["key"])

        return Defect(
            key=raw.get("key", ""),
            summary=f.get("summary") or "",
            description=_adf_to_text(f.get("description")).strip(),
            status=((f.get("status") or {}).get("name") or ""),
            resolution=((f.get("resolution") or {}).get("name") or ""),
            resolution_date=f.get("resolutiondate") or "",
            priority=((f.get("priority") or {}).get("name") or ""),
            labels=f.get("labels") or [],
            components=[c.get("name", "") for c in f.get("components") or []],
            created=f.get("created") or "",
            updated=f.get("updated") or "",
            comments=comments,
            attachments=attachments,
            linked_keys=linked,
        )
