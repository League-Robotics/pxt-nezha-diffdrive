"""tests/host/test_sim_geometry_matches_kernel_and_setters_apply.py --
sprint 032 ticket 006 (`simulator-split-parity-and-geometry-drift.md`):
`blocks/sim.ts`'s geometry constants had no drift test, and its
`_setGeometry`/`_setKernelValue` shims were confirmed no-ops -- each
recorded its arguments into a module variable nothing else read and
left `_setWheels()`'s yaw-rate divisor permanently fixed at its two
built-in defaults. A project that pastes a calibration block (`set
track width`, or a `set config rotational slip` kernel-value write)
therefore got ZERO change in simulated turning behavior: the browser
twin kept turning at the factory-default rate regardless of what the
student's own calibration measured.

**Two separate claims, two separate tests -- do not conflate them.**

1. **The DEFAULT values agree.** `blocks/sim.ts`'s `simTrackWidth`/
   `simRotationalSlip` initializers must equal `motion_engine.h`'s own
   compiled `trackWidth_`/`rotationalSlip_` defaults, so an unconfigured
   simulator matches an unconfigured robot out of the box.
2. **The LIVE values actually change simulated behavior once set.**
   `_setGeometry()`/`_setKernelValue()` must update the same state
   `_setWheels()`'s yaw-rate divisor reads, so a program that pastes a
   calibration block gets a different (correct) turn rate afterward.

**Why claim 1 is scoped to defaults, not fleet values -- the judgement
call this ticket has to make explicitly.** `trackWidth`/`rotationalSlip`
are per-robot calibration, not universal physical constants: the real
fleet's boards each carry their own measured values (see
`docs/design/DESIGN.md`'s own fleet table), and nothing in this repo
could assert "the simulator's default equals THE robot's value" without
naming a specific, moving target -- there is no such thing as *the*
robot's trackWidth. So this file does NOT pin one hardcoded number
against another as if both were fixed forever; it pins the simulator's
*compiled default* against the kernel's *compiled default* -- two
literals in two source files, comparable at the desk with no live robot
and no compiled boundary between them, in the same text-based shape
`test_wire_constants_drift.py` already uses throughout for exactly this
kind of pair (that file's own case 8 already guards `motion_engine.h`
against `docs/design/specification.md`'s doc table this same way; this
adds the third leg of that same triangle -- `blocks/sim.ts`'s own
runtime copy). The actual invariant this project needs -- "a calibrated
board's simulator twin reflects ITS calibration" -- is not a constant
equality at all; it is a *behavior*, and that is what test 2 (the
compiled-and-executed harness below) actually exercises: a program
sets its own values via the same block API a calibration paste would
use, and the simulator's subsequent output must move accordingly. A
frozen-number drift test could never prove that; only running the
setter and observing the effect can, which is why this ticket asks for
both tests rather than treating the drift test alone as sufficient.

**What this does NOT prove.** Both tests run on a desktop host, one
compiling and executing the real extracted TypeScript under `node`, per
`test_run_dispatch_argument_snapshot.py`'s precedent. Neither reaches a
real `pxt build`'s browser simulator (UNVERIFIED -- a `pxt build` in
`.tmp/` or a real browser run would settle that) or says anything about
a physical robot's own turning behavior -- the simulator's contract is
parity with the KERNEL's algorithm and constants, never a claim about
hardware, which idealized kinematics can't reproduce exactly regardless
of how faithfully the geometry inputs are mirrored.

Run with::

    uv run pytest tests/host/test_sim_geometry_matches_kernel_and_setters_apply.py
"""
import pathlib
import re
import subprocess

import pytest

# tests/host/test_sim_geometry_matches_kernel_and_setters_apply.py ->
# host -> tests -> repo root
_REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
_SIM_TS = _REPO_ROOT / "src" / "blocks" / "sim.ts"
_MOTION_H = _REPO_ROOT / "src" / "motion" / "motion_engine.h"
_TSC = _REPO_ROOT / "node_modules" / ".bin" / "tsc"


def _sim_ts_source() -> str:
    return _SIM_TS.read_text(encoding="utf-8")


def _motion_engine_h_source() -> str:
    return _MOTION_H.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# 1. Drift test: blocks/sim.ts's DEFAULT simTrackWidth/simRotationalSlip
#    vs motion_engine.h's own compiled trackWidth_/rotationalSlip_
#    defaults -- text-based, no compiled boundary, same shape
#    test_wire_constants_drift.py's case 8 already uses for this exact
#    pair against docs/design/specification.md's table. Scope: compiled
#    DEFAULTS only -- see this module's own docstring for why a live
#    per-robot fleet value can never be the thing pinned here.
# ---------------------------------------------------------------------------


