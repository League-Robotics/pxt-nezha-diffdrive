"""Playfield geometry: dot/corner constants, angle wrapping, corner
scoring, path deviation.

Pure data/geometry, no process or I/O of its own -- every tour/ground-
truth tool that scores a run against the field's four orange dots now
calls the functions here instead of carrying its own copy. Before this
module: 6 duplicated `DOTS`/`ORDER`/`RECT` constant blocks, 8 separate
(functionally identical, one under a different name --
`rotation_check.py`'s `unwrap()`) `wrap()` implementations, and 4
corner-scoring implementations that had already DISAGREED for the same
recorded run -- `tour_run.py`'s console reported "SW 31.3cm" for a
corner `practice_chart.py`'s chart reported "SW=unobserved", because
only the chart's copy accounted for the camera having been blind at
the moment of closest approach. See
`clasi/sprints/005-retrofit-bench-tooling-onto-the-v6-telemetry-stream/
issues/tools-link-layer-consolidation.md` (code review R-24/R-26).

**`latest`/camera-sample tuple order (this module's documented
convention, followed by `tools/camproc.py`'s `Cam`): a single fix is
`(x_cm, y_cm, yaw_deg)`; a timestamped sample is
`(t, x_cm, y_cm, yaw_deg)`.** This unifies `tour_run.py`'s original
`(x, y, yaw)` with `tour_practice.py`'s `(yaw, x, y)` -- every function
below that takes a `rows` argument expects the timestamped, 4-tuple
form, in this order.
"""
import math

# The four orange dots, main-playfield, A1-centred, cm.
DOTS = {'NW': (-50.0, 30.0), 'NE': (50.0, 30.0),
        'SE': (50.0, -30.0), 'SW': (-50.0, -30.0)}
# Visit order, counter-clockwise from NE -- every tour drives this order.
ORDER = ['NW', 'SW', 'SE', 'NE']
# Closed rectangle (for plotting/deviation), NE -> NW -> SW -> SE -> NE.
RECT = [DOTS['NE'], DOTS['NW'], DOTS['SW'], DOTS['SE'], DOTS['NE']]

# Field boundary -- (x_cm, y_cm) half-extents of the 134.3 x 89.3 cm
# field, A1-centred. Source of truth: `.claude/rules/playfield-testing.md`
# ("Field is 134.3 x 89.3 cm, AprilTag-1-centred, so limits are
# ±67.15 / ±44.65 cm. Keep a 12 cm margin.") -- keep these two numbers
# in sync with that file; `tests/tools/test_field.py` pins both against
# the rule file's own text as a drift guard.
LIMITS = (67.15, 44.65)
MARGIN = 12.0


def _within_margin(x, y):
    lx, ly = LIMITS
    return abs(x) <= lx - MARGIN and abs(y) <= ly - MARGIN


def clears_margin(rows):
    """True if every row's `(x, y)` stays within `LIMITS` reduced by
    `MARGIN` -- for RECORDERS, checking a captured path after the
    fact. `rows` follows the module's usual `(t, x_cm, y_cm, yaw_deg)`
    convention; an empty `rows` trivially clears (nothing to violate).
    """
    return all(_within_margin(row[1], row[2]) for row in rows)


def check_path(waypoints, samples_per_segment=20):
    """Check a planner's FULL projected path against `LIMITS` reduced
    by `MARGIN`, before a run is armed -- each `(x_cm, y_cm)` waypoint
    AND the straight-line segment between each consecutive pair, not
    just the waypoints themselves, per
    `.claude/rules/playfield-testing.md`'s "compute the full projected
    path ... through every planned leg."

    Returns the list of offending `(x, y)` points (waypoints and/or
    interpolated segment points) -- empty if the whole path clears the
    margin. A caller refuses to arm the run on any non-empty result.
    """
    offenders = []
    if not waypoints:
        return offenders
    x0, y0 = waypoints[0]
    if not _within_margin(x0, y0):
        offenders.append((x0, y0))
    for (x1, y1), (x2, y2) in zip(waypoints, waypoints[1:]):
        for i in range(1, samples_per_segment + 1):
            t = i / samples_per_segment
            x = x1 + t * (x2 - x1)
            y = y1 + t * (y2 - y1)
            if not _within_margin(x, y):
                offenders.append((x, y))
    return offenders


