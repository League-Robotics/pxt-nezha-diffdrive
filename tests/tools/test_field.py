"""tests/tools/test_field.py -- pins `tools/field.py`'s playfield
geometry: `wrap()`, `score_corners()`, `path_deviation()`, `closure()`.

**Why this exists.** Sprint 005 ticket 003 closes
`clasi/sprints/005-retrofit-bench-tooling-onto-the-v6-telemetry-stream/
issues/tools-link-layer-consolidation.md` (code review R-24/R-26): 8
copies of the same angle-wrap logic, 6 duplicated `DOTS`/`ORDER`/`RECT`
constant blocks, and -- the sharpest instance -- 4 separate
corner-scoring implementations that had already DISAGREED for the same
recorded run (`tour_run.py`'s console reported "SW 31.3cm" for a
corner `practice_chart.py`'s chart reported "SW=unobserved", because
only the chart's copy accounted for the camera having been blind at
the moment of closest approach). `tools/field.py` replaces all of it
with one implementation each; this file proves `score_corners()`
actually reproduces both halves of that disagreement correctly (the
gap-blind case AND the trusted-because-it-was-close case), not just
that it runs without raising.

Run with::

    uv run pytest tests/tools/test_field.py
"""
import inspect
import math
import pathlib
import sys

import pytest

# tests/tools/test_field.py -> tools -> tests -> repo root
_REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
_TOOLS_DIR = _REPO_ROOT / 'tools'
if str(_TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(_TOOLS_DIR))

import field  # noqa: E402  (path must be set up first)


# --- wrap() --------------------------------------------------------------

@pytest.mark.parametrize('d, expected', [
    (0.0, 0.0),
    (90.0, 90.0),
    (180.0, 180.0),          # the upper boundary is INCLUSIVE
    (-180.0, 180.0),         # the lower boundary wraps to the same value
    (270.0, -90.0),
    (-270.0, 90.0),
    (360.0, 0.0),
    (-360.0, 0.0),
    (540.0, 180.0),
])
def test_wrap_boundary_values(d, expected):
    assert field.wrap(d) == pytest.approx(expected)


def test_wrap_just_past_the_upper_boundary_flips_sign():
    assert field.wrap(180.0001) == pytest.approx(-179.9999)


def test_wrap_just_past_the_lower_boundary_flips_sign():
    assert field.wrap(-180.0001) == pytest.approx(179.9999)


def test_wrap_result_always_in_range():
    for d in (-1000.0, -725.3, -1.0, 0.0, 1.0, 359.0, 1000.0):
        w = field.wrap(d)
        assert -180.0 < w <= 180.0


# --- turn_total() (sprint 034 ticket 001, TL-03) -------------------------
#
# The defect this replaces: `rotation_check.py` and a second bench
# tool (deleted outright by sprint 034 ticket 003) each unwrapped a
# pivot with `revs = round(commanded / 360.0)`, and
# `round(0.5)` is 0 under banker's rounding. So for a commanded +/-180
# the whole expression collapsed to `wrap(after - before)`, a 183 deg
# physical turn read -177, and `gyro / commanded` came out NEGATIVE --
# which then went into a mean taken over [360, 180, -180]. turn_total()
# anchors the unwrap on the commanded angle instead, with no `revs`
# term and no `round()`, so every angle (the +/-180 boundary included)
# goes through the same one line.

@pytest.mark.parametrize('commanded, measured, expected', [
    # The regression itself: over-rotation on the wrap boundary. The
    # OTOS reports the wrapped delta, -177, for a real +183 deg turn.
    (180.0, -177.0, 183.0),
    (-180.0, 177.0, -183.0),
    # Under-rotation on the same boundary still works.
    (180.0, 177.0, 177.0),
    (-180.0, -177.0, -177.0),
    # Exactly on the command.
    (180.0, 180.0, 180.0),
    (-180.0, -180.0, -180.0),
    # A full revolution, which a wrapped heading cannot show at all.
    (360.0, 3.0, 363.0),
    (360.0, 0.0, 360.0),
    (-360.0, -3.0, -363.0),
    # Small commanded angles, where no unwrapping is needed.
    (90.0, 92.0, 92.0),
    (-90.0, -88.0, -88.0),
    (0.5, 0.7, 0.7),
    # A commanded 0 with a small measured drift reports the drift.
    (0.0, 2.5, 2.5),
    (0.0, -2.5, -2.5),
])
def test_turn_total_unwraps_onto_the_commanded_revolution(
        commanded, measured, expected):
    assert field.turn_total(commanded, measured) == pytest.approx(expected)


