# Continue Implementation of Stream Tracklist Auto-Post

## Context

We are mid-execution of a previously-approved implementation plan. The user already:
1. Brainstormed Step 2 of their DJ tracklist auto-poster project
2. Approved the design spec at `/Users/waterhousestudios/Desktop/TRACK ID PROJECT/docs/superpowers/specs/2026-05-17-stream-tracklist-autopost-design.md`
3. Approved the implementation plan at `/Users/waterhousestudios/Desktop/TRACK ID PROJECT/docs/superpowers/plans/2026-05-17-stream-tracklist-autopost.md`
4. Chose subagent-driven execution

**Tasks 1-7 are already complete** — implemented, tested, spec-reviewed, code-reviewed, committed:

```
8415799 feat: clipboard_and_notify wraps pbcopy + osascript notifications
9a51098 feat: youtube_formatter produces description with https-prefixed URLs
117ab45 feat: songlink_lookup wraps iTunes Search + Songlink
ea9e69e feat: timestamp_builder produces Chapter list with Intro / first-track rules
74c22c6 feat: track_filter drops sub-30s master bursts
08867ad feat: stream_anchor finds latest OBS recording and parses its timestamp
736401c chore: add gitignore and test runner for Step 2
```

Current state: 41/41 tests pass.

Plan mode was triggered while dispatching Task 8 (Mixcloud OAuth client). The implementer correctly halted and asked for clarification.

## Remaining Work

Four tasks remain. Each follows the same workflow (implementer → spec reviewer → code-quality reviewer → mark complete), per the approved subagent-driven-development skill.

### Task 8 — `mixcloud_client.py` (OAuth + credential storage)
- **Files:** `mixcloud_client.py`, `tests/test_mixcloud_client.py`
- **Purpose:** Store Mixcloud app credentials, run OAuth flow with localhost callback, exchange code for token.
- **Tests:** 8 unit tests (credential I/O, mode-600 enforcement, OAuth URL building, token exchange success/failure).
- **Source code:** Fully specified in the approved plan (Task 8, Step 3).

### Task 9 — `mixcloud_client.py` additions (list cloudcasts + update)
- **Files:** Append to `mixcloud_client.py` and `tests/test_mixcloud_client.py`.
- **Purpose:** `get_me`, `latest_cloudcast`, `update_cloudcast` — uses form-encoded `sections-N-*` fields per Mixcloud's API.
- **Tests:** 6 more unit tests covering form-data shape, 401 → auth error, 403 → API error (not Pro message).
- **Source code:** Fully specified in the approved plan (Task 9, Step 3).

### Task 10 — `post_tracklist.py` orchestrator
- **Files:** `post_tracklist.py`, `tests/test_post_tracklist_integration.py`
- **Purpose:** CLI entry point that wires every module together.
- **Tests:** 6 integration tests (dry-run, normal run, --skip-mixcloud, 403 fallback, missing movie, empty log).
- **Source code:** Fully specified in the approved plan (Task 10, Step 3).

### Task 11 — Manual smoke test + README update
- **Files:** Modify `README.md`.
- **Purpose:** Document Step 2 for the user (non-coder). Manual verification steps for the OAuth round-trip.
- **Source code:** Fully specified in the approved plan (Task 11).

## Approach (Unchanged from Already-Approved Plan)

For each remaining task:
1. Dispatch general-purpose subagent (sonnet for Tasks 8-10, haiku for Task 11) with full task text.
2. Implementer writes failing tests, runs them, writes code, runs tests, commits.
3. Dispatch spec-compliance reviewer — verify the implementation matches the plan.
4. Dispatch code-quality reviewer — verify quality, no bugs.
5. Mark task complete, move to next.

No deviations from the previously approved plan; this is straight execution.

## Critical Files

- Plan: `/Users/waterhousestudios/Desktop/TRACK ID PROJECT/docs/superpowers/plans/2026-05-17-stream-tracklist-autopost.md`
- Spec: `/Users/waterhousestudios/Desktop/TRACK ID PROJECT/docs/superpowers/specs/2026-05-17-stream-tracklist-autopost-design.md`
- All implementation lives at `/Users/waterhousestudios/Desktop/TRACK ID PROJECT/`

## Verification

After all tasks: run `python3 tests/run_all.py` from the project root — expect roughly 60/60 tests passing. Final commit (Task 11) updates README to document Step 2 for the user.

The manual end-to-end test (Task 11) requires the user to: (a) create a Mixcloud developer app, (b) run `post_tracklist.py`, (c) authorize in browser, (d) verify Mixcloud cloudcast description updates and YouTube clipboard receives correctly-formatted text.

## Reason for Plan Mode Pause

Plan mode appears to have been toggled mid-execution. No design decisions remain unanswered — the plan is fully specified, fully approved, and partially implemented. Calling ExitPlanMode to resume the same execution flow that was in progress.
