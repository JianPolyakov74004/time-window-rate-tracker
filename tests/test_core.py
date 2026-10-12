import math
import unittest

from time_window_rate_tracker import TimeWindowRateTracker


class TestConstruction(unittest.TestCase):
    """Validation at construction time."""

    def test_rejects_zero_window(self):
        with self.assertRaises(ValueError):
            TimeWindowRateTracker(0)

    def test_rejects_negative_window(self):
        with self.assertRaises(ValueError):
            TimeWindowRateTracker(-1)

    def test_rejects_infinite_window(self):
        for bad in (float("inf"), float("-inf"), float("nan")):
            with self.assertRaises(ValueError):
                TimeWindowRateTracker(bad)

    def test_rejects_non_number_window(self):
        with self.assertRaises(TypeError):
            TimeWindowRateTracker("10")

    def test_rejects_bool_window(self):
        with self.assertRaises(TypeError):
            TimeWindowRateTracker(True)

    def test_accepts_int_window(self):
        t = TimeWindowRateTracker(10, clock=lambda: 0)
        self.assertEqual(t.window_size, 10.0)

    def test_accepts_float_window(self):
        t = TimeWindowRateTracker(2.5, clock=lambda: 0)
        self.assertEqual(t.window_size, 2.5)

    def test_default_clock_is_monotonic(self):
        import time
        t = TimeWindowRateTracker(10)
        self.assertIs(t._clock, time.monotonic)

    def test_custom_clock_resolves_sentinel(self):
        clk = lambda: 5.0
        t = TimeWindowRateTracker(10, clock=clk)
        self.assertIs(t._clock, clk)


class FakeClock:
    """Mutable clock for deterministic tests."""

    def __init__(self, t=0.0):
        self.t = float(t)

    def __call__(self):
        return self.t


class TestRecording(unittest.TestCase):
    """Behaviour of record() and window_total()."""

    def test_record_default_one_event(self):
        clk = FakeClock(0.0)
        t = TimeWindowRateTracker(10, clock=clk)
        t.record()
        self.assertEqual(t.window_total(0), 1)
        self.assertEqual(t.window_total(9.9), 1)
        self.assertEqual(t.window_total(10), 0)

    def test_record_accumulates_in_same_window(self):
        clk = FakeClock(0.0)
        t = TimeWindowRateTracker(10, clock=clk)
        t.record(3)
        t.record(4)
        t.record()
        self.assertEqual(t.window_total(0), 8)

    def test_record_across_windows(self):
        clk = FakeClock(0.0)
        t = TimeWindowRateTracker(10, clock=clk)
        t.record(2)  # window 0
        clk.t = 10.0
        t.record(5)  # window 1
        clk.t = 20.0
        t.record(7)  # window 2
        self.assertEqual(t.window_total(0), 2)
        self.assertEqual(t.window_total(10), 5)
        self.assertEqual(t.window_total(20), 7)
        self.assertEqual(t.window_total(15), 5)
        self.assertEqual(t.window_total(5), 2)

    def test_record_skips_zero(self):
        clk = FakeClock(0.0)
        t = TimeWindowRateTracker(10, clock=clk)
        t.record(0)
        self.assertEqual(t.window_total(0), 0)
        self.assertEqual(t.rate(), 0)

    def test_record_rejects_negative(self):
        clk = FakeClock(0.0)
        t = TimeWindowRateTracker(10, clock=clk)
        with self.assertRaises(ValueError):
            t.record(-1)

    def test_record_rejects_non_int_count(self):
        clk = FakeClock(0.0)
        t = TimeWindowRateTracker(10, clock=clk)
        with self.assertRaises(TypeError):
            t.record(1.5)
        with self.assertRaises(TypeError):
            t.record("1")

    def test_record_rejects_bool_count(self):
        clk = FakeClock(0.0)
        t = TimeWindowRateTracker(10, clock=clk)
        with self.assertRaises(TypeError):
            t.record(True)

    def test_record_rejects_bad_clock_value(self):
        clk = FakeClock()
        clk.t = -1.0
        t = TimeWindowRateTracker(10, clock=clk)
        with self.assertRaises(ValueError):
            t.record()

    def test_record_rejects_inf_clock(self):
        clk = FakeClock()
        clk.t = float("inf")
        t = TimeWindowRateTracker(10, clock=clk)
        with self.assertRaises(ValueError):
            t.record()

    def test_record_rejects_nan_clock(self):
        clk = FakeClock()
        clk.t = float("nan")
        t = TimeWindowRateTracker(10, clock=clk)
        with self.assertRaises(ValueError):
            t.record()

    def test_record_rejects_non_number_clock(self):
        t = TimeWindowRateTracker(10, clock=lambda: "5")
        with self.assertRaises(TypeError):
            t.record()

    def test_record_rejects_bool_clock(self):
        t = TimeWindowRateTracker(10, clock=lambda: True)
        with self.assertRaises(TypeError):
            t.record()

    def test_window_total_rejects_negative_t(self):
        clk = FakeClock(0.0)
        t = TimeWindowRateTracker(10, clock=clk)
        with self.assertRaises(ValueError):
            t.window_total(-1)

    def test_window_total_rejects_inf_t(self):
        clk = FakeClock(0.0)
        t = TimeWindowRateTracker(10, clock=clk)
        with self.assertRaises(ValueError):
            t.window_total(float("inf"))

    def test_window_total_rejects_non_number_t(self):
        clk = FakeClock(0.0)
        t = TimeWindowRateTracker(10, clock=clk)
        with self.assertRaises(TypeError):
            t.window_total("0")

    def test_window_total_rejects_bool_t(self):
        clk = FakeClock(0.0)
        t = TimeWindowRateTracker(10, clock=clk)
        with self.assertRaises(TypeError):
            t.window_total(True)

    def test_window_total_for_unrecorded_window(self):
        clk = FakeClock(0.0)
        t = TimeWindowRateTracker(10, clock=clk)
        t.record(5)
        self.assertEqual(t.window_total(100), 0)

    def test_current_total_matches_window_total_at_clock(self):
        clk = FakeClock(5.0)
        t = TimeWindowRateTracker(10, clock=clk)
        t.record(3)
        clk.t = 15.0
        t.record(7)
        self.assertEqual(t.current_total(), 7)
        self.assertEqual(t.window_total(15), 7)

    def test_current_total_for_unrecorded_now(self):
        clk = FakeClock(0.0)
        t = TimeWindowRateTracker(10, clock=clk)
        t.record(3)
        clk.t = 100.0
        self.assertEqual(t.current_total(), 0)


