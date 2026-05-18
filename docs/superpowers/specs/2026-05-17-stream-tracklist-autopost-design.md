# Stream Tracklist Auto-Post — Design Spec
**Date:** 2026-05-17
**Project:** DJ Tracklist Auto-Logger — Step 2

## Goal

After each livestream ends, run **one Terminal command** that:

1. Posts a timestamped tracklist (chapter markers per song) to the matching Mixcloud cloudcast.
2. Builds the same timestamped tracklist in YouTube's chapter format and copies it to the macOS clipboard, ready to paste into the YouTube video description.

Each track in the output includes a Discogs link and a Songlink universal listen-here URL.

## Setup This Builds On

Step 1 (already complete) gives us:

- Beat Link Trigger writing every played track to `~/Desktop/tracklist_live.txt` in real time, including a session header and per-track lines (`HH:MM:SS  [Player N]  Artist — Title`).
- `tracklist_parser.py` — parses that log into `Session` and `Track` dataclasses.
- `tracklist_lookup.py` — currently does Discogs lookups (kept) and Bandcamp scraping (kept as-is for Step 1 compatibility, but unused by this new code path).
- `tracklist_format.py` — current post-set formatter (kept as-is; this design adds a *new* entrypoint, not a rewrite). It continues to import `bandcamp_lookup` so we will NOT delete that function.

**Prerequisite for Mixcloud auto-post:** the user has confirmed they have a **Mixcloud Pro** subscription, which is required for the Mixcloud API to edit existing cloudcasts. Without Pro, the Mixcloud edit endpoint returns 403 and the script falls back to clipboard-paste (see Error Handling).

## User Workflow

After a stream ends:

1. Stop streaming and stop OBS recording. OBS has saved a file like `~/Movies/2026-05-17 21-30-00.mov` whose filename encodes the moment recording started.
2. Open Terminal and run:
   ```
   python3 "$HOME/Desktop/TRACK ID PROJECT/post_tracklist.py"
   ```
3. The script processes the set (~1–3 minutes depending on track count due to Songlink rate limits).
4. macOS notification appears: `✅ Posted to Mixcloud. YouTube text copied to clipboard.`
5. Open YouTube Studio, edit the just-archived stream's description, paste, save.

The very first run additionally walks the user through a 30-second Mixcloud OAuth flow and (optional) Discogs token paste. Subsequent runs use saved credentials and skip setup.

## Stream Start Anchor

OBS recordings in `~/Movies/` are named `YYYY-MM-DD HH-MM-SS.mov`. The script:

- Lists all `*.mov` files in `~/Movies/` whose name matches that pattern.
- Picks the newest one (by parsed datetime in the filename, not by mtime — more reliable).
- Parses the filename into a `datetime` representing **t=0 of the published stream**.
- All per-track timestamps are computed as `track.wall_time - stream_start`, formatted as `H:MM:SS` (or `M:SS` for sets under an hour).

The user can override with `--movie /path/to/file.mov` if the auto-pick is wrong.

**Confirmed assumption (user workflow 2026-05-17):** OBS recording starts at the same moment the live stream goes out. The `.mov` filename therefore equals stream-start time directly, with no offset required.

**Tracks before stream start:** If any tracks in the log were played before the OBS recording began (e.g., DJ was warming up), the script skips them and prints `Skipped N pre-stream tracks` so the user knows. They are not posted to either platform.

## Short-Track Filter

BLT logs every change of master player, including very short master-bursts during cueing/mixing. To keep the public tracklist clean, the script applies a **30-second filter**: any track whose duration as master is less than 30 seconds is dropped from the tracklist before posting.

- Duration as master = time between this track's log line and the next track's log line (or the end of the log for the last track).
- Dropped tracks are counted and reported: `Filtered N short tracks (< 30s).`
- The 30-second threshold is set as a constant `MIN_TRACK_SECONDS = 30` in `timestamp_builder.py` so it can be tuned without code changes elsewhere.

## Output Format

### YouTube description (copied to clipboard)

```
Tracklist:

0:00 Intro
05:23 Anthony Naples — Crystals | https://discogs.com/release/12345678 | https://song.link/i/AbCdEf12
12:47 Joy Orbison — Hyph Mngo | https://discogs.com/release/87654321 | https://song.link/i/GhIjKl34
19:12 Pearson Sound — Blanked | https://discogs.com/release/55554444 | https://song.link/i/MnOpQr56

Recorded live 2026-05-17.
```

Format requirements:

