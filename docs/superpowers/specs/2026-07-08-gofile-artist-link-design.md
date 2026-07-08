# Gofile artist download link — design (2026-07-08)

## Problem

Deploy Content Stage 3 (artist download link) used SwissTransfer through the
browser. Browser automation cannot attach multi-GB files (the Chrome file_upload
tool caps at 10 MB), so Marko had to drag the recording into the page himself
every time. The stage needs a file host that a script can upload to directly.

## Decision

Use **Gofile** (free account, `info@waterhousestudios.nl`) as the primary host,
uploaded by a new script. **SwissTransfer stays as the manual backup** when
Gofile fails: drag the file into swisstransfer.com, validity 15 days.

Chosen over alternatives because Gofile has a simple official HTTP API
(SwissTransfer has none; Pixeldrain was the runner-up). Known trade-off,
accepted by Marko: the free tier only guarantees files for ~10 days without
downloads, so the artist email/message always says **"please download within
7 days."**

## Components

- `gofile_upload.py` — CLI: `--file <path>` uploads and prints the download
  link; `--dry-run` previews name+size offline. Reads the API token from
  `~/.tracklist_secrets/gofile.json` (`{"account_id", "api_token"}`, mode 600).
  Picks an upload server via `GET api.gofile.io/servers`, preferring zone `eu`;
  streams the file with `curl -F` to
  `https://<server>.gofile.io/contents/uploadfile` with a Bearer token.
  Exit codes match project convention: 0 ok, 2 input, 4 auth, 5 upload.
- `tests/test_gofile_upload.py` — 12 unit tests, all network/subprocess mocked.
- `~/.claude/commands/deploy-content.md` Stage 3 rewritten: run the script in a
  background Bash call (multi-GB upload outlives the 10-minute foreground
  timeout), show the link labeled "send this to <artist>", Gmail draft (never
  auto-send) with the 7-day note, SwissTransfer fallback text on failure.

## Verified

- Token verified against `GET api.gofile.io/accounts/<id>`.
- Real end-to-end upload of a small test file returned a working
  `gofile.io/d/…` link; test files left to auto-expire.
- Full suite 135/135 green.
