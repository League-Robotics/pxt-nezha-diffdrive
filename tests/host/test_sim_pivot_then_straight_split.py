"""tests/host/test_sim_pivot_then_straight_split.py -- sprint 032
ticket 005 (BT-06/BT-20, `simulator-split-parity-and-geometry-drift.md`):
`blocks/sim.ts`'s `_startMove()` used to blend every `(distance, yaw)`
into ONE arc, unconditionally -- `simIntegrate()` applies the linear
velocity and the yaw rate to every step simultaneously regardless of
magnitude. The real motion engine (`MotionEngine::moveX()`,
`motion_engine.cpp`) does not: a nonzero distance combined with
`|rotation| >= kTurnFirstAngle` (50 deg) is NOT one blended segment --
it pivots to the new heading FIRST, then drives the distance straight,
as two sequential phases. A block program's own doc comment ("both at
once makes an arc") used to be true only in the browser: `move(47, 90)`
ended around 30 cm forward / 30 cm left in the simulator and 0 forward
/ 47 cm left on the robot.

**The fix.** `_startMove()` now mirrors the real split condition
exactly (`distance != 0 && yawMagnitude >= kSimTurnFirstAngle`), using the
existing `simMoveRemainDist`/`simMoveRemainYaw` fields for phase
bookkeeping plus three small fields (`simMoveHasPendingStraight`/
`simMovePendingDistance`/`simMovePendingSpeed`) recording the queued
straight phase -- the same shape `MotionEngine::queuePivotThenStraight()`
itself uses (`seg_.hasPending`/`pendingDistance`/`pendingCruise`,
`motion_engine.h`/`.cpp`). `simIntegrate()`'s own end-of-move branch now
hands off to the queued straight phase instead of unconditionally
ending the move. Below the threshold (or a pure pivot/pure straight,
where `distance == 0`), behavior is byte-for-byte the pre-fix blended
branch.

**What this proves, and how -- two layers.**

1. The real, dynamic `_startMove()`/`simIntegrate()` behavior IS
   EXECUTED here, not just pattern-matched -- following
   `test_run_dispatch_argument_snapshot.py`'s precedent (extract the
   real source verbatim, compile it with the project's own pinned
   `node_modules/.bin/tsc`, run it under `node`). `control.millis()`
   (normally a MakeCode ambient global) is stubbed as a settable fake
   clock the harness advances in fixed 24 ms steps, the same cadence
   `_tickDrive()` paces to on real hardware and in the browser.

   The boundary case (this ticket's own explicit trap: "an arc segment
   >= 50 deg silently becomes a pivot-then-straight" -- get the
   inclusivity right, `>=` not `>`) is pinned by feeding the REAL
   extracted comparison a `yaw` constructed FROM the harness's own
   extracted `kSimTurnFirstAngle` constant (not a second hardcoded 50),
   round-tripped through the exact same degree<->radian conversion
   `_startMove()` itself applies -- one value that resolves to `yawMagnitude
   >= kSimTurnFirstAngle` (must split) and one a hair below it that
   resolves to `yawMagnitude < kSimTurnFirstAngle` (must not) -- so this
   exercises the actual `>=` operator in the actual code, not a
   restatement of it.

   **What this does NOT cover.** Real TypeScript executed under
   `node`, but still a host-side stand-in for the browser's own PXT
   simulator runtime and for the real robot. It proves the split's
   arithmetic and phase hand-off do what they claim when driven
   directly; it does NOT prove a real `pxt build`'s browser simulator
   reaches this code path the same way (UNVERIFIED -- a `pxt build` in
   `.tmp/` or a real browser run would settle that; not run for this
   ticket, see the commit message), and it says NOTHING about the
   robot's own physical behavior -- `test_run_tour_programs.py`'s own
   module docstring states the identical caveat for the C++ side of
   this same threshold.

2. The threshold VALUE is drift-tested against the real C++ constant
   it mirrors (`test_sim_turn_first_angle_matches_motion_engine`,
   below) -- reads both `blocks/sim.ts`'s `kSimTurnFirstAngle` and
   `motion_engine.h`'s `kTurnFirstAngle` as text (the same technique
   `test_wire_constants_drift.py` uses throughout for pairs with no
   compiled boundary between them) and asserts they match, so a future
   edit to either literal without the other fails here instead of
   silently reopening the parity gap this ticket closes.

Also source-pins `move()`'s corrected JSDoc (`blocks/motion.ts`), which
used to claim "both at once makes an arc" unconditionally.

Run with::

    uv run pytest tests/host/test_sim_pivot_then_straight_split.py
"""
import pathlib
import re
import subprocess

