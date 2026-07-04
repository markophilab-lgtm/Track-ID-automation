import json
import sys
import tempfile
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).parent.parent))

import post_tracklist

_LOG = (
    "─── Session started 2026-05-17 20:00:00 ───\n"
    "20:00:05  [Player 1]  Anthony Naples — Crystals\n"
    "20:05:00  [Player 2]  Joy Orbison — Hyph Mngo\n"
)


def _run(argv):
    with mock.patch.object(post_tracklist, "_enrich_chapters"), \
         mock.patch.object(post_tracklist, "notify"):
        return post_tracklist.main(argv)


def test_write_descriptions_writes_files_and_meta():
    with tempfile.TemporaryDirectory() as td:
        log = Path(td) / "log.txt"; log.write_text(_LOG)
        movie = Path(td) / "2026-05-17 20-00-00.mov"; movie.write_text("")
        out = Path(td) / "out"
        rc = _run(["--movie", str(movie), "--log", str(log),
                   "--skip-mixcloud", "--skip-youtube", "--artist", "Marko",
                   "--write-descriptions", str(out)])
        assert rc == 0
        yt = (out / "youtube_description.txt").read_text()
        assert "Tracklist:" in yt
        assert (out / "soundcloud_description.txt").read_text() == yt
        meta = json.loads((out / "run_meta.json").read_text())
        assert meta["title"] == "Marko @ WTHS Radio (17.5.2026)"
        assert meta["movie_path"] == str(movie)
        assert meta["stream_start"] == "2026-05-17T20:00:00"
        assert meta["chapter_count"] >= 1


def test_dry_run_writes_nothing():
    with tempfile.TemporaryDirectory() as td:
        log = Path(td) / "log.txt"; log.write_text(_LOG)
        movie = Path(td) / "2026-05-17 20-00-00.mov"; movie.write_text("")
        out = Path(td) / "out"
        rc = _run(["--movie", str(movie), "--log", str(log), "--dry-run",
                   "--skip-mixcloud", "--skip-youtube",
                   "--write-descriptions", str(out)])
        assert rc == 0
        assert not out.exists()


def test_flag_absent_writes_nothing():
    with tempfile.TemporaryDirectory() as td:
        log = Path(td) / "log.txt"; log.write_text(_LOG)
        movie = Path(td) / "2026-05-17 20-00-00.mov"; movie.write_text("")
        rc = _run(["--movie", str(movie), "--log", str(log),
                   "--skip-mixcloud", "--skip-youtube"])
        assert rc == 0
        assert not (Path(td) / "out").exists()
