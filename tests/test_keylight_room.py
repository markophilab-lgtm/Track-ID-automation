# tests/test_keylight_room.py
"""Whole-room on/off control — what the `issacnewton` alias drives."""
import json
import pathlib
import shutil
import tempfile
import unittest

from keylight import room


class StatefulFake:
    """Fake LEDfx that actually remembers what was PUT to it."""

    def __init__(self, virtuals):
        self.virtuals = json.loads(json.dumps(virtuals))
        self.put_count = 0

    def __call__(self, request, timeout):
        url, method = request.full_url, request.get_method()
        if method == "GET":
            return _Resp({"virtuals": self.virtuals})
        if method == "PUT":
            vid = url.split("/api/virtuals/")[1].split("/effects")[0]
            self.virtuals[vid]["effect"] = json.loads(request.data.decode())
            self.put_count += 1
            return _Resp({"status": "success"})
        raise AssertionError(f"unexpected {method} {url}")


class _Resp:
    def __init__(self, payload):
        self._b = json.dumps(payload).encode()

    def read(self):
        return self._b

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def scene():
    return {
        "top": {"effect": {"type": "singleColor",
                           "config": {"color": "#ff00b2", "blur": 2.0}}},
        "3bars": {"effect": {"type": "bands",
                             "config": {"gradient": "linear-gradient(90deg, #ff0000 0%, #00ff00 100%)",
                                        "band_count": 6}}},
        "idle": {"effect": {}},
    }


class RoomTestCase(unittest.TestCase):
    def setUp(self):
        self.tmp = pathlib.Path(tempfile.mkdtemp())
        self._orig_state = room.STATE_DIR
        room.STATE_DIR = self.tmp
        self.fake = StatefulFake(scene())
        self.addCleanup(self._cleanup)

    def _cleanup(self):
        room.STATE_DIR = self._orig_state
        shutil.rmtree(self.tmp, ignore_errors=True)

    def run_room(self, *argv):
        return room.main(list(argv), opener=self.fake)


class TestOn(RoomTestCase):
    def test_on_backs_up_the_scene_then_applies_bass(self):
        self.assertEqual(self.run_room("on", "8A"), 0)
        backup = json.loads((self.tmp / "scene_backup.json").read_text())
        self.assertEqual(backup["top"]["type"], "singleColor")
        self.assertEqual(backup["top"]["config"]["color"], "#ff00b2")
        self.assertEqual(self.fake.virtuals["top"]["effect"]["type"], "magnitude")

    def test_on_twice_keeps_the_original_backup(self):
        self.run_room("on", "8A")
        self.run_room("on", "9B")          # already in bass mode
        backup = json.loads((self.tmp / "scene_backup.json").read_text())
        self.assertEqual(backup["top"]["type"], "singleColor")  # not magnitude

    def test_remembers_the_last_key(self):
        self.run_room("on", "9B")
        self.assertEqual((self.tmp / "last_key").read_text().strip(), "9B")
        self.run_room("off")
        self.run_room("on")                 # no key given
        cfg = self.fake.virtuals["top"]["effect"]["config"]
        from keylight.newton import color_for_key
        self.assertEqual(cfg["background_color"], color_for_key(7, False))  # G major

    def test_default_key_when_nothing_remembered(self):
        self.assertEqual(self.run_room("on"), 0)
        self.assertEqual((self.tmp / "last_key").read_text().strip(), room.DEFAULT_KEY)

    def test_flat_mode_skips_bass(self):
        self.run_room("on", "--flat", "8A")
        self.assertEqual(self.fake.virtuals["top"]["effect"]["type"], "singleColor")
        self.assertEqual(self.fake.virtuals["top"]["effect"]["config"]["color"],
                         "#00008c")

    def test_bad_key_is_rejected_before_touching_lights(self):
        self.assertEqual(self.run_room("on", "nonsense"), 2)
        self.assertEqual(self.fake.put_count, 0)


class TestOff(RoomTestCase):
    def test_off_restores_the_saved_scene_exactly(self):
        before = json.loads(json.dumps(self.fake.virtuals))
        self.run_room("on", "8A")
        self.assertEqual(self.run_room("off"), 0)
        self.assertEqual(self.fake.virtuals["top"], before["top"])
        self.assertEqual(self.fake.virtuals["3bars"], before["3bars"])

    def test_off_without_a_backup_explains_itself(self):
        self.assertEqual(self.run_room("off"), 1)
        self.assertEqual(self.fake.put_count, 0)


class TestStatus(RoomTestCase):
    def test_status_changes_nothing(self):
        self.run_room("on", "8A")
        puts = self.fake.put_count
        self.assertEqual(self.run_room("status"), 0)
        self.assertEqual(self.fake.put_count, puts)

    def test_status_works_before_anything_is_applied(self):
        self.assertEqual(self.run_room("status"), 0)


if __name__ == "__main__":
    unittest.main()
