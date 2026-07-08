import json
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

sys.path.insert(0, str(Path(__file__).parent.parent))

import gofile_upload as gu


def _mk_file(td, name="set.mov", size=100):
    f = Path(td) / name
    f.write_bytes(b"x" * size)
    return f


def test_missing_file_exits_2():
    rc = gu.main(["--file", "/nope/never/set.mov"])
    assert rc == 2


def test_dry_run_never_touches_network():
    with tempfile.TemporaryDirectory() as td:
        f = _mk_file(td)
        with mock.patch.object(gu, "pick_server") as ps, \
             mock.patch.object(gu, "upload") as up:
            rc = gu.main(["--file", str(f), "--dry-run"])
        assert rc == 0
        ps.assert_not_called()
        up.assert_not_called()


def test_missing_token_file_exits_4():
    with tempfile.TemporaryDirectory() as td:
        f = _mk_file(td)
        with mock.patch.object(gu, "TOKEN_PATH", Path(td) / "gofile.json"):
            rc = gu.main(["--file", str(f)])
        assert rc == 4


def test_empty_token_exits_4():
    with tempfile.TemporaryDirectory() as td:
        f = _mk_file(td)
        tp = Path(td) / "gofile.json"
        tp.write_text('{"account_id": "a", "api_token": ""}')
        with mock.patch.object(gu, "TOKEN_PATH", tp):
            rc = gu.main(["--file", str(f)])
        assert rc == 4


def _fake_servers_response(servers):
    body = json.dumps({"status": "ok", "data": {"servers": servers}}).encode()
    resp = mock.MagicMock()
    resp.read.return_value = body
    resp.__enter__ = lambda s: resp
    resp.__exit__ = lambda s, *a: False
    return resp


def test_pick_server_prefers_eu():
    servers = [{"name": "store-na-1", "zone": "na"}, {"name": "store-eu-2", "zone": "eu"}]
    with mock.patch.object(gu.urllib.request, "urlopen",
                           return_value=_fake_servers_response(servers)):
        assert gu.pick_server() == "store-eu-2"


def test_pick_server_falls_back_to_first():
    servers = [{"name": "store-na-1", "zone": "na"}]
    with mock.patch.object(gu.urllib.request, "urlopen",
                           return_value=_fake_servers_response(servers)):
        assert gu.pick_server() == "store-na-1"


def _curl_result(returncode=0, stdout="", stderr=""):
    return SimpleNamespace(returncode=returncode, stdout=stdout, stderr=stderr)


def test_upload_returns_download_page():
    ok = json.dumps({"status": "ok", "data": {"downloadPage": "https://gofile.io/d/abc123"}})
    with mock.patch.object(gu.subprocess, "run", return_value=_curl_result(stdout=ok)) as run:
        link = gu.upload(Path("/tmp/set.mov"), "TOK", "store-eu-2")
    assert link == "https://gofile.io/d/abc123"
    cmd = run.call_args[0][0]
    assert "Authorization: Bearer TOK" in cmd
    assert "https://store-eu-2.gofile.io/contents/uploadfile" in cmd


def test_upload_curl_failure_raises_upload_error():
    with mock.patch.object(gu.subprocess, "run",
                           return_value=_curl_result(returncode=56, stderr="connection reset")):
        try:
            gu.upload(Path("/tmp/set.mov"), "TOK", "srv")
            assert False, "expected GofileUploadError"
        except gu.GofileUploadError:
            pass


def test_upload_auth_error_status_raises_auth_error():
    bad = json.dumps({"status": "error-auth", "data": {}})
    with mock.patch.object(gu.subprocess, "run", return_value=_curl_result(stdout=bad)):
        try:
            gu.upload(Path("/tmp/set.mov"), "TOK", "srv")
            assert False, "expected GofileAuthError"
        except gu.GofileAuthError:
            pass


def test_main_full_success_prints_link(capsys=None):
    with tempfile.TemporaryDirectory() as td:
        f = _mk_file(td)
        tp = Path(td) / "gofile.json"
        tp.write_text('{"account_id": "a", "api_token": "TOK"}')
        with mock.patch.object(gu, "TOKEN_PATH", tp), \
             mock.patch.object(gu, "pick_server", return_value="store-eu-2"), \
             mock.patch.object(gu, "upload", return_value="https://gofile.io/d/abc123") as up, \
             mock.patch.object(gu, "notify"):
            rc = gu.main(["--file", str(f)])
        assert rc == 0
        up.assert_called_once()


def test_main_upload_error_exits_5():
    with tempfile.TemporaryDirectory() as td:
        f = _mk_file(td)
        tp = Path(td) / "gofile.json"
        tp.write_text('{"account_id": "a", "api_token": "TOK"}')
        with mock.patch.object(gu, "TOKEN_PATH", tp), \
             mock.patch.object(gu, "pick_server", return_value="srv"), \
             mock.patch.object(gu, "upload", side_effect=gu.GofileUploadError("boom")):
            rc = gu.main(["--file", str(f)])
        assert rc == 5
