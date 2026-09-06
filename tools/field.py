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

# How near the NEXT dot a sample must come before `score_corners()`
# closes the CURRENT corner's search window -- "the robot has plainly
# arrived somewhere else, stop scoring the corner it left". Comfortably
# under half the 60 cm short side of the dot rectangle (and well under
# half the 100 cm long side), so the window can only close on a genuine
# arrival at the next dot, never on a pass down the middle of the field.
CORNER_WINDOW_RADIUS = 15.0  # [cm]


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


def turn_total(commanded: float, measured: float) -> float:
    """Total physical turn of a pivot, in degrees -- the one owner of
    this arithmetic for every bench tool that scores a commanded pivot
    against a measured heading change.

    `commanded` is the angle asked for [deg]; `measured` is the
    after-minus-before heading difference [deg], wrapped or not. The
    result is `measured` unwrapped onto the revolution `commanded`
    names, so a 183 deg physical turn against a 180 deg command reports
    +183 and `turn_total(...) / commanded` keeps the sign of the turn.

    **The failure this replaces.** `rotation_check.py` and
    `truth_check.py` each carried::

        revs = round(commanded / 360.0)
        revs * 360.0 + wrap(after - before - revs * 360.0)

    which asks `round()` to guess the revolution count. For
    `commanded = +/-180`, `round(+/-0.5)` is **0** under banker's
    rounding, so the whole expression collapses to `wrap(after -
    before)` -- and a 183 deg turn (over-rotation is the norm on this
    fleet) came back as **-177 deg**, flipping the sign of
    `gyro / commanded` to -0.98 and poisoning any mean taken over a
    mixed `[360, 180, -180]` pivot set. Anchoring the unwrap on the
    commanded angle needs no `revs` term and no `round()`, and is
    correct for every commanded angle uniformly -- including the
    +/-180 boundary, which is why callers no longer need a special
    case for it.

    The one assumption: the robot turned closer to `commanded` than to
    `commanded +/- 360`, i.e. the error is under half a revolution.
    That is the same assumption the `revs` form was reaching for, made
    explicit instead of delegated to rounding.
    """
    return commanded + wrap(measured - commanded)


def robot_heading_from_tag_yaw(tag_yaw_deg, residual_deg=0.0):
    """Robot heading [deg] from a RAW (unregistered/uncorrected) tag
    yaw reading, per
    `.claude/rules/tag-yaw-is-the-front-edge-not-the-hat.md`:
    `robot_heading = tag_yaw + 90 (fixed AprilCam convention) +
    residual_deg (the sub-degree physical mount skew)`.

    This is the ONE place the +90 deg convention is added back for a
    raw reading -- `field_calibration.json` stores only the residual
    (`mount_yaw_residual_deg`), never a probe-fitted absolute like the
    pre-sprint-029 `heading_offset_deg: 91.116`. (For a tag already
    REGISTERED with the aprilcam daemon -- see `camlink.mount_yaw_rad()`
    -- the daemon does this correction itself, and its reported
    `yaw_rad` is already the robot's heading; do not add 90 again on
    top of a registered/corrected reading.)

    Result is wrapped into (-180, 180].
    """
    return wrap(tag_yaw_deg + 90.0 + residual_deg)


def pose_from_registered_samples(samples, lever_cm):
    """(x_cm, y_cm, heading_deg) of a robot's centre of rotation,
    averaged over `samples` -- each a `(yaw_rad, world_x_cm,
    world_y_cm)` tuple read from a tag already REGISTERED with the
    aprilcam daemon (`camlink.mount_yaw_rad()`). A registered tag's
    `yaw_rad` already IS the robot's heading -- the daemon applied the
    fixed +90 deg convention plus the mount's residual at registration
    time. **This function must NOT run `yaw_rad` through
    `robot_heading_from_tag_yaw()` or otherwise add 90 again** -- that
    function is for a RAW/unregistered reading only. See
    `.claude/rules/tag-yaw-is-the-front-edge-not-the-hat.md`
    ("registered vs raw: who adds the 90") and this function's own
    origin: sprint 029 ticket 007 found `tools/field_dance.py`'s
    `pose()` doing exactly this double-add -- every pivot passed
    (heading DELTAS cancel a constant offset) while every drive's
    bearing was off by +90 deg (MEASURED tovez 2026-09-04,
    `captures/bench-acceptance-029-20260904d/heading-probe.log`).

    Position is the mean of each sample's lever-corrected centre of
    rotation (`lever_cm`, the tag's own `(x_cm, y_cm)` offset from that
    centre in the robot's body frame); heading is the circular mean
    (mean of sin/cos, not a naive average of angles) of the `yaw_rad`
    values, wrapped into (-180, 180]. `None` if `samples` is empty --
    the caller (a live camera read that saw nothing) must not
    substitute a stale or fabricated pose.
    """
    if not samples:
        return None
    lx, ly = lever_cm
    xs = ys = 0.0
    sy = cy = 0.0
    for t, wx, wy in samples:
        xs += wx - (math.cos(t) * lx - math.sin(t) * ly)
        ys += wy - (math.sin(t) * lx + math.cos(t) * ly)
        sy += math.sin(t)
        cy += math.cos(t)
    n = len(samples)
    h = math.degrees(math.atan2(sy, cy))
    return xs / n, ys / n, wrap(h)