import pytest

# tests/host/test_sim_pivot_then_straight_split.py -> host -> tests -> repo root
_REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
_SIM_TS = _REPO_ROOT / "src" / "blocks" / "sim.ts"
_MOTION_TS = _REPO_ROOT / "src" / "blocks" / "motion.ts"
_MOTION_H = _REPO_ROOT / "src" / "motion" / "motion_engine.h"
_TSC = _REPO_ROOT / "node_modules" / ".bin" / "tsc"


def _sim_ts_source() -> str:
    return _SIM_TS.read_text(encoding="utf-8")


def _motion_ts_source() -> str:
    return _MOTION_TS.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# 1. Drift test: blocks/sim.ts's kSimTurnFirstAngle vs motion_engine.h's
#    kTurnFirstAngle -- the same text-based, no-compile-boundary shape
#    test_wire_constants_drift.py uses throughout.
# ---------------------------------------------------------------------------


def _sim_ts_turn_first_angle():
    match = re.search(
        r"const kSimTurnFirstAngle\s*=\s*([0-9.]+)", _sim_ts_source()
    )
    assert match, "sim.ts's kSimTurnFirstAngle declaration was not found"
    return float(match.group(1))


def _motion_engine_h_turn_first_angle():
    match = re.search(
        r"constexpr\s+float\s+kTurnFirstAngle\s*=\s*([0-9.]+)f?\s*;",
        _MOTION_H.read_text(encoding="utf-8"),
    )
    assert match, "motion_engine.h's kTurnFirstAngle declaration was not found"
    return float(match.group(1))


def test_sim_turn_first_angle_matches_motion_engine():
    """blocks/sim.ts's kSimTurnFirstAngle must equal motion_engine.h's
    kTurnFirstAngle exactly -- a mismatch means the simulator's own
    pivot-then-straight split fires at a different angle than the real
    motion engine's, reopening the parity gap this ticket closes."""
    sim_value = _sim_ts_turn_first_angle()
    engine_value = _motion_engine_h_turn_first_angle()
    assert sim_value == pytest.approx(engine_value, abs=1e-6), (
        f"blocks/sim.ts's kSimTurnFirstAngle ({sim_value}) has drifted from "
        f"motion_engine.h's kTurnFirstAngle ({engine_value})."
    )


def test_sim_turn_first_angle_is_about_50_degrees():
    """Sanity: if this stops being ~50 deg, something is badly wrong
    with either literal -- same guard test_run_tour_programs.py's own
    C++-side sanity check applies, restated here for the TS copy."""
    import math

    assert 40.0 < math.degrees(_sim_ts_turn_first_angle()) < 60.0


