"""tests/host/test_typescript_typecheck.py -- runs this project's
`tsconfig.json` through a real `tsc --noEmit`, so `src/blocks/*.ts` and
`test/*.ts` are type-checked on every `uv run pytest`, not just once per
sprint inside the build-checkpoint ticket's full `pxt build` (which
type-checks but never *executes* anything). This is sprint 017 ticket
008's gate: the review's Critical finding (block `goTo` missing its
target by 112 mm) lived in TypeScript nothing executed or type-checked
between sprint build checkpoints -- `src/blocks/` is 1149 lines of
student-facing code.

**Why this had never run before.** `tsconfig.json` existed with a
hand-maintained `files` array (kept current by sprints 012/013), but
`package.json` declared no `typescript` dependency and
`node_modules/typescript` did not exist -- the config was correct-
looking and never executed. Bare `npx tsc` in this environment is
actively dangerous to rely on for that reason: with no local
`typescript` installed, `npx tsc` resolves to an unrelated npm package
literally named `tsc` (a decoy that prints "This is not the tsc command
you are looking for" and exits nonzero) rather than fetching real
TypeScript -- a naive `subprocess.run(["npx", "tsc", ...])` would have
looked like a passing gate returning a random failure, or worse, a
silently wrong tool. This test shells the concrete installed binary
(`node_modules/.bin/tsc`, from the pinned `typescript` devDependency in
`package.json`) instead. If that binary is missing the test SKIPS with
an actionable reason naming `npm ci`, rather than either falling
through to `npx`'s resolution or failing: an uninstalled toolchain is
an environment precondition, not a defect in this repo's TypeScript,
and a fresh worktree whose only red test is "node_modules is absent"
teaches the next reader that a red suite is normal (sprint 034 ticket
010). The skip reason carries the no-`npx` reasoning above with it, so
it is still read at the moment it matters.

**What `tsconfig.json`'s own header comment covers, and doesn't
duplicate here**: getting this to run cleanly required two real fixes
to `tsconfig.json`'s `files` list (`pxt_modules/core/math.ts` and
`pxt-helpers.ts` were missing -- both listed in PXT's own
`pxt_modules/core/pxt.json` manifest, never in this project's) plus one
new file, `tsconfig-simulator-globals.d.ts` (repo root), supplying the
two genuinely-missing globals (`console`, `Array`'s iterator protocol)
neither PXT's device-only ambient set nor those two files declare. See
`tsconfig.json`'s own header comment and that file's header comment for
the full investigation -- this test just runs the result.

Modeled on `test_kernel_harness.py`'s `compile_shared_lib()`: a plain
`subprocess.run`, `capture_output=True`, assert `returncode == 0` with
the captured stdout/stderr folded into the assertion message so a
failure is diagnosable from pytest output alone, no re-running by hand
required.

Run with::

    uv run pytest tests/host/test_typescript_typecheck.py
"""

import pathlib
import subprocess

import pytest

# tests/host/test_typescript_typecheck.py -> host -> tests -> repo root
_REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
_TSC = _REPO_ROOT / "node_modules" / ".bin" / "tsc"
_TSCONFIG = _REPO_ROOT / "tsconfig.json"


def test_tsc_noemit_is_clean():
    """`tsc --noEmit -p tsconfig.json` must exit 0. A failure here means
    either a real type error was introduced in `src/blocks/*.ts` or
    `test/*.ts` (fix it, the same way a compiler error anywhere else
    would be fixed), or `tsconfig.json`'s `files` list has drifted from
    what those files actually need (see its own header comment for the
    two known-tricky classes of gap this project has already hit:
    missing `pxt_modules/core` manifest entries, and globals PXT's
    device-only ambient set doesn't declare)."""
    if not _TSC.is_file():
        pytest.skip(
            f"{_TSC} does not exist -- run `npm ci` (or `npm install`) "
            f"to install the pinned `typescript` devDependency, then "
            f"re-run. This test deliberately does not fall back to "
            f"`npx tsc`: with no local install, `npx tsc` in this "
            f"environment resolves to an unrelated decoy package named "
            f"`tsc`, not real TypeScript, so falling back would report a "
            f"random failure from the wrong tool instead of this "
            f"message."
        )
    result = subprocess.run(
        [str(_TSC), "--noEmit", "-p", str(_TSCONFIG)],
        capture_output=True,
        text=True,
        cwd=_REPO_ROOT,
    )
    assert result.returncode == 0, (
        f"tsc --noEmit failed (exit {result.returncode}):\n"
        f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )


def test_missing_tsc_skips_rather_than_fails(monkeypatch, tmp_path):
    """A checkout with no `node_modules` must SKIP this gate, not fail
    it. An absent toolchain is an environment precondition, not a defect
    in this repo's TypeScript -- and reporting it as a red test teaches
    the next person working in a fresh worktree that a red suite is
    normal, which is the state in which a real failure stops being
    visible.

    Verified by pointing the module's `_TSC` at a path that does not
    exist rather than by moving the real `node_modules`: the real tree
    is what `test_tsc_noemit_is_clean` above and the `pxt` build both
    depend on, and a test that relocates it would break every other
    consumer for the duration of its own run."""
    monkeypatch.setitem(
        globals(), "_TSC", tmp_path / "node_modules" / ".bin" / "tsc")
    with pytest.raises(pytest.skip.Exception) as excinfo:
        test_tsc_noemit_is_clean()
    reason = str(excinfo.value)
    assert "npm" in reason, (
        f"the skip reason must name the fix (`npm ci`/`npm install`); "
        f"got: {reason}"
    )
    assert "npx" in reason, (
        f"the skip reason must keep the no-`npx`-fallback reasoning "
        f"(the decoy `tsc` package this environment resolves); "
        f"got: {reason}"
    )