def test_turn_total_accepts_an_already_unwrapped_measurement():
    # A caller summing per-sample wrapped deltas (tools/pivot_truth.py's
    # _yaw_mark()) hands in a total that is already unwrapped. It must
    # pass through, not get re-wrapped onto some other revolution.
    assert field.turn_total(180.0, 183.0) == pytest.approx(183.0)
    assert field.turn_total(360.0, 363.0) == pytest.approx(363.0)
    assert field.turn_total(-360.0, -363.0) == pytest.approx(-363.0)


@pytest.mark.parametrize('commanded, measured', [
    (180.0, -177.0),    # +183 physical
    (-180.0, 177.0),    # -183 physical
])
def test_turn_total_ratio_keeps_the_sign_of_an_overrotating_pivot(
        commanded, measured):
    # The defect's user-visible symptom: `gyro / commanded` was -0.98
    # for a pivot that over-rotated by 3 deg, and that sign-flipped
    # term was averaged in with the others.
    ratio = field.turn_total(commanded, measured) / commanded
    assert ratio > 0.0
    assert ratio == pytest.approx(183.0 / 180.0)


def test_turn_total_does_not_use_round_or_a_revs_term():
    # Pins the fix itself, not just its outputs: the `revs` form is
    # what could not resolve the +/-180 boundary, and re-introducing it
    # would pass the numeric cases above only until someone commanded
    # a half-revolution again.
    src = inspect.getsource(field.turn_total)
    body = src.split('"""')[-1]
    assert 'round(' not in body
    assert 'revs' not in body


# --- robot_heading_from_tag_yaw() (sprint 029 ticket 006, TL-11) ---------
#
# robot heading = tag yaw + 90 (fixed AprilCam convention, NEVER stored
# in field_calibration.json) + residual_deg (the sub-degree physical
# mount skew, the ONLY part field_calibration.json stores). This is the
# one place a RAW/unregistered tag reading gets the +90 added back --
# see .claude/rules/tag-yaw-is-the-front-edge-not-the-hat.md.

def test_robot_heading_from_tag_yaw_adds_exactly_90_with_zero_residual():
    assert field.robot_heading_from_tag_yaw(0.0, 0.0) == pytest.approx(90.0)
    assert field.robot_heading_from_tag_yaw(10.0, 0.0) == pytest.approx(100.0)


def test_robot_heading_from_tag_yaw_adds_the_residual_on_top_of_90():
    # vevov's real residual (field_calibration.json's mount_yaw_residual_deg,
    # equal to the pre-sprint-029 91.11616234175443 minus the fixed 90).
    got = field.robot_heading_from_tag_yaw(0.0, 1.116162341754432)
    assert got == pytest.approx(91.116162341754432)


def test_robot_heading_from_tag_yaw_default_residual_is_zero():
    assert (field.robot_heading_from_tag_yaw(5.0)
            == field.robot_heading_from_tag_yaw(5.0, 0.0))


def test_robot_heading_from_tag_yaw_wraps_into_range():
    got = field.robot_heading_from_tag_yaw(170.0, 5.0)   # 170+90+5 = 265
    assert -180.0 < got <= 180.0
    assert got == pytest.approx(265.0 - 360.0)


# --- pose_from_registered_samples() (sprint 029 ticket 007) ---------------
#
# The 2026-09-04d bug, pinned here: `tools/field_dance.py`'s `pose()`
# used to run a REGISTERED tag's `yaw_rad` (already the robot's heading
# -- the daemon applies the +90 deg convention at registration time)
# through `robot_heading_from_tag_yaw()`, adding the convention a
# second time. Pivots still passed (heading DELTAS cancel a constant
# offset), but every drive's bearing was off by +90 deg (MEASURED
# tovez 2026-09-04, captures/bench-acceptance-029-20260904d/
# heading-probe.log). A fake daemon sample standing in for a
# REGISTERED tag reading must come back UNCHANGED, plus lever geometry
# -- never with 90 added.

