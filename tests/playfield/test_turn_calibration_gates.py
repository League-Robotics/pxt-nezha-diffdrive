"""tests/playfield/test_turn_calibration_gates.py -- host-testable
coverage of `turn_calibration.py`'s G1-G6 gate logic (sprint 031 ticket
007: "Restate G1/G2 bars and fold sprint 029's acceptance scripts into
turn_calibration.py as modes").

What this pins, without a robot or a camera:

- The restated G1/G2 bar CONSTANTS (a silent edit here is exactly the
  kind of drift `measurement-citations.md` exists to catch).
- The pure scoring functions each `run_gN()` drive function calls:
  `g1_score`, `g2_score`, `arc_expected_endpoint_mm`, `arc_path_points`,
  `leg_metrics`, `fit_wheel_lag`, `square_closure_ok`, plus the small
  telemetry-field helpers (`speed`, `intfield`, `frame_now_ms`) and the
  shared completion-wait (`_wait_done`).

What this does NOT cover: the drive-and-measure halves of run_g1..
run_g6 (they need a live Link + Camera against real hardware) -- those
are exercised on tovez in Session C (ticket 016), per this ticket's own
Testing section ("the on-robot drive logic itself is exercised in
Session C, not here").

Run with::

    uv run pytest tests/playfield/test_turn_calibration_gates.py
    uv run pytest tests/playfield/ tests/tools/          # this ticket's own verification command
"""
import math
import pathlib
import sys

import pytest

# tests/playfield/test_turn_calibration_gates.py -> tests/playfield itself
_THIS_DIR = pathlib.Path(__file__).resolve().parent
if str(_THIS_DIR) not in sys.path:
    sys.path.insert(0, str(_THIS_DIR))

import turn_calibration as tc  # noqa: E402  (path must be set up first)


# --- restated bar constants (sprint 031 ticket 007) -----------------------

def test_g1_bar_restated_values():
    assert tc.G1_MEAN_ABS_ERR_DEG == 1.0
    assert tc.G1_SD_DEG == 1.0
    assert tc.G1_MIN_FIX_SAMPLES == 20


def test_g2_bar_restated_value():
    assert tc.G2_ENDPOINT_MM == 10.0


def test_g3_g4_g5_g6_bars_unchanged_shape():
    # Not restated by this ticket -- pin that they still exist with the
    # values this sprint's design overlay documents, so a future edit
    # that quietly loosens one of these is caught here, not on hardware.
    assert tc.G3_LENGTH_TOL_FRAC == pytest.approx(0.005)
    assert tc.G4_MAX_ACCEL_FRAC == pytest.approx(1.5)
    assert tc.G4_MAX_DECEL_FRAC == pytest.approx(2.0)
    assert tc.G5_PEAK_OVERSHOOT_FRAC == pytest.approx(0.05)
    assert tc.G5_MAX_RISE_MM_S2 == pytest.approx(600.0)
    assert tc.G6_BASELINE_CLOSURE_MM == pytest.approx(10.8)


# --- g1_score / g2_score ---------------------------------------------------

def test_g1_score_passes_within_restated_bar():
    errs = [0.2, -0.3, 0.5, -0.1, 0.4, -0.6, 0.1, -0.2]
    score = tc.g1_score(errs)
    assert score['n'] == len(errs)
    assert score['mean_abs_err'] == pytest.approx(0.3)
    assert score['passed'] is True


def test_g1_score_fails_above_restated_bar():
    # sprint 029's own measured G1 numbers: mean|err| 2.07, sd 2.29 --
    # must still fail the RESTATED bar (1.0 / 1.0), not just the
    # original (0.5 / 0.4).
    errs = [2.5, -1.8, 2.2, -1.9, 2.0, -2.1, 1.9, -2.3, 2.4, -1.7, 2.1, -2.0]
    score = tc.g1_score(errs)
    assert score['passed'] is False


def test_g1_score_empty_is_a_fail_not_a_silent_pass():
    score = tc.g1_score([])
    assert score['n'] == 0
    assert score['passed'] is False


def test_g2_score_boundary_is_inclusive():
    score = tc.g2_score([10.0])
    assert score['passed'] is True
    assert score['n_within'] == 1


def test_g2_score_above_bar_fails():
    score = tc.g2_score([12.0, 15.0])
    assert score['mean'] == pytest.approx(13.5)
    assert score['passed'] is False
    assert score['n_within'] == 0


# --- arc_expected_endpoint_mm / arc_path_points ----------------------------

