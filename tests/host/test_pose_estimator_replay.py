"""tests/host/test_pose_estimator_replay.py -- real captures replayed
through the host-built PoseEstimator (sprint 044 ticket 003).

Fixtures (tests/host/fixtures/pose_estimator/, byte-for-byte copies; see
README.md there for origin): the 54 min / 100 m vevov run drift1.jsonl,
the vevov bench gyro1.jsonl, and the four-robot fresh-boot bench
fleet-<robot>.jsonl. captures/ is gitignored, so the tests read the copies.

What the logs are. One TLM row per leg (drift1, ~16 s apart, taken at
rest) or per 20 s (stationary runs, after a zero-speed MOVE_V refreshed the
OTOS cache). The replay therefore reconstructs what lies between rows, and
that reconstruction is the one thing here that is not recorded:

  drift1  Per leg the wheel counts come from the log. A leg turning at
          least 50 deg is a pivot then a straight, anything smaller one arc
          (the split tests/dev/otos_fusion_replay.py uses). Motion runs at
          90 deg/s and 200 mm/s, capped at 80% of the row interval; the rest
          of the interval is stillness. The gyro heading across a leg is the
          logged OTOS heading at both ends; the part of the change that is
          bias (b * interval) is spread over the whole interval, the rest
          follows the encoder progress. b and the encoder turn scale come
          from one least-squares fit of the OTOS heading changes on
          [encoder turn, interval] over the whole log; the camera is not
          used to build the input, only to score the output. OTOS x/y
          increments follow the encoder progress. Gyro reads every 4th
          tick (dt 0.05 s) in motion and every tick at rest, the cadence
          the estimator expects once ticket 004 reads the OTOS while idle.
          Headings are quantised to the chip's 0.0055 deg.
  still   Encoders held; the gyro heading is the logged OTOS heading,
          linearly interpolated between rows, read every 0.05 s.

The estimator is scored against the camera exactly as the issue's replay
was: aligned once at the first row, then position and heading error at each
row. The issue's figures (otos-rls row of the replay table, produced by
tests/dev/otos_fusion_replay.py on drift1.jsonl, re-run 2026-10-28 on these
fixtures): end 19.3 cm / -4.1 deg, 2nd-half rms 12.0 cm / 3.3 deg, causal
bias +52.2 deg/h, camera +46.7 deg/h (first half). The matching gyro-only
row (otosH-rls+enc): end 97.7 cm / -4.1 deg, 2nd-half rms 63.3 cm / 3.3 deg.

MEASURED 2026-10-28, `uv run pytest tests/host/test_pose_estimator_replay.py`
on the fixtures above (the bounds below are these plus the margin noted):
  OPTICAL     bias +55.4 deg/h (camera, whole run: +49.6); end 17.9 cm /
              -4.1 deg; 2nd-half rms 13.8 cm / 2.0 deg
  GYRO_ONLY   same bias and heading; end 97.8 cm; 2nd-half rms 63.9 cm
  still       heading held to 0.0 deg after settling in all five runs
              (uncorrected OTOS: +13.3 gyro1 over 19.3 min, +7.4 gopiv,
              +7.1 vevov, -13.0 tovez, +11.0 zuvat over 30 min); learned
              rate +43.9, +22.7, +19.5, -33.4, +35.5 deg/h against the
              data's trailing 10 min +44.3, +21.6, +20.4, -33.5, +33.6
  noise       random-walk density of the logged heading 0.003-0.006
              deg/sqrt(s) on the four fleet robots; the tracker assumes 0.067

Run with::

    uv run pytest tests/host/test_pose_estimator_replay.py
"""

import ctypes
import json
import math
import pathlib

import pytest

from test_odometry import _ROTATIONAL_SLIP
from test_pose_estimator import (  # noqa: F401
    DEG, GYRO_ONLY, OPTICAL, PER_HOUR, lib,
)

FIXTURES = pathlib.Path(__file__).resolve().parent / "fixtures" / "pose_estimator"
FLEET = ("gopiv", "vevov", "tovez", "zuvat")

OTOS_LSB = math.pi / 32768.0  # [rad]
ARM = (-42.8, 2.1)  # [mm] OTOS behind and left of the pivot centre (arm1.json, 12 pivots)
TRACK = 111.6 / 0.969  # [mm] as tests/dev/otos_fusion_replay.py
SPLIT = 50.0 * DEG
DT = 0.05  # [s]
MOTION_EVERY = 4
PIVOT_RATE = 90.0 * DEG  # [rad/s]
STRAIGHT_RATE = 200.0  # [mm/s]
MOTION_SHARE = 0.8

