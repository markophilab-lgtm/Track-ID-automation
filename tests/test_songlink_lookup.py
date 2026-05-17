import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

sys.path.insert(0, str(Path(__file__).parent.parent))

import songlink_lookup
from songlink_lookup import songlink_url


def _resp(status, json_body=None):
    r = MagicMock()
    r.status_code = status
    r.json.return_value = json_body if json_body is not None else {}
    return r


def test_happy_path():
    itunes_resp = _resp(200, {"results": [{"trackViewUrl": "https://music.apple.com/x/y/z"}]})
    songlink_resp = _resp(200, {"pageUrl": "https://song.link/i/AbCdEf"})
    with patch.object(songlink_lookup.requests, "get", side_effect=[itunes_resp, songlink_resp]):
        url = songlink_url("Anthony Naples", "Crystals")
    assert url == "https://song.link/i/AbCdEf"


def test_itunes_no_results_returns_empty():
    itunes_resp = _resp(200, {"results": []})
    with patch.object(songlink_lookup.requests, "get", return_value=itunes_resp):
        url = songlink_url("Unknown Artist", "Unknown Title")
    assert url == ""


def test_itunes_http_error_returns_empty():
    itunes_resp = _resp(500)
    with patch.object(songlink_lookup.requests, "get", return_value=itunes_resp):
        url = songlink_url("X", "Y")
    assert url == ""


def test_itunes_429_retries_once():
    first = _resp(429)
    second = _resp(200, {"results": [{"trackViewUrl": "https://music.apple.com/x/y/z"}]})
    third = _resp(200, {"pageUrl": "https://song.link/i/Final"})
    with patch.object(songlink_lookup.requests, "get", side_effect=[first, second, third]):
        with patch.object(songlink_lookup.time, "sleep"):  # don't actually sleep in tests
            url = songlink_url("X", "Y")
    assert url == "https://song.link/i/Final"


def test_songlink_failure_returns_empty():
    itunes_resp = _resp(200, {"results": [{"trackViewUrl": "https://music.apple.com/x/y/z"}]})
    songlink_resp = _resp(500)
    with patch.object(songlink_lookup.requests, "get", side_effect=[itunes_resp, songlink_resp]):
        url = songlink_url("X", "Y")
    assert url == ""


def test_network_exception_returns_empty():
    with patch.object(songlink_lookup.requests, "get", side_effect=ConnectionError("boom")):
        url = songlink_url("X", "Y")
    assert url == ""


def test_missing_trackViewUrl_returns_empty():
    itunes_resp = _resp(200, {"results": [{"otherField": "value"}]})
    with patch.object(songlink_lookup.requests, "get", return_value=itunes_resp):
        url = songlink_url("X", "Y")
    assert url == ""