def test_arc_expected_endpoint_quarter_circle():
    d_mm, theta = 100.0, math.pi / 2
    ex, ey = tc.arc_expected_endpoint_mm(d_mm, theta)
    r = d_mm / theta
    assert ex == pytest.approx(r)          # sin(pi/2) = 1
    assert ey == pytest.approx(r)          # 1 - cos(pi/2) = 1


def test_arc_expected_endpoint_reduces_to_straight_line_for_small_theta():
    # As theta -> 0 a chord-drive arc degenerates to a straight leg of
    # length d_mm: ex -> d_mm, ey -> 0.
    d_mm, theta = 100.0, 1e-6
    ex, ey = tc.arc_expected_endpoint_mm(d_mm, theta)
    assert ex == pytest.approx(d_mm, abs=1e-3)
    assert ey == pytest.approx(0.0, abs=1e-3)   # ey ~ d*theta/2 -> ~5e-5 at this theta


def test_arc_path_points_starts_at_p0_and_ends_at_expected_endpoint():
    p0 = (0.0, 0.0, 0.0)   # facing +x, world = body frame here
    d_mm, theta = 100.0, math.pi / 2
    pts = tc.arc_path_points(p0, d_mm, theta, n=10)
    assert pts[0] == pytest.approx((0.0, 0.0), abs=1e-9)
    ex, ey = tc.arc_expected_endpoint_mm(d_mm, theta)
    assert pts[-1] == pytest.approx((ex / 10.0, ey / 10.0), abs=1e-6)
    assert len(pts) == 11


def test_arc_path_points_rotates_with_heading():
    # Facing +y (90 deg): a pure-forward arc's endpoint rotates with it.
    p0 = (5.0, -5.0, 90.0)
    d_mm, theta = 100.0, math.pi / 2
    pts = tc.arc_path_points(p0, d_mm, theta, n=4)
    ex, ey = tc.arc_expected_endpoint_mm(d_mm, theta)
    # body (ex, ey) rotated +90 deg: world = (-ey, ex)/10 + p0
    want = (p0[0] - ey / 10.0, p0[1] + ex / 10.0)
    assert pts[-1] == pytest.approx(want, abs=1e-6)


# --- leg_metrics ------------------------------------------------------------

def _frame(vl, vr, dutl, dutr, now):
    return {'vl': str(vl), 'vr': str(vr), 'dutl': str(dutl), 'dutr': str(dutr), 'now': str(now)}


def test_leg_metrics_on_a_synthetic_ramp():
    frames = [
        _frame(0, 0, 0, 0, 0),
        _frame(50, 50, 100, 100, 50),
        _frame(150, 150, 200, 200, 100),
        _frame(200, 200, 200, 200, 150),
        _frame(200, 200, 200, 200, 200),
        _frame(100, 100, 50, 50, 250),
        _frame(0, 0, 0, 0, 300),
    ]
    m = tc.leg_metrics(frames)
    assert m['peak_v'] == 200
    assert m['first_moving_v'] == pytest.approx(50.0)
    assert m['max_accel'] == pytest.approx(2000.0)   # (150-50)/0.05
    assert m['min_accel'] == pytest.approx(-2000.0)  # (100-200)/0.05


def test_leg_metrics_tail_monotone_true_for_a_clean_decel():
    frames = [_frame(v, v, v, v, i * 50) for i, v in enumerate([0, 200, 200, 150, 100, 50, 0])]
    m = tc.leg_metrics(frames)
    assert m['tail_monotone'] is True


def test_leg_metrics_empty_frames_does_not_raise():
    m = tc.leg_metrics([])
    assert m['peak_v'] is None
    assert m['first_moving_v'] is None
    assert m['tail_monotone'] is True   # vacuously -- nothing to disprove monotonicity


# --- fit_wheel_lag -----------------------------------------------------------

def test_fit_wheel_lag_recovers_a_grid_aligned_lag():
    accel, vcmd, true_lag = 400.0, 200.0, 0.10   # true_lag is on the 5ms search grid
    frames = []
    for now_ms in range(0, 1401, 20):
        t = now_ms / 1000.0
        v = min(vcmd, max(0.0, accel * (t - true_lag)))
        frames.append({'vl': str(round(v)), 'now': str(now_ms)})
    fit = tc.fit_wheel_lag(frames, sign=1, accel=accel, vcmd=vcmd, key='vl')
    assert fit is not None
    assert fit['lag'] == pytest.approx(true_lag, abs=1e-9)
    assert fit['rms'] < 1.0