def test_pose_from_registered_samples_returns_yaw_unchanged_no_lever():
    # One sample, yaw_rad = 0 (i.e. the daemon already reports the
    # robot facing along the world +x axis for this REGISTERED tag).
    # A double-add bug would return 90.0 here, not 0.0.
    x, y, h = field.pose_from_registered_samples(
        [(0.0, 10.0, 20.0)], lever_cm=[0.0, 0.0])
    assert h == pytest.approx(0.0)
    assert x == pytest.approx(10.0)
    assert y == pytest.approx(20.0)


def test_pose_from_registered_samples_matches_a_nonzero_registered_yaw():
    # yaw_rad = pi/2 (90 deg) -- a registered tag reporting the robot
    # already facing +y. Must come back as 90.0, not 180.0.
    x, y, h = field.pose_from_registered_samples(
        [(math.pi / 2, 0.0, 0.0)], lever_cm=[0.0, 0.0])
    assert h == pytest.approx(90.0)


def test_pose_from_registered_samples_applies_lever_correction():
    # yaw_rad = 0 (facing +x), tag mounted 2 cm ahead of the centre of
    # rotation along the robot's own forward axis -- the centre should
    # sit 2 cm BEHIND the tag's world position, along +x.
    x, y, h = field.pose_from_registered_samples(
        [(0.0, 10.0, 0.0)], lever_cm=[2.0, 0.0])
    assert x == pytest.approx(8.0)
    assert y == pytest.approx(0.0)
    assert h == pytest.approx(0.0)


def test_pose_from_registered_samples_averages_multiple_samples():
    samples = [(0.0, 10.0, 0.0), (0.0, 12.0, 2.0)]
    x, y, h = field.pose_from_registered_samples(samples, lever_cm=[0.0, 0.0])
    assert x == pytest.approx(11.0)
    assert y == pytest.approx(1.0)
    assert h == pytest.approx(0.0)


def test_pose_from_registered_samples_circular_mean_across_the_wrap():
    # Two samples straddling +-180 deg (+179 and -179) must average to
    # 180, not 0 -- a naive arithmetic mean would get this wrong.
    samples = [(math.radians(179.0), 0.0, 0.0),
               (math.radians(-179.0), 0.0, 0.0)]
    _, _, h = field.pose_from_registered_samples(samples, lever_cm=[0.0, 0.0])
    assert h == pytest.approx(180.0)


def test_pose_from_registered_samples_empty_returns_none():
    assert field.pose_from_registered_samples([], lever_cm=[0.0, 0.0]) is None


# --- registered_pose_distance() (sprint 031 ticket 002) -------------------
#
# The positional analogue of the 2026-09-04d heading bug pinned above:
# `tools/field_dance.py` used to divide a distance computed from two
# REGISTERED-tag poses by a tool-side `parallax_k`, even though the
# daemon's own registered `mount_z_cm` had already applied that exact
# parallax correction when it reported those poses. Every tovez drive
# read ~12% short until the division was removed
# (`clasi/issues/parallax-k-and-registered-mount-z-correct-twice.md`).
# `registered_pose_distance()` takes no scaling-factor argument at all
# -- that absence is the guard against reintroducing the double
# correction, not just a comment saying not to.

def test_registered_pose_distance_matches_raw_hypot():
    a = (0.0, 0.0, 0.0)
    b = (3.0, 4.0, 0.0)
    assert field.registered_pose_distance(a, b) == pytest.approx(5.0)


def test_registered_pose_distance_ignores_heading():
    # Only the x/y components participate -- differing headings must
    # not perturb the distance.
    a = (0.0, 0.0, 10.0)
    b = (6.0, 8.0, 200.0)
    assert field.registered_pose_distance(a, b) == pytest.approx(10.0)


def test_registered_pose_distance_zero_for_identical_poses():
    a = (12.5, -3.2, 45.0)
    assert field.registered_pose_distance(a, a) == pytest.approx(0.0)


def test_registered_pose_distance_is_unscaled_not_dilated_by_a_borrowed_k():
    # This is exactly the recorded regression shape: a 20 cm commanded
    # drive, read through vevov's borrowed parallax_k = 1.1167, used to
    # come back as 20 / 1.1167 = 17.91 cm. registered_pose_distance()
    # must return the true 20.0, not that dilated figure, and its
    # signature has no k parameter to divide by in the first place.
    a = (0.0, 0.0, 0.0)
    b = (20.0, 0.0, 0.0)
    dist = field.registered_pose_distance(a, b)
    assert dist == pytest.approx(20.0)
    assert dist != pytest.approx(20.0 / 1.1167)
    import inspect
    assert 'k' not in inspect.signature(field.registered_pose_distance).parameters, (
        'registered_pose_distance() must not grow a scaling-factor '
        'parameter -- that is what let the daemon-owned parallax '
        'correction be re-applied a second time')


