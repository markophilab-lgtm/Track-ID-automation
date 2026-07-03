import sys
import tempfile
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).parent.parent))

import soundcloud_publish as sp


def _mk_inputs(td):
    movie = Path(td) / "2026-05-17 20-00-00.mov"; movie.write_bytes(b"m")
    desc = Path(td) / "soundcloud_description.txt"; desc.write_text("D")
    return movie, desc


def _base_args(movie, desc):
    return ["--movie", str(movie), "--title", "T", "--description-file", str(desc)]


def test_missing_movie_exits_2():
    with tempfile.TemporaryDirectory() as td:
        _, desc = _mk_inputs(td)
        rc = sp.main(["--movie", str(Path(td) / "nope.mov"), "--title", "T",
                      "--description-file", str(desc)])
        assert rc == 2


def test_ffmpeg_missing_exits_3():
    with tempfile.TemporaryDirectory() as td:
        movie, desc = _mk_inputs(td)
        with mock.patch.object(sp, "ffmpeg_available", return_value=False):
            rc = sp.main(_base_args(movie, desc))
        assert rc == 3


def test_dry_run_probes_and_never_uploads():
    with tempfile.TemporaryDirectory() as td:
        movie, desc = _mk_inputs(td)
        with mock.patch.object(sp, "ffmpeg_available", return_value=True), \
             mock.patch.object(sp, "probe_duration_seconds", return_value=3600.0), \
             mock.patch.object(sp, "extract_audio") as ex, \
             mock.patch.object(sp.soundcloud_client, "upload_track") as up:
            rc = sp.main(_base_args(movie, desc) + ["--dry-run"])
        assert rc == 0
        assert ex.call_count == 0
        assert up.call_count == 0


def test_duration_over_24h_exits_2():
    with tempfile.TemporaryDirectory() as td:
        movie, desc = _mk_inputs(td)
        with mock.patch.object(sp, "ffmpeg_available", return_value=True), \
             mock.patch.object(sp, "probe_duration_seconds", return_value=25 * 3600.0):
            rc = sp.main(_base_args(movie, desc) + ["--dry-run"])
        assert rc == 2


def test_real_run_extracts_uploads_notifies():
    with tempfile.TemporaryDirectory() as td:
        movie, desc = _mk_inputs(td)
        fake_mp3 = Path(td) / "out.mp3"; fake_mp3.write_bytes(b"a")
        with mock.patch.object(sp, "ffmpeg_available", return_value=True), \
             mock.patch.object(sp, "probe_duration_seconds", return_value=3600.0), \
             mock.patch.object(sp, "extract_audio", return_value=fake_mp3) as ex, \
             mock.patch.object(sp.soundcloud_client, "upload_track",
                               return_value="https://sc/u/t") as up, \
             mock.patch.object(sp, "notify") as note:
            rc = sp.main(_base_args(movie, desc))
        assert rc == 0
        assert ex.call_count == 1
        up.assert_called_once()
        assert up.call_args.args[1] == "T"
        assert note.call_count == 1


def test_auth_error_exits_4_upload_error_exits_5():
    with tempfile.TemporaryDirectory() as td:
        movie, desc = _mk_inputs(td)
        fake_mp3 = Path(td) / "out.mp3"; fake_mp3.write_bytes(b"a")
        base = _base_args(movie, desc)
        with mock.patch.object(sp, "ffmpeg_available", return_value=True), \
             mock.patch.object(sp, "probe_duration_seconds", return_value=60.0), \
             mock.patch.object(sp, "extract_audio", return_value=fake_mp3), \
             mock.patch.object(sp, "notify"), \
             mock.patch.object(sp.soundcloud_client, "upload_track",
                               side_effect=sp.soundcloud_client.SoundCloudAuthError("x")):
            assert sp.main(base) == 4
        with mock.patch.object(sp, "ffmpeg_available", return_value=True), \
             mock.patch.object(sp, "probe_duration_seconds", return_value=60.0), \
             mock.patch.object(sp, "extract_audio", return_value=fake_mp3), \
             mock.patch.object(sp, "notify"), \
             mock.patch.object(sp.soundcloud_client, "upload_track",
                               side_effect=sp.soundcloud_client.SoundCloudAPIError("x")):
            assert sp.main(base) == 5


def test_ffmpeg_command_construction():
    with mock.patch.object(sp.subprocess, "run") as m:
        sp.extract_audio("/in/x.mov", "/out/x.mp3")
    cmd = m.call_args.args[0]
    assert cmd[0] == "ffmpeg"
    assert "-vn" in cmd
    assert "libmp3lame" in cmd
    assert "320k" in cmd
    assert cmd[-1] == "/out/x.mp3"
