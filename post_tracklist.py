#!/usr/bin/env python3
"""
Post-stream tracklist publisher.

Pipeline:
  1. Find latest OBS recording in ~/Movies (or --movie) -> stream_start datetime
  2. Read ~/Desktop/tracklist_live.txt (or --log), pick latest session (or --session)
  3. Filter tracks with master-duration < 30s
  4. Build chapters relative to stream_start (with 0:00 Intro rules)
  5. For each chapter: look up Discogs + Songlink (paced)
  6. Update Mixcloud cloudcast (description + sections) unless --skip-mixcloud
  7. Copy YouTube-formatted description to clipboard unless --skip-youtube
  8. Show macOS notification with result
"""

import argparse
import os
import sys
import time
from datetime import datetime
from pathlib import Path

from tracklist_parser import parse_log
from tracklist_lookup import discogs_lookup

from stream_anchor import find_latest_movie, _FILENAME_PATTERN
from track_filter import filter_short_tracks
from timestamp_builder import build_chapters
from songlink_lookup import songlink_url
from youtube_formatter import format_youtube, format_mixcloud
from clipboard_and_notify import copy_to_clipboard, notify
from mixcloud_client import (
    ensure_token, get_me, latest_cloudcast, update_cloudcast,
    MixcloudAuthError, MixcloudAPIError,
)

DEFAULT_LOG = "~/Desktop/tracklist_live.txt"
DEFAULT_MOVIES = "~/Movies"

# Per-track pacing: total ~7s between consecutive track lookups, which keeps us under
# Songlink's ~10 req/min limit (the strictest of the three APIs we call per track).
SLEEP_BETWEEN_TRACKS = 7.0


def _prompt_mixcloud_app_creds():
    print("\nFirst-time Mixcloud setup:")
    print("  1. Go to https://www.mixcloud.com/developers/create/")
    print("  2. Create an app with redirect URI: http://localhost:8765/callback")
    print("  3. Copy the Client ID and Client Secret it gives you.")
    cid = input("\nClient ID: ").strip()
    secret = input("Client Secret: ").strip()
    return cid, secret


def _resolve_movie_path(arg):
    if arg:
        p = Path(os.path.expanduser(arg))
        if not p.is_file():
            raise FileNotFoundError(f"Movie file not found: {p}")
        # Try to parse the timestamp from the filename
        m = _FILENAME_PATTERN.match(p.name)
        if not m:
            raise ValueError(f"Filename does not match expected pattern YYYY-MM-DD HH-MM-SS.mov: {p.name}")
        date_str, hh, mm, ss = m.groups()
        ts = datetime.strptime(f"{date_str} {hh}:{mm}:{ss}", "%Y-%m-%d %H:%M:%S")
        return p, ts
    return find_latest_movie(DEFAULT_MOVIES)


def _enrich_chapters(chapters):
    """Mutate chapters list in place, filling discogs_url and songlink_url.

    Paces 7s between consecutive track lookups (no sleep before the first track).
    This keeps us under Songlink's ~10 req/min limit. Discogs and iTunes are
    less strict and well within budget at this rate.
    """
    first_real = True
    for i, ch in enumerate(chapters):
        if ch.artist == "Intro" or ch.artist == "Unknown Artist":
            continue
        if not first_real:
            time.sleep(SLEEP_BETWEEN_TRACKS)
        first_real = False
        print(f"  [{i+1}/{len(chapters)}] {ch.artist} — {ch.title}", file=sys.stderr)
        ch.discogs_url = discogs_lookup(ch.artist, ch.title)
        ch.songlink_url = songlink_url(ch.artist, ch.title)


def _post_to_mixcloud(token, slug_override, description, chapters):
    """Returns (success: bool, message: str)."""
    try:
        username = get_me(token)
        if slug_override:
            slug = slug_override
            cloudcast_name = slug_override
        else:
            cc = latest_cloudcast(token, username=username)
            slug = cc["slug"]
            cloudcast_name = cc.get("name", slug)
        print(f"  Targeting Mixcloud cloudcast: {cloudcast_name}", file=sys.stderr)
        update_cloudcast(token, username, slug, description, chapters)
        return True, f"Posted to Mixcloud: {cloudcast_name}"
    except MixcloudAuthError as e:
        return False, f"Mixcloud auth failed: {e}"
    except MixcloudAPIError as e:
        return False, f"Mixcloud API error: {e}"