def _sim_ts_track_width():
    match = re.search(
        r"let simTrackWidth\s*=\s*([0-9.]+)", _sim_ts_source()
    )
    assert match, "sim.ts's simTrackWidth declaration was not found"
    return float(match.group(1))


def _sim_ts_rotational_slip():
    match = re.search(
        r"let simRotationalSlip\s*=\s*([0-9.]+)", _sim_ts_source()
    )
    assert match, "sim.ts's simRotationalSlip declaration was not found"
    return float(match.group(1))


def _motion_engine_h_track_width():
    match = re.search(
        r"trackWidth_\s*=\s*([0-9.]+)f;", _motion_engine_h_source()
    )
    assert match, "motion_engine.h's trackWidth_ default was not found"
    return float(match.group(1))


def _motion_engine_h_rotational_slip():
    match = re.search(
        r"rotationalSlip_\s*=\s*([0-9.]+)f;", _motion_engine_h_source()
    )
    assert match, "motion_engine.h's rotationalSlip_ default was not found"
    return float(match.group(1))


def test_sim_track_width_default_matches_motion_engine():
    """blocks/sim.ts's simTrackWidth default must equal
    motion_engine.h's compiled trackWidth_ default -- a mismatch means
    an unconfigured simulator turns at a different rate than an
    unconfigured robot, out of the box, with no calibration block
    involved at all."""
    sim_value = _sim_ts_track_width()
    engine_value = _motion_engine_h_track_width()
    assert sim_value == pytest.approx(engine_value, abs=1e-6), (
        f"blocks/sim.ts's simTrackWidth default ({sim_value}) has "
        f"drifted from motion_engine.h's trackWidth_ default "
        f"({engine_value})."
    )


def test_sim_rotational_slip_default_matches_motion_engine():
    """Same guard as the trackWidth test above, for rotationalSlip."""
    sim_value = _sim_ts_rotational_slip()
    engine_value = _motion_engine_h_rotational_slip()
    assert sim_value == pytest.approx(engine_value, abs=1e-6), (
        f"blocks/sim.ts's simRotationalSlip default ({sim_value}) has "
        f"drifted from motion_engine.h's rotationalSlip_ default "
        f"({engine_value})."
    )


# ---------------------------------------------------------------------------
# 2. The real thing: compile the extracted sim.ts state/_setWheels/
#    _driveTwist/_setGeometry/_setKernelValue verbatim with the
#    project's own tsc and execute scripted setter calls under node,
#    confirming the setters actually move a subsequent _setWheels()
#    call's simYawRate -- not merely that they store a value somewhere
#    -- and that _driveTwist()'s own yaw rate stays exactly independent
#    of both, proving it needs no matching update.
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


def _extract_function(src: str, signature_re: str) -> str:
    m = re.search(signature_re, src)
    assert m, f"function matching {signature_re!r} not found in sim.ts"
    brace_idx = src.index("{", m.end())
    close_idx = _find_balanced_close(src, brace_idx)
    return src[m.start():close_idx]


def _extract_sim_core() -> str:
    """Two non-contiguous spans of sim.ts, stitched together verbatim:

    - state declarations through the end of `_driveTwist()` (covers
      `simIntegrate()`, the `simTrackWidth`/`simRotationalSlip` live
      state, `_setWheels()`'s divisor, and `_driveTwist()` itself --
      contiguous with `_setWheels()` in the real file), and
    - `_setGeometry()` through the end of `_setKernelValue()` (the two
      setters under test), which live much further down the file next
      to the other configuration shims.

    Extracted, not reimplemented, so this harness exercises the REAL
    setter/divisor logic rather than a restatement of it."""
    src = _sim_ts_source()
    start_idx = src.index("let simX = 0")
    assert start_idx >= 0, "simX declaration not found in sim.ts"
    core = _extract_function(src, r"export function _driveTwist\(")
    core_end = src.index(core) + len(core)
    state_through_drive_twist = src[start_idx:core_end]

    setters = (
        _extract_function(src, r"export function _setGeometry\(")
        + "\n\n"
        + _extract_function(src, r"export function _setKernelValue\(")
    )
    return state_through_drive_twist + "\n\n" + setters