# --- score_corners(): the disagreement this ticket fixes -----------------

def _row(t, x, y, yaw=0.0):
    return (t, x, y, yaw)


def test_score_corners_empty_rows_returns_all_none():
    res = field.score_corners([])
    assert res == {tag: None for tag in field.ORDER}


def test_score_corners_reproduces_the_recorded_disagreement():
    """One dot (SW) is approached, but the closest sample sits right
    beside a >0.4s tracking gap and the miss is > 3cm -- this is
    EXACTLY the shape of run that used to make tour_run.py's console
    print "SW 31.3cm" while practice_chart.py's own copy of this same
    algorithm printed "SW=unobserved" for the identical recorded rows.
    Now there is only one implementation, so there is only one answer.
    """
    sw_x, sw_y = field.DOTS['SW']
    rows = [
        _row(0.0, sw_x + 20.0, sw_y + 20.0),   # far from SW, well-tracked
        _row(0.2, sw_x + 15.0, sw_y + 15.0),   # still well-tracked
        # >0.4s gap here (tracking dropped out)
        _row(1.0, sw_x + 8.0, sw_y + 8.0),     # closest sample: ~11.3cm off,
                                                # right after the gap
        _row(1.2, sw_x + 25.0, sw_y + 25.0),   # moves away again
    ]
    res = field.score_corners(rows, order=['SW'], dots=field.DOTS)
    assert res['SW'] is None, (
        'a closest-approach sample sitting beside a tracking gap, more '
        'than 3cm from the dot, must be refused -- not reported as a '
        'confident distance')


def test_score_corners_trusts_a_close_approach_even_beside_a_gap():
    """The other half of the same rule: a closest sample within 3cm of
    the dot is trusted even if it sits beside a gap -- the robot was
    plainly there. Getting only the "refuse near a gap" half right
    (and this half wrong) would make every close corner touch spuriously
    unobserved, which is its own kind of wrong answer."""
    sw_x, sw_y = field.DOTS['SW']
    rows = [
        _row(0.0, sw_x + 20.0, sw_y + 20.0),
        # >0.4s gap here
        _row(1.0, sw_x + 1.0, sw_y + 1.0),     # ~1.4cm off -- genuinely close
        _row(1.2, sw_x + 20.0, sw_y + 20.0),
    ]
    res = field.score_corners(rows, order=['SW'], dots=field.DOTS)
    assert res['SW'] is not None
    assert res['SW'] == pytest.approx(math.hypot(1.0, 1.0))


def test_score_corners_no_gap_returns_real_distance_for_every_tag():
    """Continuous tracking, no gaps: every corner in `order` gets a
    real numeric answer, and the algorithm scans FORWARD through
    `rows` so an earlier corner's sample cannot be reused by a later
    one."""
    rows = []
    t = 0.0
    for tag in field.ORDER:
        dx, dy = field.DOTS[tag]
        rows.append(_row(t, dx, dy))
        t += 0.1
    res = field.score_corners(rows)
    for tag in field.ORDER:
        assert res[tag] == pytest.approx(0.0, abs=1e-9)


def test_score_corners_forward_scan_ignores_a_pre_visit_near_approach():
    """A discriminating test for the forward-only scan, not just a
    same-answer-either-way one: row0 is a SPURIOUS close pass near B's
    dot that happens BEFORE the robot has even reached A; row1 is the
    real A visit; row2 is B's real (worse) approach. A whole-list scan
    for B (no `used` tracking) would wrongly pick row0 (distance 5,
    the closest anywhere in the rows) as B's score. The forward-only
    scan must instead start B's search at A's claimed index, landing
    on row2 (distance 50) -- the approach that actually happened after
    A was visited.
    """
    dots = {'A': (0.0, 0.0), 'B': (100.0, 0.0)}
    rows = [
        _row(0.0, 95.0, 0.0),    # near B, but BEFORE A has been visited
        _row(0.1, 0.0, 0.0),     # the real A visit (dist 0)
        _row(0.2, 50.0, 0.0),    # the real B visit (dist 50, worse)
    ]
    res = field.score_corners(rows, order=['A', 'B'], dots=dots)
    assert res['A'] == pytest.approx(0.0, abs=1e-9)
    assert res['B'] == pytest.approx(50.0), (
        'B must be scored from its post-A approach (row2), not the '
        'numerically-closer but pre-A spurious pass (row0)')


