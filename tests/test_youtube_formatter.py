import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from timestamp_builder import Chapter
from youtube_formatter import format_youtube


def _chap(secs, ts, artist, title, discogs="", songlink=""):
    return Chapter(
        time_seconds=secs, time_str=ts, artist=artist, title=title,
        discogs_url=discogs, songlink_url=songlink,
    )


def test_full_description():
    chapters = [
        _chap(0, "0:00", "Intro", "Intro"),
        _chap(323, "5:23", "Anthony Naples", "Crystals",
              "discogs.com/release/12345", "https://song.link/i/abc"),
        _chap(767, "12:47", "Joy Orbison", "Hyph Mngo",
              "discogs.com/release/67890", "https://song.link/i/def"),
    ]
    out = format_youtube(chapters, date(2026, 5, 17))
    expected = (
        "Tracklist:\n"
        "\n"
        "0:00 Intro\n"
        "5:23 Anthony Naples — Crystals | https://discogs.com/release/12345 | https://song.link/i/abc\n"
        "12:47 Joy Orbison — Hyph Mngo | https://discogs.com/release/67890 | https://song.link/i/def\n"
        "\n"
        "Recorded live 2026-05-17.\n"
        "Promotional use only — not monetized."
    )
    assert out == expected, f"\nExpected:\n{expected}\n\nGot:\n{out}"


def test_missing_links_show_no_link():
    chapters = [
        _chap(0, "0:00", "Intro", "Intro"),
        _chap(60, "1:00", "A", "B", discogs="", songlink=""),
    ]
    out = format_youtube(chapters, date(2026, 5, 17))
    assert "1:00 A — B | (no link) | (no link)" in out


def test_unidentified_track_format():
    chapters = [
        _chap(0, "0:00", "Intro", "Intro"),
        _chap(60, "1:00", "Unknown Artist", "Unknown Title"),
    ]
    out = format_youtube(chapters, date(2026, 5, 17))
    assert "1:00 [unidentified]" in out
    assert "Unknown Artist" not in out


def test_discogs_gets_https_prefix():
    chapters = [
        _chap(0, "0:00", "Intro", "Intro"),
        _chap(60, "1:00", "A", "B", discogs="discogs.com/release/1"),
    ]
    out = format_youtube(chapters, date(2026, 5, 17))
    assert "https://discogs.com/release/1" in out


def test_already_prefixed_url_not_doubled():
    chapters = [
        _chap(0, "0:00", "Intro", "Intro"),
        _chap(60, "1:00", "A", "B", discogs="https://discogs.com/release/1"),
    ]
    out = format_youtube(chapters, date(2026, 5, 17))
    assert "https://https://" not in out
    assert "https://discogs.com/release/1" in out


def test_promo_note_is_last_line():
    chapters = [_chap(0, "0:00", "Intro", "Intro")]
    out = format_youtube(chapters, date(2026, 5, 17))
    assert out.splitlines()[-1] == "Promotional use only — not monetized."
