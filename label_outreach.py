"""Deterministic helpers for label outreach: parsing, Discogs lookups, dedup cache."""
import json
import os
import re
import sys
import tempfile
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional

import requests

import tracklist_parser
import track_filter


_DISCOGS_SEARCH = "https://api.discogs.com/database/search"
_DISCOGS_RELEASE = "https://api.discogs.com/releases"
_DISCOGS_LABEL = "https://api.discogs.com/labels"
_USER_AGENT = "TracklistLabelOutreach/1.0"
_EMAIL_REGEX = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")

VALID_SOURCES = frozenset({"discogs", "websearch", "manual"})


@dataclass
class ContactedEntry:
    name: str
    email: str
    source: str  # must be in VALID_SOURCES


@dataclass
class LabelInfo:
    tracks: list
    discogs_label_url: str
    discogs_contact_email: str  # "" if not found in contactinfo


def _normalize(label: str) -> str:
    return label.strip().lower()


class CorruptCacheError(Exception):
    """Cache file exists but contains invalid JSON."""


def _read_cache(cache_path: Path) -> dict:
    try:
        return json.loads(cache_path.read_text())
    except json.JSONDecodeError as e:
        raise CorruptCacheError(
            f"cache file is corrupt (invalid JSON): {cache_path} ({e.msg} at line {e.lineno})"
        ) from e


def load_contacted(cache_path: Path) -> set:
    if not cache_path.exists():
        return set()
    data = _read_cache(cache_path)
    out = set()
    for entry in data.get("labels", []):
        out.add(entry.get("name_normalized") or _normalize(entry["name"]))
    return out


def save_contacted(cache_path: Path, new_entries: list) -> None:
    cache_path.parent.mkdir(mode=0o700, exist_ok=True, parents=True)
    os.chmod(cache_path.parent, 0o700)

    if cache_path.exists():
        data = _read_cache(cache_path)
    else:
        data = {"labels": []}

    now_iso = datetime.now().isoformat(timespec="seconds")
    for entry in new_entries:
        data["labels"].append({
            "name": entry.name,
            "name_normalized": _normalize(entry.name),
            "email": entry.email,
            "first_contacted": now_iso,
            "source": entry.source,
        })

    fd, tmp_path = tempfile.mkstemp(prefix=".contacted_", dir=str(cache_path.parent))
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(data, f, indent=2)
        os.chmod(tmp_path, 0o600)
        os.replace(tmp_path, cache_path)
    except Exception:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)
        raise


def parse_latest_session(log_path: Path, end_time: Optional[datetime] = None) -> list:
    if not log_path.exists():
        return []
    sessions = tracklist_parser.parse_log(log_path.read_text())
    if not sessions:
        return []
    latest = sessions[-1]
    return track_filter.filter_short_tracks(
        latest.tracks, min_seconds=30, end_time=end_time
    )


def _discogs_get(url: str, params: dict, token: Optional[str]) -> Optional[dict]:
    headers = {"User-Agent": _USER_AGENT}
    if token:
        headers["Authorization"] = f"Discogs token={token}"
    try:
        resp = requests.get(url, params=params, headers=headers, timeout=10)
        if resp.status_code == 429:
            time.sleep(1)
            resp = requests.get(url, params=params, headers=headers, timeout=10)
        if resp.status_code != 200:
            return None
        return resp.json()
    except Exception:
        return None


def _extract_email(text: str) -> str:
    if not text:
        return ""
    m = _EMAIL_REGEX.search(text)
    return m.group(0) if m else ""


def group_by_label(tracks: list, discogs_token: Optional[str]) -> dict:
    release_cache: dict = {}
    label_for_release: dict = {}
    label_contactinfo: dict = {}
    groups: dict = {}

    for track in tracks:
        key = (track.artist, track.title)

        if key not in release_cache:
            data = _discogs_get(
                _DISCOGS_SEARCH,
                {"q": f"{track.artist} {track.title}", "type": "release"},
                discogs_token,
            )
            results = (data or {}).get("results", [])
            release_cache[key] = results[0].get("id") if results else None

        release_id = release_cache[key]
        if release_id is None:
            continue

        if release_id not in label_for_release:
            data = _discogs_get(f"{_DISCOGS_RELEASE}/{release_id}", {}, discogs_token)
            labels = (data or {}).get("labels", []) if data else []
            if labels:
                label_for_release[release_id] = (labels[0].get("id"),
                                                 labels[0].get("name"))
            else:
                label_for_release[release_id] = None

        label_pair = label_for_release[release_id]
        if label_pair is None:
            continue

        label_id, label_name = label_pair
        if not label_name:
            continue

        if label_id not in label_contactinfo:
            data = _discogs_get(f"{_DISCOGS_LABEL}/{label_id}", {}, discogs_token)
            label_contactinfo[label_id] = (data or {}).get("contactinfo", "") if data else ""

        email = _extract_email(label_contactinfo[label_id])

        if label_name not in groups:
            groups[label_name] = LabelInfo(
                tracks=[],
                discogs_label_url=f"https://www.discogs.com/label/{label_id}",
                discogs_contact_email=email,
            )
        groups[label_name].tracks.append(track)

    return groups


