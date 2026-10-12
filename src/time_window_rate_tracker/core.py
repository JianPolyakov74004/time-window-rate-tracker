"""Fixed-window event tracker with sliding aggregate counts."""

from __future__ import annotations
from typing import Dict, Final, List

# Sentinel for the clock argument.
#
# We define this once at module scope so the two consumers (the
# constructor default and every internal call site) share the exact
# same sentinel object.  Using a private class rather than None lets
# users pass None as a real clock if they ever need to (e.g. a clock
# that returns None to deliberately trip validation in their own
# tests), without colliding with the "no clock supplied" signal.


class _UseSystemClock:
    pass


_USE_SYSTEM_CLOCK: Final[_UseSystemClock] = _UseSystemClock()


class TimeWindowRateTracker:
    """Track per-window event counts and expose a sliding aggregate.

    "time" here is an opaque, monotonicly-increasing quantity — wall-clock
    seconds, logical ticks, anything the caller wants.  The tracker never
    reads the wall clock directly unless no clock was supplied to the
    constructor.  This indirection keeps tests deterministic and keeps the
    tracker honest in non-clock-bound environments.

    Window assignment is floor(t / window_size).  Each window holds the
    count of events recorded into it.  A separate running counter backs the
    sliding-window aggregate so that a rate query over N windows is O(1)
    rather than O(N).
    """

    def __init__(
        self,
        window_size: float,
        *,
        clock=_USE_SYSTEM_CLOCK,
    ) -> None:
        """Configure windowing for this tracker.

        ``window_size`` must be positive and finite.  We deliberately reject
        zero and negatives at construction rather than silently producing
        nonsensical windows (division by zero, or negative window indices)
        later when event recording might already be in flight.

        ``clock`` may be a zero-argument callable returning a number, or the
        sentinel default.  When the sentinel is used we bind to
        ``time.monotonic`` here, rather than on every call, for two
        reasons: it lets us resolve the real function exactly once (so a
        caller reading the attribute sees the actual callable, not the
        sentinel), and it keeps the per-call path to a plain function
        call with no attribute lookup or branching.
        """
        import math
        import time

        if not isinstance(window_size, (int, float)) or isinstance(
            window_size, bool
        ):
            raise TypeError(
                "window_size must be a real number, not "
                f"{type(window_size).__name__}"
            )
        if not math.isfinite(window_size) or window_size <= 0:
            raise ValueError("window_size must be a positive finite number")

        self.window_size: Final[float] = float(window_size)
        if clock is _USE_SYSTEM_CLOCK:
            self._clock = time.monotonic
        else:
            self._clock = clock

        # Maps window index -> event count for that window.
        self._windows: Dict[int, int] = {}

        # Mirror of _windows' values but ordered by window index.  Keeping
        # this list lets us compute the sliding aggregate by walking the
        # most recent N entries, and the running sum lets us answer in O(1)
        # at the cost of an extra O(1) update on record().
        self._order: List[int] = []
        self._counts: List[int] = []
        self._sum: int = 0

    def record(self, count: int = 1) -> None:
        """Record ``count`` events against the current window.

        ``count`` may be zero, which we permit because a "no-op" record is
        occasionally useful (e.g. a poll loop that records every tick even
        when nothing happened).  Negative counts are rejected to keep the
        per-window totals and the running sum internally consistent.
        """
        if not isinstance(count, int) or isinstance(count, bool):
            raise TypeError(f"count must be an int, not {type(count).__name__}")
        if count < 0:
            raise ValueError("count must be non-negative")
        if count == 0:
            return

        now = self._clock()
        if isinstance(now, bool) or not isinstance(now, (int, float)):
            raise TypeError(
                "clock must return a real number, not "
                f"{type(now).__name__}"
            )
        if not _is_finite_number(now) or now < 0:
            raise ValueError("clock must return a non-negative finite number")

        idx = int(now // self.window_size)
        cur = self._windows.get(idx)
        if cur is None:
            # New window.  This branch covers both "later than anything
            # seen" and "earlier than anything seen" because _windows is
            # keyed by absolute index, not by recency.
            self._windows[idx] = count
            self._order.append(idx)
            self._counts.append(count)
            self._sum += count
        else:
            new = cur + count
            self._windows[idx] = new
            # Linear search for the position is fine here: in the dominant
            # case the window already exists and is the most recent, so the
            # update lands at the end of the list and the search terminates
            # immediately.  Older repeated windows are rare in practice
            # (they imply out-of-order producers), and even then the list is
            # bounded by the number of distinct windows seen.
            for i in range(len(self._order) - 1, -1, -1):
                if self._order[i] == idx:
                    self._counts[i] = new
                    break
            self._sum += count

    def window_total(self, t: float) -> int:
        """Return the count recorded in the window containing ``t``.

        Windows that were never recorded into report zero.  This is the
        natural reading of "no events landed here" and keeps callers from
        having to special-case missing keys.
        """
        if isinstance(t, bool) or not isinstance(t, (int, float)):
            raise TypeError(f"t must be a real number, not {type(t).__name__}")
        if not _is_finite_number(t) or t < 0:
            raise ValueError("t must be a non-negative finite number")
        idx = int(t // self.window_size)
        return self._windows.get(idx, 0)

    def current_total(self) -> int:
        """Return the count in the window the clock currently points at."""
        now = self._clock()
        if isinstance(now, bool) or not isinstance(now, (int, float)):
            raise TypeError(
                "clock must return a real number, not "
                f"{type(now).__name__}"
            )
        if not _is_finite_number(now) or now < 0:
            raise ValueError("clock must return a non-negative finite number")
        idx = int(now // self.window_size)
        return self._windows.get(idx, 0)

    def rate(self, num_windows: int = 1) -> int:
        """Return the aggregate count over the last ``num_windows`` windows.

        "Last" is anchored at the clock's current window — i.e. the window
        containing ``clock()`` — and extends backwards.  Windows that were
        never recorded into contribute zero, which is the honest answer for
        "how many events fell in this span".

        ``num_windows`` must be at least 1.  Asking for zero or negative
        windows is a caller bug; returning zero would mask it, so we raise.
        """
        if not isinstance(num_windows, int) or isinstance(num_windows, bool):
            raise TypeError(
                f"num_windows must be an int, not {type(num_windows).__name__}"
            )
        if num_windows < 1:
            raise ValueError("num_windows must be at least 1")

        now = self._clock()
        if isinstance(now, bool) or not isinstance(now, (int, float)):
            raise TypeError(
                "clock must return a real number, not "
                f"{type(now).__name__}"
            )
        if not _is_finite_number(now) or now < 0:
            raise ValueError("clock must return a non-negative finite number")

        current_idx = int(now // self.window_size)
        if not self._order:
            return 0

        # Fast path: the caller wants a span that fully covers every window
        # we have on record.  The running sum already holds exactly that, so
        # we can return it without touching the per-window structures.
        earliest_seen = min(self._order)
        span_start = current_idx - (num_windows - 1)
        if (
            span_start <= earliest_seen
            and earliest_seen <= current_idx
            and max(self._order) <= current_idx
        ):
            return self._sum

        # General path: walk backwards through the recorded windows in
        # recency order and sum those whose index falls inside the span.
        total = 0
        for i in range(len(self._order) - 1, -1, -1):
            idx = self._order[i]
            if idx < span_start:
                break
            if idx > current_idx:
                continue
            total += self._counts[i]
        return total


def _is_finite_number(x) -> bool:
    """Return True if ``x`` is a finite int or float.

    Booleans are excluded even though ``bool`` is a subclass of ``int``
    in Python, because a clock returning True/False is almost certainly a
    bug, not a meaningful timestamp.
    """
    if isinstance(x, bool):
        return False
    if isinstance(x, int):
        return True
    if isinstance(x, float):
        import math
        return math.isfinite(x)
    return False
