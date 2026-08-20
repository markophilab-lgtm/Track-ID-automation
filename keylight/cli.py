# keylight/cli.py
"""One-shot entry point: given a musical key, recolor the LEDfx effects.

Called by the Beat Link Trigger "Tracked Update" expression (see
blt_expressions/tracked_update_with_lights.clj), which decides *when* the room
key changes; this script decides what color that key is and sends it.

    python3 -m keylight.cli "8A"
    python3 -m keylight.cli --dry-run "F#m"

Exit codes: 0 applied, 1 LEDfx unreachable/failed, 2 bad or missing key.
Never raises: BLT must never see a traceback from the light path.
"""

import argparse
import logging
import sys

from keylight.keys import parse_key
from keylight.newton import color_for_key, gradient_for_key
from keylight.ledfx import LedfxClient, BASS_FLOOR

log = logging.getLogger("keylight")


def main(argv=None, client_factory=LedfxClient):
    parser = argparse.ArgumentParser(
        prog="keylight", description="Recolor LEDfx effects for a musical key.")
    parser.add_argument("key", nargs="?",
                        help='key string, e.g. "8A", "F#m", "Bb"')
    parser.add_argument("--dry-run", action="store_true",
                        help="log the intended LEDfx calls without sending them")
    parser.add_argument("--base-url", default="http://127.0.0.1:8888",
                        help="LEDfx base URL (default: %(default)s)")
    parser.add_argument("--bass", action="store_true",
                        help="brightness follows the bass instead of staying flat")
    parser.add_argument("--bass-floor", type=float, default=BASS_FLOOR,
                        metavar="F",
                        help="dimmest the room gets between kicks, 0-1 "
                             "(default: %(default)s = 40%%)")
    parser.add_argument("--quiet", action="store_true",
                        help="suppress the result line on stdout")
    args = parser.parse_args(argv)

    if not 0.0 <= args.bass_floor < 1.0:
        print(f"keylight: --bass-floor must be between 0 and 1, "
              f"got {args.bass_floor}", file=sys.stderr)
        return 2

    if not args.key:
        print("keylight: no key given", file=sys.stderr)
        return 2

    parsed = parse_key(args.key)
    if not parsed:
        print(f"keylight: unparseable key {args.key!r}", file=sys.stderr)
        return 2

    pitch_class, is_minor = parsed
    color = color_for_key(pitch_class, is_minor)
    client = client_factory(base_url=args.base_url, dry_run=args.dry_run)

    try:
        if args.bass:
            # The gradient carries the audio-driven part, so it only gets the
            # headroom above the floor; the floor itself is the full color.
            gradient = gradient_for_key(pitch_class, is_minor,
                                        value_scale=1.0 - args.bass_floor)
            updated = client.apply_bass_reactive(color, gradient,
                                                 floor=args.bass_floor)
        else:
            updated = client.apply_key_color(
                color, gradient_for_key(pitch_class, is_minor))
    except Exception as exc:
        print(f"keylight: LEDfx unreachable ({exc}); lights unchanged",
              file=sys.stderr)
        return 1

    if not args.quiet:
        prefix = "[dry-run] " if args.dry_run else ""
        mode = (f", bass {int(args.bass_floor * 100)}-100%"
                if args.bass else "")
        print(f"{prefix}key {args.key} -> {color} on {updated} virtuals{mode}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