def wrap(d):
    """Wrap an angle in degrees into (-180, 180]."""
    while d <= -180.0:
        d += 360.0
    while d > 180.0:
        d -= 360.0
    return d


def score_corners(rows, order=ORDER, dots=DOTS, gap_s=0.4):
    """Closest approach to each dot in `order`, scanning `rows` (each a
    `(t, x_cm, y_cm, yaw_deg)` tuple, timestamps non-decreasing)
    forward so a later corner cannot reclaim an earlier corner's
    sample.

    Returns `{tag: distance_cm}`, with `distance_cm` `None` where the
    closest sample sits beside a tracking gap wider than `gap_s`
    seconds AND that closest distance is > 3 cm -- a "closest
    approach" computed across a blind stretch is measuring where
    tracking happened to die, not the robot's error (a real run once
    scored "SW 31.3 cm" this way while the camera had been blind for
    24 s and the robot had already been and gone). A close approach
    (<= 3 cm) right next to a gap is still trusted -- the robot was
    plainly there.

    This is the ONE corner-scoring algorithm every tour/ground-truth
    tool now calls -- previously 4 separate copies of it existed and
    disagreed for the same run (see module docstring).
    """
    res = {tag: None for tag in order}
    if not rows:
        return res
    gaps = [(a[0], b[0]) for a, b in zip(rows, rows[1:])
            if b[0] - a[0] > gap_s]
    used = 0
    for tag in order:
        dx, dy = dots[tag]
        best, besti = None, used
        for i in range(used, len(rows)):
            d = math.hypot(rows[i][1] - dx, rows[i][2] - dy)
            if best is None or d < best:
                best, besti = d, i
        if best is None:
            continue
        t = rows[besti][0]
        blind = any(g0 - 0.5 <= t <= g1 + 0.5 for g0, g1 in gaps)
        res[tag] = None if (blind and best > 3.0) else best
        used = besti
    return res


def path_deviation(rows, segments=None):
    """Distance from each row's (x, y) to the nearest edge of the
    playfield rectangle, ascending -- how far the path strayed from
    the ideal lap. `segments` defaults to `RECT`'s own edges.

    Guards the projection divide against a degenerate (zero-length)
    segment (PY-08) -- unguarded in every one of this function's
    former per-tool copies, though `RECT`'s own fixed 100x60 cm
    corners never produce one in practice.
    """
    segs = segments if segments is not None else list(zip(RECT, RECT[1:]))
    devs = []
    for row in rows:
        x, y = row[1], row[2]
        best = math.inf
        for (x1, y1), (x2, y2) in segs:
            ddx, ddy = x2 - x1, y2 - y1
            L = ddx * ddx + ddy * ddy
            if L <= 0.0:
                continue
            t = max(0.0, min(1.0, ((x - x1) * ddx + (y - y1) * ddy) / L))
            best = min(best, math.hypot(x - (x1 + t * ddx),
                                         y - (y1 + t * ddy)))
        devs.append(best)
    devs.sort()
    return devs


def closure(rows, start_heading=None):
    """`(distance_cm, heading_err_deg)` from the first row to the last.

    `heading_err_deg` is `None` unless `start_heading` [deg] is given,
    in which case it is `wrap(rows[-1].yaw - start_heading)`.
    `(None, None)` if `rows` is empty.
    """
    if not rows:
        return None, None
    sx, sy = rows[0][1], rows[0][2]
    ex, ey = rows[-1][1], rows[-1][2]
    dist = math.hypot(ex - sx, ey - sy)
    herr = (wrap(rows[-1][3] - start_heading)
            if start_heading is not None else None)
    return dist, herr