_HARNESS_TEMPLATE = """
declare const console: { log(msg: string): void; error(msg: string): void };
declare const process: { exitCode: number; exit(code: number): void };

// ---- stand-in for the one ambient MakeCode global this extracted
// core calls (control.millis()) -- simIntegrate() reads it but nothing
// in this harness advances time, so a fixed value is enough.
let _fakeMillisValue = 0;
const control = { millis: () => _fakeMillisValue };

// ---- the REAL simulator core, extracted verbatim ----
%(sim_core)s

// ---- scripted setter calls ----
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
    simTrackWidth = 114.2; simRotationalSlip = 0.952;
    _fakeMillisValue = 0;
}

// ---- AC: the DEFAULT yaw rate, before any setter call, matches the
// plain formula against the built-in defaults.
reset();
_setWheels(0, 100);
{
    const expected = 100 / (114.2 / 0.952);
    check(approx(simYawRate, expected, 1e-9),
        "default simYawRate must equal (right-left)/(defaultTrackWidth/defaultSlip), got " + simYawRate);
}

// ---- AC: _setGeometry()'s trackWidth argument (wire units 0.1 mm)
// actually changes a SUBSEQUENT _setWheels() call's simYawRate -- not
// just that it stores a value. 1200 (0.1 mm) == 120 mm.
reset();
_setWheels(0, 100);
const yawRateBeforeGeometry = simYawRate;
_setGeometry(1200, 0);
_setWheels(0, 100);
const yawRateAfterGeometry = simYawRate;
check(!approx(yawRateBeforeGeometry, yawRateAfterGeometry, 1e-9),
    "_setGeometry()'s trackWidth argument must change a subsequent _setWheels() call's simYawRate");
{
    const expected = 100 / (120 / 0.952);
    check(approx(yawRateAfterGeometry, expected, 1e-9),
        "post-_setGeometry simYawRate must use the NEW trackWidth (120 mm), got " + yawRateAfterGeometry);
}

// ---- AC: _setGeometry()'s trackWidth==0 means "keep the prior value"
// (mirrors shims.cpp's own setGeometry(): `if (trackWidth > 0) ...`),
// not "set the track width to zero" (which would divide by zero).
reset();
_setGeometry(1200, 0);
const yawRateAfterFirstSet = (() => { _setWheels(0, 100); return simYawRate; })();
_setGeometry(0, 12345);  // trackWidth 0 -> ignored; calib is not a live state
_setWheels(0, 100);
check(approx(simYawRate, yawRateAfterFirstSet, 1e-9),
    "_setGeometry(0, ...) must leave the previously-set trackWidth unchanged");

// ---- AC: _setKernelValue(16, ...) (ConfigField.RotationalSlip, wire
// name "rotational_slip") actually changes a SUBSEQUENT _setWheels()
// call's simYawRate -- x1000-scaled wire value, so 1200 == slip 1.2.
reset();
_setWheels(0, 100);
const yawRateBeforeSlip = simYawRate;
_setKernelValue(16, 1200);
_setWheels(0, 100);
const yawRateAfterSlip = simYawRate;
check(!approx(yawRateBeforeSlip, yawRateAfterSlip, 1e-9),
    "_setKernelValue(16, ...) must change a subsequent _setWheels() call's simYawRate");
{
    const expected = 100 / (114.2 / 1.2);
    check(approx(yawRateAfterSlip, expected, 1e-9),
        "post-_setKernelValue(16, ...) simYawRate must use the NEW rotationalSlip (1.2), got " + yawRateAfterSlip);
}

// ---- AC: both live values combine correctly (not just independently).
reset();
_setGeometry(1200, 0);      // trackWidth -> 120 mm
_setKernelValue(16, 1200);  // rotationalSlip -> 1.2
_setWheels(0, 100);
{
    const expected = 100 / (120 / 1.2);  // == 100 -- a clean check value
    check(approx(simYawRate, expected, 1e-9),
        "combined trackWidth+rotationalSlip setters must both apply to the same divisor, got " + simYawRate);
}

// ---- AC: _driveTwist() needs NO analogous geometry update -- its
// observable yaw rate for a given (speed, yawRate) input is IDENTICAL
// no matter what simTrackWidth/simRotationalSlip are currently set to,
// because (per _setWheels()'s own comment) hardware's own effective-
// track-width multiply/divide round trip cancels algebraically for ANY
// value of either. Proven here by driving the SAME _driveTwist() call
// through two very different live geometries and requiring an EXACT
// match -- not merely "close enough" -- which would fail immediately
// if _driveTwist() ever grew a trackWidth-dependent term of its own.
reset();
_setGeometry(1200, 0);      // trackWidth -> 120 mm
_setKernelValue(16, 1200);  // rotationalSlip -> 1.2
_driveTwist(50, 9000);      // 50 mm/s, 90 deg/s (cdeg/s wire units)
const yawRateGeometryA = simYawRate;
reset();
_setGeometry(500, 0);       // trackWidth -> 50 mm (a very different value)
_setKernelValue(16, 300);   // rotationalSlip -> 0.3 (a very different value)
_driveTwist(50, 9000);
const yawRateGeometryB = simYawRate;
check(yawRateGeometryA === yawRateGeometryB,
    "_driveTwist()'s yaw rate must be EXACTLY independent of simTrackWidth/simRotationalSlip -- got " +
    yawRateGeometryA + " vs " + yawRateGeometryB);

// ---- AC: every OTHER _setKernelValue() field stays a silent no-op --
// this ticket only wires field 16, not every ordinal.
reset();
_setWheels(0, 100);
const yawRateBeforeOtherField = simYawRate;
_setKernelValue(19, 5000);  // ConfigField.Accel -- has no sim model
_setWheels(0, 100);
check(approx(simYawRate, yawRateBeforeOtherField, 1e-9),
    "_setKernelValue() for a field other than 16 must not change simYawRate");

// ---- AC: a nonpositive rotational slip value is ignored (mirrors
// MotionEngine::setRotationalSlip()'s own \\"> 0, else keep\\" validation).
reset();
_setGeometry(1200, 0);
_setWheels(0, 100);
const yawRateBeforeBadSlip = simYawRate;
_setKernelValue(16, 0);
_setWheels(0, 100);
check(approx(simYawRate, yawRateBeforeBadSlip, 1e-9),
    "_setKernelValue(16, 0) must leave the previously-set rotationalSlip unchanged");

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

    tmp_dir = tmp_path_factory.mktemp("sim_geometry_setters_harness")
    ts_path = tmp_dir / "harness.ts"
    js_path = tmp_dir / "harness.js"
    tsconfig_path = tmp_dir / "tsconfig.json"
    ts_path.write_text(harness_ts, encoding="utf-8")
    # Same reasoning as test_sim_pivot_then_straight_split.py's own
    # harness: `types: []` keeps this project's PXT/browser-simulator
    # @types out of a bare script compile that wants neither; `strict:
    # false` matches this repo's own root tsconfig.json.
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


def test_geometry_setters_change_simulated_yaw_rate(_harness_result):
    """Runs the REAL extracted _setWheels()/_driveTwist()/
    _setGeometry()/_setKernelValue() logic (compiled and executed, not
    just pattern-matched): confirms the default divisor matches the
    built-in constants, that _setGeometry()'s trackWidth argument and
    _setKernelValue(16, ...)'s rotational-slip argument each move a
    subsequent _setWheels() call's simYawRate, that they combine
    correctly, that trackWidth==0 and a nonpositive slip are each
    ignored (mirroring hardware's own "> 0, else keep" validation), that
    every other _setKernelValue() field remains a no-op, and that
    _driveTwist()'s yaw rate for a fixed input is EXACTLY identical
    across two very different live geometries -- proving it needs no
    analogous geometry update, rather than merely asserting that in a
    comment."""
    assert _harness_result.returncode == 0, (
        f"geometry setter behavior check failed:\n"
        f"stdout:\n{_harness_result.stdout}\nstderr:\n{_harness_result.stderr}"
    )
    assert "PASS" in _harness_result.stdout


# ---------------------------------------------------------------------------
# 3. sim.ts: source pins for the setters' own shape (cheap and
#    specific -- names the exact mechanism the executed test above
#    exercises dynamically) and for the removal of the dead
#    last-seen-args bookkeeping the live state replaces.
# ---------------------------------------------------------------------------


def test_set_geometry_updates_live_track_width():
    src = _sim_ts_source()
    body = _extract_function(src, r"export function _setGeometry\(")
    assert "simTrackWidth = trackWidth" in body, (
        "_setGeometry() must assign into the live simTrackWidth state "
        "_setWheels() divides by"
    )


def test_set_kernel_value_updates_live_rotational_slip_for_field_16():
    src = _sim_ts_source()
    body = _extract_function(src, r"export function _setKernelValue\(")
    assert "simRotationalSlip = v" in body, (
        "_setKernelValue() must assign into the live simRotationalSlip "
        "state for field 16 (ConfigField.RotationalSlip)"
    )
    assert "16" in body, (
        "_setKernelValue() must gate the rotational-slip assignment on "
        "field 16, matching wire_adapter.cpp's \"rotational_slip\" "
        "ordinal"
    )


def test_dead_last_seen_bookkeeping_variables_are_gone():
    """simLastGeometryTrackWidth/simLastGeometryCalib/simLastKernelField/
    simLastKernelValue used to exist only because _setGeometry()/
    _setKernelValue() had nothing real to update -- now that
    simTrackWidth/simRotationalSlip are live state, keeping the old
    bookkeeping variables alongside them would be dead code recording
    the same calls twice."""
    src = _sim_ts_source()
    for name in (
        "simLastGeometryTrackWidth",
        "simLastGeometryCalib",
        "simLastKernelField",
        "simLastKernelValue",
    ):
        assert name not in src, (
            f"{name} is dead bookkeeping now that _setGeometry()/"
            f"_setKernelValue() update live state directly -- remove it"
        )
