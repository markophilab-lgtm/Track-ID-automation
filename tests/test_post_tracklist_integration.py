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
21:35:23  [Player 1]  ShortBlip — Skip Me
21:35:28  [Player 1]  Joy Orbison — Hyph Mngo
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
