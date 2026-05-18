# Stream Tracklist Auto-Post Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build `post_tracklist.py` — a single command that, after a livestream, auto-posts a timestamped tracklist (per-song chapters) to the user's most recent Mixcloud cloudcast via API, and copies an equivalent YouTube-chapter-formatted description to the macOS clipboard.

**Architecture:** A new orchestrator (`post_tracklist.py`) wires together small focused modules: `stream_anchor.py` (find OBS recording), `track_filter.py` (drop <30s tracks), `timestamp_builder.py` (compute chapter offsets), `songlink_lookup.py` (iTunes→Songlink for universal links), `youtube_formatter.py` (produce description text), `mixcloud_client.py` (OAuth + cloudcast edit), `clipboard_and_notify.py` (pbcopy + osascript). Step 1 files (`tracklist_parser.py`, `tracklist_lookup.py`, `tracklist_format.py`) are imported from but **never modified**.

**Tech Stack:** Python 3.9 stdlib, `requests` (already installed), `unittest.mock` for tests. No new dependencies. Tests follow the existing project pattern: plain functions with `assert`, run via `python3 tests/<file>.py`.

**Spec:** `docs/superpowers/specs/2026-05-17-stream-tracklist-autopost-design.md`

**Project root:** `/Users/waterhousestudios/Desktop/TRACK ID PROJECT/`

**Note on git:** The project is not currently a git repo. Each task ends with a recommended `git add` / `git commit` step — if the user runs `git init` first, these work as written. If not, treat commit steps as "snapshot checkpoint complete" markers and skip the commands.

---

### Task 1: Initialize git, install no new deps, set up test runner

**Files:**
- Create: `/Users/waterhousestudios/Desktop/TRACK ID PROJECT/.gitignore`
- Create: `/Users/waterhousestudios/Desktop/TRACK ID PROJECT/tests/run_all.py`

- [ ] **Step 1: Initialize git repo (if not already)**

Run:
```
cd "$HOME/Desktop/TRACK ID PROJECT"
git init -b main
```

Expected output:
```
Initialized empty Git repository in /Users/waterhousestudios/Desktop/TRACK ID PROJECT/.git/
```

If `git status` shows it already initialized, skip this step.

- [ ] **Step 2: Write `.gitignore`**

Save this content to `/Users/waterhousestudios/Desktop/TRACK ID PROJECT/.gitignore`:

```
__pycache__/
*.pyc
.DS_Store
.tracklist_secrets/
```

- [ ] **Step 3: Write the test runner**

Save to `/Users/waterhousestudios/Desktop/TRACK ID PROJECT/tests/run_all.py`:

```python
"""Run every test_*.py file in this directory."""
import importlib.util
import sys
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE.parent))

failures = 0
total = 0

for test_file in sorted(HERE.glob("test_*.py")):
    name = test_file.stem
    spec = importlib.util.spec_from_file_location(name, test_file)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    tests = [getattr(mod, n) for n in dir(mod) if n.startswith("test_") and callable(getattr(mod, n))]
    print(f"\n{name}:")
    for t in tests:
        total += 1
        try:
            t()
            print(f"  PASS  {t.__name__}")
        except AssertionError as e:
            failures += 1
            print(f"  FAIL  {t.__name__}: {e}")
        except Exception as e:
            failures += 1
            print(f"  ERROR {t.__name__}: {type(e).__name__}: {e}")

print(f"\n{total - failures}/{total} passed.")
sys.exit(0 if failures == 0 else 1)
```

- [ ] **Step 4: Verify existing tests still run via the new runner**

Run:
```
cd "$HOME/Desktop/TRACK ID PROJECT"
python3 tests/run_all.py
```

Expected: `6/6 passed.` (the existing `test_log_format.py` tests).

- [ ] **Step 5: Initial commit**

Run:
```
cd "$HOME/Desktop/TRACK ID PROJECT"
git add .gitignore tests/run_all.py
git commit -m "chore: add gitignore and test runner for Step 2"
```

---

### Task 2: `stream_anchor.py` — find latest OBS recording

**Files:**
- Create: `/Users/waterhousestudios/Desktop/TRACK ID PROJECT/stream_anchor.py`
- Create: `/Users/waterhousestudios/Desktop/TRACK ID PROJECT/tests/test_stream_anchor.py`

- [ ] **Step 1: Write failing tests**

Save to `tests/test_stream_anchor.py`:

```python
import sys
import tempfile
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from stream_anchor import find_latest_movie


def _touch(dir_path, name):
    (Path(dir_path) / name).write_bytes(b"")


def test_picks_newest_by_filename():
    with tempfile.TemporaryDirectory() as d:
        _touch(d, "2026-05-17 21-30-00.mov")
        _touch(d, "2026-05-15 18-00-00.mov")
        _touch(d, "2026-05-17 22-45-00.mov")
        path, ts = find_latest_movie(d)
        assert path.name == "2026-05-17 22-45-00.mov", path.name
        assert ts == datetime(2026, 5, 17, 22, 45, 0), ts


def test_handles_resume_recording_suffix():
    with tempfile.TemporaryDirectory() as d:
        _touch(d, "2026-05-17 21-30-00.mov")
        _touch(d, "2026-05-17 21-30-00 (1).mov")
        path, ts = find_latest_movie(d)
        # Both have the same timestamp; just verify one of them matched
        assert path.name.startswith("2026-05-17 21-30-00"), path.name


def test_ignores_non_matching_files():
    with tempfile.TemporaryDirectory() as d:
        _touch(d, "random.mov")
        _touch(d, "screenshot.png")
        _touch(d, "2026-05-17 21-30-00.mov")
        path, ts = find_latest_movie(d)
        assert path.name == "2026-05-17 21-30-00.mov"


def test_empty_dir_raises():
    with tempfile.TemporaryDirectory() as d:
        try:
            find_latest_movie(d)
        except FileNotFoundError:
            return
        raise AssertionError("Expected FileNotFoundError")


def test_no_matching_files_raises():
    with tempfile.TemporaryDirectory() as d:
        _touch(d, "random.mov")
        try:
            find_latest_movie(d)
        except FileNotFoundError:
            return
        raise AssertionError("Expected FileNotFoundError")


def test_missing_dir_raises():
    try:
        find_latest_movie("/tmp/this_path_definitely_does_not_exist_42")
    except FileNotFoundError:
        return
    raise AssertionError("Expected FileNotFoundError")
```

- [ ] **Step 2: Run tests, confirm they fail**

Run: `python3 tests/run_all.py`

Expected: `test_stream_anchor` section shows ERROR on each test (`ModuleNotFoundError: No module named 'stream_anchor'`).

- [ ] **Step 3: Implement `stream_anchor.py`**

Save to `/Users/waterhousestudios/Desktop/TRACK ID PROJECT/stream_anchor.py`:

```python
"""Find the latest OBS recording in ~/Movies and parse its filename for stream-start time."""

import os
import re
from datetime import datetime
from pathlib import Path

_FILENAME_PATTERN = re.compile(
    r"^(\d{4}-\d{2}-\d{2}) (\d{2})-(\d{2})-(\d{2})(?: \(\d+\))?\.mov$"
)


def find_latest_movie(movies_dir="~/Movies"):
    """Return (Path, datetime) for the newest OBS-named .mov file in movies_dir.

    Raises FileNotFoundError if the dir doesn't exist or contains no matching file.
    """
    expanded = Path(os.path.expanduser(str(movies_dir)))
    if not expanded.is_dir():
        raise FileNotFoundError(f"Directory not found: {expanded}")

    matches = []
    for path in expanded.iterdir():
        m = _FILENAME_PATTERN.match(path.name)
        if not m:
            continue
        date_str, hh, mm, ss = m.groups()
        ts = datetime.strptime(f"{date_str} {hh}:{mm}:{ss}", "%Y-%m-%d %H:%M:%S")
        matches.append((path, ts))

    if not matches:
        raise FileNotFoundError(f"No OBS recordings (YYYY-MM-DD HH-MM-SS.mov) in {expanded}")

    matches.sort(key=lambda x: x[1], reverse=True)
    return matches[0]
```

- [ ] **Step 4: Run tests, confirm they pass**

Run: `python3 tests/run_all.py`

Expected: all `test_stream_anchor` tests PASS.

- [ ] **Step 5: Commit**

```
cd "$HOME/Desktop/TRACK ID PROJECT"
git add stream_anchor.py tests/test_stream_anchor.py
git commit -m "feat: stream_anchor finds latest OBS recording and parses its timestamp"
```

---

### Task 3: `track_filter.py` — drop tracks that were master for <30s

**Files:**
- Create: `/Users/waterhousestudios/Desktop/TRACK ID PROJECT/track_filter.py`
- Create: `/Users/waterhousestudios/Desktop/TRACK ID PROJECT/tests/test_track_filter.py`

- [ ] **Step 1: Write failing tests**

Save to `tests/test_track_filter.py`:

