# Label Outreach Subagent Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship a Claude Code subagent that reads the latest DJ set, finds each record label's contact email (Discogs → web search → LLM extract), drafts a per-label email via the Gmail MCP asking the label to whitelist `waterhousestudios` on YouTube Content ID, and returns a review table. The user reviews drafts in Gmail and sends manually.

**Architecture:** One subagent definition (`.claude/agents/label-emailer.md`) for the fuzzy LLM-driven work + one deterministic Python helper module (`label_outreach.py`) for parsing, Discogs lookups, and dedup-cache I/O. Subagent shells the helper for data; uses WebSearch/WebFetch for missing emails; calls `mcp__claude_ai_Gmail__create_draft` per label.

**Tech Stack:** Python 3.9+ (uses existing `requests`, `beautifulsoup4`), Claude Code subagent format, Gmail MCP server.

**Project note:** This project is NOT under git. Commit steps are omitted; replace with "save the file" — if the user later runs `git init`, future plans can resume the commit pattern.

**Spec:** `docs/superpowers/specs/2026-05-18-label-outreach-design.md`

---

## File Structure

**Create:**
- `label_outreach.py` — deterministic helpers + CLI entrypoint (~250 lines)
- `tests/test_label_outreach.py` — unit tests (~250 lines)
- `.claude/agents/label-emailer.md` — subagent definition + system prompt (~100 lines)

**Reuse (do not modify):**
- `tracklist_parser.py` — for `parse_log` and the `Track`/`Session` dataclasses
- `track_filter.py` — for `filter_short_tracks`
- `tracklist_lookup.py` — pattern reference for Discogs `requests` calls + 429 retry
- `mixcloud_client.py` — pattern reference for `~/.tracklist_secrets/` mode 700 dir + mode 600 files

**User-owned (NOT created by this plan — see Task 7):**
- `~/.tracklist_secrets/label_email_ask.txt` — user authors before first real run
- `~/.tracklist_secrets/contacted_labels.json` — created on first `save_contacted` call

---

## Task 1: Cache I/O — `load_contacted` and `save_contacted`

**Files:**
- Create: `label_outreach.py`
- Create: `tests/test_label_outreach.py`

- [ ] **Step 1.1: Write the failing tests**

Create `tests/test_label_outreach.py`:

```python
import json
import os
import stat
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import label_outreach


def test_load_contacted_returns_empty_set_when_file_missing():
    with tempfile.TemporaryDirectory() as d:
        result = label_outreach.load_contacted(Path(d) / "missing.json")
        assert result == set()


def test_load_contacted_returns_lowercase_normalized_names():
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "contacted.json"
        p.write_text(json.dumps({
            "labels": [
                {"name": "Hessle Audio", "name_normalized": "hessle audio",
                 "email": "info@hessleaudio.com",
                 "first_contacted": "2026-05-18T22:14:00",
                 "source": "discogs"},
                {"name": "Whities", "name_normalized": "whities",
                 "email": "hello@whities.uk",
                 "first_contacted": "2026-05-18T22:15:00",
                 "source": "websearch"},
            ]
        }))
        result = label_outreach.load_contacted(p)
        assert result == {"hessle audio", "whities"}


def test_save_contacted_creates_dir_mode_700():
    with tempfile.TemporaryDirectory() as d:
        secrets = Path(d) / "secrets"
        cache = secrets / "contacted.json"
        label_outreach.save_contacted(cache, [
            label_outreach.ContactedEntry(name="Hessle Audio",
                                          email="info@hessleaudio.com",
                                          source="discogs"),
        ])
        st = os.stat(secrets)
        assert stat.S_IMODE(st.st_mode) == 0o700


def test_save_contacted_creates_file_mode_600():
    with tempfile.TemporaryDirectory() as d:
        cache = Path(d) / "contacted.json"
        label_outreach.save_contacted(cache, [
            label_outreach.ContactedEntry(name="Hessle Audio",
                                          email="info@hessleaudio.com",
                                          source="discogs"),
        ])
        st = os.stat(cache)
        assert stat.S_IMODE(st.st_mode) == 0o600


def test_save_contacted_is_append_only():
    with tempfile.TemporaryDirectory() as d:
        cache = Path(d) / "contacted.json"
        label_outreach.save_contacted(cache, [
            label_outreach.ContactedEntry(name="Hessle Audio",
                                          email="info@hessleaudio.com",
                                          source="discogs"),
        ])
        label_outreach.save_contacted(cache, [
            label_outreach.ContactedEntry(name="Whities",
                                          email="hello@whities.uk",
                                          source="websearch"),
        ])
        data = json.loads(cache.read_text())
        names = [entry["name"] for entry in data["labels"]]
        assert names == ["Hessle Audio", "Whities"]


def test_save_contacted_writes_normalized_name_and_timestamp():
    with tempfile.TemporaryDirectory() as d:
        cache = Path(d) / "contacted.json"
        label_outreach.save_contacted(cache, [
            label_outreach.ContactedEntry(name="Hessle Audio",
                                          email="info@hessleaudio.com",
                                          source="discogs"),
        ])
        data = json.loads(cache.read_text())
        entry = data["labels"][0]
        assert entry["name_normalized"] == "hessle audio"
        assert "first_contacted" in entry
        assert entry["first_contacted"].startswith("20")  # ISO timestamp
```

