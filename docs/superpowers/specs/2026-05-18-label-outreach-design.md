# Label Outreach Subagent — Design Spec
**Date:** 2026-05-18
**Project:** DJ Tracklist Auto-Logger — Step 3

## Goal

After a livestream is logged, dispatch a Claude Code **subagent** that:

1. Reads the latest session from `~/Desktop/tracklist_live.txt`.
2. Resolves each unique track to a record label via Discogs.
3. For every label not already contacted, finds a contact email (Discogs `contactinfo` first, then web search + page extraction).
4. Drafts a per-label email in Gmail (via Gmail MCP `create_draft`) that mentions the specific track(s) of theirs played and pastes the user's pre-authored ask text verbatim.
5. Returns a review table to the main Claude session.

The user opens Gmail → Drafts → reviews → sends manually. No email is ever sent automatically.

**The ask** in every email is a request that the label whitelist `waterhousestudios` from YouTube Content ID claims so DJ sets containing their tracks don't get muted, monetized away, or struck down. Exact wording is owned by the user (see "User-Owned Assets" below).

## Setup This Builds On

- Step 1: Beat Link Trigger writes tracks to `~/Desktop/tracklist_live.txt`.
- Step 2: `tracklist_parser.py` parses sessions; `tracklist_lookup.py:discogs_lookup` already calls Discogs's `/database/search` endpoint with token-based auth via `DISCOGS_TOKEN`; `~/.tracklist_secrets/` (mode 700) is the established secrets directory pattern.
- Gmail MCP server is connected to the user's Claude Code session and exposes `mcp__claude_ai_Gmail__create_draft` and `list_drafts`. **Note:** the Gmail MCP does NOT expose a "send" tool; this is intentional — drafts must be sent manually from Gmail.

## User Workflow

After Step 2's `post_tracklist.py` finishes, in the same Claude Code session:

1. User says: "run the label emailer" (or invokes a slash command — see "Out of Scope").
2. Main Claude dispatches: `Agent({subagent_type: "label-emailer", prompt: "Process the latest session in tracklist_live.txt"})`.
3. Subagent runs the pipeline (see Data Flow). Cold-start: re-derives all context from its system prompt + project files.
4. Subagent returns a markdown table. Example:

   | Label | Email | Status | Notes |
   |---|---|---|---|
   | Hessle Audio | info@hessleaudio.com | DRAFT_CREATED | 2 tracks |
   | Hyperdub | (none) | NO_EMAIL_FOUND | searched: hyperdub.net/contact returned 403 |
   | Whities | hello@whities.uk | DRAFT_CREATED | 1 track |
   | Black Acre | — | SKIPPED_ALREADY_CONTACTED | first contacted 2026-04-12 |

5. User opens Gmail → Drafts → reviews each draft → edits if desired → sends.
6. No further confirmation is needed back to Claude; the cache was updated when drafts were created (see Dedup Semantics).

## Architecture

A single subagent definition + a small deterministic Python helper + two on-disk state files.

```
.claude/agents/label-emailer.md                ← subagent definition + system prompt
label_outreach.py                              ← deterministic helpers (testable)
tests/test_label_outreach.py                   ← unit tests
~/.tracklist_secrets/contacted_labels.json     ← dedup cache (mode 600)
~/.tracklist_secrets/label_email_ask.txt       ← user's verbatim ask text (mode 600)
```

