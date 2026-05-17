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