- [ ] **Step 1.2: Run tests to verify they fail**

Run: `cd /Users/marko/Desktop/Track-ID-automation-main && python3 -m pytest tests/test_label_outreach.py -v 2>&1 | head -30`

Expected: All six tests ERROR with `ModuleNotFoundError: No module named 'label_outreach'`.

- [ ] **Step 1.3: Implement the cache helpers**

Create `label_outreach.py`:

```python
"""Deterministic helpers for label outreach: parsing, Discogs lookups, dedup cache."""
import json
import os
import tempfile
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path
from typing import Optional


@dataclass
class ContactedEntry:
    name: str
    email: str
    source: str  # "discogs" | "websearch" | "manual"


def _normalize(label: str) -> str:
    return label.strip().lower()


def load_contacted(cache_path: Path) -> set[str]:
    """Return the set of normalized label names that have already been contacted.

    Returns an empty set if the file does not exist. Reads `name_normalized` if
    present, otherwise normalizes `name`.
    """
    if not cache_path.exists():
        return set()
    data = json.loads(cache_path.read_text())
    out = set()
    for entry in data.get("labels", []):
        out.add(entry.get("name_normalized") or _normalize(entry["name"]))
    return out


def save_contacted(cache_path: Path, new_entries: list[ContactedEntry]) -> None:
    """Append new entries to the JSON cache, atomically.

    Creates parent dir mode 700 and file mode 600 if not already present.
    Preserves existing entries.
    """
    cache_path.parent.mkdir(mode=0o700, exist_ok=True, parents=True)
    os.chmod(cache_path.parent, 0o700)

    if cache_path.exists():
        data = json.loads(cache_path.read_text())
    else:
        data = {"labels": []}

    now_iso = datetime.now().isoformat(timespec="seconds")
    for entry in new_entries:
        data["labels"].append({
            "name": entry.name,
            "name_normalized": _normalize(entry.name),
            "email": entry.email,
            "first_contacted": now_iso,
            "source": entry.source,
        })

    # Atomic write: tmp file in same dir then rename
    fd, tmp_path = tempfile.mkstemp(prefix=".contacted_", dir=str(cache_path.parent))
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(data, f, indent=2)
        os.chmod(tmp_path, 0o600)
        os.replace(tmp_path, cache_path)
    except Exception:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)
        raise
```

- [ ] **Step 1.4: Run tests to verify they pass**

Run: `cd /Users/marko/Desktop/Track-ID-automation-main && python3 -m pytest tests/test_label_outreach.py -v`

Expected: 6 passed.

---

## Task 2: `parse_latest_session` — read the log, filter short tracks

**Files:**
- Modify: `label_outreach.py`
- Modify: `tests/test_label_outreach.py`

- [ ] **Step 2.1: Write the failing tests**

Append to `tests/test_label_outreach.py`:

```python
from datetime import datetime as _dt

_SAMPLE_LOG = """\
─── Session started 2026-05-17 20:00:00 ───
20:00:10  [Player 1]  Old Artist — Old Track
20:15:00  [Player 2]  Old Artist Two — Another

─── Session started 2026-05-17 21:30:00 ───
21:30:00  [Player 1]  Anthony Naples — Crystals
21:30:05  [Player 2]  Skipped Short — Too Brief
21:30:10  [Player 1]  Joy Orbison — Hyph Mngo
21:35:00  [Player 2]  Pearson Sound — Blanked
"""


def test_parse_latest_session_returns_last_session_only():
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "tracklist_live.txt"
        p.write_text(_SAMPLE_LOG)
        tracks = label_outreach.parse_latest_session(
            p, end_time=_dt(2026, 5, 17, 21, 45, 0)
        )
        artists = [t.artist for t in tracks]
        # "Skipped Short" lasted only 5s; "Old Artist"/"Old Artist Two" are
        # from the earlier session and must not appear.
        assert "Old Artist" not in artists
        assert "Old Artist Two" not in artists
        assert "Skipped Short" not in artists
        assert "Anthony Naples" in artists
        assert "Joy Orbison" in artists
        assert "Pearson Sound" in artists


def test_parse_latest_session_returns_empty_when_log_missing():
    with tempfile.TemporaryDirectory() as d:
        tracks = label_outreach.parse_latest_session(Path(d) / "missing.txt")
        assert tracks == []


def test_parse_latest_session_returns_empty_when_no_sessions():
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "tracklist_live.txt"
        p.write_text("some junk with no session header\n")
        tracks = label_outreach.parse_latest_session(p)
        assert tracks == []
```

- [ ] **Step 2.2: Run tests to verify they fail**

Run: `cd /Users/marko/Desktop/Track-ID-automation-main && python3 -m pytest tests/test_label_outreach.py::test_parse_latest_session_returns_last_session_only -v`

Expected: ERROR with `AttributeError: module 'label_outreach' has no attribute 'parse_latest_session'`.

