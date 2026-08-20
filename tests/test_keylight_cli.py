# tests/test_keylight_cli.py
import unittest
from keylight import cli


class RecordingLedfx:
    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self.calls = []

    def apply_key_color(self, color_hex, gradient):
        self.calls.append((color_hex, gradient))
        return 3


class ExplodingLedfx:
    def __init__(self, **kwargs):
        pass

    def apply_key_color(self, color_hex, gradient):
        raise OSError("connection refused")


class TestCli(unittest.TestCase):
    def test_valid_key_applies_color(self):
        client = RecordingLedfx()
        code = cli.main(["8A"], client_factory=lambda **kw: client)
        self.assertEqual(code, 0)
        self.assertEqual(len(client.calls), 1)
        color, gradient = client.calls[0]
        self.assertEqual(color, "#00008c")  # A minor: darker blue
        self.assertTrue(gradient.startswith("linear-gradient("))

    def test_classical_key_also_works(self):
        client = RecordingLedfx()
        code = cli.main(["D"], client_factory=lambda **kw: client)
        self.assertEqual(code, 0)
        self.assertEqual(client.calls[0][0], "#ff0000")  # D major: pure red

    def test_unparseable_key_exits_nonzero_without_calling(self):
        client = RecordingLedfx()
        code = cli.main(["garbage"], client_factory=lambda **kw: client)
        self.assertEqual(code, 2)
        self.assertEqual(client.calls, [])

    def test_missing_argument_exits_nonzero(self):
        self.assertEqual(cli.main([], client_factory=RecordingLedfx), 2)

    def test_ledfx_failure_exits_nonzero_not_traceback(self):
        code = cli.main(["8A"], client_factory=lambda **kw: ExplodingLedfx())
        self.assertEqual(code, 1)

    def test_dry_run_flag_passed_through(self):
        seen = {}

        def factory(**kwargs):
            seen.update(kwargs)
            return RecordingLedfx()

        cli.main(["--dry-run", "8A"], client_factory=factory)
        self.assertTrue(seen["dry_run"])

    def test_base_url_flag_passed_through(self):
        seen = {}

        def factory(**kwargs):
            seen.update(kwargs)
            return RecordingLedfx()

        cli.main(["--base-url", "http://10.0.0.5:8888", "8A"],
                 client_factory=factory)
        self.assertEqual(seen["base_url"], "http://10.0.0.5:8888")


if __name__ == "__main__":
    unittest.main()
