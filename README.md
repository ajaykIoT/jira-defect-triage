# jira-triage

Auto-triages Jira defects. For every new or updated defect it:

1. Reads the defect details, comments, and **image attachments** (screenshots analyzed with GPT-4o vision).
2. Compares it against all existing defects and detects **duplicates** (fast fuzzy retrieval + LLM confirmation).
3. If a duplicate was already resolved, surfaces the **past resolution**.
4. Determines the likely **root cause** and a **suggested resolution**.
5. **Logs everything back into Jira**: triage comment, labels (`auto-triaged`, `auto-dup`), and a "Duplicate" issue link to the original.

## Setup

```bash
pip install -r requirements.txt
cp .env.example .env        # fill in Jira + OpenAI credentials
```

Edit `config.yaml`:
- Replace `PROJ` in `triage_jql` / `corpus_jql` with your project key.
- Adjust thresholds and labels if desired.

Jira API token: https://id.atlassian.com/manage-profile/security/api-tokens

## Run

```bash
# Safe first run — analyzes but writes nothing to Jira
python -m jira_triage.main --once --dry-run

# Single triage cycle
python -m jira_triage.main --once

# Continuous polling (default, every poll.interval_seconds)
python -m jira_triage.main

# Triage specific issues
python -m jira_triage.main --issues PROJ-123 PROJ-456
```

## How it works

```
Jira (JQL poll) ──> new/updated defects
                      │
                      ├── image attachments ──> GPT-4o vision ──> extracted evidence
                      │
corpus (all defects) ─┴─> fuzzy ranking (rapidfuzz) ──> top-K candidates
                                                          │
                                     GPT-4o ──> duplicate? past resolution?
                                                root cause, suggested fix
                                                          │
Jira <── comment + labels + duplicate link <──────────────┘
```

State is kept in `.triage_state.json` (issue key → last-seen `updated` timestamp), so an issue is re-triaged only when it changes. The `auto-triaged` label in `triage_jql` also keeps already-processed issues out of the queue.

## Testing end-to-end with a free Jira Cloud site

**1. Create a test Jira site** (free, up to 10 users, no credit card):
https://www.atlassian.com/try/cloud/signup — pick Jira, choose a site name (e.g. `mytest.atlassian.net`).

**2. Create a project**: Projects → Create project → Bug tracking / Kanban / Scrum template. Note the **project key** Jira assigns (e.g. `SCRUM`).

**3. Create an API token**: https://id.atlassian.com/manage-profile/security/api-tokens (must be the same Atlassian account that owns the site).

**4. Fill `.env`** (copy from `.env.example`):

```
JIRA_BASE_URL=https://mytest.atlassian.net
JIRA_EMAIL=you@example.com
JIRA_API_TOKEN=<token from step 3>
OPENAI_API_KEY=sk-...
```

**5. Verify credentials and find your project key** (if unsure):

```bash
python -c "import os,requests; from dotenv import load_dotenv; load_dotenv(); a=(os.environ['JIRA_EMAIL'],os.environ['JIRA_API_TOKEN']); b=os.environ['JIRA_BASE_URL']; print(requests.get(b+'/rest/api/3/myself',auth=a).status_code); print([(p['key'],p['name']) for p in requests.get(b+'/rest/api/3/project/search',auth=a).json().get('values',[])])"
```

Expect `200` and your project list, e.g. `[('SCRUM', 'BugTracking')]`. Use that exact key below.

**6. Update `config.yaml`**: replace `PROJ` with your project key in `triage_jql` and `corpus_jql`. If your project has no "Bug" issue type (some templates only have Task), change `issuetype = Bug` to `issuetype = Task` in both.

**7. Seed test defects** (3 duplicate pairs, 2 with screenshot attachments, 2 resolved originals with fix comments):

```bash
pip install Pillow                                    # only needed for seeding
python scripts/seed_test_data.py --project SCRUM --dry-run   # preview
python scripts/seed_test_data.py --project SCRUM             # create issues
```

The script prints which issue keys should be flagged as duplicates of which.

**8. Dry run the triage** (analyzes, prints reports, writes nothing to Jira):

```bash
python -m jira_triage.main --once --dry-run
```

Check that: the duplicate pairs are detected with the past resolution surfaced, the screenshot issues include image findings, and unique bugs get root cause + suggested resolution.

**9. Real run** (posts comments, labels, duplicate links back to Jira):

```bash
python -m jira_triage.main --once
```

Open the issues in Jira and verify the triage comment, `auto-triaged` / `auto-dup` labels, and "Duplicate" links. Re-running skips already-triaged issues (state in `.triage_state.json` + label filter in JQL).

## Unit tests

No network or credentials needed (Jira and OpenAI are mocked):

```bash
python -m unittest discover tests -v
```

## Files

| File | Purpose |
|---|---|
| `jira_triage/jira_client.py` | Jira Cloud REST v3: search, attachments, comments, labels, links |
| `jira_triage/similarity.py` | Fast duplicate-candidate retrieval (rapidfuzz) |
| `jira_triage/analyzer.py` | OpenAI: image analysis, duplicate confirmation, root cause, resolution |
| `jira_triage/reporter.py` | Formats the triage comment posted to Jira |
| `jira_triage/engine.py` | Orchestration + write-back |
| `jira_triage/state.py` | Processed-issue tracking |
| `jira_triage/main.py` | CLI (`--once`, `--poll`, `--issues`, `--dry-run`) |