- [ ] **Step 2.3: Implement `parse_latest_session`**

Append to `label_outreach.py` (add imports at top of file):

```python
# Add to imports at top of file:
import tracklist_parser
import track_filter


def parse_latest_session(log_path: Path, end_time: Optional[datetime] = None):
    """Return the most recent session's tracks, filtered to those that were
    master for at least 30 seconds.

    Args:
        log_path: Path to tracklist_live.txt.
        end_time: Used to compute the duration of the LAST track (which has no
            "next" track to bound it). Defaults to datetime.now() inside
            track_filter.filter_short_tracks.

    Returns:
        A list of tracklist_parser.Track. Empty if file missing or no sessions.
    """
    if not log_path.exists():
        return []
    sessions = tracklist_parser.parse_log(log_path.read_text())
    if not sessions:
        return []
    latest = sessions[-1]
    return track_filter.filter_short_tracks(latest.tracks, min_seconds=30, end_time=end_time)
```

- [ ] **Step 2.4: Run tests to verify they pass**

Run: `cd /Users/marko/Desktop/Track-ID-automation-main && python3 -m pytest tests/test_label_outreach.py -v`

Expected: 9 passed (6 from Task 1 + 3 new).

---

## Task 3: `group_by_label` — Discogs lookups + email regex on `contactinfo`

**Files:**
- Modify: `label_outreach.py`
- Modify: `tests/test_label_outreach.py`

- [ ] **Step 3.1: Write the failing tests**

Append to `tests/test_label_outreach.py`:

```python
from unittest.mock import patch, MagicMock


def _make_track(artist: str, title: str) -> "tracklist_parser.Track":
    import tracklist_parser
    from datetime import timedelta
    return tracklist_parser.Track(
        wall_time=_dt(2026, 5, 17, 21, 30, 0),
        relative_time=timedelta(0),
        player="Player 1",
        artist=artist,
        title=title,
    )


def _resp(status, json_body=None):
    r = MagicMock()
    r.status_code = status
    r.json.return_value = json_body if json_body is not None else {}
    return r


def test_group_by_label_groups_tracks_under_their_label():
    tracks = [
        _make_track("Pearson Sound", "Blanked"),
        _make_track("Joy Orbison", "Hyph Mngo"),
    ]

    def fake_get(url, params=None, headers=None, timeout=None):
        if "/database/search" in url:
            q = (params or {}).get("q", "")
            if "Pearson Sound" in q:
                return _resp(200, {"results": [{"id": 100}]})
            if "Joy Orbison" in q:
                return _resp(200, {"results": [{"id": 200}]})
        if url.endswith("/releases/100"):
            return _resp(200, {"labels": [{"id": 10, "name": "Hessle Audio"}]})
        if url.endswith("/releases/200"):
            return _resp(200, {"labels": [{"id": 20, "name": "Hotflush"}]})
        if url.endswith("/labels/10"):
            return _resp(200, {"contactinfo": "Email: info@hessleaudio.com"})
        if url.endswith("/labels/20"):
            return _resp(200, {"contactinfo": "PO Box 123, London"})
        return _resp(404)

    with patch("label_outreach.requests.get", side_effect=fake_get):
        groups = label_outreach.group_by_label(tracks, discogs_token=None)

    assert set(groups.keys()) == {"Hessle Audio", "Hotflush"}
    assert groups["Hessle Audio"].discogs_contact_email == "info@hessleaudio.com"
    assert groups["Hotflush"].discogs_contact_email == ""
    assert groups["Hessle Audio"].tracks[0].artist == "Pearson Sound"
    assert groups["Hotflush"].tracks[0].artist == "Joy Orbison"


def test_group_by_label_dedups_discogs_calls_for_repeated_tracks():
    tracks = [
        _make_track("Pearson Sound", "Blanked"),
        _make_track("Pearson Sound", "Blanked"),
        _make_track("Pearson Sound", "Blanked"),
    ]

    calls = {"search": 0, "release": 0, "label": 0}

    def fake_get(url, params=None, headers=None, timeout=None):
        if "/database/search" in url:
            calls["search"] += 1
            return _resp(200, {"results": [{"id": 100}]})
        if url.endswith("/releases/100"):
            calls["release"] += 1
            return _resp(200, {"labels": [{"id": 10, "name": "Hessle Audio"}]})
        if url.endswith("/labels/10"):
            calls["label"] += 1
            return _resp(200, {"contactinfo": "info@hessleaudio.com"})
        return _resp(404)

    with patch("label_outreach.requests.get", side_effect=fake_get):
        groups = label_outreach.group_by_label(tracks, discogs_token=None)

    assert calls == {"search": 1, "release": 1, "label": 1}
    assert len(groups["Hessle Audio"].tracks) == 3


def test_group_by_label_drops_track_when_no_release_found():
    tracks = [_make_track("Unknown Artist", "Mystery Track")]

    def fake_get(url, params=None, headers=None, timeout=None):
        if "/database/search" in url:
            return _resp(200, {"results": []})
        return _resp(404)

    with patch("label_outreach.requests.get", side_effect=fake_get):
        groups = label_outreach.group_by_label(tracks, discogs_token=None)

    assert groups == {}


def test_group_by_label_drops_track_when_release_has_no_labels():
    tracks = [_make_track("Some Artist", "Some Title")]

    def fake_get(url, params=None, headers=None, timeout=None):
        if "/database/search" in url:
            return _resp(200, {"results": [{"id": 100}]})
        if url.endswith("/releases/100"):
            return _resp(200, {"labels": []})
        return _resp(404)

    with patch("label_outreach.requests.get", side_effect=fake_get):
        groups = label_outreach.group_by_label(tracks, discogs_token=None)

    assert groups == {}


def test_group_by_label_extracts_email_from_sentence():
    tracks = [_make_track("A", "T")]

    def fake_get(url, params=None, headers=None, timeout=None):
        if "/database/search" in url:
            return _resp(200, {"results": [{"id": 1}]})
        if url.endswith("/releases/1"):
            return _resp(200, {"labels": [{"id": 11, "name": "Label X"}]})
        if url.endswith("/labels/11"):
            return _resp(200, {"contactinfo":
                "For demos please write to demos@labelx.co.uk and we'll respond."})
        return _resp(404)

    with patch("label_outreach.requests.get", side_effect=fake_get):
        groups = label_outreach.group_by_label(tracks, discogs_token=None)

    assert groups["Label X"].discogs_contact_email == "demos@labelx.co.uk"


def test_group_by_label_handles_label_endpoint_failure():
    tracks = [_make_track("A", "T")]

    def fake_get(url, params=None, headers=None, timeout=None):
        if "/database/search" in url:
            return _resp(200, {"results": [{"id": 1}]})
        if url.endswith("/releases/1"):
            return _resp(200, {"labels": [{"id": 11, "name": "Label X"}]})
        if url.endswith("/labels/11"):
            return _resp(500)
        return _resp(404)

    with patch("label_outreach.requests.get", side_effect=fake_get):
        groups = label_outreach.group_by_label(tracks, discogs_token=None)

    assert "Label X" in groups
    assert groups["Label X"].discogs_contact_email == ""


def test_group_by_label_retries_once_on_429():
    tracks = [_make_track("A", "T")]
    call_count = {"n": 0}

    def fake_get(url, params=None, headers=None, timeout=None):
        if "/database/search" in url:
            call_count["n"] += 1
            if call_count["n"] == 1:
                return _resp(429)
            return _resp(200, {"results": [{"id": 1}]})
        if url.endswith("/releases/1"):
            return _resp(200, {"labels": [{"id": 11, "name": "Label X"}]})
        if url.endswith("/labels/11"):
            return _resp(200, {"contactinfo": "hi@labelx.co.uk"})
        return _resp(404)

    with patch("label_outreach.requests.get", side_effect=fake_get):
        with patch("label_outreach.time.sleep"):
            groups = label_outreach.group_by_label(tracks, discogs_token=None)

    assert "Label X" in groups
    assert call_count["n"] == 2
```