```python
import sys
from datetime import datetime, timedelta
from pathlib import Path
from dataclasses import dataclass

sys.path.insert(0, str(Path(__file__).parent.parent))

from track_filter import filter_short_tracks


@dataclass
class _T:
    """Minimal stand-in for tracklist_parser.Track."""
    wall_time: datetime
    artist: str = "A"
    title: str = "T"


def _at(h, m, s):
    return _T(wall_time=datetime(2026, 5, 17, h, m, s))


def test_empty_list():
    assert filter_short_tracks([], min_seconds=30) == []


def test_drops_short_first_track():
    tracks = [_at(21, 0, 0), _at(21, 0, 10), _at(22, 0, 0)]
    out = filter_short_tracks(tracks, min_seconds=30)
    assert len(out) == 2, len(out)
    assert out[0].wall_time == datetime(2026, 5, 17, 21, 0, 10)
    assert out[1].wall_time == datetime(2026, 5, 17, 22, 0, 0)


def test_keeps_all_long_tracks():
    tracks = [_at(21, 0, 0), _at(21, 5, 0), _at(21, 10, 0)]
    end = datetime(2026, 5, 17, 21, 20, 0)
    out = filter_short_tracks(tracks, min_seconds=30, end_time=end)
    assert len(out) == 3


def test_drops_short_middle_track():
    tracks = [_at(21, 0, 0), _at(21, 5, 0), _at(21, 5, 5), _at(21, 10, 0)]
    end = datetime(2026, 5, 17, 21, 20, 0)
    out = filter_short_tracks(tracks, min_seconds=30, end_time=end)
    assert len(out) == 3
    assert all(t.wall_time != datetime(2026, 5, 17, 21, 5, 0) for t in out)


def test_last_track_uses_end_time():
    tracks = [_at(21, 0, 0), _at(21, 5, 0)]
    # Last track has duration 10s from start to end_time -> should be dropped
    end = datetime(2026, 5, 17, 21, 5, 10)
    out = filter_short_tracks(tracks, min_seconds=30, end_time=end)
    assert len(out) == 1
    assert out[0].wall_time == datetime(2026, 5, 17, 21, 0, 0)


def test_threshold_boundary_exclusive():
    # Exactly 30s should be KEPT (>= 30)
    tracks = [_at(21, 0, 0), _at(21, 0, 30), _at(22, 0, 0)]
    out = filter_short_tracks(tracks, min_seconds=30)
    assert len(out) == 3
```

- [ ] **Step 2: Run tests, confirm they fail**

Run: `python3 tests/run_all.py`

Expected: ERRORs on every `test_track_filter` (module not found).

- [ ] **Step 3: Implement `track_filter.py`**

Save to `/Users/waterhousestudios/Desktop/TRACK ID PROJECT/track_filter.py`:

```python
"""Drop tracks whose duration as master was below a threshold."""

from datetime import datetime


def filter_short_tracks(tracks, min_seconds=30, end_time=None):
    """Return only tracks where (next_track.wall_time - this_track.wall_time) >= min_seconds.

    For the final track in the list, duration is computed against end_time (default: datetime.now()).
    """
    if not tracks:
        return []

    if end_time is None:
        end_time = datetime.now()

    kept = []
    for i, t in enumerate(tracks):
        if i < len(tracks) - 1:
            duration = (tracks[i + 1].wall_time - t.wall_time).total_seconds()
        else:
            duration = (end_time - t.wall_time).total_seconds()
        if duration >= min_seconds:
            kept.append(t)
    return kept
```

- [ ] **Step 4: Run tests, confirm they pass**

Run: `python3 tests/run_all.py`

Expected: all `test_track_filter` tests PASS, plus prior tests still PASS.

- [ ] **Step 5: Commit**

```
git add track_filter.py tests/test_track_filter.py
git commit -m "feat: track_filter drops sub-30s master bursts"
```

---

### Task 4: `timestamp_builder.py` — build chapters with `0:00` rules

**Files:**
- Create: `/Users/waterhousestudios/Desktop/TRACK ID PROJECT/timestamp_builder.py`
- Create: `/Users/waterhousestudios/Desktop/TRACK ID PROJECT/tests/test_timestamp_builder.py`

- [ ] **Step 1: Write failing tests**

Save to `tests/test_timestamp_builder.py`:

```python
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from timestamp_builder import build_chapters, format_time, Chapter


@dataclass
class _T:
    wall_time: datetime
    artist: str
    title: str


def test_format_time_under_hour():
    assert format_time(0) == "0:00"
    assert format_time(5) == "0:05"
    assert format_time(65) == "1:05"
    assert format_time(3599) == "59:59"


def test_format_time_with_hours():
    assert format_time(3600) == "1:00:00"
    assert format_time(3725) == "1:02:05"


def test_inserts_intro_when_first_track_late():
    start = datetime(2026, 5, 17, 21, 30, 0)
    tracks = [
        _T(datetime(2026, 5, 17, 21, 35, 23), "Anthony Naples", "Crystals"),
        _T(datetime(2026, 5, 17, 21, 42, 47), "Joy Orbison", "Hyph Mngo"),
    ]
    chapters = build_chapters(tracks, start)
    assert len(chapters) == 3
    assert chapters[0].time_seconds == 0
    assert chapters[0].artist == "Intro"
    assert chapters[0].title == "Intro"
    assert chapters[1].artist == "Anthony Naples"
    assert chapters[1].time_seconds == 5 * 60 + 23
    assert chapters[1].time_str == "05:23"


def test_replaces_intro_when_first_track_within_10s():
    start = datetime(2026, 5, 17, 21, 30, 0)
    tracks = [
        _T(datetime(2026, 5, 17, 21, 30, 5), "First", "Track"),
        _T(datetime(2026, 5, 17, 21, 35, 0), "Second", "Track"),
    ]
    chapters = build_chapters(tracks, start)
    assert len(chapters) == 2
    assert chapters[0].time_seconds == 0
    assert chapters[0].artist == "First"
    assert chapters[0].title == "Track"
    assert chapters[1].time_seconds == 5 * 60
    assert chapters[1].artist == "Second"


def test_skips_pre_stream_tracks():
    start = datetime(2026, 5, 17, 21, 30, 0)
    tracks = [
        _T(datetime(2026, 5, 17, 21, 20, 0), "Pre", "Stream1"),
        _T(datetime(2026, 5, 17, 21, 25, 0), "Pre", "Stream2"),
        _T(datetime(2026, 5, 17, 21, 35, 0), "Real", "Track"),
        _T(datetime(2026, 5, 17, 21, 40, 0), "Another", "Track"),
    ]
    chapters = build_chapters(tracks, start)
    # 3 chapters: Intro + Real + Another (Pre tracks skipped)
    assert len(chapters) == 3
    assert chapters[0].artist == "Intro"
    assert chapters[1].artist == "Real"
    assert chapters[2].artist == "Another"


def test_no_in_stream_tracks_returns_empty():
    start = datetime(2026, 5, 17, 21, 30, 0)
    tracks = [
        _T(datetime(2026, 5, 17, 21, 20, 0), "Only", "PreStream"),
    ]
    chapters = build_chapters(tracks, start)
    assert chapters == []


def test_chapter_has_empty_link_fields_by_default():
    start = datetime(2026, 5, 17, 21, 30, 0)
    tracks = [
        _T(datetime(2026, 5, 17, 21, 35, 0), "A", "T"),
        _T(datetime(2026, 5, 17, 21, 40, 0), "B", "U"),
    ]
    chapters = build_chapters(tracks, start)
    assert chapters[1].discogs_url == ""
    assert chapters[1].songlink_url == ""
```

- [ ] **Step 2: Run tests, confirm they fail**

Run: `python3 tests/run_all.py`

Expected: ERROR on each `test_timestamp_builder` test.

- [ ] **Step 3: Implement `timestamp_builder.py`**

Save to `/Users/waterhousestudios/Desktop/TRACK ID PROJECT/timestamp_builder.py`:

```python
"""Build YouTube/Mixcloud chapter list from tracks + stream-start datetime."""

from dataclasses import dataclass, field
from datetime import datetime


MIN_TRACK_SECONDS = 30  # short-track filter threshold (used by track_filter)
MIN_CHAPTER_GAP = 10    # YouTube minimum chapter duration


@dataclass
class Chapter:
    time_seconds: int
    time_str: str
    artist: str
    title: str
    discogs_url: str = ""
    songlink_url: str = ""


def format_time(seconds):
    """Format integer seconds as 'M:SS' (< 1h) or 'H:MM:SS' (>= 1h)."""
    seconds = int(seconds)
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    if h > 0:
        return f"{h}:{m:02d}:{s:02d}"
    return f"{m}:{s:02d}"


def build_chapters(tracks, stream_start):
    """Return a list of Chapter objects.

    - Tracks logged before stream_start are skipped.
    - If the first remaining track starts within MIN_CHAPTER_GAP (10s) of stream_start,
      it BECOMES the 0:00 chapter (no separate Intro).
    - Otherwise, a synthetic 'Intro' chapter is inserted at 0:00.
    """
    in_stream = []
    skipped = 0
    for t in tracks:
        offset = (t.wall_time - stream_start).total_seconds()
        if offset < 0:
            skipped += 1
            continue
        in_stream.append((int(offset), t))

    if skipped:
        print(f"Skipped {skipped} pre-stream tracks")

    if not in_stream:
        return []

    chapters = []
    first_offset = in_stream[0][0]

    if first_offset < MIN_CHAPTER_GAP:
        _, first_t = in_stream[0]
        chapters.append(Chapter(
            time_seconds=0,
            time_str=format_time(0),
            artist=first_t.artist,
            title=first_t.title,
        ))
        rest = in_stream[1:]
    else:
        chapters.append(Chapter(
            time_seconds=0,
            time_str=format_time(0),
            artist="Intro",
            title="Intro",
        ))
        rest = in_stream

    for offset, t in rest:
        chapters.append(Chapter(
            time_seconds=offset,
            time_str=format_time(offset),
            artist=t.artist,
            title=t.title,
        ))

    return chapters
```

