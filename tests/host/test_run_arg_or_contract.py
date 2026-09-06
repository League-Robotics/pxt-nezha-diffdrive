"""tests/host/test_run_arg_or_contract.py -- sprint 032 ticket 003
(BT-22): `runArg(i)` in `src/blocks/run.ts` maps BOTH "no such
argument" and "argument present but unparseable" to the same `0`, so
`RUN:circle:abc` has `runArgCount() == 1` (the text "abc" IS present)
and `runArg(0) == 0` (parseFloat("abc") is NaN, mapped to 0) --
producing `circleTour(0, ...)`: eight 45 deg pivots-in-place, silently,
instead of either erroring or falling back to the documented default.

**What this pins, and how.** `runArgOr()` is genuinely EXECUTED here,
not just pattern-matched: the function's own source is extracted
verbatim from `run.ts` (the balanced body between its `export function
runArgOr(...)` signature and matching `}`), pasted into a throwaway
harness `.ts` file alongside a stub `runArgText()`, compiled with the
project's own pinned `node_modules/.bin/tsc` (never `npx tsc` --
`test_typescript_typecheck.py`'s own header comment explains why that
resolves to an unrelated decoy package in this environment), and run
under `node`. A source-pin regex could describe the intended shape and
still be wrong about what the code actually does on a given input;
this runs the real three-way branch structure against real arguments.

`test/test.ts`'s `circle`/`infinity`/`snake` handlers, by contrast,
cannot be executed this way without a much larger PXT/simulator
harness (they call `diffDrive.onRun`, `beginJob`, `diffDrive.stopMove`,
etc., none of which exist outside the built extension) -- those are
pinned by source-text inspection instead, following the precedent
`test_run_abort_source_pin.py` and `test_run_tour_programs.py` already
set for this exact file.

**What this is NOT.** Like its sibling `test/test.ts` source-pin files,
the `test/test.ts`-facing tests below cannot prove a real `RUN:circle:
abc` sent to a real robot is refused -- only that the source shape
which refuses it is present. That needs a robot (this sprint is
declared no-hardware; see `sprint.md`'s Test Strategy).

Run with::

    uv run pytest tests/host/test_run_arg_or_contract.py
"""
import pathlib
import re
import subprocess
import textwrap

import pytest

# tests/host/test_run_arg_or_contract.py -> host -> tests -> repo root
_REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
_RUN_TS = _REPO_ROOT / "src" / "blocks" / "run.ts"
_TEST_TS = _REPO_ROOT / "test" / "test.ts"
_TSC = _REPO_ROOT / "node_modules" / ".bin" / "tsc"


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


def _run_ts_source() -> str:
    return _RUN_TS.read_text(encoding="utf-8")


def _test_ts_source() -> str:
    return _TEST_TS.read_text(encoding="utf-8")


def _extract_run_arg_or_source() -> str:
    """The verbatim `export function runArgOr(...) { ... }` text,
    brace-balanced so a nested `if { }` doesn't truncate it early."""
    src = _run_ts_source()
    m = re.search(
        r"export function runArgOr\([^)]*\)\s*:\s*number\s*\{", src)
    assert m, "runArgOr() not found in src/blocks/run.ts"
    open_idx = m.end() - 1
    close_idx = _find_balanced_close(src, open_idx)
    return src[m.start():close_idx]


def _onrun_body(verb: str) -> str:
    src = _test_ts_source()
    m = re.search(
        r'diffDrive\.onRun\(\s*"%s"\s*,\s*function\s*\([^)]*\)\s*\{' %
        re.escape(verb), src)
    assert m, 'diffDrive.onRun("%s", ...) not found' % verb
    open_idx = m.end() - 1
    close_idx = _find_balanced_close(src, open_idx)
    return src[m.end():close_idx - 1]


def _function_source(name: str) -> str:
    src = _run_ts_source()
    m = re.search(r"export function %s\([^)]*\)(?:\s*:\s*\w+)?\s*\{" %
                  re.escape(name), src)
    assert m, "function %s() not found in run.ts" % name
    open_idx = m.end() - 1
    close_idx = _find_balanced_close(src, open_idx)
    return src[m.start():close_idx]