# ---------------------------------------------------------------------------
# 2. The real thing: compile the extracted sim.ts core (state + geometry
#    consts + simIntegrate + _setWheels/_driveTwist/_startMove) with the
#    project's own tsc and execute scripted moves under node.
# ---------------------------------------------------------------------------


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
    the two geometry consts, `_setWheels`/`_driveTwist` (harmless
    extras, contiguous with what's needed), `kSimTurnFirstAngle`, and
    `_startMove()` itself -- verbatim, so the harness below exercises
    the REAL split logic rather than a reimplementation of it."""
    src = _sim_ts_source()
    start_idx = src.index("let simX = 0")
    assert start_idx >= 0, "simX declaration not found in sim.ts"
    m = re.search(r"export function _startMove\(", src)
    assert m, "_startMove() not found in sim.ts"
    brace_idx = src.index("{", m.end())
    close_idx = _find_balanced_close(src, brace_idx)
    return src[start_idx:close_idx]


_HARNESS_TEMPLATE = """
declare const console: { log(msg: string): void; error(msg: string): void };
declare const process: { exitCode: number; exit(code: number): void };

// ---- stand-in for the one ambient MakeCode global this extracted
// core calls (control.millis()) -- a plain settable fake clock the
// scripted moves below advance in fixed 24 ms steps, the same cadence
// _tickDrive() paces to on real hardware and in the browser.
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
    simMoveActive = false; simMoveHasPendingStraight = false;
    simMovePendingDistance = 0; simMovePendingSpeed = 0;
    simEstopped = false;
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

// ---- AC3: below the threshold, behavior is UNCHANGED (one blended
// segment) -- direct state inspection right after _startMove(), the
// same shape the pre-fix code always produced.
reset();
_startMove(470, 3000, 100, 9000);  // 47 cm, 30 deg, 100 mm/s, 90 deg/s
check(!simMoveHasPendingStraight,
    "30 deg (below the 50 deg threshold) must NOT set up a pending straight phase");
{
    const expectedDuration = 4.7;  // max(470/100, 3000/9000)
    const expectedYawRad = 30 * Math.PI / 180;
    check(approx(simMoveRemainDist, 470, 1e-9), "below-threshold simMoveRemainDist");
    check(approx(simMoveRemainYaw, expectedYawRad, 1e-9), "below-threshold simMoveRemainYaw");
    check(approx(simVel, 470 / expectedDuration, 1e-9), "below-threshold simVel (unchanged blend formula)");
    check(approx(simYawRate, expectedYawRad / expectedDuration, 1e-9), "below-threshold simYawRate (unchanged blend formula)");
    check(simMoveActive, "below-threshold move must be active");
}

// ---- AC1/AC5: at/above the threshold, _startMove() sets up the pivot
// phase and queues the straight phase -- worked example move(47, 90).
reset();
_startMove(470, 9000, 100, 15000);  // 47 cm, 90 deg, 100 mm/s, 150 deg/s
check(simMoveHasPendingStraight,
    "90 deg (at/above the 50 deg threshold) must set up a pending straight phase");
check(simVel === 0, "the pivot phase must not be moving linearly yet");
check(simMoveRemainDist === 0, "the pivot phase must not consume distance yet");
check(simMovePendingDistance === 470, "the queued straight phase must remember the full distance");
check(simMovePendingSpeed === 100, "the queued straight phase must remember the commanded speed");
{
    const expectedYawDur = 9000 / 15000;
    const expectedYawRad = 90 * Math.PI / 180;
    check(approx(simMoveRemainYaw, expectedYawRad, 1e-9), "pivot-phase simMoveRemainYaw");
    check(approx(simYawRate, expectedYawRad / expectedYawDur, 1e-9), "pivot-phase simYawRate");
}

// Run the SAME move to completion: 0 forward / 47 cm left (470 mm),
// not the ~30/30 blended-arc landing the pre-fix simulator produced.
{
    const steps = runToCompletion(24, 2000);
    check(steps < 2000, "the worked-example move must actually complete");
    check(approx(simX, 0, 0.05), "worked example: 0 mm forward, got " + simX);
    check(approx(simY, 470, 0.05), "worked example: 470 mm left, got " + simY);
    check(approx(simHeading, Math.PI / 2, 1e-6), "worked example: heading ends at +90 deg");
    check(!simMoveActive, "the move must have ended");
    check(!simMoveHasPendingStraight, "no phase should still be pending once the move ends");
}

// ---- The 50 deg boundary itself, from the REAL constant, not a
// second hardcoded 50 -- one value that round-trips (through the
// SAME deg<->rad conversion _startMove() itself applies) to
// yawMagnitude >= kSimTurnFirstAngle, and one a hair under it.
function centidegForRad(rad: number): number {
    return rad * (180 / Math.PI) * 100;
}
const atThresholdYawCentideg = centidegForRad(kSimTurnFirstAngle);
const underThresholdYawCentideg = centidegForRad(kSimTurnFirstAngle * (1 - 1e-6));

reset();
_startMove(100, atThresholdYawCentideg, 50, 9000);
check(simMoveHasPendingStraight,
    "yaw resolving to exactly kSimTurnFirstAngle must satisfy >= and split");

reset();
_startMove(100, underThresholdYawCentideg, 50, 9000);
check(!simMoveHasPendingStraight,
    "yaw resolving to just under kSimTurnFirstAngle must NOT split");

// ---- AC1's own condition: distance == 0 must never split, no matter
// how far above the threshold the rotation is (mirrors moveX()'s own
// `distance != 0.0f && ...` -- a pure pivot is one segment either way).
reset();
_startMove(0, atThresholdYawCentideg, 50, 9000);
check(!simMoveHasPendingStraight,
    "a pure pivot (distance == 0) must never split, even at/above the threshold");
check(simMoveActive, "a pure pivot must still be a real move");

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

    tmp_dir = tmp_path_factory.mktemp("sim_pivot_split_harness")
    ts_path = tmp_dir / "harness.ts"
    js_path = tmp_dir / "harness.js"
    tsconfig_path = tmp_dir / "tsconfig.json"
    ts_path.write_text(harness_ts, encoding="utf-8")
    # Same reasoning as test_run_dispatch_argument_snapshot.py's own
    # harness: `types: []` keeps this project's PXT/browser-simulator
    # @types out of a bare script compile that wants neither; `strict:
    # false` matches this repo's own root tsconfig.json (PXT's device
    # target never enables strict mode).
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
        f"harness failed to compile -- this means the EXTRACTED "
        f"sim.ts core is not valid standalone TypeScript, which should "
        f"be impossible if src/blocks/sim.ts itself type-checks (see "
        f"test_typescript_typecheck.py):\n"
        f"stdout:\n{compile_result.stdout}\nstderr:\n{compile_result.stderr}\n"
        f"---- generated harness ----\n{harness_ts}"
    )

    run_result = subprocess.run(
        ["node", str(js_path)], capture_output=True, text=True,
    )
    return run_result


