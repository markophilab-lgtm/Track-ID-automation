# keylight/__init__.py
"""Guarded facade wiring CDJ events to LEDfx colors.

Every public method is wrapped: exceptions are logged and swallowed so the
tracklist logger can never be broken by the light path.
"""

import logging

from keylight.keys import parse_key
from keylight.newton import color_for_key, gradient_for_key
from keylight.tracker import MasterTracker
from keylight.ledfx import LedfxClient

log = logging.getLogger("keylight")


def _guarded(fn):
    def wrapper(self, *args, **kwargs):
        try:
            return fn(self, *args, **kwargs)
        except Exception:
            log.exception("keylight error (lights unchanged, logging unaffected)")
    return wrapper


class KeyLight:
    def __init__(self, prodj, dry_run=False):
        self.prodj = prodj
        self.ledfx = LedfxClient(dry_run=dry_run)
        self.tracker = MasterTracker(self._on_room_key)
        self._room_apply_failed_key = None

    # -- callbacks from cdj_logger ------------------------------------------

    @_guarded
    def handle_metadata(self, source_player, reply):
        key = reply.get("key") if isinstance(reply, dict) else None
        track_id = reply.get("track_id", 0) if isinstance(reply, dict) else 0
        parsed = parse_key(key)
        if key and not parsed:
            log.warning("unparseable key %r from player %s", key, source_player)
        self.tracker.note_track(source_player, track_id,
                                key if parsed else None)

    @_guarded
    def handle_client_change(self, player_number):
        c = self.prodj.cl.getClient(player_number)
        if c is None or getattr(c, "type", "") != "cdj":
            return
        state = getattr(c, "state", []) or []
        self.tracker.note_status(
            player_number,
            is_master="master" in state,
            is_playing=("play" in state
                        or getattr(c, "play_state", "") == "playing"),
            track_id=getattr(c, "track_id", 0))
        # lazy retry: if the last color apply failed, try again on any event
        if self._room_apply_failed_key is not None:
            key, self._room_apply_failed_key = self._room_apply_failed_key, None
            self._apply(key)

    # -- internal -----------------------------------------------------------

    def _on_room_key(self, key_string):
        self._apply(key_string)

    def _apply(self, key_string):
        parsed = parse_key(key_string)
        if not parsed:
            return
        pc, minor = parsed
        color = color_for_key(pc, minor)
        gradient = gradient_for_key(pc, minor)
        try:
            n = self.ledfx.apply_key_color(color, gradient)
            log.info("room key %s -> %s on %d virtuals", key_string, color, n)
        except Exception:
            self._room_apply_failed_key = key_string
            raise
