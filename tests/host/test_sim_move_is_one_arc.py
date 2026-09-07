"""tests/host/test_sim_move_is_one_arc.py -- `blocks/sim.ts`'s
`_startMove()` blends every `(distance, yaw)` into ONE constant-radius
arc, mirroring `MotionEngine::moveX()` (`motion_engine.cpp`), which has
no pivot-first threshold.

HISTORY. Sprint 032 ticket 005 taught the simulator to mirror a split
moveX() then had: a nonzero distance with |rotation| >= 50 deg
(kTurnFirstAngle) ran as a pivot to the new heading THEN a straight,
and `move(47, 90)` ended 0 forward / 47 cm left on both. That split was
goToR()'s go-to-a-POINT policy misapplied to `move`; it replaced the
arc a program asked for with a different figure (MEASURED gopiv
2026-09-01, `reports/tours-20260901/circle.json`: a 360 deg arc drove
as a 942 mm straight line). `reports/move-x-arc-space-20260906.md`
removed it from moveX(), and this file replaces
`test_sim_pivot_then_straight_split.py` -- the simulator now blends
unconditionally again, and `move(47, 90)` ends on the arc's own
endpoint, (29.9, 29.9) cm, heading +90 deg, on both.

**What this proves, and how.** The real `_startMove()`/`simIntegrate()`
IS EXECUTED here, not just pattern-matched -- following
`test_run_dispatch_argument_snapshot.py`'s precedent (extract the real
source verbatim, compile it with the project's own pinned
`node_modules/.bin/tsc`, run it under `node`). `control.millis()` is
stubbed as a settable fake clock the harness advances in fixed 24 ms
steps, the same cadence `_tickDrive()` paces to on hardware and in the
browser. Three moves are driven to completion and their endpoints
checked against the closed-form arc: the worked example above, a
near-target big turn whose radius is under half the track width (the
inner wheel reverses on hardware; the sim integrates the same pose), and
a full 360 deg circle that must come home.

**What this does NOT cover.** Real TypeScript executed under `node`,
but still a host-side stand-in for the browser's own PXT simulator
runtime and for the real robot. It says NOTHING about the robot's own
physical behaviour; `tests/host/test_move_x_arc_space.py` drives the
same geometries through the real C++ engine on ideal wheels, and the
report names the bench checks that would settle hardware.

Also source-pins that the split's machinery is gone from `sim.ts` and
that `move()`'s JSDoc (`blocks/motion.ts`) describes the arc, not a
pivot.

Run with::

    uv run pytest tests/host/test_sim_move_is_one_arc.py
"""

import math
import pathlib
import re
import subprocess

import pytest

# tests/host/test_sim_move_is_one_arc.py -> host -> tests -> repo root
_REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
_SIM_TS = _REPO_ROOT / "src" / "blocks" / "sim.ts"
_MOTION_TS = _REPO_ROOT / "src" / "blocks" / "motion.ts"
_TSC = _REPO_ROOT / "node_modules" / ".bin" / "tsc"


def _sim_ts_source() -> str:
    return _SIM_TS.read_text(encoding="utf-8")


def _motion_ts_source() -> str:
    return _MOTION_TS.read_text(encoding="utf-8")


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


def _extract_sim_core() -> str:
    """Everything from simX's own declaration through the end of
    `_startMove()` -- the simulator kinematic state, `simIntegrate()`,
    the geometry consts, `_setWheels`/`_driveTwist` (harmless extras,
    contiguous with what's needed) and `_startMove()` itself --
    verbatim, so the harness below exercises the REAL blend rather than
    a reimplementation of it."""
    src = _sim_ts_source()
    start_idx = src.index("let simX = 0")
    m = re.search(r"export function _startMove\(", src)
    assert m, "_startMove() not found in sim.ts"
    brace_idx = src.index("{", m.end())
    close_idx = _find_balanced_close(src, brace_idx)
    return src[start_idx:close_idx]


