#!/usr/bin/env python3
"""Watches tracklist_live.txt and keeps now_playing.txt updated with ONLY the
current track, so OBS can show a clean 'now playing' overlay.

Run this in Terminal during a set:  python3 now_playing.py
Stop it with Control-C.
"""

import os
import sys
import time

HOME = os.path.expanduser("~")
SOURCE = os.path.join(HOME, "Desktop", "tracklist_live.txt")
TARGET = os.path.join(HOME, "Desktop", "now_playing.txt")
POLL_SECONDS = 1.0
# Added to the end of the text so that when OBS scrolls/loops the overlay,
# there's a clear gap before the title repeats (instead of running together).
SUFFIX = "   •   "
# With the --space flag, use a long run of spaces instead, so the scrolling
# text takes much longer to come back around (a big blank gap, no symbol).
SUFFIX_SPACE = " " * 60


def latest_track(path):
    """Return 'Artist — Title' from the most recent real track line, or None."""
    try:
        with open(path, "r", encoding="utf-8") as f:
            lines = f.readlines()
    except FileNotFoundError:
        return None
    for line in reversed(lines):
        line = line.strip()
        # Skip blank lines and the "─── Session started ───" header lines
        if not line or line.startswith("─"):
            continue
        # A track line looks like:  18:09:28  [Player 3]  Boddika — Basement
        # Take everything after the "]" to drop the time + player prefix.
        idx = line.find("]")
        if idx == -1:
            continue
        return line[idx + 1:].strip()
    return None


def main():
    suffix = SUFFIX_SPACE if "--space" in sys.argv else SUFFIX
    print("Now-playing watcher is running. Press Control-C to stop.")
    print(f"  Reading:  {SOURCE}")
    print(f"  Writing:  {TARGET}")
    print(f"  Spacing:  {'big gap (--space)' if suffix is SUFFIX_SPACE else 'dot'}\n")
    last_written = None
    last_mtime = None
    while True:
        try:
            mtime = os.path.getmtime(SOURCE)
        except FileNotFoundError:
            mtime = None
        if mtime != last_mtime:
            last_mtime = mtime
            track = latest_track(SOURCE)
            if track and track != last_written:
                with open(TARGET, "w", encoding="utf-8") as f:
                    f.write(track + suffix)
                last_written = track
                print(f"Now playing: {track}")
        time.sleep(POLL_SECONDS)


if __name__ == "__main__":
    main()
