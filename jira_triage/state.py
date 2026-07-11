"""Track which issues were already triaged (issue key -> updated timestamp)."""

import json
from pathlib import Path


class State:
    def __init__(self, path: str):
        self.path = Path(path)
        self.data: dict = {}
        if self.path.exists():
            try:
                self.data = json.loads(self.path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                self.data = {}

    def needs_triage(self, key: str, updated: str) -> bool:
        return self.data.get(key) != updated

    def mark(self, key: str, updated: str) -> None:
        self.data[key] = updated
        self.path.write_text(json.dumps(self.data, indent=1), encoding="utf-8")
