"""tests/host/test_run_tour_programs.py -- source pins for the on-robot
tour programs `RUN:square`, `RUN:infinity` and `RUN:spline` in
`test/test.ts`, plus the one geometric constraint they can silently
violate.

**The bug this exists to catch.** `MotionEngine::moveX()` SPLITS any
move with a nonzero distance and |rotation| >= `kTurnFirstAngleRad`
into a pivot THEN a straight (`motion_engine.cpp:371`). An arc asked
for in pieces at or above that threshold therefore comes out as a
corner, and a circle built from such pieces comes out as a POLYGON --
with no error, no warning, and a completion receipt that looks normal.

MEASURED gopiv 2026-09-01, `reports/tours-20260901/circle.json`: the
first version of `circle.tour` asked for one 360 deg arc and the robot
drove a **942 mm straight line** (closure 942.2 mm); a 90 deg-per-arc
version drew a square. The fix in both the `.tour` files and the
TypeScript was to step every arc at 45 deg. Nothing but this test
connects that choice back to the C++ constant it depends on, so a later
edit raising the step to a rounder 90 would reintroduce the bug
silently.

**What this is NOT.** Like `test_run_abort_source_pin.py`, this reads
`.ts` source text; `tests/host/` cannot compile or execute PXT code
(see `tests/host/README.md`). It cannot prove the robot drives a
circle. It proves the handlers are registered and that the arc step
they use is on the safe side of the split threshold as that threshold
is actually defined in the firmware -- both cheap, both otherwise
unguarded.

Run with::

    uv run pytest tests/host/test_run_tour_programs.py
"""
import json
import math
import pathlib
import re
import sys

# tests/host/test_run_tour_programs.py -> host -> tests -> repo root
_REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
_TEST_TS = _REPO_ROOT / "test" / "test.ts"
_MOTION_H = _REPO_ROOT / "src" / "motion" / "motion_engine.h"
_TOURS_DIR = _REPO_ROOT / "tests" / "system" / "tours"

sys.path.insert(0, str(_REPO_ROOT / "tests" / "system"))
from tourfile import parse_tour  # noqa: E402  (path set up first)

_TS = _TEST_TS.read_text()


def _split_threshold_deg():
    """The real `kTurnFirstAngleRad`, read from the firmware header.

    Read rather than hardcoded on purpose: the point of the test is
    that the TypeScript arc step tracks the C++ constant. A copy of
    0.8726646 here would keep passing if the constant moved.
    """
    m = re.search(
        r"constexpr\s+float\s+kTurnFirstAngleRad\s*=\s*([0-9.]+)f?\s*;", _MOTION_H.read_text()
    )
    assert m, "kTurnFirstAngleRad not found in motion_engine.h"
    return math.degrees(float(m.group(1)))


def test_split_threshold_is_where_we_think_it_is():
    # Sanity: if this stops being ~50 deg the tours need re-sizing, and
    # the failure should say so rather than surfacing as a bent figure.
    assert 40.0 < _split_threshold_deg() < 60.0


def test_every_arc_figure_has_an_on_robot_handler():
    """One `onRun` verb per figure the .tour suite drives with arcs.

    `spline` is deliberately absent: the fitted-curve tour is followed
    with pure pursuit from the host, which needs the sampled path and a
    steering loop. The on-robot serpentine that used to answer to that
    name is `snake` -- it is a chain of circular arcs, and the wire
    command now says so.
    """
    for verb in ("square", "diamond", "circle", "infinity", "snake"):
        assert re.search(
            r'diffDrive\.onRun\(\s*"%s"' % verb, _TS
        ), f"RUN:{verb} handler missing from test.ts"
    assert not re.search(r'diffDrive\.onRun\(\s*"spline"', _TS), (
        "RUN:spline is registered again. That name drove a serpentine, "
        "not a spline, which is exactly the confusion the rename fixed -- "
        "the host-driven .tour file of the same name follows a fitted "
        "curve with pure pursuit and is a different figure entirely."
    )


