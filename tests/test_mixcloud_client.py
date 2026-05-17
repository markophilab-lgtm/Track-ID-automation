import json
import os
import stat
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock

sys.path.insert(0, str(Path(__file__).parent.parent))

import mixcloud_client


def _resp(status, json_body=None, text=""):
    r = MagicMock()
    r.status_code = status
    r.json.return_value = json_body if json_body is not None else {}
    r.text = text
    return r


def test_load_app_credentials_reads_existing_file(tmp_dir=None):
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "mixcloud_app.json"
        p.write_text(json.dumps({"client_id": "abc", "client_secret": "xyz"}))
        cid, sec = mixcloud_client.load_app_credentials(p)
        assert cid == "abc"
        assert sec == "xyz"


def test_load_app_credentials_missing_file_raises():
    try:
        mixcloud_client.load_app_credentials(Path("/tmp/definitely_does_not_exist_42"))
    except FileNotFoundError:
        return
    raise AssertionError("Expected FileNotFoundError")


def test_save_token_uses_mode_600():
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "mixcloud.json"
        mixcloud_client.save_token(p, "secret-token-value")
        st = os.stat(p)
        # Mode bits should be exactly owner-read+write, no group/other
        assert stat.S_IMODE(st.st_mode) == 0o600
        data = json.loads(p.read_text())
        assert data["access_token"] == "secret-token-value"


def test_load_token_returns_none_if_missing():
    with tempfile.TemporaryDirectory() as d:
        result = mixcloud_client.load_token(Path(d) / "missing.json")
        assert result is None


def test_load_token_reads_existing():
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "mixcloud.json"
        p.write_text(json.dumps({"access_token": "tok"}))
        assert mixcloud_client.load_token(p) == "tok"


def test_exchange_code_for_token_success():
    resp = _resp(200, {"access_token": "the-token"})
    with patch.object(mixcloud_client.requests, "post", return_value=resp):
        token = mixcloud_client.exchange_code_for_token(
            client_id="cid", client_secret="csec",
            redirect_uri="http://localhost:8765/callback",
            code="auth-code",
        )
    assert token == "the-token"


def test_exchange_code_for_token_failure_raises():
    resp = _resp(400, text="Bad request")
    with patch.object(mixcloud_client.requests, "post", return_value=resp):
        try:
            mixcloud_client.exchange_code_for_token(
                client_id="cid", client_secret="csec",
                redirect_uri="http://localhost:8765/callback",
                code="auth-code",
            )
        except mixcloud_client.MixcloudAuthError as e:
            assert "400" in str(e)
            return
    raise AssertionError("Expected MixcloudAuthError")


def test_authorize_url_includes_all_params():
    url = mixcloud_client.build_authorize_url(
        client_id="abc",
        redirect_uri="http://localhost:8765/callback",
    )
    assert url.startswith("https://www.mixcloud.com/oauth/authorize/")
    assert "client_id=abc" in url
    assert "redirect_uri=http%3A%2F%2Flocalhost%3A8765%2Fcallback" in url
    assert "response_type=code" in url


from timestamp_builder import Chapter


def _chap(secs, artist, title):
    return Chapter(
        time_seconds=secs, time_str=f"{secs//60}:{secs%60:02d}",
        artist=artist, title=title,
    )


def test_get_me_returns_username():
    resp = _resp(200, {"username": "the_dj", "name": "The DJ"})
    with patch.object(mixcloud_client.requests, "get", return_value=resp):
        assert mixcloud_client.get_me("tok") == "the_dj"


def test_get_me_401_raises_auth_error():
    resp = _resp(401)
    with patch.object(mixcloud_client.requests, "get", return_value=resp):
        try:
            mixcloud_client.get_me("expired-token")
        except mixcloud_client.MixcloudAuthError:
            return
    raise AssertionError("Expected MixcloudAuthError on 401")


def test_latest_cloudcast_picks_first():
    resp = _resp(200, {
        "data": [
            {"slug": "newest-stream", "name": "Stream 2026-05-17", "created_time": "2026-05-17T22:00:00Z"},
            {"slug": "older", "name": "Older", "created_time": "2026-05-15T22:00:00Z"},
        ]
    })
    with patch.object(mixcloud_client.requests, "get", return_value=resp):
        cc = mixcloud_client.latest_cloudcast("tok", username="the_dj")
    assert cc["slug"] == "newest-stream"


def test_latest_cloudcast_none_found_raises():
    resp = _resp(200, {"data": []})
    with patch.object(mixcloud_client.requests, "get", return_value=resp):
        try:
            mixcloud_client.latest_cloudcast("tok", username="the_dj")
        except mixcloud_client.MixcloudAPIError:
            return
    raise AssertionError("Expected MixcloudAPIError")


def test_update_cloudcast_sends_form_fields():
    chapters = [
        _chap(0, "Intro", "Intro"),
        _chap(323, "Anthony Naples", "Crystals"),
        _chap(767, "Joy Orbison", "Hyph Mngo"),
    ]
    resp = _resp(200, {"result": {"success": True}})
    with patch.object(mixcloud_client.requests, "post", return_value=resp) as p:
        mixcloud_client.update_cloudcast(
            token="tok", username="the_dj", slug="my-stream",
            description="hello world", chapters=chapters,
        )
    args, kwargs = p.call_args
    # The POST body should contain description and indexed section fields
    data = kwargs["data"]
    assert data["description"] == "hello world"
    assert data["sections-0-start_time"] == 0
    assert data["sections-0-artist_name"] == "Intro"
    assert data["sections-0-song_name"] == "Intro"
    assert data["sections-1-start_time"] == 323
    assert data["sections-1-artist_name"] == "Anthony Naples"
    assert data["sections-1-song_name"] == "Crystals"
    assert data["sections-2-start_time"] == 767
    # And the URL should be the edit endpoint with the access token
    posted_url = args[0]
    assert "/upload/the_dj/my-stream/edit/" in posted_url
    assert "access_token=tok" in posted_url


def test_update_cloudcast_403_raises_specific_error():
    resp = _resp(403, text="Forbidden")
    with patch.object(mixcloud_client.requests, "post", return_value=resp):
        try:
            mixcloud_client.update_cloudcast(
                token="tok", username="the_dj", slug="x",
                description="hi", chapters=[_chap(0, "I", "I")],
            )
        except mixcloud_client.MixcloudAPIError as e:
            assert "403" in str(e)
            return
    raise AssertionError("Expected MixcloudAPIError on 403")


def test_update_cloudcast_401_raises_auth_error():
    resp = _resp(401, text="Unauthorized")
    with patch.object(mixcloud_client.requests, "post", return_value=resp):
        try:
            mixcloud_client.update_cloudcast(
                token="tok", username="the_dj", slug="x",
                description="hi", chapters=[_chap(0, "I", "I")],
            )
        except mixcloud_client.MixcloudAuthError:
            return
    raise AssertionError("Expected MixcloudAuthError on 401")