# --- score_corners(): the TL-08 bounded window ---------------------------

def _tl08_lap_rows(dt=0.25):
    """The TL-08 scenario, written out as an explicit leg list: a lap
    that starts on NE, passes NW 4 cm off at t = 5 s, touches SW / SE /
    NE 1 cm off at t = 15 / 25 / 35 s, and then OVER-CLOSES -- its
    closing leg drifts back along the north edge and ends 1.5 cm from
    NW at t = 38 s.

    Sampled every `dt` s so no interval exceeds `score_corners()`'s
    0.4 s `gap_s`; a gap would make the blind-stretch rule, not the
    window, decide the answer and the fixture would stop testing what
    it is here to test.
    """
    nw, sw, se, ne = (field.DOTS['NW'], field.DOTS['SW'],
                      field.DOTS['SE'], field.DOTS['NE'])
    legs = [
        # (t_start, t_end, from_xy, to_xy)
        (0.0, 5.0, ne, (nw[0] + 4.0, nw[1])),    # NE start -> 4 cm off NW
        (5.0, 15.0, (nw[0] + 4.0, nw[1]), (sw[0], sw[1] + 1.0)),
        (15.0, 25.0, (sw[0], sw[1] + 1.0), (se[0] - 1.0, se[1])),
        (25.0, 35.0, (se[0] - 1.0, se[1]), (ne[0], ne[1] - 1.0)),
        # the over-close: back west along the north edge, ending 1.5 cm
        # from NW -- NW's GLOBAL closest approach over the whole run.
        (35.0, 38.0, (ne[0], ne[1] - 1.0), (nw[0] + 1.5, nw[1])),
    ]
    rows = [_row(0.0, ne[0], ne[1])]
    for t0, t1, (x0, y0), (x1, y1) in legs:
        n = int(round((t1 - t0) / dt))
        for k in range(1, n + 1):
            f = k / n
            rows.append(_row(t0 + f * (t1 - t0),
                             x0 + f * (x1 - x0), y0 + f * (y1 - y0)))
    return rows


def test_score_corners_bounds_each_corner_to_its_own_window():
    """TL-08 (08-26 C-16). The unbounded scan let NW take the late
    1.5 cm over-close at t = 38 s, which pushed `used` to the tail and
    left SW / SE / NE a handful of final samples -- one good run read
    as three bad corners. With a per-corner window NW is scored from
    its real 4 cm pass at t = 5 s and every corner keeps its own
    approach."""
    rows = _tl08_lap_rows()

    res = field.score_corners(rows)

    assert res['NW'] == pytest.approx(4.0, abs=0.2), (
        "NW must be scored from its own approach (4 cm at t=5 s), not "
        "from the closing leg's 1.5 cm re-approach at t=38 s")
    for tag in ('SW', 'SE', 'NE'):
        assert res[tag] is not None, (
            f'{tag} was starved by an earlier corner claiming the tail '
            f'of the run')
        assert res[tag] == pytest.approx(1.0, abs=0.2), (
            f'{tag} must score its own ~1 cm touch, not a leftover '
            f'tail sample tens of cm away')


def test_score_corners_two_corners_cannot_claim_the_same_sample():
    """`used = besti` (the old code) let the NEXT corner start its scan
    AT the sample the previous corner just claimed, so two consecutive
    corners could both be scored from one row. Here row0 is A's exact
    hit and is also the closest row to B; `used = besti + 1` forces B
    onto row1."""
    dots = {'A': (0.0, 0.0), 'B': (0.5, 0.0)}
    rows = [
        _row(0.0, 0.0, 0.0),     # A's exact hit -- and B's closest row
        _row(0.1, 20.0, 0.0),    # the only row left for B
    ]

    res = field.score_corners(rows, order=['A', 'B'], dots=dots)

    assert res['A'] == pytest.approx(0.0, abs=1e-9)
    assert res['B'] == pytest.approx(19.5), (
        'B must be scored from row1; scoring it 0.5 cm means it '
        'reclaimed row0, the sample A already used')