def test_arc_steps_stay_below_the_split_threshold():
    """Every angle handed to arcSegment() must be under the threshold.

    arcSegment() is the ONLY place these programs issue a curved move,
    so collecting its call sites collects the whole exposure.
    """
    limit = _split_threshold_deg()
    # `(?<!function )` keeps arcSegment's own DECLARATION out of the
    # call list -- its parameters carry no literal angle, and letting it
    # in makes the whole check pass vacuously.
    calls = re.findall(r"(?<!function )arcSegment\(([^)]*)\)", _TS)
    assert calls, "no arcSegment() call sites found -- did the tours get rewritten?"

    checked = 0
    for args in calls:
        # Second argument onward is the angle; the first is the radius,
        # which is a variable at every current call site. Splitting on
        # the first comma rather than counting numbers keeps this
        # correct if a call ever passes a literal radius.
        _, _, angle_expr = args.partition(",")
        assert angle_expr.strip(), f"arcSegment({args}) has no angle argument"
        literals = [abs(float(a)) for a in re.findall(r"-?\d+(?:\.\d+)?", angle_expr)]
        assert literals, (
            f"arcSegment({args}) passes a computed angle this test cannot check -- "
            "either use a literal step or extend this pin"
        )
        for deg in literals:
            checked += 1
            assert deg < limit, (
                f"arcSegment() steps {deg} deg, at or above the {limit:.1f} deg split "
                "threshold -- moveX() will turn each arc into a pivot-then-straight "
                "and the figure will come out as a polygon"
            )
    assert checked >= 2, f"only {checked} arc angles checked -- extraction looks broken"


def test_tour_files_also_stay_below_the_split_threshold():
    """The same constraint on the host-driven `.tour` figures.

    They and the TypeScript drive the same geometries by different
    routes, so both need the check; only one of them having it is how
    the two drift apart.
    """
    limit = _split_threshold_deg()
    checked = 0
    for path in sorted(_TOURS_DIR.glob("*.tour")):
        for line_no, raw in enumerate(path.read_text().splitlines(), 1):
            line = raw.split("#", 1)[0].strip()
            if not line.upper().startswith("TWIST"):
                continue
            kv = dict(
                tok.split("=", 1) for tok in line.split()[1:] if "=" in tok
            )
            # Only an ARC is at risk: a pure pivot has no distance to
            # split off, and moveX() leaves it alone at any angle.
            if "vx" not in kv or "angle" not in kv:
                continue
            if float(kv["vx"]) == 0.0:
                continue
            deg = abs(float(kv["angle"]))
            checked += 1
            assert deg < limit, (
                f"{path.name}:{line_no} asks for a {deg} deg arc, at or above the "
                f"{limit:.1f} deg split threshold -- it will drive as a pivot then "
                "a straight, not a curve"
            )
    assert checked >= 3, (
        f"only {checked} arcs found across {_TOURS_DIR} -- circle, infinity and "
        "snake each contain some, so this looks like a parsing failure rather "
        "than a genuinely arc-free tour set"
    )


# The usable playfield, per the stakeholder 2026-09-01: 120 x 80 cm, so
# the robot centre lives in +-600 x +-400 mm. tours/FIELD.md keeps 50 mm
# of margin on top. Both numbers live here too because this test is what
# enforces them.
_FIELD_MM = (600.0, 400.0)
_MARGIN_MM = 50.0

# Tours that are deliberately not sized to this field: ported artifacts
# kept for comparison with radio-robot-elite, and the fault-injection
# tour, which is a protocol test rather than a figure.
_UNSIZED = {"square_cw", "square_smooth", "complex_spline", "tag_spline",
            "fault_wedge"}


