# time-window-rate-tracker

A small library that records event counts into fixed time windows and exposes both per-window totals and an aggregate over the last N windows for rate display.

```python
from time_window_rate_tracker import TimeWindowRateTracker

class FakeClock:
    def __init__(self):
        self.t = 0.0
    def __call__(self):
        return self.t

clock = FakeClock()
tracker = TimeWindowRateTracker(10.0, clock=clock)  # 10-second windows

tracker.record()          # +1 event in window 0
tracker.record(5)         # +5 events in window 0
clock.t = 12.0
tracker.record(2)         # +2 events in window 1

tracker.window_total(0)   # 6  (the window covering t=0..10)
tracker.window_total(12)  # 2  (the window covering t=10..20)
tracker.current_total()  # 2  (the window the clock currently points at)
tracker.rate(1)           # 2  (last 1 window)
tracker.rate(2)           # 8  (last 2 windows: 6 + 2)
```

## Why this exists

When you need to show a rolling rate (requests/sec, events/min) the natural unit is a fixed window, not a sliding log of timestamps. A sliding log is O(n) per query and O(n) memory; a fixed window is O(1) per query and O(w) memory where w is the number of distinct windows seen. The trade-off is precision: events that land near a window boundary count fully in whichever window they fall, so the aggregate over N windows can briefly over- or under-count relative to a true sliding window. For rate *display* that noise is acceptable; for hard rate-limiting it is not, and you should use a token bucket or a GCRA limiter instead.

## The awkward edge

The clock is taken as a constructor argument so tests stay deterministic, but nothing forces it to be monotonic. A clock that moves backwards will record events into whichever window it lands on, and `rate()` will treat any window ahead of the clock as contributing zero. This is a deliberate choice: rejecting a backwards-moving clock would break callers who legitimately want to replay events against an earlier window using the same tracker. If you need strict monotonic enforcement, wrap the clock yourself before passing it in.
