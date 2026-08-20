# tests/test_keylight_newton.py
import unittest
from keylight.newton import color_for_key, gradient_for_key, HUES


class TestNewtonWheel(unittest.TestCase):
    def test_anchor_hues_follow_newton(self):
        # Newton (Opticks): D=red E=orange F=yellow G=green A=blue B=indigo C=violet
        self.assertEqual(HUES[2], 0)     # D red
        self.assertEqual(HUES[4], 30)    # E orange
        self.assertEqual(HUES[5], 60)    # F yellow
        self.assertEqual(HUES[7], 120)   # G green
        self.assertEqual(HUES[9], 240)   # A blue
        self.assertEqual(HUES[11], 275)  # B indigo
        self.assertEqual(HUES[0], 300)   # C violet

    def test_accidentals_interpolate_between_neighbors(self):
        self.assertEqual(HUES[3], 15)    # D# between D(0) and E(30)
        self.assertEqual(HUES[6], 90)    # F# between F(60) and G(120)
        self.assertEqual(HUES[8], 180)   # G# between G(120) and A(240)
        self.assertEqual(HUES[10], 258)  # A# between A(240) and B(275), rounded
        self.assertEqual(HUES[1], 330)   # C# between C(300) and D(360)

    def test_d_major_is_pure_red(self):
        self.assertEqual(color_for_key(2, False), "#ff0000")

    def test_all_24_keys_distinct(self):
        colors = {color_for_key(pc, minor)
                  for pc in range(12) for minor in (False, True)}
        self.assertEqual(len(colors), 24)

    def test_minor_is_darker_same_hue(self):
        major = color_for_key(9, False)  # A major: pure blue #0000ff
        minor = color_for_key(9, True)
        self.assertEqual(major, "#0000ff")
        self.assertNotEqual(major, minor)
        # darker: every RGB channel <= major's channel
        mj = [int(major[i:i+2], 16) for i in (1, 3, 5)]
        mn = [int(minor[i:i+2], 16) for i in (1, 3, 5)]
        self.assertTrue(all(a <= b for a, b in zip(mn, mj)))

    def test_gradient_format(self):
        g = gradient_for_key(2, False)
        self.assertTrue(g.startswith("linear-gradient(90deg, #"))
        self.assertIn(" 0%", g)
        self.assertIn(" 50%", g)
        self.assertIn(" 100%", g)
        self.assertIn("#ff0000 50%", g)  # key color at center


if __name__ == "__main__":
    unittest.main()