ISSUE_BIAS = 52.2  # [deg/h] causal estimate at the end, otos-rls
ISSUE_BIAS_TOLERANCE = 8.0  # est. 55.4 measured; encoder-derived input, not the replay's lstsq
CAMERA_BIAS_TOLERANCE = 12.0  # against the camera's own full-run fit
HEADING_RMS_LIMIT = 3.5  # [deg] 2nd half; issue 3.3, measured 2.0, raw OTOS 33.5
HEADING_END_LIMIT = 6.0  # [deg] issue -4.1, measured -4.1
POSITION_RMS_LIMIT = 16.0  # [cm] 2nd half; issue 12.0, measured 13.8
POSITION_END_LIMIT = 25.0  # [cm] issue 19.3, measured 17.9
GYRO_ONLY_POSITION_RMS_LIMIT = 70.0  # [cm] issue 63.3, measured 63.9; leg-model floor 49.4 (camH+enc)
STILL_LIMIT = 2.0  # [deg] over 30 min after settling
STILL_SETTLE = 120.0  # [s]
RATE_TRACKING_TOLERANCE = 6.0  # [deg/h] against the data's trailing 10 min median slope
FIRST_VIOLATION_ROWS = 59  # gyro1.jsonl rows 0-58 survive (issue: moved at row 59)


def load(name):
    return [json.loads(s) for s in (FIXTURES / name).read_text().splitlines()]


def wrap(a):
    return (a + math.pi) % (2 * math.pi) - math.pi


def quantise(a):
    return round(a / OTOS_LSB) * OTOS_LSB


def fit(xs, ys):  # (slope, intercept)
    n = len(xs)
    mx, my = sum(xs) / n, sum(ys) / n
    sxx = sum((x - mx) ** 2 for x in xs)
    slope = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / sxx
    return slope, my - slope * mx


def fit2(a, b, y):  # y = p*a + q*b
    saa = sum(x * x for x in a)
    sbb = sum(x * x for x in b)
    sab = sum(x * z for x, z in zip(a, b))
    say = sum(x * z for x, z in zip(a, y))
    sby = sum(x * z for x, z in zip(b, y))
    det = saa * sbb - sab * sab
    return (say * sbb - sby * sab) / det, (saa * sby - sab * say) / det


def rms(values):
    return math.sqrt(sum(v * v for v in values) / len(values))


@pytest.fixture(scope="module")
def rlib(lib):  # noqa: F811
    f, i, v = ctypes.c_float, ctypes.c_int, ctypes.c_void_p
    lib.peAttachScripted.argtypes = [v, i]
    lib.peReplay.argtypes = [v, f, f, f, f, f, f, i]
    return lib


def estimator(lib, k, config):
    h = lib.peCreate()
    lib.peSetGeometry(h, 10.0 * k, TRACK, _ROTATIONAL_SLIP)
    lib.peAttachScripted(h, config)
    return h


