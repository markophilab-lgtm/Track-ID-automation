import os
import time
import requests
from bs4 import BeautifulSoup

_HEADERS = {"User-Agent": "TracklistFormatter/1.0"}
_DISCOGS_TOKEN = os.environ.get("DISCOGS_TOKEN", "")
_DISCOGS_SEARCH = "https://api.discogs.com/database/search"
_BANDCAMP_SEARCH = "https://bandcamp.com/search"


def discogs_lookup(artist: str, title: str) -> str:
    params = {"q": f"{artist} {title}", "type": "release"}
    headers = dict(_HEADERS)
    if _DISCOGS_TOKEN:
        headers["Authorization"] = f"Discogs token={_DISCOGS_TOKEN}"
    try:
        resp = requests.get(_DISCOGS_SEARCH, params=params, headers=headers, timeout=10)
        if resp.status_code == 429:
            time.sleep(1)
            resp = requests.get(_DISCOGS_SEARCH, params=params, headers=headers, timeout=10)
        if resp.status_code != 200:
            return ""
        results = resp.json().get("results", [])
        if not results:
            return ""
        release_id = results[0].get("id")
        if not release_id:
            return ""
        return f"discogs.com/release/{release_id}"
    except Exception:
        return ""


def bandcamp_lookup(artist: str, title: str) -> str:
    try:
        params = {"q": f"{artist} {title}", "item_type": "t"}
        resp = requests.get(_BANDCAMP_SEARCH, params=params, headers=_HEADERS, timeout=10)
        if resp.status_code == 429:
            time.sleep(1)
            resp = requests.get(_BANDCAMP_SEARCH, params=params, headers=_HEADERS, timeout=10)
        if resp.status_code != 200:
            return ""
        soup = BeautifulSoup(resp.text, "html.parser")
        result = soup.select_one("li.searchresult.track .itemurl a")
        if not result:
            return ""
        href = result.get("href") or ""
        return href.replace("https://", "").replace("http://", "").split("?")[0]
    except Exception:
        return ""
