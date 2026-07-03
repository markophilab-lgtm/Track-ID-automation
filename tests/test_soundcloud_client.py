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
    url = sc.build_authorize_url("CID", "CHAL")
    assert url.startswith("https://secure.soundcloud.com/authorize?")
    assert "client_id=CID" in url
    assert "code_challenge=CHAL" in url
    assert "code_challenge_method=S256" in url
    assert "response_type=code" in url
    assert "localhost%3A8766" in url


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
