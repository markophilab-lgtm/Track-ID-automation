# keylight/tracker.py
"""Decides when the room key changes, following the master deck."""

import time
import logging

log = logging.getLogger("keylight")


class _Deck:
    __slots__ = ("track_id", "key", "loaded_at", "is_master", "is_playing")

    def __init__(self):
        self.track_id = 0
        self.key = None
        self.loaded_at = 0.0
        self.is_master = False
        self.is_playing = False


class MasterTracker:
    def __init__(self, on_change, debounce_s=2.0, clock=time.monotonic):
        self.on_change = on_change
        self.debounce_s = debounce_s
        self.clock = clock
        self.decks = {}
        self.current_key = None
        self.last_emit_at = None
        self.pending_key = None

    def _deck(self, n):
        if n not in self.decks:
            self.decks[n] = _Deck()
        return self.decks[n]

    def note_track(self, player_number, track_id, key_string):
        d = self._deck(player_number)
        d.track_id = track_id
        d.key = key_string
        d.loaded_at = self.clock()
        self._evaluate()

    def note_status(self, player_number, is_master, is_playing, track_id):
        d = self._deck(player_number)
        d.is_master = is_master
        if is_master:
            # Pro DJ Link has exactly one master; a deck claiming it displaces
            # the rest even if their own "not master" status hasn't arrived yet.
            for n, other in self.decks.items():
                if n != player_number:
                    other.is_master = False
        d.is_playing = is_playing
        if track_id and track_id != d.track_id:
            # status shows a track we never got metadata for
            d.track_id = track_id
            d.key = None
        self._evaluate()

    def _controlling_deck(self):
        masters = [d for d in self.decks.values() if d.is_master]
        if masters:
            return masters[0]
        playing = [d for d in self.decks.values() if d.is_playing]
        if playing:
            return max(playing, key=lambda d: d.loaded_at)
        return None

    def _evaluate(self):
        deck = self._controlling_deck()
        if deck is None:
            return
        key = deck.key
        if key is None:
            log.info("controlling deck has no key tag; holding color")
            return
        now = self.clock()
        in_window = (self.last_emit_at is not None
                     and now - self.last_emit_at < self.debounce_s)

        if in_window:
            if key != self.current_key:
                self.pending_key = key
            else:
                self.pending_key = None
            return

        # window is open: emit if the controlling deck's key differs
        candidate = key
        self.pending_key = None
        if candidate != self.current_key:
            self.current_key = candidate
            self.last_emit_at = now
            self.on_change(candidate)
