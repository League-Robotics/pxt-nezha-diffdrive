# tests/tools — unit tests for the repo's own Python tooling

**Owner:** Eric Busboom · **Last reviewed:** 2026-08-24 · **Status:** stable (sprint 005 adds `test_tlm.py` pinning `tools/tlm.py`'s telemetry parser, `test_camproc.py`/`test_field.py` pinning ticket 003's link-layer consolidation, and `test_run_verbs.py` pinning ticket 006's RUN-string retargeting)

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

Five files: `test_make_deploy_triage.py`, pinning
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
someone breaks it later.

`test_tlm.py` (sprint 005 ticket 001) applies the same "tests that can
fail" theme to `tools/tlm.py`'s `TlmStream` telemetry parser and its
three fail-loud guards (`require_stream()`, `write_tlm_csv()`, the
`.meta.json` zero-frame refusal) — the parser this sprint introduced
specifically to replace six tools' worth of scattered, silently-broken
arity logic (`tour_watch.py:202`, `tour_capture.py:70`), so it is
pinned here from day one rather than left to drift the same way.
`test_camproc.py`/`test_field.py` (sprint 005 ticket 003) pin
`tools/camproc.py`'s interpreter-resolution/`ERR`-surfacing/stale-pose-
invalidation contract and `tools/field.py`'s playfield geometry
(`wrap()`, the gap-aware `score_corners()`, `path_deviation()`)
against a `Cam(_spawn=False)` double — the consolidation that replaced
seven copied `Cam`/`CamStream`/`CamProc` scaffolds and four
*disagreeing* corner-scoring implementations with one of each.
`test_run_verbs.py` (sprint 005 ticket 006) pins the exact RUN string
five bench tools (`otos_levercal.py`, `pivot_truth.py`,
`truth_check.py`, `rotation_check.py`, `turn_sweep.py`) send against a
fake link, proving each now matches a real `test.ts`/`testrig.ts`
handler instead of a dead numeric offset. All five files import the
module under test directly, in-process; nothing under `tools/` knows
this directory exists.

## 2. Orientation

### `test_make_deploy_triage.py`

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

### `test_tlm.py` (sprint 005)

Imports `tools/tlm.py`'s `TlmStream` directly (same `sys.path`-insert
convention as `test_make_deploy_triage.py`) and feeds it synthetic and
captured `thdr`/`t` lines, no serial/radio link involved:

- **Header tracking** — a `thdr` sets the current column set; an
  identical re-read is a no-op; a second `thdr` after 20 frames with an
  unchanged column set is still accepted (the firmware's 1 Hz memo
  re-emit, not an error); a `t` before any `thdr` counts into
  `orphan_frames` and is not added to `frames`.
- **`seq`-gap loss** — consecutive `seq` values with a gap increment
  `dropped`/`loss_pct` by the right amount; a 7-bit wraparound
  (127 → 0) is not miscounted as a gap.
