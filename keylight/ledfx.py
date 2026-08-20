# keylight/ledfx.py
"""Minimal LEDfx REST client: recolor active effects, preserve everything else."""

import json
import logging
import urllib.request

log = logging.getLogger("keylight")


def _default_opener(request, timeout):
    return urllib.request.urlopen(request, timeout=timeout)


def _is_color(value):
    return isinstance(value, str) and (
        value.startswith("#") or value.startswith("linear-gradient("))


class LedfxClient:
    def __init__(self, base_url="http://127.0.0.1:8888", timeout=2.0,
                 dry_run=False, opener=None):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.dry_run = dry_run
        self.opener = opener or _default_opener

    def _get(self, path):
        req = urllib.request.Request(self.base_url + path, method="GET")
        with self.opener(req, self.timeout) as resp:
            return json.loads(resp.read().decode())

    def _put(self, path, payload):
        req = urllib.request.Request(
            self.base_url + path,
            data=json.dumps(payload).encode(),
            headers={"Content-Type": "application/json"},
            method="PUT")
        with self.opener(req, self.timeout) as resp:
            return json.loads(resp.read().decode())

    def _recolored(self, config, color_hex, gradient):
        new = dict(config)
        for k, v in config.items():
            if k.startswith("background"):
                continue
            if _is_color(v):
                new[k] = gradient if v.startswith("linear-gradient(") else color_hex
        return new

    def apply_key_color(self, color_hex, gradient):
        """Recolor all active virtuals. Returns count updated. Raises on I/O error."""
        data = self._get("/api/virtuals")
        updated = 0
        for vid, vdata in data.get("virtuals", {}).items():
            effect = vdata.get("effect") or {}
            etype = effect.get("type")
            config = effect.get("config")
            if not etype or not isinstance(config, dict):
                continue
            payload = {"type": etype,
                       "config": self._recolored(config, color_hex, gradient)}
            if self.dry_run:
                log.info("[dry-run] PUT /api/virtuals/%s/effects %s", vid, payload)
            else:
                self._put(f"/api/virtuals/{vid}/effects", payload)
            updated += 1
        return updated
