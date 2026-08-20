# tests/test_keylight_ledfx.py
import json
import unittest
from keylight.ledfx import LedfxClient


class FakeOpener:
    """Collects requests; serves canned GET responses."""

    def __init__(self, virtuals_payload):
        self.virtuals_payload = virtuals_payload
        self.puts = []  # (url, payload dict)

    def __call__(self, request, timeout):
        url = request.full_url
        method = request.get_method()
        if method == "GET" and url.endswith("/api/virtuals"):
            return _Resp(self.virtuals_payload)
        if method == "PUT":
            self.puts.append((url, json.loads(request.data.decode())))
            return _Resp({"status": "success"})
        raise AssertionError(f"unexpected {method} {url}")


class _Resp:
    def __init__(self, payload):
        self._body = json.dumps(payload).encode()

    def read(self):
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


VIRTUALS = {
    "virtuals": {
        "strip-1": {
            "effect": {
                "type": "wavelength",
                "config": {
                    "gradient": "linear-gradient(90deg, #ff0000 0%, #0000ff 100%)",
                    "background_color": "#000000",
                    "flip_gradient": False,
                    "blur": 3.0,
                },
            }
        },
        "strip-2": {
            "effect": {
                "type": "scroll",
                "config": {
                    "color_lows": "#ff0000",
                    "color_mids": "#00ff00",
                    "color_high": "#0000ff",
                    "speed": 5,
                },
            }
        },
        "strip-idle": {"effect": {}},  # no active effect: skipped
    }
}


class TestLedfxClient(unittest.TestCase):
    def setUp(self):
        self.opener = FakeOpener(VIRTUALS)
        self.client = LedfxClient(opener=self.opener)

    def test_updates_only_active_virtuals(self):
        n = self.client.apply_key_color("#123456", "linear-gradient(90deg, #111111 0%, #123456 50%, #222222 100%)")
        self.assertEqual(n, 2)
        self.assertEqual(len(self.opener.puts), 2)

    def test_gradient_and_colors_swapped_others_preserved(self):
        grad = "linear-gradient(90deg, #111111 0%, #123456 50%, #222222 100%)"
        self.client.apply_key_color("#123456", grad)
        by_url = dict(self.opener.puts)
        cfg1 = by_url["http://127.0.0.1:8888/api/virtuals/strip-1/effects"]["config"]
        self.assertEqual(cfg1["gradient"], grad)
        self.assertEqual(cfg1["background_color"], "#000000")  # untouched
        self.assertEqual(cfg1["blur"], 3.0)
        self.assertEqual(cfg1["flip_gradient"], False)
        cfg2 = by_url["http://127.0.0.1:8888/api/virtuals/strip-2/effects"]["config"]
        self.assertEqual(cfg2["color_lows"], "#123456")
        self.assertEqual(cfg2["color_mids"], "#123456")
        self.assertEqual(cfg2["speed"], 5)

    def test_effect_type_preserved(self):
        self.client.apply_key_color("#123456", "linear-gradient(90deg, #111111 0%, #123456 50%, #222222 100%)")
        by_url = dict(self.opener.puts)
        self.assertEqual(
            by_url["http://127.0.0.1:8888/api/virtuals/strip-1/effects"]["type"],
            "wavelength")

    def test_dry_run_sends_nothing(self):
        client = LedfxClient(dry_run=True, opener=self.opener)
        n = client.apply_key_color("#123456", "linear-gradient(90deg, #111111 0%, #123456 50%, #222222 100%)")
        self.assertEqual(n, 2)          # still counts what it would update
        self.assertEqual(self.opener.puts, [])


if __name__ == "__main__":
    unittest.main()