- [ ] **Step 3.2: Run tests to verify they fail**

Run: `cd /Users/marko/Desktop/Track-ID-automation-main && python3 -m pytest tests/test_label_outreach.py -v 2>&1 | tail -30`

Expected: 7 new tests ERROR (`AttributeError: module 'label_outreach' has no attribute 'group_by_label'`); the 9 from earlier tasks still PASS.

- [ ] **Step 3.3: Implement `group_by_label`**

Append to `label_outreach.py` (add `requests`, `re`, `time` to imports at top):

```python
# Add to imports at top of file:
import re
import time
import requests

_DISCOGS_SEARCH = "https://api.discogs.com/database/search"
_DISCOGS_RELEASE = "https://api.discogs.com/releases"
_DISCOGS_LABEL = "https://api.discogs.com/labels"
_USER_AGENT = "TracklistLabelOutreach/1.0"
_EMAIL_REGEX = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")


@dataclass
class LabelInfo:
    tracks: list  # list of tracklist_parser.Track
    discogs_label_id: int
    discogs_label_url: str
    discogs_contact_email: str  # "" if not found in contactinfo


def _discogs_get(url: str, params: dict, token: Optional[str]) -> Optional[dict]:
    """One Discogs GET with one 429-retry. Returns parsed JSON on 200, else None."""
    headers = {"User-Agent": _USER_AGENT}
    if token:
        headers["Authorization"] = f"Discogs token={token}"
    try:
        resp = requests.get(url, params=params, headers=headers, timeout=10)
        if resp.status_code == 429:
            time.sleep(1)
            resp = requests.get(url, params=params, headers=headers, timeout=10)
        if resp.status_code != 200:
            return None
        return resp.json()
    except Exception:
        return None


def _extract_email(text: str) -> str:
    if not text:
        return ""
    m = _EMAIL_REGEX.search(text)
    return m.group(0) if m else ""


def group_by_label(tracks: list, discogs_token: Optional[str]) -> dict:
    """For each unique (artist, title), resolve a Discogs release → label, then
    fetch the label's contactinfo and try to extract an email.

    Returns: {label_name: LabelInfo} (only labels that resolved).
    Tracks that don't resolve to a release-with-labels are silently dropped.

    Network behavior: one 429-retry per call (matches tracklist_lookup.py).
    In-memory dedup ensures repeated (artist, title) pairs hit Discogs once.
    """
    # Cache by (artist, title) → release_id (or None)
    release_cache: dict[tuple, Optional[int]] = {}
    # Cache by release_id → (label_id, label_name) (or None)
    label_for_release: dict[int, Optional[tuple]] = {}
    # Cache by label_id → contactinfo text
    label_contactinfo: dict[int, str] = {}

    groups: dict[str, LabelInfo] = {}

    for track in tracks:
        key = (track.artist, track.title)

        if key not in release_cache:
            data = _discogs_get(
                _DISCOGS_SEARCH,
                {"q": f"{track.artist} {track.title}", "type": "release"},
                discogs_token,
            )
            results = (data or {}).get("results", [])
            release_cache[key] = results[0].get("id") if results else None

        release_id = release_cache[key]
        if release_id is None:
            continue

        if release_id not in label_for_release:
            data = _discogs_get(f"{_DISCOGS_RELEASE}/{release_id}", {}, discogs_token)
            labels = (data or {}).get("labels", []) if data else []
            if labels:
                label_for_release[release_id] = (labels[0].get("id"),
                                                 labels[0].get("name"))
            else:
                label_for_release[release_id] = None

        label_pair = label_for_release[release_id]
        if label_pair is None:
            continue

        label_id, label_name = label_pair
        if not label_name:
            continue

        if label_id not in label_contactinfo:
            data = _discogs_get(f"{_DISCOGS_LABEL}/{label_id}", {}, discogs_token)
            label_contactinfo[label_id] = (data or {}).get("contactinfo", "") if data else ""

        email = _extract_email(label_contactinfo[label_id])

        if label_name not in groups:
            groups[label_name] = LabelInfo(
                tracks=[],
                discogs_label_id=label_id,
                discogs_label_url=f"https://www.discogs.com/label/{label_id}",
                discogs_contact_email=email,
            )
        groups[label_name].tracks.append(track)

    return groups
```

