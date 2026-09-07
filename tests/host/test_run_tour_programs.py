"""tests/host/test_run_tour_programs.py -- source pins for the on-robot
tour programs `RUN:square`, `RUN:infinity`, `RUN:snake` etc. in
`test/test.ts`, plus the field-sizing check on the host-driven `.tour`
figures.

HISTORY. This file used to enforce that every arc, in test.ts and in the
`.tour` files, stayed under 50 deg: `MotionEngine::moveX()` split any
move with a nonzero distance and |rotation| >= `kTurnFirstAngle` into a
pivot THEN a straight, so a circle asked for in 90 deg pieces came out
as a square and one 360 deg arc as a **942 mm straight line** (MEASURED
gopiv 2026-09-01, `reports/tours-20260901/circle.json`). moveX() no
longer splits at any angle (`reports/move-x-arc-space-20260906.md`);
the 45 deg steps the tours settled on are still fine, they are just no
longer load-bearing, and the threshold pins are gone with the
threshold. `kTurnFirstAngle` now belongs to goToR() alone.

**What this is NOT.** Like `test_run_abort_source_pin.py`, this reads
`.ts` source text; `tests/host/` cannot compile or execute PXT code
(see `tests/host/README.md`). It cannot prove the robot drives a
circle.

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
_TOURS_DIR = _REPO_ROOT / "tests" / "system" / "tours"

sys.path.insert(0, str(_REPO_ROOT / "tests" / "system"))
sys.path.insert(0, str(_REPO_ROOT / "tools"))
from tourfile import parse_tour  # noqa: E402  (path set up first)
from field import usable_half_extent  # noqa: E402  (path set up first)

_TS = _TEST_TS.read_text()


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


# The eleven motion verbs whose job used to hand-roll (or, for most of
# them, skip) its own reset/profile/terminal-line handling -- "tour"
# itself is a pure router onto tourRobot/tourWheels/tourWorld and is
# not counted separately here, matching the issue's own "~11" count.
# Verbs that route through a named function (straight/cal/square/
# infinity/snake/diamond/circle) are checked via that function; the
# rest (goto/face/pivot/arc) carry beginJob()/endJob() directly in
# their onRun() handler body.
_ELEVEN_VERB_JOB_FUNCTIONS = {
    "straight": "straightRun",
    "cal": "leverCal",
    "square": "squareTour",
    "infinity": "infinityTour",
    "snake": "snakeTour",
    "diamond": "diamondTour",
    "circle": "circleTour",
}
_ELEVEN_VERB_DIRECT = ("goto", "face", "pivot", "arc")


def _find_balanced_close(text: str, open_brace_idx: int) -> int:
    """Index just past the '}' matching the '{' at open_brace_idx."""
    depth = 0
    i = open_brace_idx
    while i < len(text):
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
            if depth == 0:
                return i + 1
        i += 1
    raise ValueError("unbalanced braces starting at %d" % open_brace_idx)


def _function_body(name: str) -> str:
    m = re.search(r"function\s+%s\s*\([^)]*\)(?:\s*:\s*\w+)?\s*\{" %
                  re.escape(name), _TS)
    assert m, "function %s() not found" % name
    open_idx = m.end() - 1
    close_idx = _find_balanced_close(_TS, open_idx)
    return _TS[m.end():close_idx - 1]


def test_wheels_tour_does_not_require_or_sample_otos():
    body = _function_body("tourWheels")
    for forbidden in ("worldReady()", "seedPose(", "logFix("):
        assert forbidden not in body
    assert "sampleWorld = false" in body
    assert "sampleWorld = true" in body
    assert "sampleWorld &&" in _function_body("tickToCompletion")


def _onrun_body(verb: str) -> str:
    m = re.search(
        r'diffDrive\.onRun\(\s*"%s"\s*,\s*function\s*\([^)]*\)\s*\{' %
        re.escape(verb), _TS)
    assert m, 'diffDrive.onRun("%s", ...) not found' % verb
    open_idx = m.end() - 1
    close_idx = _find_balanced_close(_TS, open_idx)
    return _TS[m.end():close_idx - 1]


def test_every_verb_reaches_a_reasoned_terminal_line():
    """Every one of the eleven motion verbs -- not just the three
    original tours -- must end in a terminal line containing `:end:`
    followed by a reason token, via the shared endJob() mechanism (see
    test_run_abort_source_pin.py for the beginJob()/endJob() pins
    themselves; this test's job is just to confirm all eleven verbs are
    wired to it, and that endJob() actually produces the reasoned
    line)."""
    for verb, fn in _ELEVEN_VERB_JOB_FUNCTIONS.items():
        body = _function_body(fn)
        assert "endJob(" in body, (
            "RUN:%s (%s()) must call endJob()" % (verb, fn)
        )
    for verb in _ELEVEN_VERB_DIRECT:
        body = _onrun_body(verb)
        assert "endJob(" in body, "RUN:%s handler must call endJob()" % verb
    end_job_body = _function_body("endJob")
    assert re.search(r'":end:"\s*\+\s*reason', end_job_body), (
        "endJob() must emit a terminal line containing ':end:' followed "
        "by a reason token"
    )


# The usable playfield comes from `tools/field.py` -- ONE field size for
# the whole repo. This file used to carry its own `_FIELD_MM = (600.0,
# 400.0)` / `_MARGIN_MM = 50.0` (the stakeholder's 2026-09-01 120 x 80 cm
# envelope, less 50 mm), which made two "enforced" fields: 55.0 x 35.0 cm
# usable here against `field.LIMITS - field.MARGIN`'s 55.15 x 32.65 cm,
# the latter cited to `.claude/rules/playfield-testing.md`. x agreed to
# 1.5 mm; y did NOT, and the private pair was the looser of the two by
# 2.35 cm -- so a figure could pass its sizing gate here and still be
# refused by the geofence every driving tool now pre-flights against
# (`field.require_clear_path()`). Sprint 034 ticket 007 deleted the
# private pair; the numbers live in `field.py` and nowhere else.
#
# Sizing outcome of that unification, checked 2026-09-05: EVERY tour and
# spline path still fits under the tighter y limit -- nothing had to be
# re-sized and nothing was added to `_UNSIZED`. The "either orientation"
# allowance is what carries the tall figures (`snake` is 125 x 500 mm
# half-extent, `infinity` 250 x 500; both are staged across the field's
# long axis, where 500 <= 551.5).


def _usable_half_extent_mm():
    """The usable half-extents in mm, derived from `tools/field.py`.

    `field.usable_half_extent()` answers in cm (the tools' unit); the
    `.tour` files are in mm (the wire's unit). This is the ONE place
    the two meet -- and it is a derivation, not a second copy.
    """
    hx, hy = usable_half_extent()
    return hx * 10.0, hy * 10.0

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
    limit_x, limit_y = _usable_half_extent_mm()
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
            f"fit the usable field ({2 * limit_x:.0f} x {2 * limit_y:.0f} mm, "
            f"tools/field.py's LIMITS less its MARGIN) in either orientation"
        )
    assert checked >= 5, f"only {checked} tours sized -- expected at least 5"


def test_spline_paths_exist_and_fit():
    limit_x, limit_y = _usable_half_extent_mm()
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