- **Arity/malformed rejection** — a `t` line whose value count disagrees
  with the last `thdr`'s column count counts into `malformed`, is not
  added to `frames`, and does not raise (fail-loud is `require_stream`/
  `write_tlm_csv`'s job, not a parse-time exception here).
- **Unit helpers** — `pose_cm`/`otos_cm`/`wheels_mms` against the
  shared golden frame in
  [`tests/host/golden_telemetry.py`](../host/golden_telemetry.py) (the
  same fixture `tests/host/test_wire_telemetry_projection.py` uses as
  expected *emitted* wire bytes, imported here as parser *input*, so
  emitter and parser are pinned against one shared source of truth and
  cannot silently drift apart from each other).
- **Fail-loud guards** — `require_stream()` raises before any
  run-triggering `send()` is observed on a fake link when no `t` frame
  arrives inside its timeout, and returns normally once one does;
  `write_tlm_csv()` raises on zero accumulated frames and leaves no
  file on disk, and writes normally (with a matching `.meta.json`
  sidecar) otherwise.

Run: `uv run pytest tests/tools/test_tlm.py`, or as part of the whole
suite.

### `test_camproc.py` (sprint 005 ticket 003)

Imports `tools/camproc.py` directly (same `sys.path`-insert convention)
and drives its `Cam` class through a `_spawn=False` constructor
argument, so no real camera subprocess, thread, or interpreter is ever
started:

- **`resolve_venv()`** — `APRILTAGS_VENV` set overrides the default;
  unset, falls back to the historically-correct hardcoded path.
- **`ERR` surfacing** — an `ERR` line fed to the double reaches the
  calling tool (via a callback/attribute the double lets the test
  inspect) instead of being discarded the way the old `stderr=DEVNULL`
  scaffolds did.
- **Stale-pose invalidation** — once the stream is marked dead,
  `.latest`/`.fix()` both return `None` rather than a frozen pre-death
  value, even if a pose was cached moments before.

Run: `uv run pytest tests/tools/test_camproc.py`, or as part of the
whole suite.

### `test_field.py` (sprint 005 ticket 003)

Imports `tools/field.py` directly:

- **`wrap()`** — parametrized angle-wrap cases into `(-180, 180]`.
- **`score_corners()`** — the gap-aware forward-only scan, including
  the exact disagreement `tour_run.py`'s console and
  `practice_chart.py`'s chart used to produce for the same recorded run
  (one corner scored from a nearby-but-gap-blind sample, the other
  correctly reported unobserved) — this file proves the shared
  implementation reproduces the *correct* outcome for both halves of
  that disagreement, not just that it runs without raising.
- **`path_deviation()`** — the PY-08 degenerate-zero-length-segment
  divide guard.

Run: `uv run pytest tests/tools/test_field.py`, or as part of the
whole suite.

### `test_run_verbs.py` (sprint 005 ticket 006)

No `tools/`-internal module is imported here beyond each tool's own
script; each test monkeypatches the tool's `Link`/`send`/`send_until`
call with a fake that records the exact string sent, then asserts it
against `test.ts`'s/`testrig.ts`'s real named-verb vocabulary and
asserts none of the old dead numeric forms (`RUN:8`, `RUN:14`,
`RUN:10`, `RUN:2`, `RUN:4`, `RUN:5`, `RUN:{57000+rate}`,
`RUN:{58360+deg}`) appear anywhere in what was sent — a regression back
to the numeric vocabulary fails loudly instead of silently. Covers
`otos_levercal.py` (`RUN:cal`/`RUN:cal:1`), `pivot_truth.py`/
`truth_check.py`/`rotation_check.py` (`RUN:fix`, `RUN:pivot:<deg>`),
and `turn_sweep.py` (`RUN:turnrate:<rate>` then `RUN:pivot:<deg>`).
Cannot prove the robot moves — no serial port, no robot — only that
each tool's own RUN-sending code path targets a real handler.

Run: `uv run pytest tests/tools/test_run_verbs.py`, or as part of the
whole suite.

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
- **`test_tlm.py`: an absent CSV is unambiguous; an empty one is not
  — never assert the opposite.** Every fail-loud-guard test asserts
  *both* halves of that: the raising path leaves no file on disk, and
  the non-raising path's file/sidecar actually matches the fed data.
  Asserting only "it raised" without also checking "and wrote nothing"
  would leave the guard's whole reason for existing unverified.
- **`test_tlm.py`: parser input is the emitter's own expected-output
  fixture, not a hand-rolled one.** `tests/host/golden_telemetry.py`'s
  `EXPECTED_T_LINE`/`EXPECTED_THDR_LINE` (what `WireHandler` is proven
  to emit) are fed to `TlmStream` as-is; a test that instead
  hand-wrote its own "plausible" `t` line could pass while silently
  disagreeing with what the firmware actually sends.
- **`test_camproc.py`/`test_field.py`: no real subprocess, camera, or
  thread, ever.** `Cam(_spawn=False)` is the one seam these tests use
  to exercise interpreter resolution, `ERR` surfacing, and pose
  invalidation without ever starting the real AprilTags process this
  class normally spawns.
- **`test_run_verbs.py`: asserts both the positive and the negative.**
  Every test checks the exact string sent AND that none of the old
  dead numeric forms appear in it — asserting only the positive half
  would leave a tool that sends both the new named verb and a leftover
  numeric one (a merge artifact, not a hypothetical) passing.

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
- **`uv run pytest tests/tools/test_tlm.py`** (sprint 005) — this file
  alone.
- **`uv run pytest tests/tools/test_camproc.py`**,
  **`tests/tools/test_field.py`** (sprint 005 ticket 003) — each file
  alone.
- **`uv run pytest tests/tools/test_run_verbs.py`** (sprint 005 ticket
  006) — this file alone.
- All also run as part of **`uv run pytest`** from the repo root, and
  the once-per-sprint gate `close_sprint` runs.

### Consumes
- **`tools/make_deploy.py`**'s `classify_attempt()` and `build()` —
  see [`tools/DESIGN.md`](../../tools/DESIGN.md)'s "Build checkpoint
  triage" section for the contract this file pins.
- **`tools/tlm.py`**'s `TlmStream`, `require_stream()`,
  `write_tlm_csv()`, and the unit-conversion helpers (sprint 005) —
  see [`tools/DESIGN.md`](../../tools/DESIGN.md)'s "Telemetry
  (`tlm.py`)" section.
- **`tests/host/golden_telemetry.py`**'s expected wire-frame constants,
  as parser input (sprint 005) — the same fixture
  `tests/host/test_wire_telemetry_projection.py` uses as expected
  emitted bytes, so `test_tlm.py` cannot silently drift from what the
  firmware actually sends.
- **`tools/camproc.py`**'s `Cam`/`resolve_venv()` and **`tools/field.py`**'s
  `wrap()`/`score_corners()`/`path_deviation()` (sprint 005 ticket 003)
  — see [`tools/DESIGN.md`](../../tools/DESIGN.md)'s "Link layer" section.
- **`otos_levercal.py`**, **`pivot_truth.py`**, **`truth_check.py`**,
  **`rotation_check.py`**, **`turn_sweep.py`**'s own RUN-sending code
  paths (sprint 005 ticket 006), each monkeypatched at its `Link`/
  `send`/`send_until` call.

## 6. Coverage — what is and is not tested here

Covered: all four `classify_attempt()` verdicts (`SUCCESS`,
`HARD_FAILURE`, `BENIGN`, `UNKNOWN`) across seven fixture shapes,
including the compile-error-wins-over-hex-existence ordering and the
manifest-omission-caught-via-the-same-path case; `build()`'s
retry-then-succeed path, its bounded-retry failure path (the benign
shape recurring on retry), and its no-retry-on-hard-failure path.
`TlmStream`'s header tracking (fresh, no-op re-read, 20-frame memo
re-emit), `seq`-gap loss counting and 7-bit wraparound, arity/malformed
rejection, orphan-frame counting, the unit-conversion helpers against
the shared golden frame, and both fail-loud guards' raising and
non-raising paths. `camproc.py`'s `resolve_venv()` env-var override/
default, `ERR` surfacing, and stale-pose invalidation against a
`Cam(_spawn=False)` double. `field.py`'s `wrap()`, `score_corners()`'s
gap-aware scan (including the historical console-vs-chart
disagreement), and `path_deviation()`'s degenerate-segment guard. The
exact RUN string each of the five retargeted tools sends, and the
absence of every old dead numeric form, for both the fix/pivot/
turnrate path and the `cal`/`cal:1` rename.

Not covered, by design: `sync()` (manifest promotion/rewrite),
`flash()` (the `mbdeploy` subprocess), and `main()` — none of them are
part of the triage this file exists to pin, and none can be exercised
without either a real `pxt.json`/filesystem or a real subprocess,
which this subsystem's whole purpose is to avoid needing. A real build
against a sprint's own combined final state is verified manually and
recorded in `tools/DESIGN.md`'s "Build checkpoint triage" section, not
exercised here. For `test_tlm.py`: a live radio link's actual loss
behavior is not exercised here either — that is the sprint's
real-hardware end-to-end check (`tour_run.py --tour world` against a
real robot), not a unit test; this file only pins the parsing/guard
*logic* against synthetic and captured-but-replayed frames. For
`test_camproc.py`/`test_field.py`/`test_run_verbs.py`: none of them
exercise a real camera daemon, a real robot, or a real radio link
either — that is this sprint's own bench handoff checklist (ticket
007), not a unit test.
