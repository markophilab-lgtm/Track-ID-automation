# tests/test_keylight_keys.py
import unittest
from keylight.keys import parse_key


class TestClassicalNotation(unittest.TestCase):
    def test_major_keys(self):
        self.assertEqual(parse_key("C"), (0, False))
        self.assertEqual(parse_key("F#"), (6, False))
        self.assertEqual(parse_key("Bb"), (10, False))
        self.assertEqual(parse_key("Db"), (1, False))

    def test_minor_keys(self):
        self.assertEqual(parse_key("Am"), (9, True))
        self.assertEqual(parse_key("F#m"), (6, True))
        self.assertEqual(parse_key("Bbm"), (10, True))
        self.assertEqual(parse_key("Cmin"), (0, True))
        self.assertEqual(parse_key("A minor"), (9, True))

    def test_explicit_major_suffix(self):
        self.assertEqual(parse_key("Cmaj"), (0, False))
        self.assertEqual(parse_key("G major"), (7, False))

    def test_case_and_whitespace(self):
        self.assertEqual(parse_key(" am "), (9, True))
        self.assertEqual(parse_key("f#M"), (6, True))  # trailing m = minor


class TestCamelotNotation(unittest.TestCase):
    def test_majors(self):
        self.assertEqual(parse_key("8B"), (0, False))   # C
        self.assertEqual(parse_key("9B"), (7, False))   # G
        self.assertEqual(parse_key("1B"), (11, False))  # B
        self.assertEqual(parse_key("12B"), (4, False))  # E

    def test_minors(self):
        self.assertEqual(parse_key("8A"), (9, True))    # Am
        self.assertEqual(parse_key("1A"), (8, True))    # Abm
        self.assertEqual(parse_key("12A"), (1, True))   # Dbm/C#m

    def test_leading_zero_and_case(self):
        self.assertEqual(parse_key("08A"), (9, True))
        self.assertEqual(parse_key("08a"), (9, True))


class TestGarbage(unittest.TestCase):
    def test_unparseable(self):
        for bad in [None, "", "  ", "13B", "0A", "H", "Xm", "8", "AB", "8C"]:
            self.assertIsNone(parse_key(bad), f"expected None for {bad!r}")


if __name__ == "__main__":
    unittest.main()
