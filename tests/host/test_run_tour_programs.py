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
import math
import pathlib
import re

# tests/host/test_run_tour_programs.py -> host -> tests -> repo root
_REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
_TEST_TS = _REPO_ROOT / "test" / "test.ts"
_MOTION_H = _REPO_ROOT / "src" / "motion" / "motion_engine.h"
_TOURS_DIR = _REPO_ROOT / "tests" / "system" / "tours"

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


def test_three_tour_handlers_are_registered():
    for verb in ("square", "infinity", "spline"):
        assert re.search(
            r'diffDrive\.onRun\(\s*"%s"' % verb, _TS
        ), f"RUN:{verb} handler missing from test.ts"


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
        "spline each contain some, so this looks like a parsing failure rather "
        "than a genuinely arc-free tour set"
    )
