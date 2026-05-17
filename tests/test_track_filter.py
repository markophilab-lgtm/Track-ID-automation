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
    end = datetime(2026, 5, 17, 22, 5, 0)
    out = filter_short_tracks(tracks, min_seconds=30, end_time=end)
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
    end = datetime(2026, 5, 17, 22, 5, 0)
    out = filter_short_tracks(tracks, min_seconds=30, end_time=end)
    assert len(out) == 3
