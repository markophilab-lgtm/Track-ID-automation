"""Drop tracks whose duration as master was below a threshold."""

from datetime import datetime


def filter_short_tracks(tracks, min_seconds=30, end_time=None):
    """Return only tracks where (next_track.wall_time - this_track.wall_time) >= min_seconds.

    For the final track in the list, duration is computed against end_time (default: datetime.now()).
    """
    if not tracks:
        return []

    if end_time is None:
        end_time = datetime.now()

    kept = []
    for i, t in enumerate(tracks):
        if i < len(tracks) - 1:
            duration = (tracks[i + 1].wall_time - t.wall_time).total_seconds()
        else:
            duration = (end_time - t.wall_time).total_seconds()
        if duration >= min_seconds:
            kept.append(t)
    return kept
