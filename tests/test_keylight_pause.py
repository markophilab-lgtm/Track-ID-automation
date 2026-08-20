# tests/test_keylight_pause.py
"""`issacnewton off` must also stop Beat Link Trigger repainting the room.

Once the BLT trigger is installed, every track change calls keylight.cli. If
`off` only restored the scene, the next track would wipe it out again — so
`off` sets a pause that cli honours, and `on` clears it.
"""
import json
import pathlib
import shutil
import tempfile
import unittest

from keylight import cli, room, state
from tests.test_keylight_room import StatefulFake, scene


class PauseTestCase(unittest.TestCase):
    def setUp(self):
        self.tmp = pathlib.Path(tempfile.mkdtemp())
        self._orig = state.STATE_DIR
        state.STATE_DIR = self.tmp
        self.fake = StatefulFake(scene())
        self.addCleanup(self._cleanup)

    def _cleanup(self):
        state.STATE_DIR = self._orig
        shutil.rmtree(self.tmp, ignore_errors=True)

    def run_room(self, *argv):
        return room.main(list(argv), opener=self.fake)

    def run_cli(self, *argv):
        from keylight.ledfx import LedfxClient
        return cli.main(list(argv),
                        client_factory=lambda **kw: LedfxClient(opener=self.fake, **kw))


class TestPauseState(PauseTestCase):
    def test_starts_unpaused(self):
        self.assertFalse(state.is_paused())

    def test_pause_then_resume(self):
        state.pause()
        self.assertTrue(state.is_paused())
        state.resume()
        self.assertFalse(state.is_paused())

    def test_resume_when_not_paused_is_harmless(self):
        state.resume()
        self.assertFalse(state.is_paused())


class TestOffPauses(PauseTestCase):
    def test_off_pauses(self):
        self.run_room("on", "8A")
        self.assertFalse(state.is_paused())
        self.run_room("off")
        self.assertTrue(state.is_paused())

    def test_on_resumes(self):
        self.run_room("on", "8A")
        self.run_room("off")
        self.run_room("on", "9B")
        self.assertFalse(state.is_paused())

    def test_off_with_no_backup_still_pauses(self):
        """Even when there's nothing to restore, stop BLT painting over things."""
        self.run_room("off")
        self.assertTrue(state.is_paused())


class TestCliHonoursPause(PauseTestCase):
    def test_cli_touches_nothing_while_paused(self):
        state.pause()
        self.assertEqual(self.run_cli("--quiet", "--bass", "8A"), 0)
        self.assertEqual(self.fake.put_count, 0)
        self.assertEqual(self.fake.virtuals["top"]["effect"]["type"], "singleColor")

    def test_cli_works_again_once_resumed(self):
        state.pause()
        self.run_cli("--quiet", "--bass", "8A")
        state.resume()
        self.assertEqual(self.run_cli("--quiet", "--bass", "8A"), 0)
        self.assertEqual(self.fake.virtuals["top"]["effect"]["type"], "magnitude")

    def test_the_real_scenario_off_survives_a_track_change(self):
        """off -> BLT reports a new key -> the manual scene is still there."""
        before = json.loads(json.dumps(self.fake.virtuals))
        self.run_room("on", "8A")
        self.run_room("off")
        self.run_cli("--quiet", "--bass", "5A")     # BLT, next track
        self.assertEqual(self.fake.virtuals["top"], before["top"])
        self.assertEqual(self.fake.virtuals["3bars"], before["3bars"])

    def test_dry_run_still_reports_while_paused(self):
        """--dry-run sends nothing anyway; it stays useful for checking colors."""
        state.pause()
        self.assertEqual(self.run_cli("--dry-run", "--quiet", "8A"), 0)


class TestStatusMentionsPause(PauseTestCase):
    def test_status_says_it_is_paused(self):
        from keylight.ledfx import LedfxClient
        self.run_room("on", "8A")
        self.run_room("off")
        told = room.describe(LedfxClient(opener=self.fake))
        self.assertIn("paused", told.lower())


if __name__ == "__main__":
    unittest.main()