- [ ] **Step 3.4: Run tests to verify they pass**

Run: `cd /Users/marko/Desktop/Track-ID-automation-main && python3 -m pytest tests/test_label_outreach.py -v`

Expected: 16 passed (9 + 7 new).

---

## Task 4: CLI entrypoint — `--action enrich` and `--action mark-contacted`

**Files:**
- Modify: `label_outreach.py`
- Modify: `tests/test_label_outreach.py`

- [ ] **Step 4.1: Write the failing tests**

Append to `tests/test_label_outreach.py`:

```python
import subprocess


_SAMPLE_LOG_SIMPLE = """\
─── Session started 2026-05-17 21:30:00 ───
21:30:00  [Player 1]  Pearson Sound — Blanked
21:35:00  [Player 2]  Joy Orbison — Hyph Mngo
"""


def _run_cli(args, env=None):
    proj_root = Path(__file__).parent.parent
    cmd = ["python3", str(proj_root / "label_outreach.py")] + args
    return subprocess.run(cmd, capture_output=True, text=True, env=env)


def test_cli_enrich_emits_json_for_new_labels(monkeypatch=None):
    # We patch group_by_label via env-driven stub: simpler is to call directly.
    # The CLI's network behavior is verified end-to-end via the unit tests on
    # group_by_label. Here we verify the CLI shape only, using a stub log
    # that won't actually find Discogs results (the test asserts on exit code
    # and JSON shape, accepting an empty result list as valid output).
    with tempfile.TemporaryDirectory() as d:
        log = Path(d) / "tracklist_live.txt"
        log.write_text(_SAMPLE_LOG_SIMPLE)
        cache = Path(d) / "contacted.json"

        # Run with a fake discogs token to skip auth; the network calls will fail
        # in CI / offline, so we don't assert on label content — only that the
        # CLI runs, prints valid JSON, and exits 0.
        result = _run_cli([
            "--action", "enrich",
            "--log", str(log),
            "--cache", str(cache),
            "--end-time", "2026-05-17T21:45:00",
        ])
        assert result.returncode == 0, f"stderr={result.stderr}"
        parsed = json.loads(result.stdout)
        assert isinstance(parsed, list)


def test_cli_enrich_exits_nonzero_when_log_missing():
    with tempfile.TemporaryDirectory() as d:
        result = _run_cli([
            "--action", "enrich",
            "--log", str(Path(d) / "does_not_exist.txt"),
            "--cache", str(Path(d) / "contacted.json"),
        ])
        assert result.returncode != 0
        assert "no session" in result.stderr.lower() or "missing" in result.stderr.lower()


def test_cli_mark_contacted_appends_entries():
    with tempfile.TemporaryDirectory() as d:
        cache = Path(d) / "contacted.json"
        result = _run_cli([
            "--action", "mark-contacted",
            "--cache", str(cache),
            "--labels", "Hessle Audio|info@hessleaudio.com,Whities|hello@whities.uk",
        ])
        assert result.returncode == 0, f"stderr={result.stderr}"
        data = json.loads(cache.read_text())
        names = [e["name"] for e in data["labels"]]
        assert names == ["Hessle Audio", "Whities"]
        sources = [e["source"] for e in data["labels"]]
        assert all(s == "websearch" for s in sources)  # default source for CLI


def test_cli_mark_contacted_creates_cache_if_missing():
    with tempfile.TemporaryDirectory() as d:
        cache = Path(d) / "subdir" / "contacted.json"
        result = _run_cli([
            "--action", "mark-contacted",
            "--cache", str(cache),
            "--labels", "Only Label|only@label.com",
        ])
        assert result.returncode == 0, f"stderr={result.stderr}"
        assert cache.exists()
```

