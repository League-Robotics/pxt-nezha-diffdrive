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