# --- path_deviation(): the PY-08 unguarded-divide guard -------------------

def test_path_deviation_on_the_rectangle_is_near_zero():
    nw = field.DOTS['NW']
    devs = field.path_deviation([_row(0.0, nw[0], nw[1])])
    assert devs[0] == pytest.approx(0.0, abs=1e-9)


def test_path_deviation_guards_a_degenerate_zero_length_segment():
    """PY-08: a segment whose two endpoints coincide must not raise a
    ZeroDivisionError -- it is skipped, and any other real segment
    still scores the point. Every one of this function's former
    per-tool copies computed `.../L` unguarded."""
    degenerate = [((0.0, 0.0), (0.0, 0.0))]     # zero-length segment
    real = [((0.0, 0.0), (10.0, 0.0))]          # a real segment for contrast
    devs = field.path_deviation([_row(0.0, 5.0, 0.0)],
                                segments=degenerate + real)
    assert devs[0] == pytest.approx(0.0, abs=1e-9)


def test_path_deviation_all_degenerate_segments_returns_infinity():
    """If EVERY segment is degenerate there is nothing to project onto
    -- this must not crash, it reports the point as arbitrarily far
    from a (nonexistent) rectangle."""
    degenerate = [((1.0, 1.0), (1.0, 1.0))]
    devs = field.path_deviation([_row(0.0, 0.0, 0.0)], segments=degenerate)
    assert devs[0] == math.inf


# --- closure() -------------------------------------------------------------

def test_closure_empty_rows():
    assert field.closure([]) == (None, None)


def test_closure_distance_and_heading_error():
    rows = [_row(0.0, 0.0, 0.0, yaw=0.0), _row(1.0, 3.0, 4.0, yaw=170.0)]
    dist, herr = field.closure(rows, start_heading=180.0)
    assert dist == pytest.approx(5.0)
    assert herr == pytest.approx(-10.0)


def test_closure_heading_error_is_none_without_start_heading():
    rows = [_row(0.0, 0.0, 0.0), _row(1.0, 3.0, 4.0)]
    dist, herr = field.closure(rows)
    assert dist == pytest.approx(5.0)
    assert herr is None


# --- LIMITS/MARGIN: pinned against the rule file's own numbers -----------

def test_limits_and_margin_match_the_playfield_rule_file():
    """Drift guard: `.claude/rules/playfield-testing.md` is the source
    of truth for these two numbers (134.3 x 89.3 cm field, A1-centred,
    ±67.15/±44.65 cm limits, 12 cm margin). If the rule file's numbers
    ever change without this module being updated to match (or vice
    versa), this test must fail -- it reads the rule file itself
    rather than duplicating its literals blind.
    """
    rule_path = (_REPO_ROOT / '.claude' / 'rules' / 'playfield-testing.md')
    text = rule_path.read_text()
    assert '67.15' in text, 'rule file no longer states the x limit'
    assert '44.65' in text, 'rule file no longer states the y limit'
    assert '12 cm margin' in text, 'rule file no longer states the margin'
    assert field.LIMITS == (67.15, 44.65)
    assert field.MARGIN == 12.0


# --- clears_margin(): recorder-side, after-the-fact check -----------------

def test_clears_margin_empty_rows_trivially_clears():
    assert field.clears_margin([]) is True


def test_clears_margin_the_tour_rectangle_clears_comfortably():
    """The 100x60 cm tour rectangle (+/-50/+/-30) is well inside
    LIMITS - MARGIN (+/-55.15/+/-32.65) -- 17 x 15 cm of raw spare to
    the field edge, comfortably past the 12cm margin requirement. A
    good sanity-check pass case."""
    rows = [_row(i * 0.1, x, y) for i, (x, y) in enumerate(field.RECT)]
    assert field.clears_margin(rows) is True


def test_clears_margin_a_row_outside_the_margin_fails():
    rows = [_row(0.0, 0.0, 0.0), _row(0.1, 60.0, 0.0)]   # 60 > 55.15
    assert field.clears_margin(rows) is False


def test_clears_margin_checks_y_independently_of_x():
    rows = [_row(0.0, 0.0, 40.0)]   # x fine, but 40 > 32.65
    assert field.clears_margin(rows) is False