def _simulate(tour):
    """Drive a parsed tour from (0, 0) heading +x and return its extent.

    Pure dead reckoning of the commanded geometry -- no robot, no error
    model. That is the right thing for a sizing check: it answers "does
    the figure fit", and a real run only ever adds error on top.
    """
    x = y = th = 0.0
    xs, ys = [0.0], [0.0]
    for st in tour.steps:
        if getattr(st, "kind", "") not in ("straight", "pivot", "arc"):
            continue
        d, rot = st.dist_mm, st.rot_mrad / 1000.0
        if abs(rot) < 1e-9:
            x, y = x + d * math.cos(th), y + d * math.sin(th)
        else:
            # Constant-curvature arc of radius d/rot (a pivot has d = 0,
            # so it only turns).
            r = d / rot
            cx, cy = x - r * math.sin(th), y + r * math.cos(th)
            th2 = th + rot
            # Sample the arc, not just its endpoint: the bulge of a
            # circle leaves the field long before its endpoint does.
            for i in range(1, 13):
                a = th + rot * i / 12.0
                xs.append(cx + r * math.sin(a))
                ys.append(cy - r * math.cos(a))
            x, y = cx + r * math.sin(th2), cy - r * math.cos(th2)
            th = th2
        xs.append(x)
        ys.append(y)
    return xs, ys


def test_every_tour_fits_the_usable_playfield():
    """Each figure, centred on its own extent, must fit the field.

    This is the check that was missing. MEASURED-by-construction
    2026-09-01: `infinity.tour` at r = 300 mm spanned 1200 mm, the
    entire usable width, with zero margin -- and the geometry that made
    it so (the figure-8's long axis runs PERPENDICULAR to the start
    heading) is exactly the kind of thing a comment gets wrong and
    arithmetic does not.

    Centring is the fair test: a tour is staged wherever it needs to be,
    so what matters is its extent, not where it happens to start.
    """
    limit_x = _FIELD_MM[0] - _MARGIN_MM
    limit_y = _FIELD_MM[1] - _MARGIN_MM
    checked = 0
    for path in sorted(_TOURS_DIR.glob("*.tour")):
        if path.stem in _UNSIZED:
            continue
        tour = parse_tour(path)
        if not any(getattr(s, "kind", "") in ("straight", "pivot", "arc")
                   for s in tour.steps):
            continue          # SPLINE-only tours are checked separately
        xs, ys = _simulate(tour)
        # Half-extents once the figure is centred, and allowed either
        # orientation: a tall figure is staged across the field's long
        # axis, which is what FIELD.md tells the operator to do.
        hx, hy = (max(xs) - min(xs)) / 2.0, (max(ys) - min(ys)) / 2.0
        fits = ((hx <= limit_x and hy <= limit_y) or
                (hy <= limit_x and hx <= limit_y))
        checked += 1
        assert fits, (
            f"{path.name} spans {2 * hx:.0f} x {2 * hy:.0f} mm, which does not "
            f"fit the usable field ({2 * limit_x:.0f} x {2 * limit_y:.0f} mm "
            f"after {_MARGIN_MM:.0f} mm margin) in either orientation"
        )
    assert checked >= 5, f"only {checked} tours sized -- expected at least 5"


def test_spline_paths_exist_and_fit():
    limit_x = _FIELD_MM[0] - _MARGIN_MM
    limit_y = _FIELD_MM[1] - _MARGIN_MM
    checked = 0
    for path in sorted(_TOURS_DIR.glob("*.tour")):
        if path.stem in _UNSIZED:
            continue
        for st in parse_tour(path).steps:
            if getattr(st, "kind", "") != "spline":
                continue
            ref = _TOURS_DIR / st.path
            assert ref.exists(), f"{path.name} references missing path {st.path}"
            pts = json.loads(ref.read_text())["points"]
            hx = (max(p[0] for p in pts) - min(p[0] for p in pts)) / 2.0
            hy = (max(p[1] for p in pts) - min(p[1] for p in pts)) / 2.0
            fits = ((hx <= limit_x and hy <= limit_y) or
                    (hy <= limit_x and hx <= limit_y))
            checked += 1
            assert fits, (
                f"{path.name}'s path {st.path} spans "
                f"{2 * hx:.0f} x {2 * hy:.0f} mm and does not fit the field"
            )
    assert checked >= 1, "no SPLINE steps found -- spline.tour should have one"
