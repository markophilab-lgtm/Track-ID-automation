# keylight/room.py
"""Whole-room switch for key-to-light — what the `issacnewton` alias runs.

    issacnewton              turn it on, in the last key used
    issacnewton 9B           turn it on in G major
    issacnewton off          put the previous LEDfx scene back
    issacnewton status       say what the room is doing right now

Turning it on saves whatever LEDfx was showing first, so `off` can put the
exact same look back — including effects that bass mode replaces.
"""

import argparse
import json
import pathlib
import sys

from keylight import cli
from keylight.keys import parse_key
from keylight.ledfx import LedfxClient, BASS_EFFECT, BASS_FLOOR
from keylight.newton import color_for_key

STATE_DIR = pathlib.Path.home() / ".keylight"
DEFAULT_KEY = "D"


def _state_file(name):
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    return STATE_DIR / name


def active_effects(client):
    """{virtual_id: {"type", "config"}} for every virtual running an effect."""
    data = client._get("/api/virtuals")
    out = {}
    for vid, vdata in data.get("virtuals", {}).items():
        effect = vdata.get("effect") or {}
        if effect.get("type") and isinstance(effect.get("config"), dict):
            out[vid] = {"type": effect["type"], "config": effect["config"]}
    return out


def is_bass_mode(effects):
    """True when the room is already showing our bass-reactive effect."""
    return bool(effects) and all(
        e["type"] == BASS_EFFECT and e["config"].get("frequency_range") == "Bass"
        for e in effects.values())


def save_scene(client):
    """Back up the current look, unless it's already ours (that would lose it)."""
    effects = active_effects(client)
    if is_bass_mode(effects):
        return 0
    _state_file("scene_backup.json").write_text(json.dumps(effects, indent=1))
    return len(effects)


def restore_scene(client):
    """Put the saved scene back. Returns virtuals restored, or -1 if none saved."""
    path = _state_file("scene_backup.json")
    if not path.exists():
        return -1
    for vid, effect in json.loads(path.read_text()).items():
        client._put(f"/api/virtuals/{vid}/effects", effect)
    return len(json.loads(path.read_text()))


def describe(client):
    effects = active_effects(client)
    if not effects:
        return "No LEDfx effects are running."
    if is_bass_mode(effects):
        colors = {e["config"].get("background_color") for e in effects.values()}
        floor = {e["config"].get("background_brightness") for e in effects.values()}
        key = _state_file("last_key")
        key_txt = f" (key {key.read_text().strip()})" if key.exists() else ""
        return (f"Bass mode ON across {len(effects)} strips{key_txt}: "
                f"color {', '.join(sorted(c for c in colors if c))}, "
                f"dipping to {int(min(floor) * 100)}% between kicks.")
    kinds = sorted({e["type"] for e in effects.values()})
    return (f"Bass mode is OFF. {len(effects)} strips running your own effects "
            f"({', '.join(kinds)}).")


def main(argv=None, opener=None):
    parser = argparse.ArgumentParser(
        prog="issacnewton",
        description="Colour the room by the key of the music, Newton style.")
    # One loose list rather than fixed positions, so every order a tired hand
    # might type at 2am works: "9B", "on 9B", "9B --flat", "on --flat 9B".
    parser.add_argument("words", nargs="*", metavar="[on|off|status] [KEY]",
                        help='e.g. "issacnewton 9B", "issacnewton off"')
    parser.add_argument("--flat", action="store_true",
                        help="steady colour instead of pulsing with the bass")
    parser.add_argument("--floor", type=float, default=BASS_FLOOR, metavar="F",
                        help="dimmest between kicks, 0-1 (default: %(default)s)")
    parser.add_argument("--base-url", default="http://127.0.0.1:8888")
    # parse_known_args because argparse before 3.12 drops positionals that
    # follow an option ("on --flat 8A" loses the 8A otherwise).
    args, leftover = parser.parse_known_args(argv)
    for stray in leftover:
        if stray.startswith("-"):
            print(f"issacnewton: don't know the option {stray!r}",
                  file=sys.stderr)
            return 2
    words = list(args.words) + leftover

    command, key = "on", None
    for word in words:
        if word in ("on", "off", "status"):
            command = word
        elif parse_key(word):
            key = word
        else:
            print(f"issacnewton: don't understand {word!r}. "
                  f"Try: issacnewton, issacnewton 9B, issacnewton off, "
                  f"issacnewton status", file=sys.stderr)
            return 2

    client = LedfxClient(base_url=args.base_url, opener=opener)

    try:
        if command == "status":
            print(describe(client))
            return 0

        if command == "off":
            restored = restore_scene(client)
            if restored < 0:
                print("issacnewton: nothing saved to go back to — pick a scene "
                      "in LEDfx instead.", file=sys.stderr)
                return 1
            print(f"Your scene is back on {restored} strips.")
            return 0

        # ---- on -------------------------------------------------------------
        key = key or _remembered_key()
        saved = save_scene(client)
        _state_file("last_key").write_text(key + "\n")
    except Exception as exc:
        print(f"issacnewton: can't reach LEDfx ({exc}). Is it running?",
              file=sys.stderr)
        return 1

    forward = ["--quiet", key, "--base-url", args.base_url]
    if not args.flat:
        forward = ["--bass", "--bass-floor", str(args.floor)] + forward
    code = cli.main(forward,
                    client_factory=lambda **kw: LedfxClient(opener=opener, **kw))
    if code != 0:
        return code

    pc, minor = parse_key(key)
    how = ("steady" if args.flat
           else f"pulsing {int(args.floor * 100)}-100% with the bass")
    note = f" (your scene is saved on {saved} strips)" if saved else ""
    print(f"Room is {key} — {color_for_key(pc, minor)}, {how}.{note}")
    return 0


def _remembered_key():
    path = _state_file("last_key")
    if path.exists():
        remembered = path.read_text().strip()
        if remembered:
            return remembered
    return DEFAULT_KEY


if __name__ == "__main__":
    sys.exit(main())