def registered_pose_distance(a, b):
    """Straight-line distance [cm] between two registered-tag poses,
    each an `(x_cm, y_cm, heading_deg)` tuple from
    `pose_from_registered_samples()`.

    Deliberately takes no scaling factor -- a registered tag's world
    position already carries the aprilcam daemon's own `mount_z_cm`
    parallax correction, applied once, at registration
    (`tools/camlink.py::Cam.register()`). This function's signature is
    the guard: there is nowhere to pass a tool-side `parallax_k` into
    it, so a caller cannot re-apply that correction on top even by
    accident. Dividing a distance computed from two registered poses
    by `parallax_k` corrects the SAME parallax twice -- exactly the bug
    pinned by `clasi/issues/
    parallax-k-and-registered-mount-z-correct-twice.md`: tovez's
    `field_dance.py` drives read ~12% short (MEASURED tovez 2026-09-04,
    `captures/bench-acceptance-029-20260904d/field-dance-refit-run1.log`:
    17.6 cm for a commanded 20, 35.3 cm for a commanded 40 -- i.e.
    20/1.1167, 40/1.1167) until that division was found and removed
    (sprint 031 ticket 002).

    This is the positional analogue of
    `pose_from_registered_samples()`'s heading fix -- one owner (the
    daemon's registered `mount_z_cm`) for camera-parallax correction,
    the same shape as `robot_heading_from_tag_yaw()` vs a registered
    tag's `yaw_rad` for heading
    (`.claude/rules/tag-yaw-is-the-front-edge-not-the-hat.md`,
    "registered vs raw: who adds the 90").
    """
    return math.hypot(b[0] - a[0], b[1] - a[1])


def _first_approach(rows, start, dot, radius):
    """First index >= `start` at which `rows` comes within `radius` of
    `dot`, or `len(rows)` if it never does. Helper for
    `score_corners()`'s per-corner window."""
    dx, dy = dot
    for i in range(start, len(rows)):
        if math.hypot(rows[i][1] - dx, rows[i][2] - dy) <= radius:
            return i
    return len(rows)


def score_corners(rows, order=ORDER, dots=DOTS, gap_s=0.4,
                  window_radius=CORNER_WINDOW_RADIUS):
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

    **Each corner searches a BOUNDED window, not the rest of the run.**
    Of the two remedies the 2026-09-02 review offered for TL-08 (a
    bounded window, or one monotone assignment over all four corners)
    this takes the first: corner *k* is scored over
    `rows[used : first_approach(k + 1)]`, where `first_approach` is the
    first sample AFTER `used` within `window_radius` of the NEXT dot in
    `order` -- i.e. the window closes the moment the robot has plainly
    arrived somewhere else. The last corner in `order` has no next dot
    and keeps the rest of the run. `window_radius` defaults to
    `CORNER_WINDOW_RADIUS`.

    The unbounded scan this replaces (08-26 C-16, still open as TL-08)
    let one corner eat the whole run: a lap that starts on NE, passes
    NW 4 cm off early and re-approaches NW 1.5 cm off on its closing
    leg scored NW from the LATE sample, pushed `used` to the tail, and
    left SW/SE/NE a handful of final samples to report tens of cm or
    `None` from. One good run read as three bad corners. The
    first-approach bound is searched from `used + 1`, never `used`, so
    the current corner always keeps at least its own first sample and
    the window can never come back empty.

    `used` advances to `besti + 1`, so two consecutive corners cannot
    claim the same sample -- the reverse of the monotonicity the
    docstring has always promised, and the other half of TL-08.

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
    for k, tag in enumerate(order):
        if used >= len(rows):
            break
        dx, dy = dots[tag]
        nxt = dots[order[k + 1]] if k + 1 < len(order) else None
        end = (len(rows) if nxt is None
               else _first_approach(rows, used + 1, nxt, window_radius))
        best, besti = None, used
        for i in range(used, end):
            d = math.hypot(rows[i][1] - dx, rows[i][2] - dy)
            if best is None or d < best:
                best, besti = d, i
        if best is None:
            continue
        t = rows[besti][0]
        blind = any(g0 - 0.5 <= t <= g1 + 0.5 for g0, g1 in gaps)
        res[tag] = None if (blind and best > 3.0) else best
        used = besti + 1
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
