import json
import sys
import tempfile
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from description_writer import write_outputs, default_title


def test_writes_all_three_files():
    with tempfile.TemporaryDirectory() as td:
        out = Path(td) / "deploy_output"
        meta = {"stream_start": "2026-05-17T20:00:00", "movie_path": "/tmp/x.mov",
                "title": "t", "chapter_count": 3}
        returned = write_outputs(out, "YT DESC", "SC DESC", meta)
        assert returned == out
        assert (out / "youtube_description.txt").read_text() == "YT DESC"
        assert (out / "soundcloud_description.txt").read_text() == "SC DESC"
        assert json.loads((out / "run_meta.json").read_text()) == meta


def test_creates_missing_directory_and_overwrites():
    with tempfile.TemporaryDirectory() as td:
        out = Path(td) / "a" / "b"
        meta = {"stream_start": "s", "movie_path": "m", "title": "t", "chapter_count": 1}
        write_outputs(out, "one", "one", meta)
        write_outputs(out, "two", "two", meta)
        assert (out / "youtube_description.txt").read_text() == "two"


def test_default_title():
    assert default_title(date(2026, 5, 17)) == "waterhousestudios live stream 2026-05-17"
