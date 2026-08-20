# tests/test_keylight_bass.py
"""Bass-reactive brightness: the room breathes with the kick, in the key color.

LEDfx's `magnitude` effect renders `gradient * band_power`, and the base effect
adds `background_color * background_brightness` on top. So a gradient at 60%
brightness plus a 40% background floor gives brightness that swings 40% -> 100%
with the bass, without any process of ours running between tracks.
"""
import json
import unittest

from keylight.newton import color_for_key, gradient_for_key
from keylight.ledfx import LedfxClient, BASS_EFFECT
from keylight import cli
from tests.test_keylight_ledfx import FakeOpener, VIRTUALS


class TestValueScaling(unittest.TestCase):
    def test_default_is_unscaled(self):
        self.assertEqual(color_for_key(2, False), "#ff0000")
        self.assertEqual(color_for_key(2, False, value_scale=1.0), "#ff0000")

    def test_scaling_dims_without_changing_hue(self):
        self.assertEqual(color_for_key(2, False, value_scale=0.6), "#990000")

    def test_gradient_scales_too(self):
        full = gradient_for_key(2, False)
        dim = gradient_for_key(2, False, value_scale=0.6)
        self.assertNotEqual(full, dim)
        self.assertIn("#990000 50%", dim)


class TestBassReactiveApply(unittest.TestCase):
    def setUp(self):
        self.opener = FakeOpener(VIRTUALS)
        self.client = LedfxClient(opener=self.opener)

    def apply(self, floor=0.4):
        return self.client.apply_bass_reactive(
            color_for_key(9, True), gradient_for_key(9, True, value_scale=1 - floor),
            floor=floor)

    def test_updates_every_active_virtual(self):
        self.assertEqual(self.apply(), 2)
        self.assertEqual(len(self.opener.puts), 2)

    def test_switches_effect_to_magnitude_driven_by_bass(self):
        self.apply()
        payload = dict(self.opener.puts)[
            "http://127.0.0.1:8888/api/virtuals/strip-1/effects"]
        self.assertEqual(payload["type"], BASS_EFFECT)
        self.assertEqual(payload["config"]["frequency_range"], "Bass")

    def test_floor_is_the_key_color_at_floor_brightness(self):
        self.apply(floor=0.4)
        cfg = dict(self.opener.puts)[
            "http://127.0.0.1:8888/api/virtuals/strip-1/effects"]["config"]
        self.assertEqual(cfg["background_color"], color_for_key(9, True))
        self.assertEqual(cfg["background_brightness"], 0.4)
        self.assertEqual(cfg["brightness"], 1.0)

    def test_custom_floor_respected(self):
        self.apply(floor=0.25)
        cfg = dict(self.opener.puts)[
            "http://127.0.0.1:8888/api/virtuals/strip-1/effects"]["config"]
        self.assertEqual(cfg["background_brightness"], 0.25)

    def test_keeps_the_feel_of_the_strip(self):
        # blur/mirror/flip carried over from whatever was running
        self.apply()
        cfg = dict(self.opener.puts)[
            "http://127.0.0.1:8888/api/virtuals/strip-1/effects"]["config"]
        self.assertEqual(cfg["blur"], 3.0)

    def test_sends_only_keys_the_effect_accepts(self):
        self.apply()
        allowed = {"frequency_range", "gradient", "background_color",
                   "background_brightness", "brightness", "blur", "mirror",
                   "flip", "gradient_roll"}
        for _, payload in self.opener.puts:
            extra = set(payload["config"]) - allowed
            self.assertEqual(extra, set(), f"unexpected config keys: {extra}")

    def test_dry_run_sends_nothing(self):
        c = LedfxClient(dry_run=True, opener=self.opener)
        n = c.apply_bass_reactive("#00008c", "linear-gradient(90deg, #000054 0%, #000054 50%, #000054 100%)")
        self.assertEqual(n, 2)
        self.assertEqual(self.opener.puts, [])


class TestBassCli(unittest.TestCase):
    class Recorder:
        def __init__(self, **kw):
            self.plain, self.bass = [], []

        def apply_key_color(self, color, gradient):
            self.plain.append((color, gradient))
            return 1

        def apply_bass_reactive(self, color, gradient, floor=0.4):
            self.bass.append((color, gradient, floor))
            return 1

    def test_without_flag_stays_plain_recolor(self):
        r = self.Recorder()
        self.assertEqual(cli.main(["8A"], client_factory=lambda **kw: r), 0)
        self.assertEqual(len(r.plain), 1)
        self.assertEqual(r.bass, [])

    def test_bass_flag_uses_bass_mode(self):
        r = self.Recorder()
        self.assertEqual(cli.main(["--bass", "8A"], client_factory=lambda **kw: r), 0)
        self.assertEqual(r.plain, [])
        self.assertEqual(len(r.bass), 1)
        color, gradient, floor = r.bass[0]
        self.assertEqual(floor, 0.4)
        self.assertEqual(color, color_for_key(9, True))          # full for the floor
        self.assertIn("50%", gradient)

    def test_bass_floor_flag(self):
        r = self.Recorder()
        cli.main(["--bass", "--bass-floor", "0.25", "8A"],
                 client_factory=lambda **kw: r)
        self.assertEqual(r.bass[0][2], 0.25)

    def test_bass_floor_out_of_range_rejected(self):
        r = self.Recorder()
        self.assertEqual(
            cli.main(["--bass", "--bass-floor", "1.5", "8A"],
                     client_factory=lambda **kw: r), 2)
        self.assertEqual(r.bass, [])


if __name__ == "__main__":
    unittest.main()
