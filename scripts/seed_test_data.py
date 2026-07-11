"""Seed a Jira Cloud project with realistic test defects for jira-triage.

Creates ~10 bugs: three duplicate pairs (worded differently), two with
generated screenshot attachments, and resolves the "originals" with a fix
comment so past-resolution surfacing can be tested.

Usage:
    pip install Pillow          # only needed for this script
    python scripts/seed_test_data.py --project TEST [--dry-run]

Reads JIRA_BASE_URL, JIRA_EMAIL, JIRA_API_TOKEN from .env / environment.
"""

import argparse
import io
import os
import sys
import textwrap
from pathlib import Path

import requests
from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).parent.parent))
from jira_triage.jira_client import text_to_adf  # noqa: E402

# ---------------------------------------------------------------- defects

DEFECTS = [
    # --- pair 1: login NPE (original resolved, duplicate has screenshot) ---
    dict(
        id="login_npe_original",
        summary="NullPointerException on login form submit",
        description=(
            "Steps:\n1. Open /login\n2. Enter valid credentials\n3. Click Submit\n\n"
            "App crashes with HTTP 500. Server log shows:\n"
            "java.lang.NullPointerException at com.acme.auth.SessionManager.init(SessionManager.java:42)\n\n"
            "Happens only when 'Remember me' is unchecked."
        ),
        resolve_with=(
            "Fixed in release 2.4.1. SessionManager.init assumed a persistent cookie "
            "always exists; added a null guard and default in-memory session when "
            "'Remember me' is off. See commit a1b2c3d."
        ),
    ),
    dict(
        id="login_npe_dup",
        summary="Login page throws error 500 when signing in",
        description=(
            "Users report they cannot sign in since yesterday. Clicking the sign-in "
            "button shows 'Internal Server Error'. Screenshot of the error attached. "
            "Seems related to the session handling on the backend."
        ),
        screenshot=(
            "HTTP ERROR 500 — Internal Server Error",
            "java.lang.NullPointerException",
            "  at com.acme.auth.SessionManager.init(SessionManager.java:42)",
            "  at com.acme.auth.LoginController.doPost(LoginController.java:88)",
            "URL: https://app.acme.com/login  |  2026-07-04 14:22:31 UTC",
        ),
    ),
    # --- pair 2: payment timeout (original resolved) ---
    dict(
        id="payment_timeout_original",
        summary="Payment gateway timeout during checkout",
        description=(
            "Checkout hangs for 30s then fails with 'Gateway timeout'. "
            "Occurs for ~10% of transactions during peak hours. "
            "Gateway logs show connection pool exhaustion on the payment-svc side."
        ),
        resolve_with=(
            "Root cause: payment-svc HTTP connection pool capped at 10. Raised pool "
            "size to 100 and added a 5s circuit breaker. Deployed in 2.3.7, timeouts gone."
        ),
    ),
    dict(
        id="payment_timeout_dup",
        summary="Customers cannot complete purchase - checkout spins forever",
        description=(
            "Several customers complained that after clicking 'Pay now' the page spins "
            "and eventually shows a timeout error. Support ticket volume spiking in the "
            "evenings. Likely backend payment service issue."
        ),
    ),
    # --- pair 3: CSV export (open original, duplicate has screenshot) ---
    dict(
        id="csv_export_original",
        summary="Export to CSV produces an empty file",
        description=(
            "Reports > Export > CSV downloads a 0-byte file when the report has more "
            "than 1000 rows. Smaller reports export fine. No error shown to the user."
        ),
    ),
    dict(
        id="csv_export_dup",
        summary="Downloaded CSV report is blank for large datasets",
        description=(
            "Exporting the monthly transactions report gives a blank file. "
            "Works for small date ranges. Screenshot of the empty download attached."
        ),
        screenshot=(
            "report_2026-06.csv — 0 KB",
            "Export completed successfully",
            "Rows in report: 4,812   Rows exported: 0",
            "console: TypeError: Cannot read properties of undefined (reading 'pipe')",
            "  at StreamExporter.write (exporter.js:117)",
        ),
    ),
    # --- unique bugs ---
    dict(
        id="memory_leak",
        summary="Memory usage grows steadily until worker OOM restart",
        description=(
            "Background worker RSS grows ~200MB/hour under normal load and gets "
            "OOM-killed every ~12h. Heap dump shows unbounded growth of "
            "PendingJobRegistry entries that are never evicted."
        ),
    ),
    dict(
        id="ui_misalign",
        summary="Dashboard widgets overlap on 1366x768 screens",
        description=(
            "On smaller laptop resolutions the KPI cards on the dashboard overlap the "
            "chart area, hiding the legend. Reproduces on Chrome and Firefox. "
            "Looks like a CSS grid min-width issue."
        ),
    ),
    dict(
        id="emails_not_sent",
        summary="Password reset emails not delivered to Outlook addresses",
        description=(
            "Users with outlook.com / hotmail.com addresses never receive the password "
            "reset email. Gmail users receive it fine. SMTP logs show 550 rejected: "
            "SPF check failed for mailer.acme.com."
        ),
    ),
    dict(
        id="stale_search",
        summary="Search results show deleted items for up to 1 hour",
        description=(
            "After deleting a product it still appears in search results for up to an "
            "hour and clicking it gives a 404. Search index refresh job appears to run "
            "hourly instead of on-change."
        ),
    ),
]

