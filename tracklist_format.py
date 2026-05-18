#!/usr/bin/env python3
"""
Tracklist Formatter
Reads a cdj_logger tracklist file, looks up each track on Discogs and Bandcamp,
and outputs a formatted tracklist ready to paste into YouTube/Mixcloud descriptions.

Usage:
    export DISCOGS_TOKEN="your_token_here"  # get free token at discogs.com/settings/developers
    python3 tracklist_format.py ~/tracklist_live.txt
    python3 tracklist_format.py ~/tracklist_live.txt --out ~/Desktop/set.txt
    python3 tracklist_format.py ~/tracklist_live.txt --session 2
"""

import sys
import os
import time
import argparse
from datetime import timedelta

from tracklist_parser import parse_log, Track
from tracklist_lookup import discogs_lookup, bandcamp_lookup

_UNKNOWN = {"unknown artist", "unknown title"}


def format_timedelta(td: timedelta) -> str:
    total = int(td.total_seconds())
    h, rem = divmod(total, 3600)
    m, s = divmod(rem, 60)
    if h:
        return f"{h}:{m:02d}:{s:02d}"
    return f"{m:02d}:{s:02d}"


def format_track(track: Track) -> str:
    ts = format_timedelta(track.relative_time)
    if track.artist.lower() in _UNKNOWN or track.title.lower() in _UNKNOWN:
        return f"{ts} [unidentified]"
    name = f"{track.artist} - {track.title}"
    discogs = track.discogs_url or "(no Discogs)"
    bandcamp = track.bandcamp_url or "(no Bandcamp)"
    return f"{ts} {name} | {discogs} | {bandcamp}"


def main():
    parser = argparse.ArgumentParser(description="Format CDJ tracklist with Discogs + Bandcamp links")
    parser.add_argument("logfile", help="Path to tracklist_live.txt")
    parser.add_argument("--out", help="Output file path (default: stdout only)")
    parser.add_argument("--session", type=int, default=None,
                        help="Session number to use (1=first). Omit to use the last session.")
    args = parser.parse_args()

    try:
        with open(os.path.expanduser(args.logfile)) as f:
            text = f.read()
    except FileNotFoundError:
        print(f"Error: log file not found: {args.logfile}", file=sys.stderr)
        sys.exit(1)
    sessions = parse_log(text)

    if not sessions:
        print("Error: no sessions found in log file.", file=sys.stderr)
        sys.exit(1)

    if args.session is None:
        idx = -1
    elif args.session < 1:
        print("Error: --session must be 1 or higher.", file=sys.stderr)
        sys.exit(1)
    else:
        idx = args.session - 1

    try:
        session = sessions[idx]
    except IndexError:
        print(f"Error: session {args.session} not found (file has {len(sessions)}).", file=sys.stderr)
        sys.exit(1)

    print(f"Processing {len(session.tracks)} tracks...", file=sys.stderr)

    lines = []
    for i, track in enumerate(session.tracks, 1):
        print(f"  [{i}/{len(session.tracks)}] {track.artist} — {track.title}", file=sys.stderr)
        if track.artist.lower() not in _UNKNOWN and track.title.lower() not in _UNKNOWN:
            track.discogs_url = discogs_lookup(track.artist, track.title)
            track.bandcamp_url = bandcamp_lookup(track.artist, track.title)
            if i < len(session.tracks):
                time.sleep(1)
        lines.append(format_track(track))

    output = "\n".join(lines)
    print(output)

    if args.out:
        with open(os.path.expanduser(args.out), "w") as f:
            f.write(output + "\n")
        print(f"\nSaved to {args.out}", file=sys.stderr)


if __name__ == "__main__":
    main()
