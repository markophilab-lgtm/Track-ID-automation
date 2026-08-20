# keylight/state.py
"""Small bits of state that outlive a single run, in ~/.keylight/.

Both entry points need these: `keylight.room` (the `issacnewton` command) and
`keylight.cli` (what Beat Link Trigger calls on every track change). The pause
flag is what keeps them from fighting — once BLT's trigger is installed, `off`
has to silence BLT too, or the next track repaints the room.
"""

import pathlib

STATE_DIR = pathlib.Path.home() / ".keylight"
PAUSE_FILE = "paused"


def state_file(name):
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    return STATE_DIR / name


def pause():
    """Stop honouring key changes until someone turns the room back on."""
    state_file(PAUSE_FILE).write_text(
        "issacnewton is off; delete this file or run `issacnewton on`\n")


def resume():
    """Start following the music again. Safe when not paused."""
    state_file(PAUSE_FILE).unlink(missing_ok=True)


def is_paused():
    return state_file(PAUSE_FILE).exists()