- **All URLs are prefixed with `https://`** — YouTube only auto-linkifies clickable URLs that include the scheme. Step 1's `tracklist_lookup.discogs_lookup` returns a scheme-less URL (`discogs.com/release/...`); the new `youtube_formatter.py` must prepend `https://` before output. Same for Songlink URLs.
- **First chapter MUST be `0:00 Intro`** — YouTube refuses to render chapters otherwise.
- **First real track must begin at ≥ `0:10`.** YouTube's chapter rule requires ≥10s between adjacent chapters. If the first track in the log starts within 10s of stream-start, the script *replaces* the `0:00 Intro` line with the first track's name at `0:00` (no separate intro chapter). Otherwise the `0:00 Intro` line is added.
- At least three lines with timestamps required for YouTube to enable chapter mode. If after filtering (see Short-Track Filter) there are fewer than 3 tracks, YouTube won't render chapters — the description still posts but as plain text.
- Each chapter must be ≥10 seconds long; the 30-second filter ensures this.
- Timestamps formatted without leading zero on hour (`0:00`, `1:23:45`), with leading zeros on minutes and seconds (`05:23`).
- Missing Discogs or Songlink for a given track → that field is replaced with `(no link)`. The chapter line still works.
- Tracks logged as `Unknown Artist` / `Unknown Title` → line becomes `05:23 [unidentified]` (safety net only — does not happen in this user's rekordbox-analyzed workflow).

### Mixcloud (via Mixcloud API)

**Endpoint:** `POST https://api.mixcloud.com/upload/{username}/{slug}/edit/?access_token={token}`

**Encoding:** `multipart/form-data` (NOT JSON). Mixcloud's edit endpoint expects form fields, with sections expressed as an indexed array of form keys.

Fields sent:

1. **`description`** — plaintext block (same content as the YouTube description, including the timestamped chapter lines and the Discogs / Songlink URLs with `https://` prefix).
2. **`sections-N-start_time`** / **`sections-N-artist_name`** / **`sections-N-song_name`** — one set of three form fields per track, indexed from `N=0`. `start_time` is integer seconds from cloudcast start.

Example fragment of the form body for the first three tracks:
```
sections-0-start_time=0
sections-0-artist_name=Intro
sections-0-song_name=Intro
sections-1-start_time=323
sections-1-artist_name=Anthony Naples
sections-1-song_name=Crystals
sections-2-start_time=767
sections-2-artist_name=Joy Orbison
sections-2-song_name=Hyph Mngo
```

This makes each track clickable in the Mixcloud player.

Mixcloud cloudcast identification: the script lists the authenticated user's cloudcasts via `GET https://api.mixcloud.com/{username}/cloudcasts/?limit=5&access_token={token}` and picks the one with the most recent `created_time`. Optional `--cloudcast <slug>` flag to override.

**Caveat on "most recent":** Mixcloud's `created_time` reflects upload time, not stream date. If the user uploads another cloudcast between the stream and running this script, the wrong one is targeted. Mitigation: the script prints `Targeting: <cloudcast title>` before posting; if the user runs with `--dry-run` they can sanity-check.

## Links Per Track

Discogs lookup is unchanged from Step 1 (`tracklist_lookup.discogs_lookup`). It returns a URL string *without* the `https://` scheme (e.g., `discogs.com/release/12345`). The new `youtube_formatter.py` and the Mixcloud description builder both prepend `https://` before emitting.

Bandcamp scraping is **left in place** in `tracklist_lookup.py` (so Step 1's `tracklist_format.py` keeps working) but is **not called** from this new code path. Universal links are sourced via a two-step lookup:

1. Query iTunes Search API (no auth required, public):
   `https://itunes.apple.com/search?term={artist}+{title}&entity=song&limit=1`
2. Take the `trackViewUrl` from the response (e.g., `https://music.apple.com/us/album/.../...?i=...`) and pass it to Songlink:
   `https://api.song.link/v1-alpha.1/links?url={trackViewUrl}`
3. Return the `pageUrl` from Songlink's response (full URL including scheme, e.g., `https://song.link/i/AbCdEf12`).

Any failure at any step → field is `(no link)` in the output line. The rest of the tracklist proceeds.

**Per-track API pacing (per track, sequential):**

| API | Sleep before call | Reason |
|-----|-------------------|--------|
| Discogs | 1.0s | Matches Step 1's pacing (`tracklist_format.py` already does this). Untoken'd is 25 RPM, tokened is 60 RPM. 1s sleep stays under both. |
| iTunes Search | 0.5s | Public limit is ~20 RPM per IP; 0.5s sleep keeps below the cap. |
| Songlink | 6.0s | Public limit ~10 RPM (documented). 6s sleep is the documented safe spacing. |

Total per track: ~7.5s. A 25-track set (after filtering) → ~3 minutes total runtime. Acceptable for a post-stream batch.

On HTTP 429 from any API, sleep 30s and retry once. Second 429 → give up that field for that track, continue.

## Code Structure

A new entrypoint `post_tracklist.py` orchestrates the work. From the user's perspective it is one command. Internally it is split into focused modules for maintainability:

| File | Responsibility | Status |
|------|----------------|--------|
| `post_tracklist.py` | Entry point. Argparse, orchestration, error reporting. | **New** |
| `tracklist_parser.py` | Read `tracklist_live.txt` → `[Session]`. | Reuse (untouched) |
| `tracklist_lookup.py` | `discogs_lookup` and `bandcamp_lookup` (both left in place; Step 1 still imports them). | Reuse (untouched) |
| `tracklist_format.py` | Existing post-set formatter. | Reuse (untouched) |
| `stream_anchor.py` | `find_latest_movie(dir) → (path, datetime)`. Filename-based, with `--movie` override. | **New** |
| `songlink_lookup.py` | `songlink_url(artist, title) → url` — iTunes search + Songlink. Internal rate limiting. | **New** |
| `track_filter.py` | `filter_short_tracks(tracks, min_seconds=30) → tracks` — drops tracks where master duration < threshold. | **New** |
| `timestamp_builder.py` | `build_chapters(tracks, stream_start) → [Chapter]` where `Chapter` is a dataclass with `time_seconds: int`, `time_str: str`, `artist: str`, `title: str`, `discogs_url: str`, `songlink_url: str`. Skips pre-stream tracks. Inserts or replaces `0:00 Intro` per the rules in Output Format. | **New** |
| `youtube_formatter.py` | `format_youtube(chapters, stream_date) → str` — plaintext description with `https://` prefixed on URLs. | **New** |
| `mixcloud_client.py` | OAuth flow, `latest_cloudcast()`, `update_cloudcast(slug, description, chapters)` — encodes form fields as documented in the Mixcloud section. | **New** |
| `clipboard_and_notify.py` | `copy_to_clipboard(text)` via `pbcopy`; `notify(title, body)` via `osascript`. | **New** |

Step 1 files are untouched: `tracklist_parser.py`, `tracklist_lookup.py`, and `tracklist_format.py` all keep working. The new pipeline imports `parse_log` and `discogs_lookup` but adds nothing to them.

The shared `Chapter` dataclass lives in `timestamp_builder.py` and is the unit passed between modules — keeping the `Track` dataclass from `tracklist_parser.py` unmodified.

## First-Run Setup (Inside `post_tracklist.py`)

Before posting, the script checks for required credentials:

1. **Mixcloud app registration** (one-time, manual, before anything else works):
   - The user visits `https://www.mixcloud.com/developers/create/` and creates an app with:
     - Name: "Tracklist Auto-Post" (or anything)
     - Redirect URI: `http://localhost:8765/callback` (must match exactly what the script uses)
   - Mixcloud shows a **Client ID** and **Client Secret**.
   - The script's first run prompts the user to paste both. They are saved to `~/.tracklist_secrets/mixcloud_app.json`.
   - This step is unavoidable — Mixcloud's API requires per-app credentials. The script explains why in plain language during first run.
2. **Mixcloud access token** at `~/.tracklist_secrets/mixcloud.json`:
   - If missing, print explanation, open browser to Mixcloud's OAuth authorize URL (using the saved Client ID), run a tiny local HTTP listener on `localhost:8765/callback` to catch the redirect, exchange the code for an access token, save to file (mode `600`), continue.
   - Mixcloud access tokens **do not expire** under current API behavior, so this is genuinely a one-time step.
3. **Discogs token** at `~/.tracklist_secrets/discogs.json`:
   - If missing AND env `DISCOGS_TOKEN` not set, prompt user to paste a token (or press Enter to skip). Lookups still work without one, just slower (untoken'd Discogs is 25 req/min vs. 60 req/min).

The `~/.tracklist_secrets/` directory is created with mode `700`. Files are mode `600`. The directory is outside the project tree so it cannot accidentally be committed to git.

## Error Handling

| Failure | Behavior | Exit code |
|---------|----------|-----------|
| No `.mov` matching `YYYY-MM-DD HH-MM-SS.mov` in `~/Movies/` | Print: "No recording found in ~/Movies. Pass `--movie /path/to/file.mov` to override." Stop. | 2 |
| `tracklist_live.txt` missing or no sessions parsed | Print: "No tracks found in tracklist_live.txt — was BLT open during the stream?" Stop. | 2 |
| After 30s-filter and pre-stream skip, fewer than 1 track remains | Print: "No tracks survived filtering — nothing to post." Stop. | 2 |
| Discogs / iTunes / Songlink failure for a single track | Field becomes `(no link)`. Continue. | — |
| Mixcloud returns **401 Unauthorized** (token revoked/invalid) | Delete the cached token at `~/.tracklist_secrets/mixcloud.json`, re-run the OAuth flow inline, retry the post once. If OAuth also fails, fall through to the "Mixcloud auth refused" row. | 0 |
| Mixcloud returns **403 Forbidden** (typically: account is not Pro) | Print: "Mixcloud rejected the edit (403). Make sure your Mixcloud account is Pro." Skip Mixcloud, complete YouTube clipboard step. | 0 (partial) |
| Mixcloud: cannot find user's latest cloudcast | Warn, skip Mixcloud, complete YouTube clipboard. | 0 (partial) |
| Mixcloud other API failure (500, network) | Same as above: warn with reason, skip Mixcloud, complete YouTube clipboard. | 0 (partial) |
| `pbcopy` / `osascript` fails (unlikely on macOS) | Fall back to printing the formatted YouTube text to stdout. | 0 |

The YouTube clipboard step is intentionally last, so the clipboard never contains a partially-built tracklist after an early failure.

Re-running the command is idempotent for Mixcloud — `update_cloudcast` overwrites the description and sections each time; it does not append.

## CLI Flags

| Flag | Purpose |
|------|---------|
| (none) | Default flow: latest movie in `~/Movies`, latest Mixcloud cloudcast |
| `--movie PATH` | Override stream-start anchor |
| `--cloudcast SLUG` | Override Mixcloud cloudcast target |
| `--log PATH` | Override `~/Desktop/tracklist_live.txt` |
| `--session N` | Pick a specific session from the log file (default: latest) |
| `--dry-run` | Print what *would* be posted; touch nothing on Mixcloud, copy nothing to clipboard |
| `--skip-mixcloud` | Build YouTube clipboard only |
| `--skip-youtube` | Update Mixcloud only |

## Out of Scope (Deliberately)

- Bandcamp-direct links (replaced by Songlink, which links to Bandcamp among others).
- Manual fix-up UI for `[unidentified]` tracks — user's rekordbox library means this case effectively never fires.
- YouTube auto-post — explicitly deferred; clipboard paste is the chosen workflow.
- Background monitoring or auto-trigger on stream-end — explicitly chosen "I run one command" workflow.
- Set statistics, history, archive features — separate future scope.

## Security

- Credentials live in `~/.tracklist_secrets/`, mode `700`. Token files mode `600`.
- No credential is ever printed to terminal or logged to disk outside that folder.
- All HTTP calls use HTTPS. Timeouts set to 10s with one retry on `429`.

## Testing

Unit tests under `tests/`:

- `test_stream_anchor.py` — given a directory listing fixture, picks the right file; handles missing dir, no matches, malformed names, and OBS resume-recording filenames like `2026-05-17 21-30-00 (1).mov`.
- `test_track_filter.py` — given a list of tracks, verifies tracks with master-duration `<30s` are dropped and the rest pass through unchanged; verifies the last-track duration calculation (uses end-of-log or now).
- `test_timestamp_builder.py` — given tracks + stream start, produces expected `time_seconds` and `time_str` for each chapter; correctly skips tracks logged before stream start; correctly inserts a `0:00 Intro` chapter when first real track is ≥10s out; correctly *replaces* the intro with the first track when it starts <10s out.
- `test_youtube_formatter.py` — golden-file test: given fixture chapters, produces exact expected description string; verifies all URLs are emitted with `https://` prefix.
- `test_songlink_lookup.py` — mocks iTunes + Songlink HTTP calls; verifies graceful empty-string return on each failure mode (timeout, 404, malformed JSON, no iTunes match); verifies one-retry behavior on 429.
- `test_mixcloud_client.py` — mocks Mixcloud API; verifies the multipart/form-data body contains exactly the expected `description` + `sections-N-*` fields; verifies 401 triggers re-auth path; verifies 403 surfaces as a "not Pro" message.
- `test_post_tracklist_integration.py` — end-to-end with all HTTP mocked; verifies `--dry-run` does no network writes and no clipboard copy.

Existing `tests/test_log_format.py` continues to pass untouched.

## Open Questions (none — all resolved during brainstorming)

All design decisions made during the 2026-05-17 brainstorm. If new ones surface during implementation, log them in the plan doc (`docs/superpowers/plans/2026-05-17-stream-tracklist-autopost.md`).