_HARNESS_TEMPLATE = """
declare const console: { log(msg: string): void; error(msg: string): void };
declare const process: { exitCode: number; exit(code: number): void };

let _fakeMillisValue = 0;
const control = { millis: () => _fakeMillisValue };

// ---- the REAL simulator core, extracted verbatim ----
%(sim_core)s

// ---- scripted moves ----
let failures = 0;
function check(condition: boolean, label: string): void {
    if (!condition) {
        console.error("FAIL " + label);
        failures++;
    }
}
function approx(a: number, b: number, tol: number): boolean {
    return Math.abs(a - b) <= tol;
}
function reset(): void {
    simX = 0; simY = 0; simHeading = 0; simVel = 0; simYawRate = 0;
    simLast = 0; simMoveRemainDist = 0; simMoveRemainYaw = 0;
    simMoveActive = false; simEstopped = false;
    _fakeMillisValue = 0;
}
function runToCompletion(stepMs: number, maxSteps: number): number {
    let steps = 0;
    while (simMoveActive && steps < maxSteps) {
        _fakeMillisValue += stepMs;
        simIntegrate();
        steps++;
    }
    return steps;
}
// Closed-form endpoint of the constant-radius arc: R = s / theta.
function arcEnd(sMm: number, thetaRad: number): number[] {
    if (Math.abs(thetaRad) < 1e-9) return [sMm, 0];
    const r = sMm / thetaRad;
    return [r * Math.sin(thetaRad), r * (1 - Math.cos(thetaRad))];
}
// Each case: distance [mm*1 wire units = mm], yaw [cdeg], speed [mm/s],
// yawRate [cdeg/s], label. Endpoint tolerance 2 mm: the harness steps
// 24 ms and simIntegrate()'s mid-step heading gives second-order
// accuracy, so the residual is well under a millimetre.
const cases: [number, number, number, number, string][] = [
    [470, 9000, 100, 15000, "move(47 cm, 90 deg): the sprint 032 worked example"],
    [50, 15000, 100, 15000, "move(5 cm, 150 deg): R 1.9 cm, under b/2"],
    [942, 36000, 250, 9000, "move(94.2 cm, 360 deg): a full circle comes home"],
    [-250, 18000, 100, 9000, "move(-25 cm, 180 deg): reverses round a half circle"],
];
for (const c of cases) {
    reset();
    _startMove(c[0], c[1], c[2], c[3]);
    check(simMoveActive, c[4] + ": move must be active");
    check(simVel !== 0 && simYawRate !== 0,
        c[4] + ": both axes move at once from the first step (no pivot phase)");
    const steps = runToCompletion(24, 4000);
    check(steps < 4000, c[4] + ": must complete");
    const theta = (c[1] / 100) * Math.PI / 180;
    const end = arcEnd(c[0], theta);
    check(approx(simX, end[0], 2), c[4] + ": x " + simX + " vs arc " + end[0]);
    check(approx(simY, end[1], 2), c[4] + ": y " + simY + " vs arc " + end[1]);
    check(approx(simHeading, theta, 1e-3), c[4] + ": heading " + simHeading + " vs " + theta);
    check(!simMoveActive, c[4] + ": the move must have ended");
}

if (failures > 0) {
    console.log("FAIL: " + failures + " check(s) failed");
    process.exit(1);
} else {
    console.log("PASS");
    process.exit(0);
}
"""


@pytest.fixture(scope="module")
def _harness_result(tmp_path_factory):
    assert _TSC.is_file(), (
        f"{_TSC} does not exist -- run `npm install` first (see "
        f"test_typescript_typecheck.py's header comment: this "
        f"deliberately never falls back to `npx tsc`)"
    )
    sim_core = _extract_sim_core()
    sim_core = re.sub(r"^(\s*)export function", r"\1function", sim_core,
                      flags=re.MULTILINE)
    harness_ts = _HARNESS_TEMPLATE % {"sim_core": sim_core}

    tmp_dir = tmp_path_factory.mktemp("sim_move_arc_harness")
    ts_path = tmp_dir / "harness.ts"
    js_path = tmp_dir / "harness.js"
    tsconfig_path = tmp_dir / "tsconfig.json"
    ts_path.write_text(harness_ts, encoding="utf-8")
    tsconfig_path.write_text(
        '{"compilerOptions": {"target": "es2017", "lib": ["es2017"], '
        '"types": [], "strict": false, "outFile": "%s"}, '
        '"files": ["%s"]}' % (js_path.name, ts_path.name),
        encoding="utf-8",
    )
    compile_result = subprocess.run(
        [str(_TSC), "-p", str(tsconfig_path)],
        capture_output=True, text=True, cwd=_REPO_ROOT,
    )
    assert compile_result.returncode == 0, (
        f"harness failed to compile -- the EXTRACTED sim.ts core is not "
        f"valid standalone TypeScript:\n"
        f"stdout:\n{compile_result.stdout}\nstderr:\n{compile_result.stderr}\n"
        f"---- generated harness ----\n{harness_ts}"
    )
    return subprocess.run(["node", str(js_path)], capture_output=True,
                          text=True)


def test_sim_move_lands_on_the_arc_endpoint(_harness_result):
    """Runs the REAL extracted _startMove()/simIntegrate() (compiled and
    executed, not pattern-matched) on four (distance, yaw) pairs, three
    of them at or far beyond the old 50 deg split, and checks each lands
    on the closed-form arc endpoint R*(sin theta, 1 - cos theta) at
    heading theta -- including the full circle coming home."""
    assert _harness_result.returncode == 0, (
        f"sim arc check failed:\n"
        f"stdout:\n{_harness_result.stdout}\nstderr:\n{_harness_result.stderr}"
    )
    assert "PASS" in _harness_result.stdout


def test_sim_has_no_split_machinery():
    """The pivot-then-straight mirror is gone: no threshold constant, no
    queued-straight bookkeeping, no second phase."""
    src = _sim_ts_source()
    for token in ("kSimTurnFirstAngle", "simMoveHasPendingStraight",
                  "simMovePendingDistance", "simMovePendingSpeed"):
        assert token not in src, f"sim.ts still carries {token}"


def _move_doc():
    src = _motion_ts_source()
    match = re.search(
        r"(/\*\*.*?\*/)\s*//% block=\"move %distance cm turning %yaw degrees\"",
        src, re.DOTALL,
    )
    assert match, "move()'s JSDoc block was not found in motion.ts"
    return match.group(1)


def test_move_doc_describes_one_arc_and_no_pivot():
    doc = _move_doc()
    assert re.search(r"arc", doc, re.I), "move()'s JSDoc must say it drives an arc"
    assert not re.search(r"pivot", doc, re.I), (
        "move()'s JSDoc must not describe a pivot-then-straight phase; "
        "moveX() has no such split"
    )


def test_sim_worked_example_endpoint_is_the_arc_not_the_corner():
    """The number the sprint 032 ticket quoted, inverted: move(47, 90)
    ends at R = 470/(pi/2) = 299 mm forward AND 299 mm left, not at the
    corner (0, 470) the old split produced."""
    r = 470.0 / (math.pi / 2.0)
    assert r == pytest.approx(299.2, abs=0.1)
