# Azure DevOps → Jira Pull Request Updater

A small webhook bridge that receives Azure DevOps pull request events and
appends concise, human-readable event entries into a single comment on the
corresponding Jira issue.

Highlights

- Detects Jira issue key from PR title using the pattern `[J:<ISSUE_KEY>]`.
- Appends each event to the end of an existing Jira comment (or creates one
  if missing), separated by a visible delimiter: `----------------------------------`.
- On PR creation the service creates the initial comment; the compact
  reviewers summary is omitted for the creation event.
- On updates, an "PR updated" block is appended only when the source commit
  hash changed. Reviewer actions (approve/reject/waiting-author) include the
  commit hash they occurred on.
- For PR comment events the service includes the comment author, content and
  a direct link to the discussion; it does not append the reviewers-update
  block for these events.

Requirements

- Python 3.10+
- See `requirements.txt` for runtime dependencies (`Flask`, `requests`, `python-dotenv`).

Install

```bash
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

Configuration
Set environment variables in a `.env` file or in your shell:

- `JIRA_URL` — base URL of your Jira instance (for example, `https://jira.example.com`).
- `JIRA_API_KEY` — Jira API key (the app uses `Authorization: Bearer <API_KEY>`).
- `JIRA_TIMEOUT` — optional HTTP timeout in seconds (default: `10`).
- `USER_AGENT` — optional User-Agent string to send with requests.

Run locally

```bash
python app.py
```

VS Code debugging

- A `.vscode/launch.json` configuration is included. Configure environment
  variables there or rely on a local `.env` file.

Example payloads (local testing)

- PR created (creates a comment; reviewers summary omitted):

```bash
curl -X POST http://localhost:8023/webhook \
  -H "Content-Type: application/json" \
  -d '{"eventType":"git.pullrequest.created","resource":{"title":"[J:PROJ-123] Add feature","_links":{"web":{"href":"https://dev.azure/.../pullrequest/1"}},"lastMergeSourceCommit":{"commitId":"abc123"},"creationDate":"2026-01-27T21:24:42Z"}}'
```

- PR comment event (appends the author, content and a link; no reviewers block):

```bash
curl -X POST http://localhost:8023/webhook \
  -H "Content-Type: application/json" \
  -d '{"eventType":"ms.vss-code.git-pullrequest-comment-event","resource":{"pullRequest":{"title":"[J:PROJ-123] Add feature","_links":{"web":{"href":"https://dev.azure/.../pullrequest/1"}},"lastMergeSourceCommit":{"commitId":"abc123"}},"comment":{"content":"Looks good","publishedDate":"2026-01-28T00:24:40Z","author":{"displayName":"Alice"}}},"message":{"markdown":"Alice has [commented](https://dev.azure/.../pullrequest/1?_a=files&discussionId=10)"}}'
```

Notes about Jira XSRF and cookies

- Some Jira installations require an XSRF token for mutating requests. The
  service performs an initial `GET` to the Jira comments endpoint to capture
  cookies like `JSESSIONID` and `atlassian.xsrf.token` and then sets
  `X-Atlassian-Token`, `Referer` and `Origin` headers for subsequent POST/PUT
  requests when necessary.

Logging and security

- Default logging level is `INFO` to avoid leaking sensitive values.
- Errors include a stack trace via `logger.exception`, but the code avoids
  logging request bodies, headers, cookies, or API keys.

Code overview

- `app.py` — main webhook server and core logic. Key functions:
  - `get_jira_headers()` — builds the headers used for Jira API calls.
  - `process_jira_comment()` — creates or appends event entries to a Jira comment.
  - `vote_to_status()` — maps numeric reviewer votes to readable status strings.

Contributing

- Add unit tests under `tests/` for behavior changes.
- Keep normal logs at `INFO` and use `logger.exception` for exceptions.

If you'd like, I can run a local POST simulation and show the exact Jira
comment text that would be created or appended.