class TestRate(unittest.TestCase):
    """Behaviour of rate() across spans and orderings."""

    def test_rate_default_one_window(self):
        clk = FakeClock(0.0)
        t = TimeWindowRateTracker(10, clock=clk)
        t.record(5)
        self.assertEqual(t.rate(), 5)

    def test_rate_explicit_span(self):
        clk = FakeClock(0.0)
        t = TimeWindowRateTracker(10, clock=clk)
        t.record(2)  # w0
        clk.t = 10.0
        t.record(3)  # w1
        clk.t = 20.0
        t.record(4)  # w2
        clk.t = 25.0
        self.assertEqual(t.rate(1), 4)
        self.assertEqual(t.rate(2), 7)
        self.assertEqual(t.rate(3), 9)

    def test_rate_span_exceeds_recorded(self):
        clk = FakeClock(0.0)
        t = TimeWindowRateTracker(10, clock=clk)
        t.record(2)  # w0
        clk.t = 10.0
        t.record(3)  # w1
        clk.t = 20.0
        t.record(4)  # w2
        clk.t = 25.0
        # Asking for more windows than exist returns the full sum.
        self.assertEqual(t.rate(10), 9)

    def test_rate_with_gap(self):
        clk = FakeClock(0.0)
        t = TimeWindowRateTracker(10, clock=clk)
        t.record(2)  # w0
        clk.t = 30.0
        t.record(5)  # w3
        clk.t = 35.0
        # Windows 1 and 2 were never recorded and report 0.
        self.assertEqual(t.rate(4), 7)
        self.assertEqual(t.rate(2), 5)

    def test_rate_skips_future_windows(self):
        clk = FakeClock(0.0)
        t = TimeWindowRateTracker(10, clock=clk)
        t.record(2)  # w0
        clk.t = 10.0
        t.record(3)  # w1
        clk.t = 20.0
        t.record(4)  # w2
        # Clock reads in the past (w0); future windows must not count.
        clk.t = 5.0
        self.assertEqual(t.rate(1), 2)
        self.assertEqual(t.rate(2), 2)
        self.assertEqual(t.rate(3), 2)

    def test_rate_rejects_zero_span(self):
        clk = FakeClock(0.0)
        t = TimeWindowRateTracker(10, clock=clk)
        with self.assertRaises(ValueError):
            t.rate(0)

    def test_rate_rejects_negative_span(self):
        clk = FakeClock(0.0)
        t = TimeWindowRateTracker(10, clock=clk)
        with self.assertRaises(ValueError):
            t.rate(-2)

    def test_rate_rejects_non_int_span(self):
        clk = FakeClock(0.0)
        t = TimeWindowRateTracker(10, clock=clk)
        with self.assertRaises(TypeError):
            t.rate(1.5)

    def test_rate_rejects_bool_span(self):
        clk = FakeClock(0.0)
        t = TimeWindowRateTracker(10, clock=clk)
        with self.assertRaises(TypeError):
            t.rate(True)

    def test_rate_rejects_bad_clock(self):
        clk = FakeClock()
        clk.t = -1.0
        t = TimeWindowRateTracker(10, clock=clk)
        with self.assertRaises(ValueError):
            t.rate()

    def test_rate_empty_tracker(self):
        clk = FakeClock(5.0)
        t = TimeWindowRateTracker(10, clock=clk)
        self.assertEqual(t.rate(), 0)
        self.assertEqual(t.rate(5), 0)

    def test_rate_float_window_size_boundaries(self):
        clk = FakeClock(0.0)
        t = TimeWindowRateTracker(2.5, clock=clk)
        t.record(1)  # idx 0  (0..2.5)
        clk.t = 2.5
        t.record(1)  # idx 1  (2.5..5.0)
        clk.t = 5.0
        t.record(1)  # idx 2  (5.0..7.5)
        clk.t = 6.0
        self.assertEqual(t.rate(1), 1)
        self.assertEqual(t.rate(2), 2)
        self.assertEqual(t.rate(3), 3)

    def test_rate_repeat_older_window_via_clock(self):
        """Recording into the current window when the clock has not moved
        must accumulate, not replace."""
        clk = FakeClock(0.0)
        t = TimeWindowRateTracker(10, clock=clk)
        t.record(2)
        t.record(3)
        self.assertEqual(t.rate(), 5)