def main(argv=None):
    parser = argparse.ArgumentParser(description="Post timestamped tracklist to Mixcloud + YouTube clipboard.")
    parser.add_argument("--movie", help="Path to OBS recording (default: newest in ~/Movies)")
    parser.add_argument("--cloudcast", help="Override Mixcloud cloudcast slug")
    parser.add_argument("--log", default=DEFAULT_LOG, help="Path to tracklist_live.txt")
    parser.add_argument("--session", type=int, default=None, help="Session number (1-based); default last")
    parser.add_argument("--dry-run", action="store_true", help="Build everything but post/copy nothing")
    parser.add_argument("--skip-mixcloud", action="store_true")
    parser.add_argument("--skip-youtube", action="store_true")
    args = parser.parse_args(argv)

    # 1. Find recording -> stream_start
    try:
        movie_path, stream_start = _resolve_movie_path(args.movie)
    except FileNotFoundError as e:
        print(f"Error: {e}\n"
              f"Hint: pass --movie /path/to/file.mov to override.", file=sys.stderr)
        return 2
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 2
    print(f"Stream start: {stream_start.isoformat()} (from {movie_path.name})", file=sys.stderr)

    # 2. Read log -> session -> tracks
    log_path = Path(os.path.expanduser(args.log))
    if not log_path.exists():
        print(f"Error: log file not found at {log_path}\n"
              f"Was Beat Link Trigger open during the stream?", file=sys.stderr)
        return 2
    sessions = parse_log(log_path.read_text())
    if not sessions:
        print(f"Error: no sessions found in {log_path}\n"
              f"Was Beat Link Trigger open during the stream?", file=sys.stderr)
        return 2
    idx = -1 if args.session is None else args.session - 1
    try:
        session = sessions[idx]
    except IndexError:
        print(f"Error: session {args.session} not found (file has {len(sessions)})", file=sys.stderr)
        return 2

    # 3. Filter short tracks
    before = len(session.tracks)
    kept = filter_short_tracks(session.tracks, min_seconds=30)
    print(f"Filtered {before - len(kept)} short tracks (< 30s).", file=sys.stderr)

    # 4. Build chapters
    chapters = build_chapters(kept, stream_start)
    if not chapters:
        print("Error: No tracks survived filtering. Nothing to post.", file=sys.stderr)
        return 2

    # 5. Enrich with links (skip on dry-run to keep fast)
    if not args.dry_run:
        print(f"Looking up links for {len(chapters)} chapters...", file=sys.stderr)
        _enrich_chapters(chapters)

    # 6. Build descriptions (YouTube = full tracklist with links; Mixcloud = short prose,
    # tracklist is sent separately as `sections` and Mixcloud caps description at 1000 chars).
    yt_description = format_youtube(chapters, stream_start.date())
    mc_description = format_mixcloud(stream_start.date())

    if args.dry_run:
        print("\n--- DRY RUN: description that would be used ---\n", file=sys.stderr)
        print(yt_description)
        print("\n--- end dry run ---", file=sys.stderr)
        return 0

    # 7. Mixcloud
    mc_message = "(Mixcloud skipped via flag)"
    mc_ok = True
    if not args.skip_mixcloud:
        try:
            token = ensure_token(prompt_for_app_creds_fn=_prompt_mixcloud_app_creds)
        except Exception as e:
            mc_ok = False
            mc_message = f"Mixcloud setup failed: {e}"
            token = None
        if token:
            mc_ok, mc_message = _post_to_mixcloud(token, args.cloudcast, mc_description, chapters)

    # 8. YouTube clipboard
    yt_message = "(YouTube clipboard skipped via flag)"
    if not args.skip_youtube:
        try:
            copy_to_clipboard(yt_description)
            yt_message = "YouTube description copied to clipboard"
        except Exception as e:
            print(yt_description)  # fallback to stdout
            yt_message = f"Clipboard failed: {e} (description printed above)"

    # 9. Notify
    summary_title = "Tracklist posted" if mc_ok and not args.skip_mixcloud else "Partial success"
    summary_body = f"{mc_message}. {yt_message}."
    print(f"\n{summary_title}\n{summary_body}", file=sys.stderr)
    try:
        notify(summary_title, summary_body)
    except Exception:
        pass

    return 0


if __name__ == "__main__":
    sys.exit(main())
