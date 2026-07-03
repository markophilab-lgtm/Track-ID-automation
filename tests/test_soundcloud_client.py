import json
import sys
import tempfile
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).parent.parent))

import soundcloud_client as sc


def test_pkce_challenge_rfc7636_vector():
    # Known vector from RFC 7636 appendix B
    verifier = "dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk"
    assert sc.pkce_challenge(verifier) == "E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM"


def test_make_verifier_is_urlsafe_and_long_enough():
    v = sc.make_verifier()
    assert 43 <= len(v) <= 128
    assert "=" not in v and "+" not in v and "/" not in v


def test_token_save_load_roundtrip_and_modes():
    import os
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "secrets" / "soundcloud.json"
        tok = {"access_token": "a", "refresh_token": "r"}
        sc.save_token(tok, path=p)
        assert sc.load_token(path=p) == tok
        assert oct(os.stat(p).st_mode & 0o777) == "0o600"
        assert oct(os.stat(p.parent).st_mode & 0o777) == "0o700"


def test_load_token_missing_returns_none():
    with tempfile.TemporaryDirectory() as td:
        assert sc.load_token(path=Path(td) / "nope.json") is None


def test_build_authorize_url_contains_pkce_params():
    url = sc.build_authorize_url("CID", "CHAL", state="STATE123")
    assert url.startswith("https://secure.soundcloud.com/authorize?")
    assert "client_id=CID" in url
    assert "code_challenge=CHAL" in url
    assert "code_challenge_method=S256" in url
    assert "response_type=code" in url
    assert "state=STATE123" in url
    assert "localhost%3A8766" in url


def test_build_authorize_url_generates_state_when_omitted():
    # state is REQUIRED by SoundCloud (CSRF protection) — the page renders blank without it
    url = sc.build_authorize_url("CID", "CHAL")
    assert "state=" in url


def _resp(status, body):
    r = mock.Mock()
    r.status_code = status
    r.json.return_value = body
    r.text = json.dumps(body)
    return r


def test_exchange_code_sends_verifier_and_returns_tokens():
    with mock.patch.object(sc.requests, "post",
                           return_value=_resp(200, {"access_token": "A", "refresh_token": "R"})) as m:
        out = sc.exchange_code_for_token("cid", "sec", sc.REDIRECT_URI, "thecode", "theverifier")
    assert out["access_token"] == "A" and out["refresh_token"] == "R"
    sent = m.call_args.kwargs["data"]
    assert sent["grant_type"] == "authorization_code"
    assert sent["code_verifier"] == "theverifier"
    assert sent["code"] == "thecode"


def test_exchange_code_failure_raises_auth_error():
    with mock.patch.object(sc.requests, "post", return_value=_resp(401, {"error": "bad"})):
        try:
            sc.exchange_code_for_token("cid", "sec", sc.REDIRECT_URI, "c", "v")
            assert False, "should have raised"
        except sc.SoundCloudAuthError:
            pass


def test_refresh_returns_new_token_dict():
    with mock.patch.object(sc.requests, "post",
                           return_value=_resp(200, {"access_token": "A2", "refresh_token": "R2"})) as m:
        out = sc.refresh_access_token("cid", "sec", "oldR")
    assert out == {"access_token": "A2", "refresh_token": "R2"}
    assert m.call_args.kwargs["data"]["grant_type"] == "refresh_token"
    assert m.call_args.kwargs["data"]["refresh_token"] == "oldR"


def _upload_env(td, post_responses, refresh_result=None):
    """Patch token/creds paths into td and requests.post with a response sequence."""
    tok_path = Path(td) / "soundcloud.json"
    cred_path = Path(td) / "soundcloud_app.json"
    sc.save_token({"access_token": "OLD", "refresh_token": "R"}, path=tok_path)
    sc.save_app_credentials("cid", "sec", path=cred_path)
    patches = [
        mock.patch.object(sc, "TOKEN_PATH", tok_path),
        mock.patch.object(sc, "APP_CRED_PATH", cred_path),
        mock.patch.object(sc.time, "sleep"),
        mock.patch.object(sc.requests, "post", side_effect=post_responses),
    ]
    if refresh_result is not None:
        patches.append(mock.patch.object(sc, "refresh_access_token",
                                         return_value=refresh_result))
    return patches, tok_path


def test_upload_success_returns_permalink():
    with tempfile.TemporaryDirectory() as td:
        audio = Path(td) / "set.mp3"; audio.write_bytes(b"x" * 10)
        patches, _ = _upload_env(td, [_resp(201, {"permalink_url": "https://soundcloud.com/u/set"})])
        with patches[0], patches[1], patches[2], patches[3] as m:
            url = sc.upload_track(audio, "My Set", "desc", tags="dj mix")
        assert url == "https://soundcloud.com/u/set"
        assert m.call_args.kwargs["data"]["track[title]"] == "My Set"
        assert m.call_args.kwargs["data"]["track[sharing]"] == "public"
        assert m.call_args.kwargs["data"]["track[tag_list]"] == "dj mix"
        assert "track[asset_data]" in m.call_args.kwargs["files"]
        assert m.call_args.kwargs["headers"]["Authorization"] == "OAuth OLD"


def test_upload_refreshes_on_401_and_saves_new_token():
    with tempfile.TemporaryDirectory() as td:
        audio = Path(td) / "set.mp3"; audio.write_bytes(b"x")
        patches, tok_path = _upload_env(
            td,
            [_resp(401, {}), _resp(201, {"permalink_url": "https://sc/u/s"})],
            refresh_result={"access_token": "NEW", "refresh_token": "R2"},
        )
        with patches[0], patches[1], patches[2], patches[3] as m, patches[4]:
            url = sc.upload_track(audio, "t", "d")
        assert url == "https://sc/u/s"
        assert m.call_args.kwargs["headers"]["Authorization"] == "OAuth NEW"
        assert sc.load_token(path=tok_path)["access_token"] == "NEW"


def test_upload_rejects_oversize_file_before_network():
    with tempfile.TemporaryDirectory() as td:
        audio = Path(td) / "set.mp3"; audio.write_bytes(b"x" * 100)
        with mock.patch.object(sc, "MAX_UPLOAD_BYTES", 50), \
             mock.patch.object(sc.requests, "post") as m:
            try:
                sc.upload_track(audio, "t", "d")
                assert False, "should have raised"
            except sc.SoundCloudAPIError as e:
                assert "4 GB" in str(e) or "limit" in str(e)
        assert m.call_count == 0


def test_upload_no_token_raises_with_setup_hint():
    with tempfile.TemporaryDirectory() as td:
        audio = Path(td) / "set.mp3"; audio.write_bytes(b"x")
        with mock.patch.object(sc, "TOKEN_PATH", Path(td) / "missing.json"):
            try:
                sc.upload_track(audio, "t", "d")
                assert False, "should have raised"
            except sc.SoundCloudAuthError as e:
                assert "--setup" in str(e)


def test_upload_server_error_retries_once_then_raises():
    with tempfile.TemporaryDirectory() as td:
        audio = Path(td) / "set.mp3"; audio.write_bytes(b"x")
        patches, _ = _upload_env(td, [_resp(500, {"error": "boom"}),
                                      _resp(500, {"error": "boom"})])
        with patches[0], patches[1], patches[2], patches[3] as m:
            try:
                sc.upload_track(audio, "t", "d")
                assert False, "should have raised"
            except sc.SoundCloudAPIError as e:
                assert "500" in str(e)
        assert m.call_count == 2