- [ ] **Step 4: Run tests, confirm they pass**

Run: `python3 tests/run_all.py`

Expected: all `test_timestamp_builder` tests PASS.

- [ ] **Step 5: Commit**

```
git add timestamp_builder.py tests/test_timestamp_builder.py
git commit -m "feat: timestamp_builder produces Chapter list with Intro / first-track rules"
```

---

### Task 5: `songlink_lookup.py` — iTunes Search → Songlink universal URL

**Files:**
- Create: `/Users/waterhousestudios/Desktop/TRACK ID PROJECT/songlink_lookup.py`
- Create: `/Users/waterhousestudios/Desktop/TRACK ID PROJECT/tests/test_songlink_lookup.py`

- [ ] **Step 1: Write failing tests**

Save to `tests/test_songlink_lookup.py`:

```python
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

sys.path.insert(0, str(Path(__file__).parent.parent))

import songlink_lookup
from songlink_lookup import songlink_url


def _resp(status, json_body=None):
    r = MagicMock()
    r.status_code = status
    r.json.return_value = json_body if json_body is not None else {}
    return r


def test_happy_path():
    itunes_resp = _resp(200, {"results": [{"trackViewUrl": "https://music.apple.com/x/y/z"}]})
    songlink_resp = _resp(200, {"pageUrl": "https://song.link/i/AbCdEf"})
    with patch.object(songlink_lookup.requests, "get", side_effect=[itunes_resp, songlink_resp]):
        url = songlink_url("Anthony Naples", "Crystals")
    assert url == "https://song.link/i/AbCdEf"


def test_itunes_no_results_returns_empty():
    itunes_resp = _resp(200, {"results": []})
    with patch.object(songlink_lookup.requests, "get", return_value=itunes_resp):
        url = songlink_url("Unknown Artist", "Unknown Title")
    assert url == ""


def test_itunes_http_error_returns_empty():
    itunes_resp = _resp(500)
    with patch.object(songlink_lookup.requests, "get", return_value=itunes_resp):
        url = songlink_url("X", "Y")
    assert url == ""


def test_itunes_429_retries_once():
    first = _resp(429)
    second = _resp(200, {"results": [{"trackViewUrl": "https://music.apple.com/x/y/z"}]})
    third = _resp(200, {"pageUrl": "https://song.link/i/Final"})
    with patch.object(songlink_lookup.requests, "get", side_effect=[first, second, third]):
        with patch.object(songlink_lookup.time, "sleep"):  # don't actually sleep in tests
            url = songlink_url("X", "Y")
    assert url == "https://song.link/i/Final"


def test_songlink_failure_returns_empty():
    itunes_resp = _resp(200, {"results": [{"trackViewUrl": "https://music.apple.com/x/y/z"}]})
    songlink_resp = _resp(500)
    with patch.object(songlink_lookup.requests, "get", side_effect=[itunes_resp, songlink_resp]):
        url = songlink_url("X", "Y")
    assert url == ""


def test_network_exception_returns_empty():
    with patch.object(songlink_lookup.requests, "get", side_effect=ConnectionError("boom")):
        url = songlink_url("X", "Y")
    assert url == ""


def test_missing_trackViewUrl_returns_empty():
    itunes_resp = _resp(200, {"results": [{"otherField": "value"}]})
    with patch.object(songlink_lookup.requests, "get", return_value=itunes_resp):
        url = songlink_url("X", "Y")
    assert url == ""
```

- [ ] **Step 2: Run tests, confirm they fail**

Run: `python3 tests/run_all.py`

Expected: ERROR on each `test_songlink_lookup` test.

- [ ] **Step 3: Implement `songlink_lookup.py`**

Save to `/Users/waterhousestudios/Desktop/TRACK ID PROJECT/songlink_lookup.py`:

```python
"""Look up universal listen-here links via iTunes Search + Songlink."""

import time
import requests

_ITUNES_SEARCH = "https://itunes.apple.com/search"
_SONGLINK = "https://api.song.link/v1-alpha.1/links"
_TIMEOUT = 10
_RETRY_SLEEP_429 = 30  # seconds to wait before retrying after a 429


def _itunes_track_url(artist, title):
    """Return the iTunes trackViewUrl for the top match, or '' on any failure."""
    params = {"term": f"{artist} {title}", "entity": "song", "limit": 1}
    try:
        resp = requests.get(_ITUNES_SEARCH, params=params, timeout=_TIMEOUT)
        if resp.status_code == 429:
            time.sleep(_RETRY_SLEEP_429)
            resp = requests.get(_ITUNES_SEARCH, params=params, timeout=_TIMEOUT)
        if resp.status_code != 200:
            return ""
        results = resp.json().get("results", [])
        if not results:
            return ""
        return results[0].get("trackViewUrl", "")
    except Exception:
        return ""


def _songlink_page_url(itunes_url):
    """Pass an iTunes URL to Songlink, return its pageUrl, or '' on any failure."""
    params = {"url": itunes_url}
    try:
        resp = requests.get(_SONGLINK, params=params, timeout=_TIMEOUT)
        if resp.status_code == 429:
            time.sleep(_RETRY_SLEEP_429)
            resp = requests.get(_SONGLINK, params=params, timeout=_TIMEOUT)
        if resp.status_code != 200:
            return ""
        return resp.json().get("pageUrl", "")
    except Exception:
        return ""


def songlink_url(artist, title):
    """Public entrypoint: artist+title -> universal song.link URL, or '' on any failure."""
    itunes_url = _itunes_track_url(artist, title)
    if not itunes_url:
        return ""
    return _songlink_page_url(itunes_url)
```

- [ ] **Step 4: Run tests, confirm they pass**

Run: `python3 tests/run_all.py`

Expected: all `test_songlink_lookup` tests PASS.

- [ ] **Step 5: Commit**

```
git add songlink_lookup.py tests/test_songlink_lookup.py
git commit -m "feat: songlink_lookup wraps iTunes Search + Songlink"
```

---

### Task 6: `youtube_formatter.py` — produce the YouTube description string

**Files:**
- Create: `/Users/waterhousestudios/Desktop/TRACK ID PROJECT/youtube_formatter.py`
- Create: `/Users/waterhousestudios/Desktop/TRACK ID PROJECT/tests/test_youtube_formatter.py`

- [ ] **Step 1: Write failing tests**

Save to `tests/test_youtube_formatter.py`:

```python
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from timestamp_builder import Chapter
from youtube_formatter import format_youtube


def _chap(secs, ts, artist, title, discogs="", songlink=""):
    return Chapter(
        time_seconds=secs, time_str=ts, artist=artist, title=title,
        discogs_url=discogs, songlink_url=songlink,
    )


def test_full_description():
    chapters = [
        _chap(0, "0:00", "Intro", "Intro"),
        _chap(323, "05:23", "Anthony Naples", "Crystals",
              "discogs.com/release/12345", "https://song.link/i/abc"),
        _chap(767, "12:47", "Joy Orbison", "Hyph Mngo",
              "discogs.com/release/67890", "https://song.link/i/def"),
    ]
    out = format_youtube(chapters, date(2026, 5, 17))
    expected = (
        "Tracklist:\n"
        "\n"
        "0:00 Intro\n"
        "05:23 Anthony Naples — Crystals | https://discogs.com/release/12345 | https://song.link/i/abc\n"
        "12:47 Joy Orbison — Hyph Mngo | https://discogs.com/release/67890 | https://song.link/i/def\n"
        "\n"
        "Recorded live 2026-05-17."
    )
    assert out == expected, f"\nExpected:\n{expected}\n\nGot:\n{out}"


def test_missing_links_show_no_link():
    chapters = [
        _chap(0, "0:00", "Intro", "Intro"),
        _chap(60, "1:00", "A", "B", discogs="", songlink=""),
    ]
    out = format_youtube(chapters, date(2026, 5, 17))
    assert "1:00 A — B | (no link) | (no link)" in out


def test_unidentified_track_format():
    chapters = [
        _chap(0, "0:00", "Intro", "Intro"),
        _chap(60, "1:00", "Unknown Artist", "Unknown Title"),
    ]
    out = format_youtube(chapters, date(2026, 5, 17))
    assert "1:00 [unidentified]" in out
    assert "Unknown Artist" not in out


def test_discogs_gets_https_prefix():
    chapters = [
        _chap(0, "0:00", "Intro", "Intro"),
        _chap(60, "1:00", "A", "B", discogs="discogs.com/release/1"),
    ]
    out = format_youtube(chapters, date(2026, 5, 17))
    assert "https://discogs.com/release/1" in out


def test_already_prefixed_url_not_doubled():
    chapters = [
        _chap(0, "0:00", "Intro", "Intro"),
        _chap(60, "1:00", "A", "B", discogs="https://discogs.com/release/1"),
    ]
    out = format_youtube(chapters, date(2026, 5, 17))
    assert "https://https://" not in out
    assert "https://discogs.com/release/1" in out
```

