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
    assert chapters[1].time_str == "5:23"


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
