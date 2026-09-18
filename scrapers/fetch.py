"""Polite HTTP fetcher: honest UA, fixed delay between requests, retries.

The daily build makes ~1000 requests against cdep.ro/senat.ro; the 0.3s
delay (~3 req/sec, ~5 min total) keeps us a considerate guest on
government infrastructure while not dragging the build out.
"""

from __future__ import annotations

import logging
import time

import requests

log = logging.getLogger("demnitari.fetch")

UA = "demnitari-bot/1.0 (+https://github.com/bigdot/demnitari; date publice)"


class Fetcher:
    def __init__(self, delay: float = 0.3, retries: int = 3, timeout: int = 30):
        self.delay = delay
        self.retries = retries
        self.timeout = timeout
        self._session = requests.Session()
        self._session.headers["User-Agent"] = UA
        self._last = 0.0
        self.stats = {"requests": 0, "retries": 0}

    # separate seam so tests can stub the transport
    def _session_get(self, url: str, **kw):
        return self._session.get(url, timeout=self.timeout, **kw)

    def _session_post(self, url: str, data: dict, **kw):
        return self._session.post(url, data=data, timeout=self.timeout, **kw)

    def _politete(self):
        de_asteptat = self._last + self.delay - time.monotonic()
        if de_asteptat > 0:
            time.sleep(de_asteptat)
        self._last = time.monotonic()

    def _cu_retry(self, fa_request, url: str):
        ultima_eroare: Exception | None = None
        for incercare in range(self.retries):
            self._politete()
            try:
                self.stats["requests"] += 1
                resp = fa_request()
                resp.raise_for_status()
                return resp
            except Exception as e:  # retry pe orice: HTTP >= 400, timeout, DNS
                ultima_eroare = e
                if incercare < self.retries - 1:
                    self.stats["retries"] += 1
                    log.warning("retry %d/%d %s (%s)", incercare + 2, self.retries, url, e)
                time.sleep(2**incercare)  # backoff: 1s, 2s, 4s
        log.error("abandonat dupa %d incercari: %s (%s)", self.retries, url, ultima_eroare)
        raise ultima_eroare

    def get(self, url: str, **kw):
        return self._cu_retry(lambda: self._session_get(url, **kw), url)

    def post(self, url: str, data: dict, **kw):
        return self._cu_retry(lambda: self._session_post(url, data, **kw), url)
