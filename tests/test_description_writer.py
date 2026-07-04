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


def test_default_title_artist_at_wths_radio_dmy():
    # Format requested by Marko 2026-07-04: (artist name) @ WTHS Radio (D.M.Y)
    assert default_title(date(2026, 7, 1), "Marko") == "Marko @ WTHS Radio (1.7.2026)"


def test_default_title_no_leading_zeros():
    assert default_title(date(2026, 12, 25), "Anna B") == "Anna B @ WTHS Radio (25.12.2026)"


def test_default_title_fallback_artist():
    assert default_title(date(2026, 7, 1)) == "waterhousestudios @ WTHS Radio (1.7.2026)"