def test_fit_wheel_lag_negative_sign():
    accel, vcmd, true_lag = 400.0, 200.0, 0.05
    frames = []
    for now_ms in range(0, 1401, 20):
        t = now_ms / 1000.0
        v = -min(vcmd, max(0.0, accel * (t - true_lag)))
        frames.append({'vr': str(round(v)), 'now': str(now_ms)})
    fit = tc.fit_wheel_lag(frames, sign=-1, accel=accel, vcmd=vcmd, key='vr')
    assert fit['lag'] == pytest.approx(true_lag, abs=1e-9)


def test_fit_wheel_lag_too_few_frames_returns_none():
    assert tc.fit_wheel_lag([{'vl': '0', 'now': '0'}], sign=1) is None
    assert tc.fit_wheel_lag([], sign=1) is None


# --- square_closure_ok -------------------------------------------------------

def test_square_closure_ok_boundary_is_inclusive():
    assert tc.square_closure_ok(tc.G6_BASELINE_CLOSURE_MM) is True
    assert tc.square_closure_ok(tc.G6_BASELINE_CLOSURE_MM + 0.1) is False
    assert tc.square_closure_ok(0.0) is True


# --- small telemetry-field helpers -------------------------------------------

def test_speed_clips_a_corrupted_value():
    assert tc.speed({'vl': '5567'}, 'vl') == 0     # radio-corrupted frame, tigez 2026-09-04
    assert tc.speed({'vl': '200'}, 'vl') == 200
    assert tc.speed({}, 'vl') == 0


def test_intfield_falls_back_on_bad_value():
    assert tc.intfield({'dutl': 'not-a-number'}, 'dutl', default=-1) == -1
    assert tc.intfield({'dutl': '300'}, 'dutl') == 300
    assert tc.intfield({}, 'now', default=7) == 7


def test_frame_now_ms():
    assert tc.frame_now_ms({'now': '1234'}) == 1234
    assert tc.frame_now_ms({}) == 0


# --- _wait_done ---------------------------------------------------------------

class _FakeLinkDoneAfterN:
    """Answers STATUS with `done` unset for `n_polls_before_done` calls,
    then reports the matching id -- enough to exercise `_wait_done()`
    without a socket."""

    def __init__(self, n_polls_before_done, tid, reason='stop'):
        self.n = n_polls_before_done
        self.tid = tid
        self.reason = reason
        self.calls = 0

    def status(self):
        self.calls += 1
        if self.calls > self.n:
            return {'done': str(self.tid), 'reason': self.reason}
        return {'done': '0'}


def test_wait_done_returns_reason_once_matched():
    link = _FakeLinkDoneAfterN(n_polls_before_done=2, tid=7, reason='stop')
    reason = tc._wait_done(link, tid=7, timeout_ms=5000, extra_s=5.0)
    assert reason == 'stop'
    assert link.calls == 3


def test_wait_done_times_out_to_none():
    link = _FakeLinkDoneAfterN(n_polls_before_done=10**6, tid=7)
    reason = tc._wait_done(link, tid=7, timeout_ms=1, extra_s=0.05)
    assert reason is None


# --- camera_noise_floor -------------------------------------------------------

class _FakeCam:
    """A `.sample()` source cycling through a fixed heading sequence --
    enough to drive `camera_noise_floor()` without a real camera."""

    def __init__(self, headings):
        self._headings = list(headings)
        self._i = 0

    def sample(self):
        if self._i >= len(self._headings):
            return None
        h = self._headings[self._i]
        self._i += 1
        return (0.0, 0.0, 0.0, h, 0.0)


def test_camera_noise_floor_zero_sd_for_identical_samples():
    cam = _FakeCam([10.0] * 20)
    noise = tc.camera_noise_floor(cam, n=20, gap=0.0)
    assert noise['n'] == 20
    assert noise['sd'] == pytest.approx(0.0, abs=1e-9)
    assert noise['ptp'] == pytest.approx(0.0, abs=1e-9)


def test_camera_noise_floor_nonzero_sd_for_spread_samples():
    cam = _FakeCam([9.0, 11.0] * 10)
    noise = tc.camera_noise_floor(cam, n=20, gap=0.0)
    assert noise['n'] == 20
    assert noise['sd'] == pytest.approx(1.0, abs=1e-2)


def test_camera_noise_floor_no_samples_does_not_raise():
    cam = _FakeCam([])
    noise = tc.camera_noise_floor(cam, n=5, gap=0.0)
    assert noise == {'n': 0, 'sd': None, 'ptp': None}
