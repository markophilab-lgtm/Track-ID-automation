"""Build YouTube/Mixcloud chapter list from tracks + stream-start datetime."""

from dataclasses import dataclass, field
from datetime import datetime


MIN_TRACK_SECONDS = 30  # short-track filter threshold (used by track_filter)
MIN_CHAPTER_GAP = 10    # YouTube minimum chapter duration


@dataclass
class Chapter:
    time_seconds: int
    time_str: str
    artist: str
    title: str
    discogs_url: str = ""
    songlink_url: str = ""


def format_time(seconds):
    """Format integer seconds as 'M:SS' (< 1h) or 'H:MM:SS' (>= 1h)."""
    seconds = int(seconds)
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    if h > 0:
        return f"{h}:{m:02d}:{s:02d}"
    return f"{m}:{s:02d}"


def build_chapters(tracks, stream_start):
    """Return a list of Chapter objects.

    - Tracks logged before stream_start are skipped.
    - If the first remaining track starts within MIN_CHAPTER_GAP (10s) of stream_start,
      it BECOMES the 0:00 chapter (no separate Intro).
    - Otherwise, a synthetic 'Intro' chapter is inserted at 0:00.
    """
    in_stream = []
    skipped = 0
    for t in tracks:
        offset = (t.wall_time - stream_start).total_seconds()
        if offset < 0:
            skipped += 1
            continue
        in_stream.append((int(offset), t))

    if skipped:
        print(f"Skipped {skipped} pre-stream tracks")

    if not in_stream:
        return []

    chapters = []
    first_offset = in_stream[0][0]

    if first_offset < MIN_CHAPTER_GAP:
        _, first_t = in_stream[0]
        chapters.append(Chapter(
            time_seconds=0,
            time_str=format_time(0),
            artist=first_t.artist,
            title=first_t.title,
        ))
        rest = in_stream[1:]
    else:
        chapters.append(Chapter(
            time_seconds=0,
            time_str=format_time(0),
            artist="Intro",
            title="Intro",
        ))
        rest = in_stream

    for offset, t in rest:
        chapters.append(Chapter(
            time_seconds=offset,
            time_str=format_time(offset),
            artist=t.artist,
            title=t.title,
        ))

    return chapters
