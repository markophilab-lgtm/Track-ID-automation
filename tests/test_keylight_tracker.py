# tests/test_keylight_tracker.py
import unittest
from keylight.tracker import MasterTracker


class FakeClock:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t

    def advance(self, s):
        self.t += s


class TestMasterTracker(unittest.TestCase):
    def setUp(self):
        self.emitted = []
        self.clock = FakeClock()
        self.tr = MasterTracker(self.emitted.append, debounce_s=2.0,
                                clock=self.clock)

    def test_master_deck_key_emitted(self):
        self.tr.note_track(1, track_id=101, key_string="8A")
        self.tr.note_status(1, is_master=True, is_playing=True, track_id=101)
        self.assertEqual(self.emitted, ["8A"])

    def test_non_master_load_changes_nothing(self):
        self.tr.note_track(1, 101, "8A")
        self.tr.note_status(1, True, True, 101)
        self.tr.note_track(2, 202, "3B")   # cueing on deck 2
        self.tr.note_status(2, False, True, 202)
        self.assertEqual(self.emitted, ["8A"])

    def test_master_handoff_emits_new_key_after_debounce(self):
        self.tr.note_track(1, 101, "8A")
        self.tr.note_status(1, True, True, 101)
        self.tr.note_track(2, 202, "3B")
        self.clock.advance(5)
        self.tr.note_status(1, False, True, 101)
        self.tr.note_status(2, True, True, 202)
        self.assertEqual(self.emitted, ["8A", "3B"])

    def test_debounce_suppresses_flapping(self):
        self.tr.note_track(1, 101, "8A")
        self.tr.note_status(1, True, True, 101)          # emit 1: 8A
        self.tr.note_track(2, 202, "3B")
        self.tr.note_status(2, True, True, 202)           # within 2s: deferred
        self.tr.note_status(1, True, True, 101)           # flaps back
        self.assertEqual(self.emitted, ["8A"])
        self.clock.advance(3)
        self.tr.note_status(1, True, True, 101)           # stable master after window
        self.assertEqual(self.emitted, ["8A"])            # same key: nothing new

    def test_deferred_emit_fires_after_window(self):
        self.tr.note_track(1, 101, "8A")
        self.tr.note_status(1, True, True, 101)
        self.tr.note_track(2, 202, "3B")
        self.tr.note_status(2, True, True, 202)           # deferred (within 2s)
        self.assertEqual(self.emitted, ["8A"])
        self.clock.advance(3)
        self.tr.note_status(2, True, True, 202)           # next event delivers
        self.assertEqual(self.emitted, ["8A", "3B"])

    def test_no_master_falls_back_to_latest_loaded_playing(self):
        self.tr.note_track(1, 101, "8A")
        self.tr.note_status(1, False, True, 101)
        self.assertEqual(self.emitted, ["8A"])
        self.clock.advance(5)
        self.tr.note_track(2, 202, "3B")                  # loaded later
        self.tr.note_status(2, False, True, 202)
        self.assertEqual(self.emitted, ["8A", "3B"])

    def test_missing_key_holds_color(self):
        self.tr.note_track(1, 101, "8A")
        self.tr.note_status(1, True, True, 101)
        self.clock.advance(5)
        self.tr.note_track(1, 102, None)                  # untagged track
        self.tr.note_status(1, True, True, 102)
        self.assertEqual(self.emitted, ["8A"])            # held

    def test_master_track_change_emits(self):
        self.tr.note_track(1, 101, "8A")
        self.tr.note_status(1, True, True, 101)
        self.clock.advance(5)
        self.tr.note_track(1, 102, "10B")                 # new track same deck
        self.tr.note_status(1, True, True, 102)
        self.assertEqual(self.emitted, ["8A", "10B"])

    def test_same_key_not_re_emitted(self):
        self.tr.note_track(1, 101, "8A")
        self.tr.note_status(1, True, True, 101)
        self.clock.advance(5)
        self.tr.note_status(1, True, True, 101)
        self.assertEqual(self.emitted, ["8A"])


if __name__ == "__main__":
    unittest.main()
