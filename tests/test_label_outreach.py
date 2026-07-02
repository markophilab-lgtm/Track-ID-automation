import json
import os
import stat
import subprocess
import sys
import tempfile
from datetime import datetime as _dt, timedelta
from pathlib import Path
from unittest.mock import patch, MagicMock

sys.path.insert(0, str(Path(__file__).parent.parent))

import label_outreach
import tracklist_parser


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


_SAMPLE_LOG_SIMPLE = """\
─── Session started 2026-05-17 21:30:00 ───
21:30:00  [Player 1]  Pearson Sound — Blanked
21:35:00  [Player 2]  Joy Orbison — Hyph Mngo
"""


def _make_track(artist, title):
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


def _run_cli(args, stdin_text=None):
    proj_root = Path(__file__).parent.parent
    cmd = ["python3", str(proj_root / "label_outreach.py")] + args
    return subprocess.run(cmd, capture_output=True, text=True, input=stdin_text)


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


# ---------- parse_latest_session ----------

def test_parse_latest_session_returns_last_session_only():
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "tracklist_live.txt"
        p.write_text(_SAMPLE_LOG)
        tracks = label_outreach.parse_latest_session(
            p, end_time=_dt(2026, 5, 17, 21, 45, 0)
        )
        artists = [t.artist for t in tracks]
        # Earlier session entirely excluded:
        assert "Old Artist" not in artists
        assert "Old Artist Two" not in artists
        # Within latest session, sub-30s tracks dropped:
        # - "Anthony Naples" had 5s as master before "Skipped Short" took over
        # - "Skipped Short" had 5s as master before "Joy Orbison" took over
        assert "Anthony Naples" not in artists
        assert "Skipped Short" not in artists
        # Kept: 290s and 600s-against-end_time
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


# ---------- group_by_label ----------

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


# ---------- CLI ----------

def test_cli_enrich_emits_json_for_new_labels():
    with tempfile.TemporaryDirectory() as d:
        log = Path(d) / "tracklist_live.txt"
        log.write_text(_SAMPLE_LOG_SIMPLE)
        cache = Path(d) / "contacted.json"

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
        assert ("no session" in result.stderr.lower()
                or "missing" in result.stderr.lower())


def test_cli_mark_contacted_appends_entries_from_stdin():
    with tempfile.TemporaryDirectory() as d:
        cache = Path(d) / "contacted.json"
        stdin = json.dumps([
            {"name": "Hessle Audio", "email": "info@hessleaudio.com", "source": "discogs"},
            {"name": "Whities", "email": "hello@whities.uk", "source": "websearch"},
        ])
        result = _run_cli([
            "--action", "mark-contacted",
            "--cache", str(cache),
            "--labels-stdin",
        ], stdin_text=stdin)
        assert result.returncode == 0, f"stderr={result.stderr}"
        data = json.loads(cache.read_text())
        names = [e["name"] for e in data["labels"]]
        assert names == ["Hessle Audio", "Whities"]
        sources = [e["source"] for e in data["labels"]]
        assert sources == ["discogs", "websearch"]


def test_cli_mark_contacted_creates_cache_if_missing():
    with tempfile.TemporaryDirectory() as d:
        cache = Path(d) / "subdir" / "contacted.json"
        stdin = json.dumps([
            {"name": "Only Label", "email": "only@label.com", "source": "discogs"},
        ])
        result = _run_cli([
            "--action", "mark-contacted",
            "--cache", str(cache),
            "--labels-stdin",
        ], stdin_text=stdin)
        assert result.returncode == 0, f"stderr={result.stderr}"
        assert cache.exists()


def test_cli_mark_contacted_preserves_label_name_with_comma_or_pipe():
    """Regression: the previous comma/pipe CLI parser mangled these names silently."""
    with tempfile.TemporaryDirectory() as d:
        cache = Path(d) / "contacted.json"
        stdin = json.dumps([
            {"name": "Numbers, Records", "email": "x@y.z", "source": "websearch"},
            {"name": "Pipe|Label", "email": "a@b.c", "source": "websearch"},
        ])
        result = _run_cli([
            "--action", "mark-contacted",
            "--cache", str(cache),
            "--labels-stdin",
        ], stdin_text=stdin)
        assert result.returncode == 0, f"stderr={result.stderr}"
        data = json.loads(cache.read_text())
        names = [e["name"] for e in data["labels"]]
        assert names == ["Numbers, Records", "Pipe|Label"]


def test_cli_mark_contacted_empty_list_is_noop():
    """If no labels had DRAFT_CREATED, subagent will pass [] — must succeed, not crash."""
    with tempfile.TemporaryDirectory() as d:
        cache = Path(d) / "contacted.json"
        result = _run_cli([
            "--action", "mark-contacted",
            "--cache", str(cache),
            "--labels-stdin",
        ], stdin_text="[]")
        assert result.returncode == 0, f"stderr={result.stderr}"
        # File not written for an empty list:
        assert not cache.exists()


def test_cli_mark_contacted_rejects_missing_source():
    """Missing source field is rejected (no silent default). Subagent must supply it."""
    with tempfile.TemporaryDirectory() as d:
        cache = Path(d) / "contacted.json"
        stdin = json.dumps([{"name": "X", "email": "x@y.z"}])
        result = _run_cli([
            "--action", "mark-contacted",
            "--cache", str(cache),
            "--labels-stdin",
        ], stdin_text=stdin)
        assert result.returncode == 4
        assert "invalid or missing source" in result.stderr.lower()


def test_cli_mark_contacted_rejects_unknown_source():
    with tempfile.TemporaryDirectory() as d:
        cache = Path(d) / "contacted.json"
        stdin = json.dumps([
            {"name": "X", "email": "x@y.z", "source": "made_up"},
        ])
        result = _run_cli([
            "--action", "mark-contacted",
            "--cache", str(cache),
            "--labels-stdin",
        ], stdin_text=stdin)
        assert result.returncode == 4
        assert "invalid or missing source" in result.stderr.lower()


def test_cli_enrich_exits_with_clear_error_on_corrupt_cache():
    """Spec: corrupt cache → non-zero exit with the path, do NOT silently overwrite."""
    with tempfile.TemporaryDirectory() as d:
        log = Path(d) / "tracklist_live.txt"
        log.write_text(_SAMPLE_LOG_SIMPLE)
        cache = Path(d) / "contacted.json"
        cache.write_text("{not valid json at all")

        result = _run_cli([
            "--action", "enrich",
            "--log", str(log),
            "--cache", str(cache),
            "--end-time", "2026-05-17T21:45:00",
        ])
        assert result.returncode == 3
        assert "corrupt" in result.stderr.lower()
        # Confirm cache file was NOT overwritten:
        assert cache.read_text() == "{not valid json at all"


def test_load_contacted_raises_on_corrupt_cache():
    with tempfile.TemporaryDirectory() as d:
        cache = Path(d) / "contacted.json"
        cache.write_text("{not valid")
        try:
            label_outreach.load_contacted(cache)
        except label_outreach.CorruptCacheError:
            return
        raise AssertionError("Expected CorruptCacheError")
