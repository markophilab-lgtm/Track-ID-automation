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
from keylight.ledfx import LedfxClient

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
    parser.add_argument("--quiet", action="store_true",
                        help="suppress the result line on stdout")
    args = parser.parse_args(argv)

    if not args.key:
        print("keylight: no key given", file=sys.stderr)
        return 2

    parsed = parse_key(args.key)
    if not parsed:
        print(f"keylight: unparseable key {args.key!r}", file=sys.stderr)
        return 2

    pitch_class, is_minor = parsed
    color = color_for_key(pitch_class, is_minor)
    gradient = gradient_for_key(pitch_class, is_minor)

    try:
        updated = client_factory(base_url=args.base_url, dry_run=args.dry_run)\
            .apply_key_color(color, gradient)
    except Exception as exc:
        print(f"keylight: LEDfx unreachable ({exc}); lights unchanged",
              file=sys.stderr)
        return 1

    if not args.quiet:
        prefix = "[dry-run] " if args.dry_run else ""
        print(f"{prefix}key {args.key} -> {color} on {updated} virtuals")
    return 0


if __name__ == "__main__":
    sys.exit(main())
