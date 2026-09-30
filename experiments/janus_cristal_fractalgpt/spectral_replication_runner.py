#!/usr/bin/env python3
"""Transport-only wrapper for the frozen spectral replication experiment.

Wikimedia may return HTTP 429 after earlier crystal-corpus downloads in the same
GitHub runner. This wrapper changes only network pacing/retry behavior. It does
not change image bytes after download, registration, difference-field weights,
thresholds, FractalGPT trajectories, null tests, or admission rules.
"""
from __future__ import annotations

import time
import urllib.error

import spectral_replication_probe as probe

_ORIGINAL_FETCH = probe.fcp.fetch
_LAST_NETWORK = 0.0


def paced_fetch(url, dest):
    global _LAST_NETWORK
    # Give the public media endpoint room between full-resolution requests.
    minimum_spacing = 8.0
    initial_cooldown = 20.0
    if _LAST_NETWORK == 0.0:
        time.sleep(initial_cooldown)
    else:
        wait = minimum_spacing - (time.monotonic() - _LAST_NETWORK)
        if wait > 0:
            time.sleep(wait)

    delays = [0.0, 15.0, 30.0, 60.0]
    last = None
    for delay in delays:
        if delay:
            time.sleep(delay)
        try:
            _ORIGINAL_FETCH(url, dest)
            _LAST_NETWORK = time.monotonic()
            return
        except urllib.error.HTTPError as exc:
            last = exc
            if exc.code != 429:
                raise
            _LAST_NETWORK = time.monotonic()
    raise last


probe.fcp.fetch = paced_fetch

if __name__ == "__main__":
    raise SystemExit(probe.main())
