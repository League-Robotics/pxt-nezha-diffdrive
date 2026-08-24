# tests/tools — unit tests for the repo's own Python tooling

**Owner:** Eric Busboom · **Last reviewed:** 2026-08-24 · **Status:** stable

---

## 1. Purpose

Plain-Python unit tests over the logic inside this repo's own `tools/`
scripts — no compiler, no subprocess, no network. The seam that
separates this directory from its sibling
[`tests/host/`](../host/DESIGN.md): `tests/host/` compiles the
extension's portable firmware C++ for the desktop and drives it
through `ctypes` shims; this directory calls plain Python functions
directly, in-process, with `monkeypatch` standing in for anything that
would otherwise shell out or touch the network. Different toolchain,
different fixtures, different failure modes — one shared harness would
fit neither well.

One file so far: `test_make_deploy_triage.py`, pinning
`tools/make_deploy.py`'s build-checkpoint triage (added sprint 008,
ticket 006) — the logic that decides whether a real `pxt build`
attempt succeeded, hard-failed, or hit a known-benign abort worth
retrying. This subsystem exists because that triage is sprint 008's
own "tests that can fail" theme applied to the tool doing the
checking: three real target-only defects — `Wire::Column`'s C++11
non-aggregate-under-NSDMI break, `setRxBufferSize`'s `uint8_t`
truncation, and three headers missing from `pxt.json`'s `files`
manifest — escaped a fully green host suite across sprints 004-007,
each one caught only because some ticket happened to need real build
evidence. The triage is now the standing mechanism that catches that
class; this file is what makes it fail loudly, instead of silently, if
someone breaks it later. Nothing under `tools/` knows this directory
exists.

## 2. Orientation

Two parts, one file:

- **Fixtures** — module-level string constants holding synthetic and
  saved `pxt build` log text, one per triage outcome: a clean success;
  a real GCC-style compile diagnostic (mirroring the `Wire::Column`
  defect that motivated this triage); a `pxt.json` manifest-omission
  diagnostic (same file:line shape, no separate code path); the legacy
  V1 hex-merge failure; the three observed packaging-abort codes; and
  an unrecognized failure matching none of the above.
- **Tests** — `classify_attempt()` is a pure function, so most tests
  call it directly against a fixture and assert the returned
  `(verdict, reason)`. Three more drive `build()` itself through
  `monkeypatch`, replacing `make_deploy._run_pxt_build` and
  `os.path.exists`/`getsize` so the retry-then-report wiring runs with
  no real subprocess or filesystem state involved.

Run: `uv run pytest tests/tools/test_make_deploy_triage.py`, or as
part of the whole suite (`uv run pytest` from the repo root).

## 3. Constraints and Invariants

- **A real compile diagnostic wins, unconditionally.**
  `classify_attempt()` checks for a genuine GCC/Clang diagnostic
  (`file.(cpp|cc|cxx|h|hpp):line:[col:] error|fatal error:`) *before*
  it ever looks at `hex_exists` — a hex produced by one build variant
  must never excuse a compile error surfaced by another.
  `test_compile_error_wins_even_if_a_hex_exists` pins this ordering
  explicitly, not just the individual outcomes.
- **Retry is bounded, not infinite.** A `BENIGN` verdict is retried
  exactly once; a `BENIGN` recurrence on that retry is promoted to
  `HARD_FAILURE` rather than retried again.
- **`UNKNOWN` is fail-closed and never retried — a known, stated
  limitation, not an oversight.** Output matching none of the
  documented shapes (no hex, no compile diagnostic, neither benign
  pattern) is reported as a failure immediately. This means a
  genuinely benign abort shape that has not been observed and
  documented yet is indistinguishable, by this logic, from a real
  defect, and gets reported as one — a false alarm, not a false pass.
  The alternative (retry anything unrecognized) risks silently
  retrying past an actual failure, which is the one thing this triage
  exists to stop. See [`tools/DESIGN.md`](../../tools/DESIGN.md)'s
  "Build checkpoint triage" section for the full decision table this
  file pins.
- **No real toolchain, no network, anywhere in this file.** `build()`'s
  tests replace every collaborator that would otherwise shell out or
  touch disk state. A future test that needs a real `pxt build` does
  not belong in this file.

## 4. Design

`test_make_deploy_triage.py` is not a package member of `tools/` — it
inserts `tools/` onto `sys.path` at import time (`tools/` has no
`__init__.py` and is not installed as a package) and then
`import make_deploy` directly. `classify_attempt()` tests call the
function against fixture text with no indirection. `build()` tests use
`monkeypatch` to replace `make_deploy._run_pxt_build` (returns fixture
text instead of running `pxt build`) and
`make_deploy.os.path.exists`/`getsize` (reports hex presence and size
keyed to a fake per-call attempt counter, instead of touching the real
filesystem) — the same caller-driven-fake pattern `tests/host/`'s
fakes use for the firmware's ports, applied at Python function-call
granularity instead of a C++ vtable.

## 5. Interfaces

### Exposes
- **`uv run pytest tests/tools/test_make_deploy_triage.py`** — this
  file alone.
- Also runs as part of **`uv run pytest`** from the repo root, and the
  once-per-sprint gate `close_sprint` runs.

### Consumes
- **`tools/make_deploy.py`**'s `classify_attempt()` and `build()` —
  see [`tools/DESIGN.md`](../../tools/DESIGN.md)'s "Build checkpoint
  triage" section for the contract this file pins.

## 6. Coverage — what is and is not tested here

Covered: all four `classify_attempt()` verdicts (`SUCCESS`,
`HARD_FAILURE`, `BENIGN`, `UNKNOWN`) across seven fixture shapes,
including the compile-error-wins-over-hex-existence ordering and the
manifest-omission-caught-via-the-same-path case; `build()`'s
retry-then-succeed path, its bounded-retry failure path (the benign
shape recurring on retry), and its no-retry-on-hard-failure path.

Not covered, by design: `sync()` (manifest promotion/rewrite),
`flash()` (the `mbdeploy` subprocess), and `main()` — none of them are
part of the triage this file exists to pin, and none can be exercised
without either a real `pxt.json`/filesystem or a real subprocess,
which this subsystem's whole purpose is to avoid needing. A real build
against a sprint's own combined final state is verified manually and
recorded in `tools/DESIGN.md`'s "Build checkpoint triage" section, not
exercised here.
