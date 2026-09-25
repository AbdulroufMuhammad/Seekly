"""In-memory fixed-window rate limiter, keyed by API key id.

Single-process only — matches the existing in-memory response cache
(api/cache.py). A multi-instance deployment needs a shared store (e.g.
Redis) instead; swapping the backing dict for one is the only change
`check_and_increment` callers would need.
"""

import time
from collections import defaultdict

_WINDOW_SECONDS = 60
_windows: dict[str, dict[int, int]] = defaultdict(dict)


def check_and_increment(key_id: str, limit_per_minute: int) -> tuple[bool, int]:
    """Records one request against `key_id`'s current window.

    Returns (allowed, retry_after_seconds). retry_after_seconds is 0 when
    allowed is True.
    """
    now = time.time()
    window = int(now // _WINDOW_SECONDS)

    windows = _windows[key_id]
    for stale_window in [w for w in windows if w != window]:
        del windows[stale_window]

    count = windows.get(window, 0)
    if count >= limit_per_minute:
        retry_after = int((window + 1) * _WINDOW_SECONDS - now) + 1
        return False, retry_after

    windows[window] = count + 1
    return True, 0