# ---------------------------------------------------------------------------
# The real thing: compile the extracted runArgOr() source with the
# project's own tsc and execute it under node.
# ---------------------------------------------------------------------------

_HARNESS_TEMPLATE = """
// Minimal ambient declarations for the two node globals this harness
// uses, so the compile needs none of this project's own
// node_modules/@types/* (which are baked in for the PXT/browser
// simulator target and collide with each other -- @types/audioworklet
// vs the DOM lib -- in a bare script compile that wants neither).
declare const console: { log(msg: string): void; error(msg: string): void };
declare const process: { exitCode: number; exit(code: number): void };

let ARGV: string[] = [];
function runArgText(i: number): string {
    if (i < 0 || i >= ARGV.length) return "";
    return ARGV[i];
}

%(run_arg_or_source)s

let failures = 0;
function check(actual: number, expected: number, label: string): void {
    const bothNaN = isNaN(actual) && isNaN(expected);
    if (actual !== expected && !bothNaN) {
        console.error("FAIL " + label + ": expected " + expected +
            ", got " + actual);
        failures++;
    }
}
function checkNaN(actual: number, label: string): void {
    if (!isNaN(actual)) {
        console.error("FAIL " + label + ": expected NaN, got " + actual);
        failures++;
    }
}
function checkNot(actual: number, notExpected: number, label: string): void {
    if (actual === notExpected) {
        console.error("FAIL " + label + ": must not equal " + notExpected +
            ", got " + actual);
        failures++;
    }
}

// absent -> fallback
ARGV = [];
check(runArgOr(0, 30), 30, "absent returns fallback");

// present, valid, no bound -> the parsed value
ARGV = ["45"];
check(runArgOr(0, 30), 45, "present+valid returns the value");

// present, valid, exactly a legitimately-zero argument (no bound
// requested) -> 0 itself, NOT the NaN sentinel -- the sentinel must
// not collide with a real value a caller might need.
ARGV = ["0"];
check(runArgOr(0, 30), 0, "a real zero argument is not confused with NaN");

// present but unparseable (the BT-22 case: RUN:circle:abc) -> NaN,
// and specifically NOT the fallback and NOT 0.
ARGV = ["abc"];
const typoResult = runArgOr(0, 30);
checkNaN(typoResult, "present+invalid (typo) is the NaN sentinel");
checkNot(typoResult, 30, "present+invalid (typo) must not silently be the fallback");
checkNot(typoResult, 0, "present+invalid (typo) must not silently be 0");

// present, valid, but at the minExclusive bound (a non-positive
// radius) -> NaN, same sentinel as a typo, not the fallback either.
ARGV = ["0"];
const zeroRadius = runArgOr(0, 30, 0);
checkNaN(zeroRadius, "a zero radius is rejected when minExclusive=0");
checkNot(zeroRadius, 30, "a rejected radius must not silently be the fallback");

// present, valid, negative -> also rejected by the same bound.
ARGV = ["-5"];
checkNaN(runArgOr(0, 30, 0), "a negative radius is rejected when minExclusive=0");

// present, valid, positive, above the bound -> passes through.
ARGV = ["12.5"];
check(runArgOr(0, 30, 0), 12.5, "a positive radius above the bound passes through");

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
    run_arg_or_source = _extract_run_arg_or_source()
    # export/declare are meaningless (and one is a parse error) outside
    # a module/namespace -- strip the leading `export ` so the harness
    # compiles as a plain script, without touching the function body.
    run_arg_or_source = run_arg_or_source.replace(
        "export function runArgOr", "function runArgOr", 1)
    harness_ts = _HARNESS_TEMPLATE % {"run_arg_or_source": run_arg_or_source}

    tmp_dir = tmp_path_factory.mktemp("run_arg_or_harness")
    ts_path = tmp_dir / "harness.ts"
    js_path = tmp_dir / "harness.js"
    tsconfig_path = tmp_dir / "tsconfig.json"
    ts_path.write_text(harness_ts, encoding="utf-8")
    # `types: []` in a real tsconfig.json (not the CLI --types flag,
    # which has no clean way to say "none") keeps this project's OWN
    # node_modules/@types/* (audioworklet, node's DOM globals, etc. --
    # baked in for the PXT simulator target) from being auto-included
    # and colliding with each other in a bare script compile that
    # wants neither.
    tsconfig_path.write_text(
        '{"compilerOptions": {"target": "es2017", "lib": ["es2017"], '
        '"types": [], "strict": true, "outFile": "%s"}, '
        '"files": ["%s"]}' % (js_path.name, ts_path.name),
        encoding="utf-8",
    )

    compile_result = subprocess.run(
        [str(_TSC), "-p", str(tsconfig_path)],
        capture_output=True, text=True, cwd=_REPO_ROOT,
    )
    assert compile_result.returncode == 0, (
        f"harness failed to compile -- this means the EXTRACTED "
        f"runArgOr() source is not valid standalone TypeScript, which "
        f"should be impossible if src/blocks/run.ts itself type-checks "
        f"(see test_typescript_typecheck.py):\n"
        f"stdout:\n{compile_result.stdout}\nstderr:\n{compile_result.stderr}\n"
        f"---- generated harness ----\n{harness_ts}"
    )

    run_result = subprocess.run(
        ["node", str(js_path)], capture_output=True, text=True,
    )
    return run_result


def test_run_arg_or_three_way_contract_executes_correctly(_harness_result):
    """Runs the REAL extracted runArgOr() body (compiled and executed,
    not just pattern-matched) against the three-way contract the
    ticket's acceptance criteria specify: absent -> fallback,
    present+valid -> value, present+invalid (typo OR non-positive with
    a radius bound) -> neither fallback nor 0."""
    assert _harness_result.returncode == 0, (
        f"runArgOr() contract check failed:\n"
        f"stdout:\n{_harness_result.stdout}\nstderr:\n{_harness_result.stderr}"
    )
    assert "PASS" in _harness_result.stdout


# ---------------------------------------------------------------------------
# run.ts: runArg()'s own contract is unchanged (AC: 0 for
# absent-or-invalid, for every OTHER existing call site).
# ---------------------------------------------------------------------------


def test_run_arg_contract_is_unchanged():
    body = _function_source("runArg")
    assert re.search(r"if\s*\(text\.length == 0\)\s*return 0", body), (
        "runArg() must still return 0 for an absent argument -- this "
        "ticket adds runArgOr() as a new, opt-in function; it must not "
        "change runArg()'s own existing contract"
    )
    assert re.search(r"isNaN\(value\)\s*\?\s*0\s*:\s*value", body), (
        "runArg() must still map an unparseable argument to 0"
    )


def test_run_arg_or_is_a_new_function_not_a_runarg_rename():
    src = _run_ts_source()
    assert "export function runArgOr(" in src, (
        "run.ts must gain a new export function runArgOr()"
    )
    assert re.search(r"export function runArg\(i: number\): number \{", src), (
        "runArg()'s own signature must be untouched"
    )


# ---------------------------------------------------------------------------
# test/test.ts: circle/infinity/snake use runArgOr for radius; every
# other runArg() call site (pivot, face, arc, straight, seedxy,
# turnrate) is left alone.
# ---------------------------------------------------------------------------

_OLD_RADIUS_TERNARY = re.compile(
    r"runArgCount\(\)\s*>\s*0\s*\?\s*diffDrive\.runArg\(0\)")

_RADIUS_VERBS = ("circle", "infinity", "snake")

# Every runArg()/runArgCount() call site this ticket's own acceptance
# criteria says must stay on runArg() -- explicitly enumerated in the
# ticket text, not just "whatever wasn't touched", so a future runArg()
# regression at one of these shows up here by name.
_UNCHANGED_RUNARG_VERBS = ("pivot", "face", "arc", "straight", "seedxy",
                           "turnrate")


@pytest.mark.parametrize("verb", _RADIUS_VERBS)
def test_radius_handlers_no_longer_use_the_bare_ternary(verb):
    body = _onrun_body(verb)
    assert not _OLD_RADIUS_TERNARY.search(body), (
        f'RUN:{verb} still uses the old '
        f'`runArgCount() > 0 ? diffDrive.runArg(0) : <default>` pattern '
        f'for its radius argument -- BT-22: that pattern maps '
        f'"RUN:{verb}:abc" (unparseable) to the SAME value as a real '
        f'zero, and both silently to a plausible-looking run'
    )


@pytest.mark.parametrize("verb", _RADIUS_VERBS)
def test_radius_handlers_use_run_arg_or_with_a_positive_bound(verb):
    body = _onrun_body(verb)
    assert re.search(r"diffDrive\.runArgOr\(\s*0\s*,\s*[\d.]+\s*,\s*0\s*\)",
                      body), (
        f'RUN:{verb} must call diffDrive.runArgOr(0, <default>, 0) for '
        f'its radius argument -- the minExclusive=0 bound is what '
        f'rejects a non-positive radius (Solution: "rejects NaN and '
        f'non-positive radii"), not just an unparseable one'
    )


@pytest.mark.parametrize("verb", _RADIUS_VERBS)
def test_radius_handlers_refuse_on_nan_instead_of_running(verb):
    """BT-22's actual fix: an invalid radius must not reach the tour
    function at all -- it must be refused, with a wire-visible signal,
    before ever calling circleTour/infinityTour/snakeTour."""
    body = _onrun_body(verb)
    m = re.search(r"if\s*\(\s*isNaN\(\s*r\s*\)\s*\)\s*\{", body)
    assert m, (
        f'RUN:{verb} must check isNaN() on the runArgOr() result and '
        f'refuse the job -- silently substituting 0 or the fallback is '
        f'exactly the BT-22 defect this ticket fixes'
    )
    open_idx = m.end() - 1
    close_idx = _find_balanced_close(body, open_idx)
    guard_body = body[m.end():close_idx - 1]
    assert re.search(r'diffDrive\.emitLine\(\s*"ARGERR:', guard_body), (
        f'RUN:{verb}\'s invalid-radius branch must emit a wire-visible '
        f'ARGERR: line -- a silent no-op is the "mysterious" failure '
        f'mode the ticket explicitly rejects for a student-facing verb'
    )
    assert re.search(r"\breturn\b", guard_body), (
        f'RUN:{verb}\'s invalid-radius branch must return without '
        f'starting the tour'
    )
    # The tour function itself must not be reachable from inside the
    # guard -- it must only run in the branch that follows.
    tour_fn = {"circle": "circleTour", "infinity": "infinityTour",
               "snake": "snakeTour"}[verb]
    assert tour_fn not in guard_body, (
        f'RUN:{verb} calls {tour_fn}() from inside its own invalid-radius '
        f'guard -- an invalid radius must never start the tour'
    )
    assert tour_fn in body[close_idx:], (
        f'RUN:{verb} must still call {tour_fn}() once a valid radius is '
        f'in hand'
    )


@pytest.mark.parametrize("verb", _UNCHANGED_RUNARG_VERBS)
def test_other_run_arg_call_sites_are_left_on_run_arg(verb):
    """AC: runArg()'s existing call sites are UNCHANGED by this ticket
    -- pivot/face/arc/straight/seedxy/turnrate keep using runArg(),
    not runArgOr(), so no unreviewed behavior change lands at any of
    them."""
    body = _onrun_body(verb)
    assert "diffDrive.runArgOr(" not in body, (
        f'RUN:{verb} now calls runArgOr() -- the ticket explicitly '
        f'scopes this change to circle/infinity/snake\'s radius '
        f'argument and leaves every other existing runArg() call site '
        f'alone unless a specific reason surfaced during implementation '
        f'(none did for {verb})'
    )
