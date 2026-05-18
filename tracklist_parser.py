import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta

@dataclass
class Track:
    wall_time: datetime
    relative_time: timedelta
    player: str
    artist: str
    title: str
    album: str = ""
    discogs_url: str = ""
    bandcamp_url: str = ""

@dataclass
class Session:
    start_time: datetime
    tracks: list[Track] = field(default_factory=list)

_SESSION_START = re.compile(r"─── Session started (\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) ───")
_TRACK_LINE = re.compile(
    r"(\d{2}:\d{2}:\d{2})\s+\[([^\]]+)\]\s+(.+?) — (.+?)(?:\s+\((.+?)\))?\s*$"
)

def parse_log(text: str) -> list[Session]:
    sessions = []
    current = None

    for line in text.splitlines():
        m = _SESSION_START.search(line)
        if m:
            current = Session(start_time=datetime.strptime(m.group(1), "%Y-%m-%d %H:%M:%S"))
            sessions.append(current)
            continue

        if current is None:
            continue

        m = _TRACK_LINE.match(line.strip())
        if not m:
            continue

        time_str, player, artist, title, album = m.groups()
        wall_time = datetime.strptime(
            current.start_time.strftime("%Y-%m-%d") + " " + time_str,
            "%Y-%m-%d %H:%M:%S"
        )
        # Handle sets that run past midnight
        if wall_time < current.start_time:
            wall_time = wall_time + timedelta(days=1)

        current.tracks.append(Track(
            wall_time=wall_time,
            relative_time=wall_time - current.start_time,
            player=player,
            artist=artist,
            title=title,
            album=album or "",
        ))

    return sessions
