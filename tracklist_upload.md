# Uploading tracklists from the recording computer

Handoff doc for the recording computer. Goal: after each recorded set, a script
uploads the tracklist generated during the show to the Waterhouse API, which
**matches it to the right event automatically** from a timestamp — no event IDs
to look up. Once uploaded, the tracklist shows on the public event page and the
Dropbox file browser attaches it to each recording with chapter timestamps
re-based onto that recording (paste-ready for YouTube).

This doc is self-contained; a reference script is at the bottom.

---

## 1. One-time setup

You need two values, kept in environment variables (or a config file the
script reads — never hardcode the token in the script):

| variable | value |
| --- | --- |
| `TRACKLIST_API_URL` | `https://api.waterhousestudios.nl` |
| `TRACKLIST_API_TOKEN` | ask Dean — it's the `TRACKLIST_API_TOKEN` from the API server env |

The token is a static bearer credential dedicated to tracklist uploads; it
can't do anything else, so it's safe to store on the recording machine.

## 2. The API in one paragraph

```
POST {TRACKLIST_API_URL}/api/tracklists
Authorization: Bearer {TRACKLIST_API_TOKEN}
Content-Type: application/json
```

```json
{
  "recorded_at": "2025-10-25T01:15:16+02:00",
  "tracks": [
    { "artist": "Bertrum",  "title": "Opening Intro", "started_at": "2025-10-25T01:16:02+02:00" },
    { "artist": "Overmono", "title": "Gunk",          "started_at": "2025-10-25T01:21:47+02:00" }
  ]
}
```