class TestOutdatedBehaviour(unittest.TestCase):
    """Document the chosen interpretation for out-of-order clocks."""

    def test_clock_can_move_backwards_silently(self):
        """The brief is silent on clock monotonicity.  This implementation
        deliberately does not reject a clock that moves backwards: callers
        may use the same tracker across a deliberately rewound fake clock,
        and the rate() query already defines future windows as contributing
        zero.  We document and test that interpretation here so it is locked
        in as behaviour, not accident.
        """
        clk = FakeClock(20.0)
        t = TimeWindowRateTracker(10, clock=clk)
        t.record(5)  # w2
        clk.t = 10.0
        t.record(3)  # w1 — clock moved back, still recorded honestly
        self.assertEqual(t.window_total(10), 3)
        self.assertEqual(t.window_total(20), 5)
        # Clock at w1, asking for 2 windows: w1 + w0 (w0 empty) = 3.
        self.assertEqual(t.rate(2), 3)
        # Asking for 3 windows from w1 covers w1, w0, w-1 — only w1 has data.
        self.assertEqual(t.rate(3), 3)


class TestWindowTotalBoundaries(unittest.TestCase):
    """Boundary semantics for window_total()."""

    def test_window_total_lower_boundary_inclusive(self):
        clk = FakeClock(0.0)
        t = TimeWindowRateTracker(10, clock=clk)
        t.record(1)  # w0
        self.assertEqual(t.window_total(0), 1)

    def test_window_total_upper_boundary_excluded(self):
        clk = FakeClock(0.0)
        t = TimeWindowRateTracker(10, clock=clk)
        t.record(1)  # w0
        self.assertEqual(t.window_total(10), 0)

    def test_window_total_exact_boundary_in_next_window(self):
        clk = FakeClock(10.0)
        t = TimeWindowRateTracker(10, clock=clk)
        t.record(1)  # w1
        self.assertEqual(t.window_total(10), 1)
        self.assertEqual(t.window_total(0), 0)


class TestSumConsistency(unittest.TestCase):
    """The internal running sum must always equal the sum of all stored
    per-window counts, regardless of recording order."""

    def test_sum_after_forward_sequence(self):
        clk = FakeClock(0.0)
        t = TimeWindowRateTracker(10, clock=clk)
        t.record(2)
        clk.t = 10.0
        t.record(3)
        clk.t = 20.0
        t.record(4)
        self.assertEqual(t._sum, 9)

    def test_sum_after_backward_sequence(self):
        clk = FakeClock(20.0)
        t = TimeWindowRateTracker(10, clock=clk)
        t.record(4)
        clk.t = 10.0
        t.record(3)
        clk.t = 0.0
        t.record(2)
        self.assertEqual(t._sum, 9)

    def test_sum_after_repeat_window(self):
        clk = FakeClock(0.0)
        t = TimeWindowRateTracker(10, clock=clk)
        t.record(2)
        t.record(3)
        t.record(1)
        self.assertEqual(t._sum, 6)

    def test_sum_after_gap_then_back(self):
        clk = FakeClock(0.0)
        t = TimeWindowRateTracker(10, clock=clk)
        t.record(2)  # w0
        clk.t = 30.0
        t.record(5)  # w3
        clk.t = 0.0
        t.record(1)  # w0 again
        self.assertEqual(t._sum, 8)
        self.assertEqual(t.window_total(0), 3)
        self.assertEqual(t.window_total(30), 5)


if __name__ == "__main__":
    unittest.main()
