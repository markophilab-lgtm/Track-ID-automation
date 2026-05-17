"""Render a YouTube-chapter-formatted tracklist description from a Chapter list."""


def _prefix_https(url):
    if not url:
        return "(no link)"
    if url.startswith("http://") or url.startswith("https://"):
        return url
    return f"https://{url}"


def _chapter_line(ch):
    if ch.artist == "Intro" and ch.title == "Intro":
        return f"{ch.time_str} Intro"
    if ch.artist == "Unknown Artist" or ch.title == "Unknown Title":
        return f"{ch.time_str} [unidentified]"
    discogs = _prefix_https(ch.discogs_url)
    songlink = _prefix_https(ch.songlink_url)
    return f"{ch.time_str} {ch.artist} — {ch.title} | {discogs} | {songlink}"


def format_youtube(chapters, stream_date):
    """Return the YouTube description string. stream_date is a datetime.date."""
    lines = ["Tracklist:", ""]
    for ch in chapters:
        lines.append(_chapter_line(ch))
    lines.append("")
    lines.append(f"Recorded live {stream_date.isoformat()}.")
    return "\n".join(lines)
