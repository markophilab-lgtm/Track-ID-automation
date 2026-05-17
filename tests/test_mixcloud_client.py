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