**Tool whitelist for the subagent:** `Bash`, `Read`, `Write`, `WebSearch`, `WebFetch`, `mcp__claude_ai_Gmail__create_draft`, `mcp__claude_ai_Gmail__list_drafts`. Excludes `Edit` (it doesn't modify project code) and `Agent` (no recursive dispatch).

**Why subagent + helper:** the deterministic parts (BLT log parsing, Discogs lookups, dedup cache I/O) must be reliable and free — they go in Python and have unit tests. The fuzzy parts (interpreting Google results, extracting an obfuscated email from arbitrary HTML, writing a warm-toned email) genuinely need an LLM — those live in the subagent's prompt. Subagent isolation keeps web-fetch noise out of the main session's context.

## Components

### `label_outreach.py`

Pure Python module, mirrors the style and testability of `mixcloud_client.py`. Four public functions plus a CLI entrypoint.

```python
def parse_latest_session(log_path: Path) -> list[Track]: ...
    # Reads the log, calls tracklist_parser.parse_log, returns the LAST session's
    # tracks after passing them through track_filter.filter_short_tracks(min_seconds=30).
    # (Track has no duration field; track_filter computes duration from consecutive
    # wall-times, with the last track's duration computed against datetime.now().)

def group_by_label(tracks: list[Track], discogs_token: str | None) -> dict[str, LabelInfo]: ...
    # For each unique (artist, title): hit Discogs /database/search for a release ID,
    # then /releases/{id} for labels[0].name and labels[0].id. From the label endpoint
    # extract contactinfo (free-text) and apply a permissive email regex.
    # Returns: {label_name: LabelInfo(tracks_played, discogs_label_url, discogs_email_or_none)}.
    # In-memory cache for the run avoids duplicate API calls for repeated artists.

def load_contacted(cache_path: Path) -> set[str]: ...
    # Returns lowercase-normalized label names from contacted_labels.json.
    # Empty set if file missing.

def save_contacted(cache_path: Path, new_entries: list[ContactedEntry]) -> None: ...
    # Appends entries to the JSON. Writes parent dir mode 700, file mode 600.
    # Atomic via tempfile + rename.
```

**CLI:**

- `python3 label_outreach.py --action enrich --log <log> --cache <cache>`
  - Parses latest session, drops already-contacted labels, prints JSON to stdout:
    ```json
    [{"label": "Hessle Audio",
      "tracks": [{"artist": "Pearson Sound", "title": "Blanked"}],
      "discogs_label_url": "https://www.discogs.com/label/12345",
      "discogs_contact_email": "info@hessleaudio.com"}]
    ```
- `python3 label_outreach.py --action mark-contacted --cache <cache> --labels "Hessle Audio|info@hessleaudio.com,Whities|hello@whities.uk"`
  - Appends each `name|email` pair as a `ContactedEntry` with current ISO timestamp.

### `.claude/agents/label-emailer.md`

YAML frontmatter:
```yaml
---
name: label-emailer
description: Process the latest DJ set, find label contact emails, and create per-label Gmail drafts asking labels not to block waterhousestudios on YouTube Content ID.
tools: Bash, Read, Write, WebSearch, WebFetch, mcp__claude_ai_Gmail__create_draft, mcp__claude_ai_Gmail__list_drafts
---
```

System prompt covers (in this order):
1. **Project paths**: log at `~/Desktop/tracklist_live.txt`, cache at `~/.tracklist_secrets/contacted_labels.json`, ask text at `~/.tracklist_secrets/label_email_ask.txt`, helper at `~/Desktop/Track-ID-automation-main/label_outreach.py`.
2. **Pipeline steps**: shell the helper → for each label without an email do `WebSearch` then `WebFetch` then extract → for each label with an email read the ask text and call `create_draft` → shell `mark-contacted` only for labels where `create_draft` succeeded → print the report table.
3. **Email drafting rules:**
   - Subject: `DJ set including {label} releases — quick request re: YouTube Content ID`
   - Body sections in order: friendly greeting, one sentence naming the specific tracks played and the channel (`waterhousestudios`), the verbatim contents of `label_email_ask.txt`, signoff `— waterhousestudios`.
   - Tone: warm, brief, not gushing. Max ~150 words body.
   - Never invent a contact name; use "Hi there," if no person is known.
4. **Failure handling** (see Error Handling table below).
5. **Output contract**: must end the run by printing a markdown table with columns `Label | Email | Status | Notes`.

### `~/.tracklist_secrets/label_email_ask.txt` — User-owned

Plain text. Pasted verbatim into every email's body. **The user authors this before the first real run.** Spec considers it required.

### `~/.tracklist_secrets/contacted_labels.json` — Dedup cache

```json
{
  "labels": [
    {"name": "Hessle Audio",
     "name_normalized": "hessle audio",
     "email": "info@hessleaudio.com",
     "first_contacted": "2026-05-18T22:14:00",
     "source": "discogs"}
  ]
}
```

`source` is one of `discogs`, `websearch`, `manual`. To blacklist a label (never email), pre-seed an entry with `"source": "manual"` and any `email` (or `""`).

## Data Flow

1. User dispatches subagent from main Claude session.
2. Subagent: `python3 label_outreach.py --action enrich --log ~/Desktop/tracklist_live.txt --cache ~/.tracklist_secrets/contacted_labels.json` → JSON of new labels.
3. For each label without an email: `WebSearch("<label name> record label contact email")` → up to 2 results → `WebFetch` each in turn → extract first plausible email (regex on text plus `mailto:` href).
4. For each label with an email: read `label_email_ask.txt`, compose subject + body per the drafting rules, call `mcp__claude_ai_Gmail__create_draft({to, subject, body})`.
5. Collect successes and call `python3 label_outreach.py --action mark-contacted --labels "..."` once at the end.
6. Subagent returns the markdown table.

## Dedup Semantics

A label enters the cache the moment a draft is successfully created for it — not when the user actually sends. Rationale: a draft created represents an outreach decision; if the user opens the draft and decides not to send, they can delete it, but the dedup intent ("don't try this label again") still holds. To deliberately re-attempt a label, the user manually removes its entry from `contacted_labels.json`. This trades a tiny amount of edge-case manual work for a much simpler "one source of truth" model.

## Error Handling

| Failure | Behavior |
|---|---|
| `tracklist_live.txt` missing or no session in it | Helper exits non-zero; subagent reports `no session found` and stops |
| Discogs 429 | One retry with 1 s delay (matches `tracklist_lookup.py:19-21`); on second failure, drop that track silently |
| Discogs returns no release for a track | Track dropped from outreach (no label = no target) |
| Discogs returns release but no `labels` array | Track dropped from outreach |
| `contactinfo` present but no email regex hit | Treat as no Discogs email; proceed to web search |
| `WebSearch` returns zero results | Mark label `NO_EMAIL_FOUND`; do NOT add to cache (so future runs retry) |
| `WebFetch` returns 4xx/5xx for both top results | Mark `NO_EMAIL_FOUND`; do NOT add to cache; Notes column records the URL(s) tried |
| Extracted email is malformed (missing `@`, internal whitespace, etc.) | Mark `NO_EMAIL_FOUND`; Notes records the page URL |
| `create_draft` MCP call errors | Mark `DRAFT_API_ERROR`; do NOT add to cache; Notes records the MCP error message |
| `label_email_ask.txt` missing | Subagent refuses to proceed, prints the exact path to create and aborts before any web fetches |
| `label_email_ask.txt` empty | Same as missing |
| Cache file corrupt (invalid JSON) | Helper exits non-zero with the path; subagent reports it and stops (do not silently overwrite) |

## Testing

### Unit tests — `tests/test_label_outreach.py`

Follows the style and stub-based approach of `tests/test_mixcloud_client.py`. Tests:

- `parse_latest_session` returns only the most recent session given a multi-session log.
- `parse_latest_session` filters out tracks under 30 s via `track_filter.filter_short_tracks`, including the last-track-uses-end-time case.
- `group_by_label` correctly maps tracks to labels given stubbed Discogs responses (release-search hit, release-search miss, release endpoint missing `labels`).
- `group_by_label` deduplicates Discogs calls when the same `(artist, title)` appears twice.
- `group_by_label` extracts emails from realistic `contactinfo` strings (plain email, "name [at] domain", embedded in a sentence).
- `load_contacted` returns empty set when file missing.
- `load_contacted` returns the right set given a populated cache.
- `save_contacted` writes mode 600 (verified via `os.stat`) and creates the parent dir mode 700.
- `save_contacted` is append-only — pre-existing entries survive.

All Discogs calls are stubbed via `unittest.mock`; no network in unit tests.

### First-run protocol — manual

The spec mandates the user run this once before the first real outreach, to verify subagent behavior end-to-end:

1. Pick a small recent session (2-3 tracks, all with clearly resolvable labels).
2. Author `~/.tracklist_secrets/label_email_ask.txt` with the real ask text.
3. Dispatch the subagent.
4. Verify: the report table lists each label correctly; the Gmail Drafts folder contains exactly one draft per `DRAFT_CREATED` row; each draft's body contains the ask text verbatim and names the correct tracks.
5. If any draft is wrong, delete all drafts, fix whatever's wrong (likely the system prompt), and repeat.
6. Only after a clean first-run pass do real sends happen.

## Security & Privacy

- `~/.tracklist_secrets/` continues at mode 700; new files at mode 600 (matches existing pattern).
- The cache file contains label names + emails — sensitive enough not to commit. `.gitignore` already excludes the secrets dir (verify before first run).
- Web fetches are read-only and use the default `WebFetch` tool with no custom headers.
- No outbound email is sent automatically; the Gmail MCP `create_draft` only creates drafts.
- The user's exact ask text is loaded from disk per-draft, never hardcoded in the subagent prompt — keeps the prompt static and lets the user iterate on tone without touching code.

## User-Owned Assets (Pending Before First Real Run)

The following must be authored by the user before the first non-test run:

- **`~/.tracklist_secrets/label_email_ask.txt`** — the verbatim YouTube Content ID ask the subagent pastes into every email. Authored last, intentionally outside the implementation work. The implementation will not run usefully until this file exists.

## Out of Scope

- A bound slash command (e.g., `/email-labels`) — easy to add later as a thin wrapper around the `Agent({subagent_type: "label-emailer"})` dispatch, but not required for v1.
- Auto-sending emails (deliberately excluded; manual send via Gmail is a safety feature, not a limitation).
- Re-contact flow / follow-ups (e.g., "30 days later, ping again"). Future enhancement.
- Bandcamp/SoundCloud as additional email sources. Web search covers most cases; can add later if hit rate is low.
- Tracking which drafts the user actually sent (vs. deleted). Cache treats "draft created" as the outreach event.
- Per-track label resolution when a release has multiple labels. v1 uses `labels[0]` only.