- [ ] **Step 2: Run tests, confirm they fail**

Run: `python3 tests/run_all.py`

Expected: ERROR on each `test_youtube_formatter` test.

- [ ] **Step 3: Implement `youtube_formatter.py`**

Save to `/Users/waterhousestudios/Desktop/TRACK ID PROJECT/youtube_formatter.py`:

```python
"""Render a YouTube-chapter-formatted tracklist description from a Chapter list."""


def _prefix_https(url):
    if not url:
        return "(no link)"
    if url.startswith("http://") or url.startswith("https://"):
        return url
    return f"https://{url}"


def _chapter_line(ch):
    if ch.artist == "Intro" and ch.title == "Intro":
        return f"{ch.time_str} Intro"
    if ch.artist == "Unknown Artist" or ch.title == "Unknown Title":
        return f"{ch.time_str} [unidentified]"
    discogs = _prefix_https(ch.discogs_url)
    songlink = _prefix_https(ch.songlink_url)
    return f"{ch.time_str} {ch.artist} — {ch.title} | {discogs} | {songlink}"


def format_youtube(chapters, stream_date):
    """Return the YouTube description string. stream_date is a datetime.date."""
    lines = ["Tracklist:", ""]
    for ch in chapters:
        lines.append(_chapter_line(ch))
    lines.append("")
    lines.append(f"Recorded live {stream_date.isoformat()}.")
    return "\n".join(lines)
```

- [ ] **Step 4: Run tests, confirm they pass**

Run: `python3 tests/run_all.py`

Expected: all `test_youtube_formatter` tests PASS.

- [ ] **Step 5: Commit**

```
git add youtube_formatter.py tests/test_youtube_formatter.py
git commit -m "feat: youtube_formatter produces description with https-prefixed URLs"
```

---

### Task 7: `clipboard_and_notify.py` — pbcopy + osascript wrappers

**Files:**
- Create: `/Users/waterhousestudios/Desktop/TRACK ID PROJECT/clipboard_and_notify.py`
- Create: `/Users/waterhousestudios/Desktop/TRACK ID PROJECT/tests/test_clipboard_and_notify.py`

- [ ] **Step 1: Write failing tests**

Save to `tests/test_clipboard_and_notify.py`:

```python
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

sys.path.insert(0, str(Path(__file__).parent.parent))

import clipboard_and_notify


def test_copy_to_clipboard_pipes_text():
    fake_proc = MagicMock()
    with patch.object(clipboard_and_notify.subprocess, "Popen", return_value=fake_proc) as p:
        clipboard_and_notify.copy_to_clipboard("hello world")
    p.assert_called_once_with(["pbcopy"], stdin=clipboard_and_notify.subprocess.PIPE)
    fake_proc.communicate.assert_called_once_with(b"hello world")


def test_copy_to_clipboard_unicode():
    fake_proc = MagicMock()
    with patch.object(clipboard_and_notify.subprocess, "Popen", return_value=fake_proc):
        clipboard_and_notify.copy_to_clipboard("Anthony Naples — Crystals")
    args, _ = fake_proc.communicate.call_args
    assert args[0] == "Anthony Naples — Crystals".encode("utf-8")


def test_notify_invokes_osascript():
    with patch.object(clipboard_and_notify.subprocess, "run") as r:
        clipboard_and_notify.notify("Title", "Body")
    args, kwargs = r.call_args
    cmd = args[0]
    assert cmd[0] == "osascript"
    assert cmd[1] == "-e"
    assert 'display notification "Body"' in cmd[2]
    assert 'with title "Title"' in cmd[2]


def test_notify_escapes_quotes():
    with patch.object(clipboard_and_notify.subprocess, "run") as r:
        clipboard_and_notify.notify('Has "quote"', 'Body "too"')
    cmd = r.call_args[0][0]
    # Verify the quotes were escaped so osascript doesn't see them as terminators
    assert '\\"' in cmd[2]
```

- [ ] **Step 2: Run tests, confirm they fail**

Run: `python3 tests/run_all.py`

Expected: ERROR on each `test_clipboard_and_notify` test.

- [ ] **Step 3: Implement `clipboard_and_notify.py`**

Save to `/Users/waterhousestudios/Desktop/TRACK ID PROJECT/clipboard_and_notify.py`:

```python
"""macOS clipboard + notification helpers."""

import subprocess


def copy_to_clipboard(text):
    """Pipe text to pbcopy."""
    p = subprocess.Popen(["pbcopy"], stdin=subprocess.PIPE)
    p.communicate(text.encode("utf-8"))


def notify(title, body):
    """Show a macOS notification banner via osascript."""
    title_esc = title.replace('\\', '\\\\').replace('"', '\\"')
    body_esc = body.replace('\\', '\\\\').replace('"', '\\"')
    script = f'display notification "{body_esc}" with title "{title_esc}"'
    subprocess.run(["osascript", "-e", script])
```

- [ ] **Step 4: Run tests, confirm they pass**

Run: `python3 tests/run_all.py`

Expected: all `test_clipboard_and_notify` tests PASS.

- [ ] **Step 5: Manually verify clipboard works**

Run:
```
python3 -c "import clipboard_and_notify; clipboard_and_notify.copy_to_clipboard('test from script')"
```
Then paste anywhere with Cmd+V — it should paste `test from script`.

```
python3 -c "import clipboard_and_notify; clipboard_and_notify.notify('Title', 'Body')"
```
Expected: a macOS notification banner appears briefly. (The first time, macOS may ask to grant notification permission to Terminal — say yes.)

- [ ] **Step 6: Commit**

```
git add clipboard_and_notify.py tests/test_clipboard_and_notify.py
git commit -m "feat: clipboard_and_notify wraps pbcopy + osascript notifications"
```

---

### Task 8: `mixcloud_client.py` — app credentials + OAuth flow

**Files:**
- Create: `/Users/waterhousestudios/Desktop/TRACK ID PROJECT/mixcloud_client.py`
- Create: `/Users/waterhousestudios/Desktop/TRACK ID PROJECT/tests/test_mixcloud_client.py`

This task adds the credential loading and the OAuth token-exchange call. The "run a local HTTP server and wait for redirect" piece is **not** unit-tested (it requires a real browser); it is verified manually in Task 11.

- [ ] **Step 1: Write failing tests**

Save to `tests/test_mixcloud_client.py`:

```python
import json
import os
import stat
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock

sys.path.insert(0, str(Path(__file__).parent.parent))

import mixcloud_client


def _resp(status, json_body=None, text=""):
    r = MagicMock()
    r.status_code = status
    r.json.return_value = json_body if json_body is not None else {}
    r.text = text
    return r


def test_load_app_credentials_reads_existing_file(tmp_dir=None):
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "mixcloud_app.json"
        p.write_text(json.dumps({"client_id": "abc", "client_secret": "xyz"}))
        cid, sec = mixcloud_client.load_app_credentials(p)
        assert cid == "abc"
        assert sec == "xyz"


def test_load_app_credentials_missing_file_raises():
    try:
        mixcloud_client.load_app_credentials(Path("/tmp/definitely_does_not_exist_42"))
    except FileNotFoundError:
        return
    raise AssertionError("Expected FileNotFoundError")


def test_save_token_uses_mode_600():
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "mixcloud.json"
        mixcloud_client.save_token(p, "secret-token-value")
        st = os.stat(p)
        # Mode bits should be exactly owner-read+write, no group/other
        assert stat.S_IMODE(st.st_mode) == 0o600
        data = json.loads(p.read_text())
        assert data["access_token"] == "secret-token-value"


def test_load_token_returns_none_if_missing():
    with tempfile.TemporaryDirectory() as d:
        result = mixcloud_client.load_token(Path(d) / "missing.json")
        assert result is None


def test_load_token_reads_existing():
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "mixcloud.json"
        p.write_text(json.dumps({"access_token": "tok"}))
        assert mixcloud_client.load_token(p) == "tok"


def test_exchange_code_for_token_success():
    resp = _resp(200, {"access_token": "the-token"})
    with patch.object(mixcloud_client.requests, "post", return_value=resp):
        token = mixcloud_client.exchange_code_for_token(
            client_id="cid", client_secret="csec",
            redirect_uri="http://localhost:8765/callback",
            code="auth-code",
        )
    assert token == "the-token"


def test_exchange_code_for_token_failure_raises():
    resp = _resp(400, text="Bad request")
    with patch.object(mixcloud_client.requests, "post", return_value=resp):
        try:
            mixcloud_client.exchange_code_for_token(
                client_id="cid", client_secret="csec",
                redirect_uri="http://localhost:8765/callback",
                code="auth-code",
            )
        except mixcloud_client.MixcloudAuthError as e:
            assert "400" in str(e)
            return
    raise AssertionError("Expected MixcloudAuthError")


def test_authorize_url_includes_all_params():
    url = mixcloud_client.build_authorize_url(
        client_id="abc",
        redirect_uri="http://localhost:8765/callback",
    )
    assert url.startswith("https://www.mixcloud.com/oauth/authorize/")
    assert "client_id=abc" in url
    assert "redirect_uri=http%3A%2F%2Flocalhost%3A8765%2Fcallback" in url
    assert "response_type=code" in url
```