# --- check_path(): planner-side pre-flight check, full projected path ----

def test_check_path_empty_waypoints_returns_no_offenders():
    assert field.check_path([]) == []


def test_check_path_the_tour_rectangle_clears_the_margin():
    """Same rectangle as the clears_margin() sanity check above, but
    exercised as a planner's projected path (waypoints + segments)
    rather than recorded rows."""
    assert field.check_path(field.RECT) == []


def test_check_path_a_single_waypoint_outside_the_margin_is_caught():
    offenders = field.check_path([(0.0, 0.0), (60.0, 0.0)])
    assert offenders, 'a waypoint past LIMITS - MARGIN must be flagged'
    assert any(x == pytest.approx(60.0) and y == pytest.approx(0.0)
               for x, y in offenders), (
        'the far (unsafe) endpoint itself must be among the offenders')


def test_check_path_a_multi_leg_route_safe_at_both_ends_but_not_through_an_intermediate_waypoint():
    """The route's overall start and end both clear the margin, but an
    intermediate waypoint (and therefore the segments touching it)
    does not -- this must still be caught. `closure()` elsewhere in
    this module deliberately looks only at the first and last row; a
    `check_path()` that made the same simplification would silently
    wave a route with an unsafe middle leg through pre-flight."""
    waypoints = [(0.0, 0.0), (60.0, 0.0), (0.0, 10.0)]
    offenders = field.check_path(waypoints)
    assert offenders, 'the unsafe intermediate waypoint must be caught'
    assert any(x == pytest.approx(60.0) and y == pytest.approx(0.0)
               for x, y in offenders)


def test_check_path_flags_the_whole_unsafe_stretch_of_a_segment_not_just_its_endpoint():
    """The straight-line SEGMENT is what's checked, not merely the two
    listed waypoints: once a leg crosses out of the margin it stays
    out for a whole stretch approaching the far (unsafe) endpoint, and
    check_path() must report that stretch (multiple interpolated
    points), not only the single flagged waypoint -- proving the
    segment is actually walked, not just its endpoints looked up."""
    offenders = field.check_path([(50.0, 0.0), (60.0, 0.0)])
    assert len(offenders) > 1, (
        'a segment that dips outside the margin should surface more '
        'than just its bad endpoint -- otherwise nothing distinguishes '
        'segment-walking from an endpoints-only check')




# --- usable_half_extent(): ONE field size, derived ------------------------

def test_usable_half_extent_is_derived_from_limits_and_margin():
    """Derived, never a second hand-typed pair -- that is the whole
    point of the accessor. Recomputing it here from `LIMITS` and
    `MARGIN` (which the rule-file drift guard above pins to
    `.claude/rules/playfield-testing.md`) means a typo'd literal in
    `field.py` fails here rather than shrinking the field silently."""
    hx, hy = field.usable_half_extent()
    assert hx == pytest.approx(field.LIMITS[0] - field.MARGIN)
    assert hy == pytest.approx(field.LIMITS[1] - field.MARGIN)
    assert (hx, hy) == pytest.approx((55.15, 32.65))


def test_within_margin_is_expressed_in_terms_of_the_accessor():
    """`clears_margin()` / `check_path()` must agree with
    `usable_half_extent()` exactly -- a point one millimetre inside
    clears, one millimetre outside does not, on BOTH axes. If the
    predicate ever grew its own copy of the subtraction, one of these
    four would drift."""
    hx, hy = field.usable_half_extent()
    assert field.clears_margin([_row(0.0, hx - 0.1, 0.0)]) is True
    assert field.clears_margin([_row(0.0, hx + 0.1, 0.0)]) is False
    assert field.clears_margin([_row(0.0, 0.0, hy - 0.1)]) is True
    assert field.clears_margin([_row(0.0, 0.0, hy + 0.1)]) is False