- [ ] **Step 4.2: Run tests to verify they fail**

Run: `cd /Users/marko/Desktop/Track-ID-automation-main && python3 -m pytest tests/test_label_outreach.py -v -k "cli_" 2>&1 | tail -20`

Expected: 4 CLI tests fail (no `if __name__ == "__main__"` block yet, or the script runs without producing JSON).

- [ ] **Step 4.3: Implement the CLI**

Append to `label_outreach.py`:

```python
def _cli_enrich(log_path: Path, cache_path: Path, end_time: Optional[datetime]) -> int:
    """Return shell exit code. Emits JSON list to stdout."""
    import sys as _sys
    tracks = parse_latest_session(log_path, end_time=end_time)
    if not tracks:
        print("no session found in log", file=_sys.stderr)
        return 2

    already = load_contacted(cache_path)
    discogs_token = os.environ.get("DISCOGS_TOKEN") or None
    groups = group_by_label(tracks, discogs_token=discogs_token)

    out = []
    for label_name, info in groups.items():
        if _normalize(label_name) in already:
            continue
        out.append({
            "label": label_name,
            "tracks": [{"artist": t.artist, "title": t.title} for t in info.tracks],
            "discogs_label_url": info.discogs_label_url,
            "discogs_contact_email": info.discogs_contact_email,
        })

    print(json.dumps(out, indent=2))
    return 0


def _cli_mark_contacted(cache_path: Path, labels_arg: str) -> int:
    """`labels_arg` is "Name1|email1,Name2|email2,..." (commas separate pairs)."""
    entries = []
    for pair in labels_arg.split(","):
        pair = pair.strip()
        if not pair:
            continue
        if "|" not in pair:
            entries.append(ContactedEntry(name=pair, email="", source="websearch"))
            continue
        name, email = pair.split("|", 1)
        entries.append(ContactedEntry(
            name=name.strip(),
            email=email.strip(),
            source="websearch",
        ))
    save_contacted(cache_path, entries)
    return 0


def main(argv=None):
    import argparse
    p = argparse.ArgumentParser(description="Label outreach helper for the DJ tracklist pipeline.")
    p.add_argument("--action", required=True, choices=["enrich", "mark-contacted"])
    p.add_argument("--log", type=Path, help="Path to tracklist_live.txt (required for enrich)")
    p.add_argument("--cache", type=Path, required=True,
                   help="Path to contacted_labels.json")
    p.add_argument("--labels", type=str,
                   help='For mark-contacted: "Name1|email1,Name2|email2"')
    p.add_argument("--end-time", type=str,
                   help="ISO 8601 timestamp used as the end-of-last-track bound (optional)")
    args = p.parse_args(argv)

    if args.action == "enrich":
        if not args.log:
            p.error("--log is required for --action enrich")
        end_time = datetime.fromisoformat(args.end_time) if args.end_time else None
        return _cli_enrich(args.log, args.cache, end_time)
    elif args.action == "mark-contacted":
        if not args.labels:
            p.error("--labels is required for --action mark-contacted")
        return _cli_mark_contacted(args.cache, args.labels)


if __name__ == "__main__":
    import sys
    sys.exit(main())
```

- [ ] **Step 4.4: Run all tests to verify they pass**

Run: `cd /Users/marko/Desktop/Track-ID-automation-main && python3 -m pytest tests/test_label_outreach.py -v`

Expected: 20 passed (16 + 4 new).

---

## Task 5: Confirm no regressions in existing suite

**Files:** (no changes — verification only)

- [ ] **Step 5.1: Run the project's existing run_all.py**

Run: `cd /Users/marko/Desktop/Track-ID-automation-main && python3 tests/run_all.py 2>&1 | tail -10`