def drift_inputs():
    rows = [r for r in load("drift1.jsonl") if r["n"] >= 1]
    tlm = [r["tlm"] for r in rows]
    dl = [q["posl"] - p["posl"] for p, q in zip(tlm, tlm[1:])]
    dr = [q["posr"] - p["posr"] for p, q in zip(tlm, tlm[1:])]
    ratios = sorted(
        math.hypot(q["x"] - p["x"], q["y"] - p["y"]) / ((l + r) / 2)
        for p, q, l, r in zip(tlm, tlm[1:], dl, dr)
        if abs(l + r) / 2 > 1500 and abs(r - l) < 0.2 * abs(l + r))
    k = ratios[len(ratios) // 2]  # [mm/count] firmware chord over encoder counts
    centre = []
    for t in tlm:
        h = math.radians(t["oh"] / 100)
        centre.append((t["ox"] - (ARM[0] * math.cos(h) - ARM[1] * math.sin(h)),
                       t["oy"] - (ARM[0] * math.sin(h) + ARM[1] * math.cos(h))))
    return rows, dl, dr, k, centre


def replay_drift(lib, config):
    rows, dl, dr, k, centre = drift_inputs()
    times = [r["t"] - rows[0]["t"] for r in rows]
    gyro = [0.0]
    for p, q in zip(rows, rows[1:]):
        gyro.append(gyro[-1] + wrap(math.radians(
            (q["tlm"]["oh"] - p["tlm"]["oh"]) / 100)))
    spans = [b - a for a, b in zip(times, times[1:])]
    turns = [(r - l) * k / TRACK for l, r in zip(dl, dr)]
    changes = [b - a for a, b in zip(gyro, gyro[1:])]
    _, bias = fit2(turns, spans, changes)  # [rad/s]

    h = estimator(lib, k, config)
    posl, posr = rows[0]["tlm"]["posl"], rows[0]["tlm"]["posr"]
    out = []
    for i, span in enumerate(spans):
        d = (dl[i] + dr[i]) / 2
        split = abs(turns[i]) >= SPLIT
        pivot_time = abs(turns[i]) / PIVOT_RATE
        straight_time = abs(d) * k / STRAIGHT_RATE
        moving = pivot_time + straight_time if split else max(pivot_time, straight_time)
        moving = min(max(moving, DT), MOTION_SHARE * span)
        steps = max(1, round(span / DT))
        dt = span / steps
        shift = changes[i] - bias * span
        delivered = (0.0, 0.0)
        for s in range(1, steps + 1):
            t = s * dt
            if split:
                pivot = min(1.0, t / pivot_time)
                run = min(1.0, max(0.0, (t - pivot_time) / (moving - pivot_time)))
                half = (dr[i] - dl[i]) / 2
                left, right = -half * pivot + d * run, half * pivot + d * run
                turn_share, move_share = pivot, run
            else:
                move_share = turn_share = min(1.0, t / moving)
                left, right = dl[i] * move_share, dr[i] * move_share
            want = ((centre[i + 1][0] - centre[i][0]) * move_share,
                    (centre[i + 1][1] - centre[i][1]) * move_share)
            sample = t > moving or s % MOTION_EVERY == 0
            lib.peReplay(h, dt, posl + left, posr + right,
                         quantise(gyro[i] + shift * turn_share + bias * t),
                         want[0] - delivered[0], want[1] - delivered[1],
                         1 if sample else 0)
            delivered = want
        posl += dl[i]
        posr += dr[i]
        out.append((lib.peX(h), lib.peY(h), lib.peHeading(h)))
    rate = lib.peBiasRate(h) / PER_HOUR
    lib.peDestroy(h)
    return rows, out, rate


def score(rows, track):
    cam = [r["cam"] for r in rows]
    phi = math.radians(cam[0][2])
    errors = []
    for (x, y, heading), c in zip(track, cam[1:]):
        px = (x * math.cos(phi) - y * math.sin(phi)) / 10 + cam[0][0]  # [cm]
        py = (x * math.sin(phi) + y * math.cos(phi)) / 10 + cam[0][1]
        errors.append((math.hypot(px - c[0], py - c[1]),
                       math.degrees(wrap(heading + phi - math.radians(c[2])))))
    half = len(errors) // 2
    return {
        "end_position": errors[-1][0],
        "end_heading": errors[-1][1],
        "position_rms": rms([e[0] for e in errors[half:]]),
        "heading_rms": rms([e[1] for e in errors[half:]]),
    }


def camera_bias(rows):  # [deg/h] OTOS heading minus camera heading, whole run
    otos, cam = [0.0], [0.0]
    for p, q in zip(rows, rows[1:]):
        otos.append(otos[-1] + wrap(math.radians(
            (q["tlm"]["oh"] - p["tlm"]["oh"]) / 100)))
        cam.append(cam[-1] + wrap(math.radians(q["cam"][2] - p["cam"][2])))
    minutes = [(r["t"] - rows[0]["t"]) / 60 for r in rows]
    slope, _ = fit(minutes, [math.degrees(o - c) for o, c in zip(otos, cam)])
    return slope * 60


@pytest.fixture(scope="module")
def drift(rlib):
    return {config: replay_drift(rlib, config) for config in (OPTICAL, GYRO_ONLY)}


def test_learned_bias_matches_the_issues_causal_estimate_and_the_camera(drift):
    rows, _, rate = drift[OPTICAL]
    assert rate == pytest.approx(ISSUE_BIAS, abs=ISSUE_BIAS_TOLERANCE)
    assert rate == pytest.approx(camera_bias(rows), abs=CAMERA_BIAS_TOLERANCE)


def test_optical_pose_holds_the_issues_replay_figures(drift):
    rows, track, _ = drift[OPTICAL]
    result = score(rows, track)
    assert result["heading_rms"] < HEADING_RMS_LIMIT
    assert abs(result["end_heading"]) < HEADING_END_LIMIT
    assert result["position_rms"] < POSITION_RMS_LIMIT
    assert result["end_position"] < POSITION_END_LIMIT


def test_gyro_only_has_the_same_heading_and_encoder_position(drift):
    rows, optical, optical_rate = drift[OPTICAL]
    _, gyro_only, rate = drift[GYRO_ONLY]
    result = score(rows, gyro_only)
    assert rate == pytest.approx(optical_rate, abs=1.0)
    assert [g[2] for g in gyro_only] == pytest.approx([o[2] for o in optical],
                                                      abs=0.5 * DEG)
    assert result["heading_rms"] < HEADING_RMS_LIMIT
    assert abs(result["end_heading"]) < HEADING_END_LIMIT
    assert result["position_rms"] < GYRO_ONLY_POSITION_RMS_LIMIT


def still_rows(name):
    rows = load(name)
    if name != "gyro1.jsonl":
        return rows
    first = rows[0]
    keep = []
    for r in rows:
        c, c0 = r["cam"], first["cam"]
        if r["tlm"]["posl"] != first["tlm"]["posl"]:
            break
        if c is not None and math.hypot(c[0] - c0[0], c[1] - c0[1]) > 0.5:
            break
        keep.append(r)
    return keep


def replay_still(lib, rows, config):
    h = estimator(lib, 0.08, config)
    t0 = rows[0]["t"]
    times = [r["t"] - t0 for r in rows]
    heads = [math.radians(r["tlm"]["oh"] / 100) for r in rows]
    posl, posr = rows[0]["tlm"]["posl"], rows[0]["tlm"]["posr"]
    reference, worst, j, t = None, 0.0, 0, 0.0
    while t < times[-1]:
        while times[j + 1] < t:
            j += 1
        frac = (t - times[j]) / (times[j + 1] - times[j])
        g = heads[j] + frac * wrap(heads[j + 1] - heads[j])
        lib.peReplay(h, DT, posl, posr, quantise(g), 0.0, 0.0, 1)
        t += DT
        if reference is None and t >= STILL_SETTLE:
            reference = lib.peHeading(h)
        elif reference is not None:
            worst = max(worst, abs(lib.peHeading(h) - reference))
    rate = lib.peBiasRate(h) / PER_HOUR
    lib.peDestroy(h)
    return worst / DEG, rate


def trailing_rate(rows, minutes=10.0, stride=3):
    # median of short-baseline slopes: a single heading step (gyro1 row 39) is an outlier
    t = [(r["t"] - rows[0]["t"]) / 60 for r in rows]
    h = [r["tlm"]["oh"] / 100 for r in rows]
    slopes = sorted((h[i + stride] - h[i]) / (t[i + stride] - t[i]) * 60
                    for i in range(len(rows) - stride) if t[i] >= t[-1] - minutes)
    return slopes[len(slopes) // 2]


STILL_FIXTURES = ["gyro1.jsonl"] + [f"fleet-{r}.jsonl" for r in FLEET]


def test_gyro1_keeps_only_the_rows_before_the_robot_was_moved():
    assert len(still_rows("gyro1.jsonl")) == FIRST_VIOLATION_ROWS


@pytest.mark.parametrize("config", [OPTICAL, GYRO_ONLY])
@pytest.mark.parametrize("name", STILL_FIXTURES)
def test_thirty_minutes_still_holds_heading_and_learns_the_rate(rlib, name, config):
    rows = still_rows(name)
    raw = abs(rows[-1]["tlm"]["oh"] - rows[0]["tlm"]["oh"]) / 100
    worst, rate = replay_still(rlib, rows, config)
    assert raw > 2.0 * STILL_LIMIT
    assert worst < STILL_LIMIT
    assert rate == pytest.approx(trailing_rate(rows), abs=RATE_TRACKING_TOLERANCE)


def test_assumed_noise_density_is_not_below_what_the_fleet_shows():
    # Second difference of the logged heading, 20 s apart: for a random walk
    # its variance is 2 * step variance. The default 0.067 deg/sqrt(s) was
    # taken from a 20 s sd that included the rate ramp; this is the walk alone.
    assumed = 0.00117 / DEG  # [deg/sqrt(s)]
    for robot in FLEET:
        rows = load(f"fleet-{robot}.jsonl")
        x = [r["tlm"]["oh"] / 100 for r in rows]
        dt = (rows[-1]["t"] - rows[0]["t"]) / (len(rows) - 1)
        d2 = [x[i + 1] - 2 * x[i] + x[i - 1] for i in range(1, len(x) - 1)]
        density = rms(d2) / math.sqrt(2.0) / math.sqrt(dt)
        assert density < assumed / 5.0