def test_the_tour_sizing_test_no_longer_carries_its_own_field_size():
    """Drift guard for the OTHER half of "one field size".

    `tests/host/test_run_tour_programs.py` used to hold `_FIELD_MM =
    (600.0, 400.0)` and `_MARGIN_MM = 50.0` -- a 55.0 x 35.0 cm usable
    field against this module's 55.15 x 32.65, i.e. 2.35 cm LOOSER in
    y. A figure could pass its sizing gate there and still be refused
    by the geofence every driving tool pre-flights against. Sprint 034
    ticket 007 deleted the pair; this fails if anyone reintroduces one.
    """
    src = (_REPO_ROOT / 'tests' / 'host' /
           'test_run_tour_programs.py').read_text()
    for line in src.splitlines():
        code = line.split('#', 1)[0]
        assert '_FIELD_MM =' not in code and '_MARGIN_MM =' not in code, (
            'the tour sizing test has grown a private field size again; '
            'it must derive from field.usable_half_extent()')
    assert 'usable_half_extent' in src, (
        'the tour sizing test no longer derives its limits from field.py')


# --- require_clear_path(): the planners' loud refusal ---------------------

def test_require_clear_path_returns_quietly_for_a_path_that_clears():
    assert field.require_clear_path(field.RECT, what='the tour') is None


def test_require_clear_path_refuses_and_names_the_offending_points():
    """A refusal must say WHERE the path left the field. A bare
    "refused" sends the operator back to the geometry with nothing to
    go on, and is the shape of message people learn to ignore."""
    with pytest.raises(field.PathRefused) as exc:
        field.require_clear_path([(0.0, 0.0), (60.0, 0.0)],
                                 what='drive to (60.0, 0.0)')
    msg = str(exc.value)
    assert 'drive to (60.0, 0.0)' in msg, 'the refused move is not named'
    assert '60.0' in msg, 'no offending point named'
    assert '55.15' in msg and '32.65' in msg, (
        'the refusal does not state the usable extent it applied')


def test_require_clear_path_refuses_a_legal_TARGET_reached_by_an_illegal_path():
    """The target itself clears the margin; the path to it does not,
    because the robot is currently OUTSIDE the margin and the first
    part of the leg is spent getting back in.

    This is the case that makes the check a PATH check rather than a
    target check, and it is the one a reposition actually hits: the
    dots are all legal points, so a tool that only validated its
    destination would arm every one of these. (A leg between two legal
    points cannot itself leave the margin -- the usable field is a
    rectangle, hence convex -- so an out-of-margin START is exactly
    where a two-waypoint path goes wrong.)"""
    with pytest.raises(field.PathRefused) as exc:
        field.require_clear_path([(60.0, 0.0), (0.0, 0.0)],
                                 what='drive to (0.0, 0.0)')
    msg = str(exc.value)
    assert 'drive to (0.0, 0.0)' in msg
    assert '60.0' in msg, (
        'the offending START of the leg must be named, not just the '
        'destination -- the destination is fine')


def test_require_clear_path_walks_multi_leg_routes_not_just_their_ends():
    """A route whose first and last waypoints both clear but whose
    middle leg does not. `check_path()` already walks the segments;
    this pins that the planners' gate inherits that and does not
    shortcut to first/last."""
    with pytest.raises(field.PathRefused):
        field.require_clear_path([(0.0, 0.0), (60.0, 0.0), (10.0, 0.0)])


def test_require_clear_path_never_clamps_the_waypoints():
    """It raises; it does not hand back a shortened path. Nothing in
    the signature offers a corrected route, deliberately: a silently
    re-planned move is the failure this check exists to prevent."""
    waypoints = [(0.0, 0.0), (60.0, 0.0)]
    with pytest.raises(field.PathRefused):
        field.require_clear_path(waypoints)
    assert waypoints == [(0.0, 0.0), (60.0, 0.0)]


# --- field.py imports nothing that does I/O ------------------------------

def test_field_imports_nothing_that_does_io():
    """The invariant that lets `tests/calibration/*` and `tests/host/*`
    both import this module on a machine with no robot, no camera and
    no relay attached. The geofence is wired in by having the PLANNERS
    call `check_path()` -- never by teaching `field.py` about a link.
    """
    src = (_TOOLS_DIR / 'field.py').read_text()
    imported = set()
    for line in src.splitlines():
        line = line.strip()
        if line.startswith('import '):
            imported.update(n.strip().split(' as ')[0].split('.')[0]
                            for n in line[len('import '):].split(','))
        elif line.startswith('from ') and ' import ' in line:
            imported.add(line[len('from '):].split(' import ')[0].split('.')[0])
    assert imported == {'math'}, (
        f'tools/field.py must import nothing but math; found {sorted(imported)}')
