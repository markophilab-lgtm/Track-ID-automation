# Deploy Content v2 — Design Spec

**Date:** 2026-07-03
**Project:** DJ Tracklist Auto-Logger — Steps 3+4 (SoundCloud upload, YouTube publish, label outreach wired in)

## Goal

Extend the "deploy content" workflow so that one command after each stream:

1. Builds the timestamped tracklist (existing pipeline) — **Mixcloud posting dropped**
2. Uploads the set's **audio to SoundCloud** via the official API (scripted)
3. Publishes the **video on YouTube** via browser automation (no YouTube API)
4. Runs the **label-emailer agent** so labels are asked to allowlist the channel

The user is not a coder. Every stage shows a preview and reports plainly. One
broken stage never blocks the others.

## Decisions made during brainstorming (2026-07-03)

| Question | Decision |
|---|---|
| Mixcloud | **Dropped from the pipeline.** Code stays in repo; `/deploy-content` always passes `--skip-mixcloud`. |
| SoundCloud | **Official API, scripted.** Self-service app registration is open again (requires SoundCloud Artist Pro; user has a paid plan — verify tier at setup). OAuth 2.1 + PKCE. Upload via `POST https://api.soundcloud.com/tracks` (multipart, ≤4 GB, ≤24 h). |
| YouTube upload | **Browser automation only.** The Data API locks uploads from non-audited apps to private permanently (no appeal) — dealbreaker for promo content. Claude drives the user's logged-in Chrome instead. |
| YouTube live vs local | Varies per stream. The command asks: if the set was live-streamed, only the description needs pasting; if local-only, the `.mov` is uploaded through YouTube Studio. |
| Label emails | **Phase 1: Gmail drafts** (existing agent). **Phase 2: auto-send** behind a one-word mode switch, with an in-session confirmation of the recipient list before each batch. |
| Email ask wording | Sharpened from "please don't block" to **"please add channel `waterhousestudios` to your Content ID allowlist — promotional use only, not monetized"** (allowlisting is YouTube's own recommended mechanism and also protects live streams from interruption). |

## Architecture

```
post_tracklist.py                    ← MODIFIED: new --write-descriptions DIR flag
soundcloud_client.py                 ← NEW: OAuth 2.1 PKCE + upload (mirrors mixcloud_client.py style)
soundcloud_publish.py                ← NEW: CLI — ffmpeg audio extract + upload, --dry-run
send_label_email.py                  ← NEW: SMTP send via Gmail app password (used only in "send" mode)
.claude/agents/label-emailer.md      ← MODIFIED: fix project path bug, allowlist wording, mode support
~/.claude/commands/deploy-content.md ← REWRITTEN: 4-stage orchestration
tests/test_soundcloud_client.py      ← NEW
tests/test_soundcloud_publish.py     ← NEW
tests/test_send_label_email.py       ← NEW
~/.tracklist_secrets/soundcloud_app.json   ← client id/secret (600)
~/.tracklist_secrets/soundcloud.json       ← OAuth tokens (600)
~/.tracklist_secrets/label_email_ask.txt   ← user-approved ask text (600) — REQUIRED before stage 4
~/.tracklist_secrets/outreach_mode.txt     ← "draft" (default) or "send"
~/.tracklist_secrets/gmail_smtp.json       ← Gmail address + app password (600), only for "send" mode
~/Desktop/deploy_output/                   ← per-run description files (see Stage 1)
```

## Stage 1 — Tracklist build (existing pipeline, small change)

`python3 post_tracklist.py --skip-mixcloud --write-descriptions ~/Desktop/deploy_output`

New `--write-descriptions DIR` flag writes, after enrichment:

- `DIR/youtube_description.txt` — output of `format_youtube` (chapters + links + promo note)
- `DIR/soundcloud_description.txt` — same content; SoundCloud renders timestamps as seek links
- `DIR/run_meta.json` — `{"stream_start": ISO, "movie_path": str, "title": str, "chapter_count": int}`

Default title: `waterhousestudios live stream YYYY-MM-DD` (from stream_start date).
The clipboard copy stays as a fallback for manual pasting. Existing behavior
without the flag is unchanged (all current tests keep passing).

A "Promotional use only — not monetized." line is appended to both description
files by the formatter.

## Stage 2 — SoundCloud upload

### `soundcloud_client.py`

Mirrors `mixcloud_client.py` conventions (requests, localhost callback server,
secrets files mode 600, typed errors `SoundCloudAuthError` / `SoundCloudAPIError`).

- **First-run setup:** prompt the user to register an app at
  soundcloud.com/you/apps (requires Artist Pro), paste client ID + secret,
  then browser OAuth on `http://localhost:8766/callback` (port 8766 — Mixcloud
  already claims 8765). PKCE: `code_verifier` = 64 random url-safe chars,
  `code_challenge` = base64url(SHA-256(verifier)), method `S256`.
- **Tokens:** access + refresh saved to `soundcloud.json`; auto-refresh on 401
  once, then raise `SoundCloudAuthError` telling the user to re-run setup.
- **`upload_track(token, audio_path, title, description, tags) -> track_url`:**
  `POST /tracks` multipart: `track[title]`, `track[description]`,
  `track[sharing]=public`, `track[tag_list]`, `track[asset_data]`=file stream.
  Returns the new track's permalink URL. 4 GB / 24 h limits checked client-side
  before upload with a clear message.

### `soundcloud_publish.py` (CLI)

```
python3 soundcloud_publish.py \
    --movie <path.mov> --title "<title>" \
    --description-file ~/Desktop/deploy_output/soundcloud_description.txt \
    [--dry-run] [--keep-audio]

python3 soundcloud_publish.py --setup   # first-run only: app creds prompt + browser OAuth
```

1. Verify `ffmpeg` is on PATH; if missing, exit with the exact install command
   (`brew install ffmpeg`).
2. Extract audio: `ffmpeg -i movie.mov -vn -codec:a libmp3lame -b:a 320k out.mp3`
   into a temp dir (deleted after upload unless `--keep-audio`).
3. `--dry-run`: print title, description, audio duration and estimated file
   size; upload nothing; extract audio only to probe duration (`ffprobe`).
4. Real run: `ensure_token()` → `upload_track()` → print the track URL →
   macOS notification via existing `clipboard_and_notify.notify`.

Exit codes: 0 ok, 2 input problems (no movie/description), 3 ffmpeg missing or
failed, 4 auth failure, 5 API/upload failure.

## Stage 3 — YouTube publish (browser automation)

Written as instructions in `deploy-content.md`; Claude uses Claude-in-Chrome
tools in the user's logged-in Chrome. No code module.

1. Ask the user: **"Did you stream this set live to YouTube?"**
2. **If yes (video already on channel):** open `studio.youtube.com` → Content →
   newest video → Details → set description from
   `deploy_output/youtube_description.txt` → Save. Verify the save toast/state
   before reporting success.
3. **If no (local recording only):** open YouTube Studio → Create → Upload
   videos → file-upload the `.mov` from `run_meta.json`'s `movie_path` → set
   title + description → visibility Public (ask the user first if they want
   Public or Unlisted) → wait for upload+processing to reach a publishable
   state. Chrome must stay open for the duration; tell the user this before
   starting.
4. Any browser failure: report the exact step that failed, remind the user the
   description is also on the clipboard, and continue to Stage 4.

## Stage 4 — Label outreach

### Fixes to the existing agent (`.claude/agents/label-emailer.md`)

- **Path bug:** all references to `~/Desktop/Track-ID-automation-main/` become
  `~/Desktop/TRACK ID PROJECT/` (quoted — the path contains spaces).
- **Wording:** guidance to the drafting step now emphasises the allowlist ask;
  subject stays `DJ set including {label} releases — quick request re: YouTube
  Content ID`.

### The ask text (setup step, user-owned)

Claude drafts `label_email_ask.txt` content covering: allowlist request for
channel `waterhousestudios`, promotional-use-only, not monetized, offer to
remove any track on request. The **user approves the wording** before it is
saved. Stage 4 refuses to run without this file (existing agent behavior).

### Draft vs send modes

`~/.tracklist_secrets/outreach_mode.txt` contains one word: `draft` (default)
or `send`.

- **draft:** exactly the current agent behavior — Gmail drafts, user sends
  manually.
- **send:** the agent composes identically, then, instead of `create_draft`,
  the main session (not the subagent) shows the user a table of
  `label → email → tracks` and asks one go/no-go question. On "go", it runs
  `send_label_email.py` once per label. The confirmation lives in the main
  session so a runaway subagent can never mass-send.
- Switching modes = the user tells Claude "switch label emails to auto-send";
  Claude edits the mode file. First switch also triggers the SMTP setup below.

### `send_label_email.py`

- Reads `gmail_smtp.json` (`{"address": ..., "app_password": ...}`); if absent,
  prints plain-language one-time setup: Google Account → Security → 2-Step
  Verification → App passwords → create one for "Mail", paste it when prompted.
- Sends via `smtplib` SSL to `smtp.gmail.com:465`, plain-text body, `From` =
  the user's address. One recipient per invocation. Exit 0 / non-zero with a
  clear message; the orchestrator marks per-label success/failure.
- Cache semantics unchanged: a label enters `contacted_labels.json` on
  successful draft creation (draft mode) or successful send (send mode).

## `/deploy-content` command flow (rewritten)

1. Preflight: secrets present? (`soundcloud.json`; ffmpeg on PATH). If SoundCloud
   setup is missing, walk the user through first-run setup (they run
   `! python3 soundcloud_publish.py --setup` style flow in-terminal).
2. Stage 1 dry-run preview (as today: chapters, filtered count, stream start;
   flag anomalies). **Go/no-go question.**
3. Stage 1 real run (with `--write-descriptions`).
4. Stage 2: `soundcloud_publish.py --dry-run` preview → confirm → real upload
   (Bash timeout 600 000 ms; a 2 h set at 320 kbps ≈ 290 MB).
5. Stage 3: the live-vs-local question, then the browser steps.
6. Stage 4: read `outreach_mode.txt`, dispatch label-emailer; in send mode,
   the confirmation table + `send_label_email.py` loop.
7. Final summary: one line per stage — done / skipped / failed(reason).

Per-stage skip flags honored if the user asks: "skip soundcloud",
"skip youtube", "skip emails".

## Error handling

| Failure | Behavior |
|---|---|
| ffmpeg missing | Stage 2 aborts with install command; stages 3–4 continue |
| SoundCloud token expired, refresh fails | Stage 2 aborts with "re-run setup" message; continue |
| Upload > 4 GB or > 24 h | Client-side check aborts before upload with clear message |
| SoundCloud API non-2xx | Retry once after 5 s; then fail stage with response body summary |
| Browser step fails / Chrome closed | Report failed step; description remains on clipboard; continue |
| `label_email_ask.txt` missing | Stage 4 refuses (existing behavior), tells user to author it |
| `outreach_mode.txt` missing | Treated as `draft` |
| SMTP auth fails in send mode | Stage 4 falls back to draft mode for this run and says so |
| Any stage failure | Never blocks later stages; reflected in final summary |

## Testing

Unit tests follow the existing stub-based style (`unittest.mock`, no network):

- `test_soundcloud_client.py`: PKCE challenge derivation (known vector),
  token save/load modes (700/600), refresh-on-401-then-retry, upload multipart
  field construction, size-limit rejection, error mapping.
- `test_soundcloud_publish.py`: ffmpeg-missing path, ffmpeg command
  construction, dry-run makes no upload call, exit codes.
- `test_send_label_email.py`: missing-config path, SMTP call construction
  (mocked `smtplib`), one-recipient enforcement.
- `post_tracklist` tests extended for `--write-descriptions` (files written,
  meta JSON correct, absent flag = no files).
- All existing tests keep passing (`python3 tests/run_all.py`).

Manual first-run protocol: one short test recording (2–3 tracks) through all
four stages, SoundCloud upload verified playable, YouTube description verified
saved, one label draft inspected in Gmail before any real run.

## Security & privacy

- All new secret files in `~/.tracklist_secrets/` (dir 700, files 600),
  already gitignored — verify before commit.
- Gmail app password grants full mail access: stored 600, never echoed, never
  committed, and the user is told they can revoke it any time in their Google
  Account.
- In send mode, the batch never sends without an explicit in-session
  confirmation of the full recipient list.
- The channel is protected from YouTube copyright trouble primarily by the
  allowlist asks; the command never disputes Content ID claims and never
  monetizes.

## Out of scope

- Removing Mixcloud code from the repo (kept dormant).
- YouTube Data API integration (blocked by the private-lock audit policy).
- Follow-up / re-contact emails to labels.
- Uploading to any additional platform.
- Automatic retraction handling if a copyright strike occurs (manual, with
  Claude's help, using the contacted-labels list).