- `recorded_at` — when the set/recording happened. The API finds the approved
  event whose scheduled window contains this timestamp (±1 hour grace). Use
  the recording start time (it's in the OBS filename: `2025-10-25 01-15-16.mkv`),
  or any timestamp during the set.
- `tracks[].started_at` — the wall-clock time each track started. **Send
  absolute times, not offsets.** One event often has several recordings that
  start at different moments; absolute times are what let the site compute
  correct chapter offsets for each recording individually.
- **Every timestamp must include a timezone offset** (`+02:00` / `+01:00` /
  `Z`). Timestamps without one are rejected with a 400 — this is deliberate,
  so a DST mixup can't silently shift a whole tracklist.
- Track order and set-relative offsets are computed server-side; you don't
  need to sort or number anything. `artist` is optional per track.
- Re-uploading **replaces** the event's tracklist, so the script is safe to
  re-run after a fix.

### Responses

| status | meaning | what the script should do |
| --- | --- | --- |
| `200` | stored — body echoes the matched event and `track_count` | log it, done |
| `400` | validation error — body says exactly which field | fix input, re-run |
| `401` | bad/missing token | check env var |
| `404` | no event found around `recorded_at` | the event probably wasn't on the calendar; ask Dean, then re-run with `--event-id` |
| `409` | two events overlap that timestamp (parallel spaces) — body has a `candidates` list with ids and times | re-run with `--event-id <uuid>` picked from the candidates |
| `5xx` | server hiccup | retry later — upload is idempotent |

To target an event explicitly, send `"event_id": "<uuid>"` instead of
`recorded_at` (the reference script's `--event-id` flag does this).

## 3. Input: the tracklist text file

The reference script assumes one track per line, wall-clock time first:

```
23:58:41  Bertrum - Opening Intro
00:04:12  Overmono - Gunk
00:12:55  Unknown ID
```

Accepted per line: `HH:MM:SS` (or `HH:MM`) followed by `Artist - Title` (the
artist part is optional — a line without ` - ` becomes title-only). If the
real output of the tracklist software differs, adapt the single
`parse_line()` function marked in the script; everything else stays the same.

Because the file only has times of day, the script derives full dates from
the recording date and **rolls over midnight automatically** (a set from
23:00 to 01:00 works — see `23:58` → `00:04` above). The machine's local
timezone (Europe/Amsterdam on the studio machines) is attached to every
timestamp.

## 4. When to run

After the recording stops and the tracklist file is final:

```
python3 upload_tracklist.py "2025-10-25 01-15-16.mkv" tracklist_live.txt
```

The first argument is the recording file (or just its name — only the
`YYYY-MM-DD HH-MM-SS` part is read); the second is the tracklist text.
Use `--dry-run` to print the JSON payload without sending, `--event-id <uuid>`
to bypass timestamp matching. Hooking this into OBS's "recording stopped"
event or a post-show checklist both work — there's no deadline; the upload can
happen days later and everything still lines up.

## 5. How to check it worked

- The `200` response echoes the matched event's `purpose` and times — eyeball
  that it's the right show.
- Public API (no auth): `GET https://api.waterhousestudios.nl/api/reservations/public/<event_id>`
  → `reservation.tracklist`.
- The event page on the site shows a "tracklist" card; the Files browser shows
  a 🎵 Tracklist button on recordings whose filename timestamp falls inside
  the event.

---

## Reference script

Python 3.9+, standard library only — no installs. Save as
`upload_tracklist.py`.

```python
#!/usr/bin/env python3
"""Upload a tracklist to the Waterhouse API after a recorded set.

Usage:
  python3 upload_tracklist.py <recording-file-or-timestamp> <tracklist.txt> [--dry-run] [--event-id UUID]

  <recording-file-or-timestamp>  e.g. "2025-10-25 01-15-16.mkv" (OBS filename)
                                 or an ISO timestamp "2025-10-25T01:15:16"
Env:
  TRACKLIST_API_URL    default https://api.waterhousestudios.nl
  TRACKLIST_API_TOKEN  required
"""

import json
import os
import re
import sys
import urllib.error
import urllib.request
from datetime import datetime, time, timedelta

# Times in the tracklist file and the recording filename are local studio
# time; the API requires explicit offsets, so we attach the studio's zone.
# Proper zone lookup gets DST right even when uploading days after the show;
# the fallback (today's fixed offset) is only wrong across a DST switch.
try:
    from zoneinfo import ZoneInfo
    LOCAL_TZ = ZoneInfo("Europe/Amsterdam")
except Exception:
    LOCAL_TZ = datetime.now().astimezone().tzinfo

FILENAME_RE = re.compile(r"(\d{4})-(\d{2})-(\d{2})[ _T](\d{2})[-:](\d{2})[-:](\d{2})")
# ── ADAPT HERE if the tracklist software's line format differs ──────────────
LINE_RE = re.compile(r"^\s*(\d{1,2}):(\d{2})(?::(\d{2}))?\s+(.*\S)\s*$")


def parse_line(line):
    """'23:58:41  Artist - Title' -> (time, artist|None, title), or None to skip."""
    m = LINE_RE.match(line)
    if not m:
        return None
    h, mnt, sec, rest = int(m[1]), int(m[2]), int(m[3] or 0), m[4]
    artist, title = (None, rest)
    if " - " in rest:
        artist, title = (p.strip() for p in rest.split(" - ", 1))
    return time(h, mnt, sec), artist or None, title
# ─────────────────────────────────────────────────────────────────────────────


def parse_recording_start(arg):
    m = FILENAME_RE.search(arg)
    if not m:
        sys.exit(f"error: no YYYY-MM-DD HH-MM-SS timestamp found in {arg!r}")
    return datetime(*map(int, m.groups()), tzinfo=LOCAL_TZ)


def build_tracks(path, recording_start):
    """Assign full dates to time-of-day entries, rolling over midnight."""
    # Anchor 6h before the recording start: a track logged at 23:58 for a
    # recording that started 01:15 lands on the *previous* date, correctly.
    prev = recording_start - timedelta(hours=6)
    tracks = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            parsed = parse_line(line)
            if not parsed:
                continue
            tod, artist, title = parsed
            dt = datetime.combine(prev.date(), tod, tzinfo=LOCAL_TZ)
            # 30 min tolerance for slightly out-of-order log lines
            while dt < prev - timedelta(minutes=30):
                dt += timedelta(days=1)
            prev = dt
            track = {"title": title, "started_at": dt.isoformat()}
            if artist:
                track["artist"] = artist
            tracks.append(track)
    if not tracks:
        sys.exit(f"error: no tracks parsed from {path}")
    return tracks


def main(argv):
    args = [a for a in argv if not a.startswith("--")]
    if len(args) != 2:
        sys.exit(__doc__)
    dry_run = "--dry-run" in argv
    event_id = argv[argv.index("--event-id") + 1] if "--event-id" in argv else None

    recording_start = parse_recording_start(args[0])
    payload = {"tracks": build_tracks(args[1], recording_start)}
    if event_id:
        payload["event_id"] = event_id
    else:
        payload["recorded_at"] = recording_start.isoformat()

    body = json.dumps(payload, indent=2)
    if dry_run:
        print(body)
        return

    token = os.environ.get("TRACKLIST_API_TOKEN") or sys.exit("error: TRACKLIST_API_TOKEN not set")
    url = os.environ.get("TRACKLIST_API_URL", "https://api.waterhousestudios.nl").rstrip("/")
    req = urllib.request.Request(
        url + "/api/tracklists",
        data=body.encode(),
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as res:
            result = json.load(res)
        print(f"ok: {result['track_count']} tracks -> \"{result.get('purpose') or result['event_id']}\""
              f" ({result['start_time']} - {result['end_time']})"
              + (" [replaced previous tracklist]" if result.get("replaced_previous") else ""))
    except urllib.error.HTTPError as e:
        detail = json.loads(e.read() or b"{}")
        print(f"upload failed ({e.code}): {detail.get('error', e.reason)}", file=sys.stderr)
        for c in detail.get("candidates", []):
            print(f"  candidate --event-id {c['event_id']}  {c.get('purpose','')} "
                  f"({c['start_time']} - {c['end_time']})", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main(sys.argv[1:])
```

### Quick test without touching real data

```bash
python3 upload_tracklist.py "2025-10-25 01-15-16.mkv" tracklist_live.txt --dry-run
```

Check that the printed `started_at` values have the right dates around
midnight and the right `+02:00`/`+01:00` offset, then run it for real.
