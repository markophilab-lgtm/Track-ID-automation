# tests/test_keylight_facade.py
import unittest
from keylight import KeyLight


class FakeClient:
    def __init__(self, state=(), track_id=0, play_state="playing", type="cdj"):
        self.state = list(state)
        self.track_id = track_id
        self.play_state = play_state
        self.type = type


class FakeCl:
    def __init__(self):
        self.clients = {}

    def getClient(self, n):
        return self.clients.get(n)


class FakeProdj:
    def __init__(self):
        self.cl = FakeCl()


class RecordingLedfx:
    def __init__(self):
        self.calls = []

    def apply_key_color(self, color_hex, gradient):
        self.calls.append((color_hex, gradient))
        return 1


class TestKeyLight(unittest.TestCase):
    def setUp(self):
        self.prodj = FakeProdj()
        self.kl = KeyLight(self.prodj, dry_run=True)
        self.kl.ledfx = RecordingLedfx()          # replace real client
        self.kl.tracker.debounce_s = 0.0          # no waiting in tests

    def test_full_flow_metadata_then_master_status(self):
        self.prodj.cl.clients[1] = FakeClient(
            state=["master", "play"], track_id=101)
        self.kl.handle_metadata(1, {"track_id": 101, "key": "8A",
                                    "artist": "x", "title": "y"})
        self.kl.handle_client_change(1)
        self.assertEqual(len(self.kl.ledfx.calls), 1)
        color, gradient = self.kl.ledfx.calls[0]
        # 8A = A minor: pitch class 9, minor -> darker blue
        self.assertTrue(color.startswith("#"))
        self.assertTrue(gradient.startswith("linear-gradient("))

    def test_unknown_player_ignored(self):
        self.kl.handle_client_change(3)           # no such client
        self.assertEqual(self.kl.ledfx.calls, [])

    def test_djm_ignored(self):
        self.prodj.cl.clients[2] = FakeClient(type="djm")
        self.kl.handle_client_change(2)
        self.assertEqual(self.kl.ledfx.calls, [])

    def test_exceptions_are_swallowed(self):
        class Exploding:
            def apply_key_color(self, *a):
                raise RuntimeError("ledfx down")

        self.prodj.cl.clients[1] = FakeClient(
            state=["master", "play"], track_id=101)
        self.kl.ledfx = Exploding()
        self.kl.handle_metadata(1, {"track_id": 101, "key": "8A"})
        self.kl.handle_client_change(1)           # must not raise
        # after failure, a repeat event retries (lazy retry)
        self.kl.ledfx = RecordingLedfx()
        self.kl.handle_client_change(1)
        self.assertEqual(len(self.kl.ledfx.calls), 1)

    def test_unparseable_key_no_call(self):
        self.prodj.cl.clients[1] = FakeClient(
            state=["master", "play"], track_id=101)
        self.kl.handle_metadata(1, {"track_id": 101, "key": "??"})
        self.kl.handle_client_change(1)
        self.assertEqual(self.kl.ledfx.calls, [])


if __name__ == "__main__":
    unittest.main()