Expected output: ends with `62/62 passed.` (the existing pre-change baseline; `run_all.py` does NOT auto-discover pytest-style functions in `test_label_outreach.py` because of how it discovers tests — that's fine, the new tests are pytest-managed).

- [ ] **Step 5.2: Run the new tests via pytest to confirm full coverage**

Run: `cd /Users/marko/Desktop/Track-ID-automation-main && python3 -m pytest tests/test_label_outreach.py -v`

Expected: 20 passed.

(If you want `run_all.py` to also pick up these tests, that's a separate small fix — out of scope for this plan since the existing tests' style is pytest-discoverable too. The team may unify later.)

---

## Task 6: Subagent definition

**Files:**
- Create: `.claude/agents/label-emailer.md`

- [ ] **Step 6.1: Create the agents directory if it doesn't exist**

Run: `mkdir -p /Users/marko/Desktop/Track-ID-automation-main/.claude/agents`

- [ ] **Step 6.2: Write the subagent definition**

Create `.claude/agents/label-emailer.md`:

```markdown
---
name: label-emailer
description: Process the latest DJ set from tracklist_live.txt — find each record label's contact email (Discogs → web search → page extraction) and create per-label Gmail drafts via the Gmail MCP. The user reviews drafts in Gmail and sends manually. Dispatch after each stream.
tools: Bash, Read, Write, WebSearch, WebFetch, mcp__claude_ai_Gmail__create_draft, mcp__claude_ai_Gmail__list_drafts
---

You are the label-outreach subagent for the DJ Tracklist Auto-Logger project. You process the most recent DJ set, find contact emails for the record labels whose tracks were played, and create per-label Gmail drafts asking those labels to whitelist `waterhousestudios` from YouTube Content ID claims.

You DO NOT send emails. You create drafts in the user's Gmail Drafts folder. The user reviews and sends manually.

## Project paths

- Tracklist log: `~/Desktop/tracklist_live.txt`
- Dedup cache: `~/.tracklist_secrets/contacted_labels.json`
- User's verbatim ask text: `~/.tracklist_secrets/label_email_ask.txt`
- Python helper: `~/Desktop/Track-ID-automation-main/label_outreach.py`

## Pipeline (execute in this order)

### Step A — Pre-flight checks

1. `Read` `~/.tracklist_secrets/label_email_ask.txt`. If it does not exist OR is empty, STOP. Print exactly:
   `ERROR: ~/.tracklist_secrets/label_email_ask.txt is missing or empty. Author the ask text before running this agent.`
   Do not proceed.

### Step B — Enrich the session

2. Shell:
   `python3 ~/Desktop/Track-ID-automation-main/label_outreach.py --action enrich --log ~/Desktop/tracklist_live.txt --cache ~/.tracklist_secrets/contacted_labels.json`
3. If exit code is non-zero, print the stderr to the user and STOP.
4. Parse the JSON from stdout. It is a list of `{label, tracks, discogs_label_url, discogs_contact_email}` objects. If the list is empty, print `No new labels to contact for the latest session.` and STOP.

### Step C — Resolve missing emails via web search

For each label entry where `discogs_contact_email` is `""`:

5. `WebSearch` with query: `"<label name>" record label contact email`
6. Pick up to the top 2 result URLs.
7. `WebFetch` the first URL.
8. Extract the first plausible contact email from the fetched content. Handle these patterns:
   - `mailto:foo@bar.com` hrefs
   - Plain `foo@bar.com` in body text
   - Obfuscated forms: `foo [at] bar [dot] com`, `foo (at) bar (dot) com`, `foo AT bar DOT com`
   - Common contact-page phrases like "Contact us at...", "For demos: ..."
9. Prefer emails on the label's own domain (e.g., for label "Whities" prefer `*@whities.*`). Ignore obvious noise: `noreply@`, `webmaster@`, `info@example.com` placeholders.
10. If no email is found in the first URL's content, fetch the second URL and repeat.
11. If still no email after both, mark the label `NO_EMAIL_FOUND` with the URLs tried in Notes.

### Step D — Draft per-label emails

For each label that now has an email:

12. `Read` `~/.tracklist_secrets/label_email_ask.txt` (cache it across iterations).
13. Compose the email:
    - **Subject:** `DJ set including {label} releases — quick request re: YouTube Content ID`
    - **Body** (in this order):
      - Greeting: `Hi there,` (do not invent a contact name)
      - One sentence naming the specific tracks of theirs played and the channel. Example: `I just played {tracks_list} from your catalogue on my livestream channel waterhousestudios.`
        - For `{tracks_list}`: join with commas, "and" before the last; format each as `"{title}" by {artist}`.
      - The verbatim contents of `label_email_ask.txt`. Do not paraphrase, do not edit, do not add a leading sentence to it. Paste it exactly as-is.
      - Signoff: `— waterhousestudios`
    - Keep the whole body under ~150 words excluding the ask text.
14. Call `mcp__claude_ai_Gmail__create_draft` with `to`, `subject`, `body`.
15. Record `DRAFT_CREATED` if the call succeeds, else `DRAFT_API_ERROR` with the error in Notes.

### Step E — Update cache

16. Collect every label whose status is `DRAFT_CREATED`.
17. Shell:
    `python3 ~/Desktop/Track-ID-automation-main/label_outreach.py --action mark-contacted --cache ~/.tracklist_secrets/contacted_labels.json --labels "Label1|email1,Label2|email2"`
    Quote the `--labels` argument; escape any internal `,` or `|` if a label name contains them (unlikely but possible).

### Step F — Report

18. Print a markdown table summarising every label processed in this run, in original order:

    | Label | Email | Status | Notes |
    |---|---|---|---|

    Statuses: `DRAFT_CREATED`, `NO_EMAIL_FOUND`, `DRAFT_API_ERROR`. (Already-contacted labels are filtered out by the helper and do not appear in the table.)
19. After the table, print one line: `Done. Open Gmail → Drafts to review and send.`

## Failure modes

- If the helper exits non-zero in Step B: report and stop.
- If Step C fails for a label: mark `NO_EMAIL_FOUND`, do NOT add to cache (so a future run can retry).
- If Step D's `create_draft` fails: mark `DRAFT_API_ERROR`, do NOT add to cache.
- Network errors in WebSearch/WebFetch should not crash the run — log them per-label and continue.

## What you must NOT do

- Do NOT send emails (Gmail MCP doesn't expose a send tool anyway).
- Do NOT modify project source code.
- Do NOT spawn further subagents.
- Do NOT make up email addresses.
- Do NOT paraphrase or shorten the user's ask text.
- Do NOT add the label to the cache for any status other than `DRAFT_CREATED`.
```

- [ ] **Step 6.3: Verify the subagent file is well-formed**

Run: `head -5 /Users/marko/Desktop/Track-ID-automation-main/.claude/agents/label-emailer.md`

Expected: YAML frontmatter starts with `---`, contains `name: label-emailer`, contains the `tools:` line.

---

## Task 7: First-run protocol — manual verification (USER ACTION)

**Files:** none (this task is for the user, not the implementing engineer)

This task is documented in the plan so the implementing engineer knows where to stop. After Tasks 1-6 are complete, hand off to the user with these instructions:

- [ ] **Step 7.1: Tell the user the implementation is complete and what they need to do next**

Print to the user:

```
Implementation complete. Before first real outreach, you need to do two things:

1. Author your verbatim YouTube Content ID ask:
   - Create the file: ~/.tracklist_secrets/label_email_ask.txt
   - Write whatever you want pasted verbatim into every email's body
     (between the track-mention sentence and the signoff).
   - Example length: 2-5 sentences asking the label to whitelist
     waterhousestudios from Content ID, with whatever specifics you want.

2. First-run protocol (do this with a SMALL session so mistakes are cheap):
   - Pick a recent ~2-3 track session in tracklist_live.txt.
   - In a Claude Code session, dispatch the subagent:
       Agent({subagent_type: "label-emailer",
              prompt: "Process the latest session"})
   - Verify: the report table is sensible, and the Gmail Drafts folder
     contains exactly one draft per DRAFT_CREATED row.
   - Open each draft, read it. Confirm:
       - The track names are correct.
       - Your ask text appears verbatim.
       - The signoff is "— waterhousestudios".
       - The subject line is correctly formatted.
   - If anything is wrong: delete the drafts, fix the issue (most likely
     in .claude/agents/label-emailer.md), and re-run.
   - Only after a clean first-run pass should you send real emails.
```

---

## Self-Review

(Per the writing-plans skill: ran inline.)

**Spec coverage:**
- Goal — Task 1-6 wire up the full pipeline. ✓
- User Workflow — Task 6 (subagent prompt) + Task 7 (user hand-off). ✓
- Architecture (subagent + helper + cache + ask file) — Task 6 + Task 1 + Task 4 + Task 7. ✓
- `label_outreach.py` functions — Task 1 (`load_contacted`, `save_contacted`), Task 2 (`parse_latest_session`), Task 3 (`group_by_label`), Task 4 (CLI). ✓
- `~/.tracklist_secrets/label_email_ask.txt` — Task 7 (user-owned). ✓
- `~/.tracklist_secrets/contacted_labels.json` — created by `save_contacted` in Task 1. ✓
- Tool whitelist — Task 6 YAML frontmatter. ✓
- Data flow steps 1-6 — Task 6 subagent prompt. ✓
- Dedup Semantics — Task 6 step E (cache update only for `DRAFT_CREATED`). ✓
- Error Handling table — Task 6 Failure Modes section + Task 4 stderr behavior. ✓
- Unit tests list — Task 1 (cache), Task 2 (parse), Task 3 (group). ✓
- First-run protocol — Task 7. ✓
- Security / file modes — Task 1 implementation enforces 700/600 and tests verify. ✓

**Placeholder scan:** No "TBD", "TODO", or vague directives in any task. Every code step shows the actual code; every command is exact.

**Type consistency:**
- `ContactedEntry(name, email, source)` — used identically in Task 1 implementation, Task 1 tests, and Task 4 CLI. ✓
- `LabelInfo` fields — `tracks`, `discogs_label_id`, `discogs_label_url`, `discogs_contact_email`. CLI in Task 4 reads `info.tracks`, `info.discogs_label_url`, `info.discogs_contact_email` — all match. ✓
- `parse_latest_session(log_path, end_time=None)` — Task 2 signature and Task 4 CLI call match. ✓
- `group_by_label(tracks, discogs_token)` — Task 3 signature and Task 4 CLI call match. ✓
- `load_contacted(cache_path) → set[str]` and `save_contacted(cache_path, list[ContactedEntry])` — consistent across tasks. ✓

No gaps; no inconsistencies; no placeholders.
