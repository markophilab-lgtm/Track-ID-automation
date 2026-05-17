"""Look up universal listen-here links via iTunes Search + Songlink."""

import time
import requests

_ITUNES_SEARCH = "https://itunes.apple.com/search"
_SONGLINK = "https://api.song.link/v1-alpha.1/links"
_TIMEOUT = 10
_RETRY_SLEEP_429 = 30  # seconds to wait before retrying after a 429


def _itunes_track_url(artist, title):
    """Return the iTunes trackViewUrl for the top match, or '' on any failure."""
    params = {"term": f"{artist} {title}", "entity": "song", "limit": 1}
    try:
        resp = requests.get(_ITUNES_SEARCH, params=params, timeout=_TIMEOUT)
        if resp.status_code == 429:
            time.sleep(_RETRY_SLEEP_429)
            resp = requests.get(_ITUNES_SEARCH, params=params, timeout=_TIMEOUT)
        if resp.status_code != 200:
            return ""
        results = resp.json().get("results", [])
        if not results:
            return ""
        return results[0].get("trackViewUrl", "")
    except Exception:
        return ""


def _songlink_page_url(itunes_url):
    """Pass an iTunes URL to Songlink, return its pageUrl, or '' on any failure."""
    params = {"url": itunes_url}
    try:
        resp = requests.get(_SONGLINK, params=params, timeout=_TIMEOUT)
        if resp.status_code == 429:
            time.sleep(_RETRY_SLEEP_429)
            resp = requests.get(_SONGLINK, params=params, timeout=_TIMEOUT)
        if resp.status_code != 200:
            return ""
        return resp.json().get("pageUrl", "")
    except Exception:
        return ""


def songlink_url(artist, title):
    """Public entrypoint: artist+title -> universal song.link URL, or '' on any failure."""
    itunes_url = _itunes_track_url(artist, title)
    if not itunes_url:
        return ""
    return _songlink_page_url(itunes_url)