def _cli_enrich(log_path: Path, cache_path: Path, end_time: Optional[datetime]) -> int:
    tracks = parse_latest_session(log_path, end_time=end_time)
    if not tracks:
        print("no session found in log", file=sys.stderr)
        return 2

    try:
        already = load_contacted(cache_path)
    except CorruptCacheError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 3

    discogs_token = os.environ.get("DISCOGS_TOKEN") or None
    groups = group_by_label(tracks, discogs_token=discogs_token)

    out = []
    for label_name, info in groups.items():
        if _normalize(label_name) in already:
            continue
        out.append({
            "label": label_name,
            "tracks": [{"artist": t.artist, "title": t.title} for t in info.tracks],
            "discogs_label_url": info.discogs_label_url,
            "discogs_contact_email": info.discogs_contact_email,
        })

    print(json.dumps(out, indent=2))
    return 0


def _cli_mark_contacted_from_stdin(cache_path: Path) -> int:
    """Read a JSON list from stdin and append entries to the cache.

    Expected stdin shape:
        [{"name": "Hessle Audio", "email": "info@hessleaudio.com", "source": "discogs"}, ...]

    `source` must be one of "discogs", "websearch", "manual". JSON avoids the
    shell-escape problems of comma/pipe-separated args (label names can contain
    those characters).
    """
    raw = sys.stdin.read().strip()
    if not raw:
        print("ERROR: --labels-stdin expected a JSON list on stdin", file=sys.stderr)
        return 4

    try:
        items = json.loads(raw)
    except json.JSONDecodeError as e:
        print(f"ERROR: stdin is not valid JSON: {e}", file=sys.stderr)
        return 4

    if not isinstance(items, list):
        print("ERROR: stdin JSON must be a list of {name, email, source} objects",
              file=sys.stderr)
        return 4

    if not items:
        # No-op: nothing to mark. Successful exit so the subagent doesn't choke.
        return 0

    entries = []
    for item in items:
        if not isinstance(item, dict):
            print(f"ERROR: each entry must be an object, got {type(item).__name__}",
                  file=sys.stderr)
            return 4
        name = item.get("name", "").strip()
        if not name:
            print("ERROR: entry missing 'name'", file=sys.stderr)
            return 4
        source = item.get("source")
        if source not in VALID_SOURCES:
            print(f"ERROR: invalid or missing source '{source}' "
                  f"(required, one of: {sorted(VALID_SOURCES)})", file=sys.stderr)
            return 4
        entries.append(ContactedEntry(
            name=name,
            email=item.get("email", "").strip(),
            source=source,
        ))

    try:
        save_contacted(cache_path, entries)
    except CorruptCacheError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 3
    return 0


def main(argv=None):
    import argparse
    p = argparse.ArgumentParser(
        description="Label outreach helper for the DJ tracklist pipeline."
    )
    p.add_argument("--action", required=True, choices=["enrich", "mark-contacted"])
    p.add_argument("--log", type=Path, help="Path to tracklist_live.txt (required for enrich)")
    p.add_argument("--cache", type=Path, required=True,
                   help="Path to contacted_labels.json")
    p.add_argument("--labels-stdin", action="store_true",
                   help="For mark-contacted: read JSON list from stdin")
    p.add_argument("--end-time", type=str,
                   help="ISO 8601 timestamp used as the end-of-last-track bound (optional)")
    args = p.parse_args(argv)

    if args.action == "enrich":
        if not args.log:
            p.error("--log is required for --action enrich")
        end_time = datetime.fromisoformat(args.end_time) if args.end_time else None
        return _cli_enrich(args.log, args.cache, end_time)
    elif args.action == "mark-contacted":
        if not args.labels_stdin:
            p.error("--labels-stdin is required for --action mark-contacted")
        return _cli_mark_contacted_from_stdin(args.cache)


if __name__ == "__main__":
    sys.exit(main())