def test_pivot_then_straight_split_matches_worked_example(_harness_result):
    """Runs the REAL extracted _startMove()/simIntegrate() split logic
    (compiled and executed, not just pattern-matched): below the 50 deg
    threshold the blend formula is byte-for-byte unchanged; at/above it,
    move(47, 90) pivots in place to +90 deg THEN drives 47 cm straight,
    landing at 0 mm forward / 470 mm left -- not the ~30/30 cm blended-
    arc landing the pre-fix simulator produced. Also pins the >=
    boundary itself against the real kSimTurnFirstAngle constant (not a
    second hardcoded 50) and confirms a pure pivot never splits."""
    assert _harness_result.returncode == 0, (
        f"pivot-then-straight split check failed:\n"
        f"stdout:\n{_harness_result.stdout}\nstderr:\n{_harness_result.stderr}"
    )
    assert "PASS" in _harness_result.stdout


# ---------------------------------------------------------------------------
# 3. sim.ts: the split's own shape (source-pin, cheap and specific --
#    names the exact mechanism the executed test above exercises
#    dynamically).
# ---------------------------------------------------------------------------


def test_start_move_condition_mirrors_move_x_exactly():
    src = _sim_ts_source()
    assert re.search(
        r"distance != 0 && yawMagnitude >= kSimTurnFirstAngle", src
    ), (
        "_startMove()'s split condition must read `distance != 0 && "
        "yawMagnitude >= kSimTurnFirstAngle`, mirroring MotionEngine::moveX()'s "
        "own `distance != 0.0f && std::fabs(rotation) >= kTurnFirstAngle` "
        "exactly (including the >= inclusivity)"
    )


def test_start_move_reuses_move_remain_fields_for_phase_bookkeeping():
    """The pivot phase must reuse simMoveRemainYaw/simMoveRemainDist
    (per the ticket's own Solution text), not invent a fresh pair of
    remain-fields duplicating their job."""
    src = _sim_ts_source()
    start_idx = src.index("export function _startMove(")
    brace_idx = src.index("{", start_idx)
    body = src[brace_idx:_find_balanced_close(src, brace_idx)]
    assert "simMoveRemainYaw = yawMagnitude" in body
    assert "simMoveRemainDist = 0" in body


# ---------------------------------------------------------------------------
# 4. blocks/motion.ts: move()'s corrected JSDoc -- no longer claims
#    "both at once makes an arc" unconditionally.
# ---------------------------------------------------------------------------


def _move_doc_and_signature():
    src = _motion_ts_source()
    match = re.search(
        r"(/\*\*.*?\*/)\s*//% block=\"move %distance cm turning %yaw degrees\"",
        src, re.DOTALL,
    )
    assert match, "move()'s JSDoc block was not found in motion.ts"
    return match.group(1)


def test_move_doc_no_longer_claims_unconditional_arc():
    doc = _move_doc_and_signature()
    assert "Both at once makes an arc." not in doc, (
        "move()'s JSDoc must no longer unconditionally claim \"both at "
        "once makes an arc\" -- that was only ever true in the browser, "
        "and is no longer true there either now that the simulator "
        "mirrors the real >=50 deg pivot-then-straight split."
    )


def test_move_doc_states_the_actual_split_behavior():
    doc = _move_doc_and_signature()
    assert re.search(r"blend", doc, re.I), (
        "move()'s JSDoc must describe the below-threshold blended case"
    )
    assert re.search(r"pivot", doc, re.I), (
        "move()'s JSDoc must describe the at/above-threshold "
        "pivot-then-straight case"
    )