DUPLICATE_PAIRS = [  # (duplicate_id, original_id)
    ("login_npe_dup", "login_npe_original"),
    ("payment_timeout_dup", "payment_timeout_original"),
    ("csv_export_dup", "csv_export_original"),
]

# ---------------------------------------------------------------- helpers


def make_screenshot_png(lines) -> bytes:
    """Render fake error-screenshot PNG from text lines (requires Pillow)."""
    from PIL import Image, ImageDraw

    pad, lh = 24, 26
    img = Image.new("RGB", (900, pad * 2 + lh * (len(lines) + 1)), "#1e1e1e")
    d = ImageDraw.Draw(img)
    d.rectangle([0, 0, 900, 36], fill="#c0392b")
    d.text((pad, 9), lines[0], fill="white")
    for i, line in enumerate(lines[1:], start=1):
        d.text((pad, 36 + pad // 2 + i * lh), line, fill="#dddddd")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _check(r):
    """raise_for_status but include Jira's error body in the message."""
    if r.status_code >= 400:
        raise SystemExit(f"Jira API error {r.status_code} for {r.url}\n{r.text[:2000]}")
    return r


class Seeder:
    def __init__(self, base_url, email, token, project, dry_run=False):
        self.base = base_url.rstrip("/")
        self.project = project
        self.dry_run = dry_run
        self.s = requests.Session()
        self.s.auth = (email, token)
        self.s.headers["Accept"] = "application/json"

    def create_bug(self, summary, description) -> str:
        if self.dry_run:
            print(f"[dry-run] create: {summary}")
            return "DRY-0"
        payload = {"fields": {
            "project": {"key": self.project},
            "issuetype": {"name": "Bug"},
            "summary": summary,
            "description": text_to_adf(description),
        }}
        r = self.s.post(f"{self.base}/rest/api/3/issue", json=payload, timeout=30)
        if r.status_code == 400 and "issuetype" in r.text.lower():
            # project may use a different type name (e.g. team-managed "Task")
            payload["fields"]["issuetype"] = {"name": "Task"}
            r = self.s.post(f"{self.base}/rest/api/3/issue", json=payload, timeout=30)
        _check(r)
        key = r.json()["key"]
        print(f"created {key}: {summary}")
        return key

    def attach(self, key, filename, data):
        if self.dry_run:
            print(f"[dry-run] attach {filename} to {key}")
            return
        r = self.s.post(
            f"{self.base}/rest/api/3/issue/{key}/attachments",
            headers={"X-Atlassian-Token": "no-check"},
            files={"file": (filename, data, "image/png")}, timeout=30)
        _check(r)
        print(f"  attached {filename}")

    def comment(self, key, text):
        if self.dry_run:
            return
        r = self.s.post(f"{self.base}/rest/api/3/issue/{key}/comment",
                        json={"body": text_to_adf(text)}, timeout=30)
        _check(r)

    def resolve(self, key, fix_comment):
        """Add fix comment and transition the issue to Done."""
        self.comment(key, f"Resolution: {fix_comment}")
        if self.dry_run:
            print(f"[dry-run] resolve {key}")
            return
        r = self.s.get(f"{self.base}/rest/api/3/issue/{key}/transitions", timeout=30)
        _check(r)
        done = next((t for t in r.json()["transitions"]
                     if t.get("to", {}).get("statusCategory", {}).get("key") == "done"), None)
        if not done:
            print(f"  WARNING: no 'Done' transition found for {key}, left open")
            return
        r = self.s.post(f"{self.base}/rest/api/3/issue/{key}/transitions",
                        json={"transition": {"id": done["id"]}}, timeout=30)
        _check(r)
        print(f"  resolved {key} (transition: {done['name']})")


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--project", required=True, help="Jira project key, e.g. TEST")
    ap.add_argument("--dry-run", action="store_true", help="print actions, write nothing")
    args = ap.parse_args()

    load_dotenv()
    base = os.environ.get("JIRA_BASE_URL", "")
    email = os.environ.get("JIRA_EMAIL", "")
    token = os.environ.get("JIRA_API_TOKEN", "")
    if not (base and email and token):
        raise SystemExit("Set JIRA_BASE_URL, JIRA_EMAIL, JIRA_API_TOKEN (see .env.example)")

    seeder = Seeder(base, email, token, args.project, args.dry_run)
    keys = {}

    for d in DEFECTS:
        key = seeder.create_bug(d["summary"], d["description"])
        keys[d["id"]] = key
        if "screenshot" in d:
            try:
                png = make_screenshot_png(d["screenshot"])
                seeder.attach(key, f"error_{d['id']}.png", png)
            except ImportError:
                print("  WARNING: Pillow not installed, skipping screenshot "
                      "(pip install Pillow)")
        if "resolve_with" in d:
            seeder.resolve(key, d["resolve_with"])

    print(textwrap.dedent(f"""
        Done. Created {len(keys)} issues in project {args.project}.
        Duplicate pairs to verify triage against:
    """).rstrip())
    for dup, orig in DUPLICATE_PAIRS:
        print(f"  {keys[dup]}  should be flagged duplicate of  {keys[orig]}")
    print(f"\nNext: python -m jira_triage.main --once --dry-run")


if __name__ == "__main__":
    main()