- [ ] **Step 2: Run tests, confirm they fail**

Run: `python3 tests/run_all.py`

Expected: ERRORs on `test_mixcloud_client` tests (module not found).

- [ ] **Step 3: Implement `mixcloud_client.py` (this task's portion)**

Save to `/Users/waterhousestudios/Desktop/TRACK ID PROJECT/mixcloud_client.py`:

```python
"""Mixcloud API client: credential storage, OAuth exchange, cloudcast operations."""

import http.server
import json
import os
import threading
import time
import urllib.parse
import webbrowser
from pathlib import Path

import requests

SECRETS_DIR = Path(os.path.expanduser("~/.tracklist_secrets"))
APP_CRED_PATH = SECRETS_DIR / "mixcloud_app.json"
TOKEN_PATH = SECRETS_DIR / "mixcloud.json"

REDIRECT_HOST = "localhost"
REDIRECT_PORT = 8765
REDIRECT_PATH = "/callback"
REDIRECT_URI = f"http://{REDIRECT_HOST}:{REDIRECT_PORT}{REDIRECT_PATH}"

OAUTH_AUTHORIZE = "https://www.mixcloud.com/oauth/authorize/"
OAUTH_TOKEN = "https://www.mixcloud.com/oauth/access_token/"

_TIMEOUT = 15


class MixcloudAuthError(Exception):
    """OAuth or token exchange failed."""


class MixcloudAPIError(Exception):
    """A Mixcloud API call returned a non-success status."""


def _ensure_dir(dir_path):
    """Create the directory with mode 700 (and fix mode if it already exists)."""
    Path(dir_path).mkdir(mode=0o700, exist_ok=True, parents=True)
    os.chmod(dir_path, 0o700)


def load_app_credentials(path=APP_CRED_PATH):
    """Return (client_id, client_secret). Raises FileNotFoundError if not set up."""
    if not Path(path).exists():
        raise FileNotFoundError(f"Mixcloud app credentials not found at {path}")
    data = json.loads(Path(path).read_text())
    return data["client_id"], data["client_secret"]


def save_app_credentials(client_id, client_secret, path=APP_CRED_PATH):
    path = Path(path)
    _ensure_dir(path.parent)
    path.write_text(json.dumps({"client_id": client_id, "client_secret": client_secret}))
    os.chmod(path, 0o600)


def load_token(path=TOKEN_PATH):
    """Return the saved access_token string, or None if not yet saved."""
    if not Path(path).exists():
        return None
    return json.loads(Path(path).read_text()).get("access_token")


def save_token(path, access_token):
    path = Path(path)
    _ensure_dir(path.parent)
    path.write_text(json.dumps({"access_token": access_token}))
    os.chmod(path, 0o600)


def build_authorize_url(client_id, redirect_uri=REDIRECT_URI):
    params = {
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
    }
    return OAUTH_AUTHORIZE + "?" + urllib.parse.urlencode(params)


def exchange_code_for_token(client_id, client_secret, redirect_uri, code):
    """Exchange an OAuth authorization code for an access token. Raises MixcloudAuthError on failure."""
    params = {
        "client_id": client_id,
        "client_secret": client_secret,
        "redirect_uri": redirect_uri,
        "code": code,
    }
    resp = requests.post(OAUTH_TOKEN, params=params, timeout=_TIMEOUT)
    if resp.status_code != 200:
        raise MixcloudAuthError(
            f"Token exchange failed: HTTP {resp.status_code} — {resp.text[:200]}"
        )
    body = resp.json()
    if "access_token" not in body:
        raise MixcloudAuthError(f"Token exchange returned no access_token: {body}")
    return body["access_token"]


# --- OAuth browser flow (NOT unit-tested; verified in manual smoke test) ---

class _CallbackHandler(http.server.BaseHTTPRequestHandler):
    captured_code = None
    captured_error = None

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path != REDIRECT_PATH:
            self.send_response(404)
            self.end_headers()
            return
        qs = urllib.parse.parse_qs(parsed.query)
        if "code" in qs:
            _CallbackHandler.captured_code = qs["code"][0]
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write(b"<h1>Mixcloud connected.</h1><p>You can close this tab.</p>")
        else:
            _CallbackHandler.captured_error = qs.get("error", ["unknown"])[0]
            self.send_response(400)
            self.end_headers()

    def log_message(self, *args, **kwargs):  # silence stderr noise
        pass


def run_oauth_flow(client_id, client_secret):
    """Open browser, run local HTTP listener, return access_token. Blocking."""
    _CallbackHandler.captured_code = None
    _CallbackHandler.captured_error = None
    server = http.server.HTTPServer((REDIRECT_HOST, REDIRECT_PORT), _CallbackHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        url = build_authorize_url(client_id)
        print(f"\nOpening browser to authorize this app with Mixcloud...\n  {url}\n")
        webbrowser.open(url)
        # Wait for the handler to capture either code or error
        while _CallbackHandler.captured_code is None and _CallbackHandler.captured_error is None:
            time.sleep(0.1)
    finally:
        server.shutdown()

    if _CallbackHandler.captured_error:
        raise MixcloudAuthError(f"OAuth error: {_CallbackHandler.captured_error}")
    return exchange_code_for_token(
        client_id, client_secret, REDIRECT_URI, _CallbackHandler.captured_code
    )


def ensure_token(prompt_for_app_creds_fn=None):
    """Return a valid access token, running OAuth if needed.

    prompt_for_app_creds_fn() -> (client_id, client_secret), called interactively
    if no app credentials are saved yet. Pass None to raise instead of prompting.
    """
    try:
        client_id, client_secret = load_app_credentials()
    except FileNotFoundError:
        if prompt_for_app_creds_fn is None:
            raise
        client_id, client_secret = prompt_for_app_creds_fn()
        save_app_credentials(client_id, client_secret)

    token = load_token()
    if token:
        return token

    token = run_oauth_flow(client_id, client_secret)
    save_token(TOKEN_PATH, token)
    return token
```

- [ ] **Step 4: Run tests, confirm they pass**

Run: `python3 tests/run_all.py`

Expected: all `test_mixcloud_client` tests PASS.

- [ ] **Step 5: Commit**

```
git add mixcloud_client.py tests/test_mixcloud_client.py
git commit -m "feat: mixcloud_client OAuth flow + credential storage"
```

---

### Task 9: `mixcloud_client.py` — list cloudcasts + update cloudcast

**Files:**
- Modify: `/Users/waterhousestudios/Desktop/TRACK ID PROJECT/mixcloud_client.py` (append new functions)
- Modify: `/Users/waterhousestudios/Desktop/TRACK ID PROJECT/tests/test_mixcloud_client.py` (append new tests)

- [ ] **Step 1: Append failing tests**

Append to `tests/test_mixcloud_client.py`:

```python
from timestamp_builder import Chapter


def _chap(secs, artist, title):
    return Chapter(
        time_seconds=secs, time_str=f"{secs//60}:{secs%60:02d}",
        artist=artist, title=title,
    )


def test_get_me_returns_username():
    resp = _resp(200, {"username": "the_dj", "name": "The DJ"})
    with patch.object(mixcloud_client.requests, "get", return_value=resp):
        assert mixcloud_client.get_me("tok") == "the_dj"


def test_get_me_401_raises_auth_error():
    resp = _resp(401)
    with patch.object(mixcloud_client.requests, "get", return_value=resp):
        try:
            mixcloud_client.get_me("expired-token")
        except mixcloud_client.MixcloudAuthError:
            return
    raise AssertionError("Expected MixcloudAuthError on 401")


def test_latest_cloudcast_picks_first():
    resp = _resp(200, {
        "data": [
            {"slug": "newest-stream", "name": "Stream 2026-05-17", "created_time": "2026-05-17T22:00:00Z"},
            {"slug": "older", "name": "Older", "created_time": "2026-05-15T22:00:00Z"},
        ]
    })
    with patch.object(mixcloud_client.requests, "get", return_value=resp):
        cc = mixcloud_client.latest_cloudcast("tok", username="the_dj")
    assert cc["slug"] == "newest-stream"


def test_latest_cloudcast_none_found_raises():
    resp = _resp(200, {"data": []})
    with patch.object(mixcloud_client.requests, "get", return_value=resp):
        try:
            mixcloud_client.latest_cloudcast("tok", username="the_dj")
        except mixcloud_client.MixcloudAPIError:
            return
    raise AssertionError("Expected MixcloudAPIError")


def test_update_cloudcast_sends_form_fields():
    chapters = [
        _chap(0, "Intro", "Intro"),
        _chap(323, "Anthony Naples", "Crystals"),
        _chap(767, "Joy Orbison", "Hyph Mngo"),
    ]
    resp = _resp(200, {"result": {"success": True}})
    with patch.object(mixcloud_client.requests, "post", return_value=resp) as p:
        mixcloud_client.update_cloudcast(
            token="tok", username="the_dj", slug="my-stream",
            description="hello world", chapters=chapters,
        )
    args, kwargs = p.call_args
    # The POST body should contain description and indexed section fields
    data = kwargs["data"]
    assert data["description"] == "hello world"
    assert data["sections-0-start_time"] == 0
    assert data["sections-0-artist_name"] == "Intro"
    assert data["sections-0-song_name"] == "Intro"
    assert data["sections-1-start_time"] == 323
    assert data["sections-1-artist_name"] == "Anthony Naples"
    assert data["sections-1-song_name"] == "Crystals"
    assert data["sections-2-start_time"] == 767
    # And the URL should be the edit endpoint with the access token
    posted_url = args[0]
    assert "/upload/the_dj/my-stream/edit/" in posted_url
    assert "access_token=tok" in posted_url


def test_update_cloudcast_403_raises_specific_error():
    resp = _resp(403, text="Forbidden")
    with patch.object(mixcloud_client.requests, "post", return_value=resp):
        try:
            mixcloud_client.update_cloudcast(
                token="tok", username="the_dj", slug="x",
                description="hi", chapters=[_chap(0, "I", "I")],
            )
        except mixcloud_client.MixcloudAPIError as e:
            assert "403" in str(e)
            return
    raise AssertionError("Expected MixcloudAPIError on 403")


def test_update_cloudcast_401_raises_auth_error():
    resp = _resp(401, text="Unauthorized")
    with patch.object(mixcloud_client.requests, "post", return_value=resp):
        try:
            mixcloud_client.update_cloudcast(
                token="tok", username="the_dj", slug="x",
                description="hi", chapters=[_chap(0, "I", "I")],
            )
        except mixcloud_client.MixcloudAuthError:
            return
    raise AssertionError("Expected MixcloudAuthError on 401")
```

- [ ] **Step 2: Run tests, confirm they fail**

Run: `python3 tests/run_all.py`

Expected: ERROR on each new `test_mixcloud_client` test (`get_me`, `latest_cloudcast`, `update_cloudcast` not yet defined).

- [ ] **Step 3: Append implementation to `mixcloud_client.py`**

Append (at the bottom of `mixcloud_client.py`):

```python
# --- Cloudcast operations ---

API_BASE = "https://api.mixcloud.com"


def get_me(token):
    """Return the authenticated username. Raises MixcloudAuthError on 401."""
    resp = requests.get(f"{API_BASE}/me/", params={"access_token": token}, timeout=_TIMEOUT)
    if resp.status_code == 401:
        raise MixcloudAuthError("Mixcloud token invalid or expired (401)")
    if resp.status_code != 200:
        raise MixcloudAPIError(f"GET /me/ failed: HTTP {resp.status_code}")
    return resp.json()["username"]


def latest_cloudcast(token, username=None):
    """Return the dict for the user's most recent cloudcast.

    If username is None, calls get_me() first.
    Raises MixcloudAPIError if no cloudcasts exist.
    """
    if username is None:
        username = get_me(token)
    resp = requests.get(
        f"{API_BASE}/{username}/cloudcasts/",
        params={"access_token": token, "limit": 5},
        timeout=_TIMEOUT,
    )
    if resp.status_code == 401:
        raise MixcloudAuthError("Mixcloud token invalid or expired (401)")
    if resp.status_code != 200:
        raise MixcloudAPIError(f"List cloudcasts failed: HTTP {resp.status_code}")
    data = resp.json().get("data", [])
    if not data:
        raise MixcloudAPIError(f"No cloudcasts found for user {username}")
    return data[0]  # Mixcloud returns most-recent first


def update_cloudcast(token, username, slug, description, chapters):
    """Edit a cloudcast's description and tracklist sections via the Mixcloud upload edit endpoint.

    Raises MixcloudAuthError on 401, MixcloudAPIError on 403 (typically: not Pro) or other failures.
    """
    url = f"{API_BASE}/upload/{username}/{slug}/edit/?access_token={token}"
    form = {"description": description}
    for i, ch in enumerate(chapters):
        form[f"sections-{i}-start_time"] = ch.time_seconds
        form[f"sections-{i}-artist_name"] = ch.artist
        form[f"sections-{i}-song_name"] = ch.title

    resp = requests.post(url, data=form, timeout=_TIMEOUT)
    if resp.status_code == 401:
        raise MixcloudAuthError("Mixcloud token invalid or expired (401)")
    if resp.status_code == 403:
        raise MixcloudAPIError(
            f"Mixcloud refused edit (403). Most common cause: account is not Pro. Detail: {resp.text[:200]}"
        )
    if resp.status_code not in (200, 201):
        raise MixcloudAPIError(f"Update cloudcast failed: HTTP {resp.status_code} — {resp.text[:200]}")
    return resp.json() if resp.text else {}
```

- [ ] **Step 4: Run tests, confirm they pass**

Run: `python3 tests/run_all.py`

Expected: all `test_mixcloud_client` tests PASS.

- [ ] **Step 5: Commit**

```
git add mixcloud_client.py tests/test_mixcloud_client.py
git commit -m "feat: mixcloud_client list cloudcasts + edit cloudcast description/sections"
```

---

### Task 10: `post_tracklist.py` — the orchestrator

**Files:**
- Create: `/Users/waterhousestudios/Desktop/TRACK ID PROJECT/post_tracklist.py`
- Create: `/Users/waterhousestudios/Desktop/TRACK ID PROJECT/tests/test_post_tracklist_integration.py`

- [ ] **Step 1: Write failing integration test**

Save to `tests/test_post_tracklist_integration.py`:

```python
import sys
import tempfile
from datetime import datetime
from pathlib import Path
from unittest.mock import patch, MagicMock

sys.path.insert(0, str(Path(__file__).parent.parent))

import post_tracklist


SAMPLE_LOG = """\
─── Session started 2026-05-17 21:30:00 ───
21:30:05  [Player 3]  Anthony Naples — Crystals
21:35:23  [Player 1]  Joy Orbison — Hyph Mngo
21:35:28  [Player 1]  ShortBlip — Skip Me
21:42:47  [Player 3]  Pearson Sound — Blanked
"""


def _setup_dirs(tmp):
    movies = Path(tmp) / "Movies"
    movies.mkdir()
    (movies / "2026-05-17 21-30-00.mov").write_bytes(b"")
    log = Path(tmp) / "tracklist_live.txt"
    log.write_text(SAMPLE_LOG)
    return movies, log


def test_dry_run_does_no_writes():
    with tempfile.TemporaryDirectory() as tmp:
        movies, log = _setup_dirs(tmp)
        with patch.object(post_tracklist, "discogs_lookup", return_value="discogs.com/release/1"), \
             patch.object(post_tracklist, "songlink_url", return_value="https://song.link/i/x"), \
             patch.object(post_tracklist, "copy_to_clipboard") as cb, \
             patch.object(post_tracklist, "notify"), \
             patch.object(post_tracklist, "ensure_token", return_value="tok"), \
             patch.object(post_tracklist, "get_me", return_value="the_dj"), \
             patch.object(post_tracklist, "latest_cloudcast", return_value={"slug": "stream"}), \
             patch.object(post_tracklist, "update_cloudcast") as upd, \
             patch.object(post_tracklist.time, "sleep"):
            rc = post_tracklist.main([
                "--movie", str(movies / "2026-05-17 21-30-00.mov"),
                "--log", str(log),
                "--dry-run",
            ])
        assert rc == 0
        cb.assert_not_called()
        upd.assert_not_called()


def test_normal_run_calls_clipboard_and_mixcloud():
    with tempfile.TemporaryDirectory() as tmp:
        movies, log = _setup_dirs(tmp)
        with patch.object(post_tracklist, "discogs_lookup", return_value="discogs.com/release/1"), \
             patch.object(post_tracklist, "songlink_url", return_value="https://song.link/i/x"), \
             patch.object(post_tracklist, "copy_to_clipboard") as cb, \
             patch.object(post_tracklist, "notify"), \
             patch.object(post_tracklist, "ensure_token", return_value="tok"), \
             patch.object(post_tracklist, "get_me", return_value="the_dj"), \
             patch.object(post_tracklist, "latest_cloudcast", return_value={"slug": "stream", "name": "Live"}), \
             patch.object(post_tracklist, "update_cloudcast") as upd, \
             patch.object(post_tracklist.time, "sleep"):
            rc = post_tracklist.main([
                "--movie", str(movies / "2026-05-17 21-30-00.mov"),
                "--log", str(log),
            ])
        assert rc == 0
        cb.assert_called_once()
        upd.assert_called_once()
        clip_text = cb.call_args[0][0]
        # The short "ShortBlip" track should NOT appear (5s as master)
        assert "ShortBlip" not in clip_text
        # Real tracks should appear with the correct https-prefixed Discogs URL
        assert "Anthony Naples" in clip_text
        assert "https://discogs.com/release/1" in clip_text
        assert "https://song.link/i/x" in clip_text


def test_skip_mixcloud_flag():
    with tempfile.TemporaryDirectory() as tmp:
        movies, log = _setup_dirs(tmp)
        with patch.object(post_tracklist, "discogs_lookup", return_value=""), \
             patch.object(post_tracklist, "songlink_url", return_value=""), \
             patch.object(post_tracklist, "copy_to_clipboard") as cb, \
             patch.object(post_tracklist, "notify"), \
             patch.object(post_tracklist, "update_cloudcast") as upd, \
             patch.object(post_tracklist.time, "sleep"):
            rc = post_tracklist.main([
                "--movie", str(movies / "2026-05-17 21-30-00.mov"),
                "--log", str(log),
                "--skip-mixcloud",
            ])
        assert rc == 0
        cb.assert_called_once()
        upd.assert_not_called()


def test_mixcloud_403_still_runs_clipboard():
    from mixcloud_client import MixcloudAPIError
    with tempfile.TemporaryDirectory() as tmp:
        movies, log = _setup_dirs(tmp)
        with patch.object(post_tracklist, "discogs_lookup", return_value=""), \
             patch.object(post_tracklist, "songlink_url", return_value=""), \
             patch.object(post_tracklist, "copy_to_clipboard") as cb, \
             patch.object(post_tracklist, "notify"), \
             patch.object(post_tracklist, "ensure_token", return_value="tok"), \
             patch.object(post_tracklist, "get_me", return_value="the_dj"), \
             patch.object(post_tracklist, "latest_cloudcast", return_value={"slug": "stream"}), \
             patch.object(post_tracklist, "update_cloudcast", side_effect=MixcloudAPIError("403 not Pro")), \
             patch.object(post_tracklist.time, "sleep"):
            rc = post_tracklist.main([
                "--movie", str(movies / "2026-05-17 21-30-00.mov"),
                "--log", str(log),
            ])
        # Partial success still returns 0
        assert rc == 0
        cb.assert_called_once()


def test_missing_movie_returns_2():
    with tempfile.TemporaryDirectory() as tmp:
        movies, log = _setup_dirs(tmp)
        with patch.object(post_tracklist, "copy_to_clipboard") as cb:
            rc = post_tracklist.main([
                "--movie", str(Path(tmp) / "does_not_exist.mov"),
                "--log", str(log),
            ])
        assert rc == 2
        cb.assert_not_called()


def test_empty_log_returns_2():
    with tempfile.TemporaryDirectory() as tmp:
        movies, log = _setup_dirs(tmp)
        log.write_text("")
        with patch.object(post_tracklist, "copy_to_clipboard") as cb:
            rc = post_tracklist.main([
                "--movie", str(movies / "2026-05-17 21-30-00.mov"),
                "--log", str(log),
            ])
        assert rc == 2
        cb.assert_not_called()
```

- [ ] **Step 2: Run tests, confirm they fail**

Run: `python3 tests/run_all.py`

Expected: ERROR on each `test_post_tracklist_integration` test.

- [ ] **Step 3: Implement `post_tracklist.py`**

Save to `/Users/waterhousestudios/Desktop/TRACK ID PROJECT/post_tracklist.py`:

```python
#!/usr/bin/env python3
"""
Post-stream tracklist publisher.

Pipeline:
  1. Find latest OBS recording in ~/Movies (or --movie) -> stream_start datetime
  2. Read ~/Desktop/tracklist_live.txt (or --log), pick latest session (or --session)
  3. Filter tracks with master-duration < 30s
  4. Build chapters relative to stream_start (with 0:00 Intro rules)
  5. For each chapter: look up Discogs + Songlink (paced)
  6. Update Mixcloud cloudcast (description + sections) unless --skip-mixcloud
  7. Copy YouTube-formatted description to clipboard unless --skip-youtube
  8. Show macOS notification with result
"""

import argparse
import os
import sys
import time
from datetime import datetime
from pathlib import Path

from tracklist_parser import parse_log
from tracklist_lookup import discogs_lookup

from stream_anchor import find_latest_movie
from track_filter import filter_short_tracks
from timestamp_builder import build_chapters
from songlink_lookup import songlink_url
from youtube_formatter import format_youtube
from clipboard_and_notify import copy_to_clipboard, notify
from mixcloud_client import (
    ensure_token, get_me, latest_cloudcast, update_cloudcast,
    MixcloudAuthError, MixcloudAPIError,
)

DEFAULT_LOG = "~/Desktop/tracklist_live.txt"
DEFAULT_MOVIES = "~/Movies"

# Per-track pacing: total ~7s between consecutive track lookups, which keeps us under
# Songlink's ~10 req/min limit (the strictest of the three APIs we call per track).
SLEEP_BETWEEN_TRACKS = 7.0


def _prompt_mixcloud_app_creds():
    print("\nFirst-time Mixcloud setup:")
    print("  1. Go to https://www.mixcloud.com/developers/create/")
    print("  2. Create an app with redirect URI: http://localhost:8765/callback")
    print("  3. Copy the Client ID and Client Secret it gives you.")
    cid = input("\nClient ID: ").strip()
    secret = input("Client Secret: ").strip()
    return cid, secret


def _resolve_movie_path(arg):
    if arg:
        p = Path(os.path.expanduser(arg))
        if not p.is_file():
            raise FileNotFoundError(f"Movie file not found: {p}")
        # Try to parse the timestamp from the filename
        from stream_anchor import _FILENAME_PATTERN
        m = _FILENAME_PATTERN.match(p.name)
        if not m:
            raise ValueError(f"Filename does not match expected pattern YYYY-MM-DD HH-MM-SS.mov: {p.name}")
        date_str, hh, mm, ss = m.groups()
        ts = datetime.strptime(f"{date_str} {hh}:{mm}:{ss}", "%Y-%m-%d %H:%M:%S")
        return p, ts
    return find_latest_movie(DEFAULT_MOVIES)


def _enrich_chapters(chapters):
    """Mutate chapters list in place, filling discogs_url and songlink_url.

    Paces 7s between consecutive track lookups (no sleep before the first track).
    This keeps us under Songlink's ~10 req/min limit. Discogs and iTunes are
    less strict and well within budget at this rate.
    """
    first_real = True
    for i, ch in enumerate(chapters):
        if ch.artist == "Intro" or ch.artist == "Unknown Artist":
            continue
        if not first_real:
            time.sleep(SLEEP_BETWEEN_TRACKS)
        first_real = False
        print(f"  [{i+1}/{len(chapters)}] {ch.artist} — {ch.title}", file=sys.stderr)
        ch.discogs_url = discogs_lookup(ch.artist, ch.title)
        ch.songlink_url = songlink_url(ch.artist, ch.title)


def _post_to_mixcloud(token, slug_override, description, chapters):
    """Returns (success: bool, message: str)."""
    try:
        username = get_me(token)
        if slug_override:
            slug = slug_override
            cloudcast_name = slug_override
        else:
            cc = latest_cloudcast(token, username=username)
            slug = cc["slug"]
            cloudcast_name = cc.get("name", slug)
        print(f"  Targeting Mixcloud cloudcast: {cloudcast_name}", file=sys.stderr)
        update_cloudcast(token, username, slug, description, chapters)
        return True, f"Posted to Mixcloud: {cloudcast_name}"
    except MixcloudAuthError as e:
        return False, f"Mixcloud auth failed: {e}"
    except MixcloudAPIError as e:
        return False, f"Mixcloud API error: {e}"


def main(argv=None):
    parser = argparse.ArgumentParser(description="Post timestamped tracklist to Mixcloud + YouTube clipboard.")
    parser.add_argument("--movie", help="Path to OBS recording (default: newest in ~/Movies)")
    parser.add_argument("--cloudcast", help="Override Mixcloud cloudcast slug")
    parser.add_argument("--log", default=DEFAULT_LOG, help="Path to tracklist_live.txt")
    parser.add_argument("--session", type=int, default=None, help="Session number (1-based); default last")
    parser.add_argument("--dry-run", action="store_true", help="Build everything but post/copy nothing")
    parser.add_argument("--skip-mixcloud", action="store_true")
    parser.add_argument("--skip-youtube", action="store_true")
    args = parser.parse_args(argv)

    # 1. Find recording -> stream_start
    try:
        movie_path, stream_start = _resolve_movie_path(args.movie)
    except FileNotFoundError as e:
        print(f"Error: {e}\n"
              f"Hint: pass --movie /path/to/file.mov to override.", file=sys.stderr)
        return 2
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 2
    print(f"Stream start: {stream_start.isoformat()} (from {movie_path.name})", file=sys.stderr)

    # 2. Read log -> session -> tracks
    log_path = Path(os.path.expanduser(args.log))
    if not log_path.exists():
        print(f"Error: log file not found at {log_path}\n"
              f"Was Beat Link Trigger open during the stream?", file=sys.stderr)
        return 2
    sessions = parse_log(log_path.read_text())
    if not sessions:
        print(f"Error: no sessions found in {log_path}\n"
              f"Was Beat Link Trigger open during the stream?", file=sys.stderr)
        return 2
    idx = -1 if args.session is None else args.session - 1
    try:
        session = sessions[idx]
    except IndexError:
        print(f"Error: session {args.session} not found (file has {len(sessions)})", file=sys.stderr)
        return 2

    # 3. Filter short tracks
    before = len(session.tracks)
    kept = filter_short_tracks(session.tracks, min_seconds=30)
    print(f"Filtered {before - len(kept)} short tracks (< 30s).", file=sys.stderr)

    # 4. Build chapters
    chapters = build_chapters(kept, stream_start)
    if not chapters:
        print("Error: No tracks survived filtering. Nothing to post.", file=sys.stderr)
        return 2

    # 5. Enrich with links (skip on dry-run to keep fast)
    if not args.dry_run:
        print(f"Looking up links for {len(chapters)} chapters...", file=sys.stderr)
        _enrich_chapters(chapters)

    # 6. Build YouTube description
    description = format_youtube(chapters, stream_start.date())

    if args.dry_run:
        print("\n--- DRY RUN: description that would be used ---\n", file=sys.stderr)
        print(description)
        print("\n--- end dry run ---", file=sys.stderr)
        return 0

    # 7. Mixcloud
    mc_message = "(Mixcloud skipped via flag)"
    mc_ok = True
    if not args.skip_mixcloud:
        try:
            token = ensure_token(prompt_for_app_creds_fn=_prompt_mixcloud_app_creds)
        except Exception as e:
            mc_ok = False
            mc_message = f"Mixcloud setup failed: {e}"
            token = None
        if token:
            mc_ok, mc_message = _post_to_mixcloud(token, args.cloudcast, description, chapters)
            # On 401, the OAuth helper would have raised; mixcloud_client emits a clear message.
            # We do not auto-retry OAuth here; user re-runs once they've re-authed.

    # 8. YouTube clipboard
    yt_message = "(YouTube clipboard skipped via flag)"
    if not args.skip_youtube:
        try:
            copy_to_clipboard(description)
            yt_message = "YouTube description copied to clipboard"
        except Exception as e:
            print(description)  # fallback to stdout
            yt_message = f"Clipboard failed: {e} (description printed above)"

    # 9. Notify
    summary_title = "✅ Tracklist posted" if mc_ok and not args.skip_mixcloud else "⚠️ Partial success"
    summary_body = f"{mc_message}. {yt_message}."
    print(f"\n{summary_title}\n{summary_body}", file=sys.stderr)
    try:
        notify(summary_title, summary_body)
    except Exception:
        pass

    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Run tests, confirm they pass**

Run: `python3 tests/run_all.py`

Expected: every test PASSes including the new integration tests. Existing `test_log_format.py` still passes too.

- [ ] **Step 5: Verify the `--dry-run` flag works against a synthetic log**

Run:
```
cd "$HOME/Desktop/TRACK ID PROJECT"
# Make a fake log + movie
mkdir -p /tmp/post_tl_test/Movies
touch "/tmp/post_tl_test/Movies/2026-05-17 21-30-00.mov"
cat > /tmp/post_tl_test/log.txt <<'EOF'
─── Session started 2026-05-17 21:30:00 ───
21:35:23  [Player 3]  Anthony Naples — Crystals
21:42:47  [Player 1]  Joy Orbison — Hyph Mngo
21:55:00  [Player 3]  Pearson Sound — Blanked
EOF
python3 post_tracklist.py \
  --movie "/tmp/post_tl_test/Movies/2026-05-17 21-30-00.mov" \
  --log /tmp/post_tl_test/log.txt \
  --dry-run
rm -rf /tmp/post_tl_test
```

Expected: prints the formatted description with `0:00 Intro`, three timestamped chapters, and the `Recorded live 2026-05-17.` footer. Exits cleanly with no network calls (Discogs/Songlink/Mixcloud are skipped in dry-run).

- [ ] **Step 6: Commit**

```
cd "$HOME/Desktop/TRACK ID PROJECT"
git add post_tracklist.py tests/test_post_tracklist_integration.py
git commit -m "feat: post_tracklist orchestrator wires all modules into one CLI"
```

---

### Task 11: Manual end-to-end smoke test + README update

**Files:**
- Modify: `/Users/waterhousestudios/Desktop/TRACK ID PROJECT/README.md`

This task validates the real OAuth flow and Mixcloud round-trip. It cannot be unit-tested.

- [ ] **Step 1: Create the Mixcloud app**

User actions (the implementer cannot do this for the user):

1. Go to `https://www.mixcloud.com/developers/create/`
2. Sign in if needed.
3. Click "Create an application."
4. Name: `Tracklist Auto-Post` (or anything).
5. Redirect URI: `http://localhost:8765/callback` — must match EXACTLY.
6. Save the app. Mixcloud displays a Client ID and Client Secret. Keep this page open.

- [ ] **Step 2: Run the script for the first time on a real post-stream state**

User actions:

1. Make sure there is a real `.mov` file in `~/Movies/` from a stream that has been uploaded to Mixcloud.
2. Make sure `~/Desktop/tracklist_live.txt` has tracks from that stream.
3. Open Terminal and run:
   ```
   python3 "$HOME/Desktop/TRACK ID PROJECT/post_tracklist.py" --dry-run
   ```
4. Verify the printed description looks right (timestamps, track names, intro line). If wrong, fix before continuing.

- [ ] **Step 3: First real run — triggers OAuth flow**

```
python3 "$HOME/Desktop/TRACK ID PROJECT/post_tracklist.py"
```

Expected behavior:
1. Script prints "First-time Mixcloud setup:" and instructions.
2. Prompts for Client ID — paste from Step 1.
3. Prompts for Client Secret — paste from Step 1.
4. Opens browser to Mixcloud's authorize page.
5. User clicks "Allow."
6. Browser shows "Mixcloud connected. You can close this tab."
7. Script proceeds to look up Discogs + Songlink for each track (~7s per track).
8. Updates the most recent cloudcast.
9. Copies the YouTube description to clipboard.
10. macOS notification appears.

If any step fails, the script prints a specific error. Common failure paths:
- Browser doesn't open → manually copy the URL from the script's output and paste into a browser.
- 403 from Mixcloud → verify the account is Pro (it is — confirmed during brainstorming).
- 401 from Mixcloud → delete `~/.tracklist_secrets/mixcloud.json` and re-run.

- [ ] **Step 4: Verify Mixcloud and YouTube side**

1. Open the just-updated cloudcast on Mixcloud in a browser. Confirm:
   - The description shows the formatted tracklist.
   - The cloudcast page shows clickable per-track timestamps (Mixcloud's native tracklist UI).
2. Paste the clipboard contents into the YouTube video description. Save.
3. After YouTube finishes processing the description, scrub the video — chapter markers should appear on the timeline.

- [ ] **Step 5: Update the project README**

Edit `/Users/waterhousestudios/Desktop/TRACK ID PROJECT/README.md`. At the bottom, replace the `## Step 2 (Not Done Yet)` section with:

```markdown
## Step 2 — Auto-Post to Mixcloud + YouTube (done 2026-05-17)

After each stream, run:

```
python3 "$HOME/Desktop/TRACK ID PROJECT/post_tracklist.py"
```

This:
1. Finds the newest `.mov` recording in `~/Movies/` to know when your stream started.
2. Reads `~/Desktop/tracklist_live.txt` (Step 1's output).
3. Filters out tracks that were master for less than 30 seconds.
4. Looks up Discogs + a Songlink universal URL for each track.
5. Posts a timestamped tracklist + description to your most recent **Mixcloud** cloudcast.
6. Copies a YouTube-chapter-formatted description to your clipboard — paste into YouTube Studio.

### First-time setup

The first time you run it, it walks you through:
1. Creating a Mixcloud app at `mixcloud.com/developers/create/` (Redirect URI: `http://localhost:8765/callback`). You paste the Client ID + Secret it gives you.
2. A browser OAuth login to grant the app access to your Mixcloud account.
3. Optional: pasting a Discogs token for faster lookups (free at `discogs.com/settings/developers`).

After that, every future run is one command.

### Flags

| Flag | Purpose |
|------|---------|
| `--movie PATH` | Override which recording's filename is used as t=0 |
| `--cloudcast SLUG` | Post to a specific cloudcast instead of the newest |
| `--log PATH` | Use a different tracklist log file |
| `--session N` | Pick a specific session from the log (default: latest) |
| `--dry-run` | Print what would post; don't touch Mixcloud or clipboard |
| `--skip-mixcloud` | Only build the YouTube clipboard |
| `--skip-youtube` | Only post to Mixcloud |

### Credentials

Live in `~/.tracklist_secrets/` (mode 700, files mode 600). Never commit this folder.
```

- [ ] **Step 6: Final test run**

Run: `python3 tests/run_all.py`

Expected: All tests still pass. (Total should be roughly 40+ across all `test_*.py` files.)

- [ ] **Step 7: Final commit**

```
cd "$HOME/Desktop/TRACK ID PROJECT"
git add README.md
git commit -m "docs: README updated for Step 2 (auto-post to Mixcloud + YouTube clipboard)"
```

---

## Done

When all 11 tasks pass, Step 2 is complete:

- Every stream's tracklist is one Terminal command away from being posted.
- Mixcloud cloudcasts get a clickable per-track timeline.
- YouTube descriptions get pasted-and-saved with chapter markers.
- Step 1 (BLT logging + `tracklist_format.py`) remains unmodified.
