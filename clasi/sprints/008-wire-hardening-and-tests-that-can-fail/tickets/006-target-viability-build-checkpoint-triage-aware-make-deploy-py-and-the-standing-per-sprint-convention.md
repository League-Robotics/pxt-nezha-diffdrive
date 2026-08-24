---
id: '006'
title: 'Target-viability build checkpoint: triage-aware make_deploy.py and the standing
  per-sprint convention'
status: open
use-cases:
- SUC-006
depends-on:
- '001'
- '002'
- '003'
- '004'
- '005'
github-issue: ''
issue: host-tests-compile-newer-standard-than-target.md
completes_issue: true
---
<!-- CLASI: Before changing code or making plans, review the SE process in CLAUDE.md -->

# Target-viability build checkpoint: triage-aware make_deploy.py and the standing per-sprint convention

## Description

Three independent defect classes have escaped the host suite because
nothing in the per-ticket or per-sprint flow requires a real target
build (`host-tests-compile-newer-standard-than-target.md`, this
sprint's centerpiece issue, filed after sprint 004 ticket 005 could not
produce a flashable hex against a fully green 253-test suite):

1. A non-aggregate struct under C++11 (`Wire::Column`'s NSDMIs, sprint
   004 ticket 005) — since closed by `test_cxx11_syntax_gate.py`.
2. `setRxBufferSize(uint8_t)` silently truncating 480→224
   (`-Woverflow`, the same build) — **not** caught by the syntax gate,
   which needs the real toolchain's headers/warnings.
3. Three headers absent from `pxt.json`'s `files` manifest, blocking
   every hex build entirely (sprint 006, found by sprint 007 ticket 001)
   — since closed by `test_pxt_manifest_completeness.py`, but the class
   it represents (silent build-eligibility gaps the host suite cannot
   see) is not fully closed by that one narrow check.

**This sprint's decision** (see `sprint.md`'s Architecture section and
`design/DESIGN.md` §11/§14 in the overlay for the full reasoning): do
not attempt a hard automated gate in `close_sprint` (CLASI-server code
outside this project's own repository — no ticket here can implement
that, and the two known-benign failure modes below make a naive
pass/fail gate unreliable). Instead, formalize what sprints 004 and 007
already did by accident: **every sprint that touches build-eligible
source includes a mandatory, always-last build-checkpoint ticket** —
this one, for sprint 008. This ticket both performs that checkpoint AND
gives `tools/make_deploy.py` the triage logic that was missing, so
future checkpoint tickets do not require a human to read raw compiler
output to tell a real failure from a benign one.

**Known-benign failure modes this ticket's triage must tolerate**
(retry once, do not report as a failure):
- The legacy V1 `bbc-microbit-classic-gcc` target's hex-merge failure.
- The nondeterministic packaging abort, surfaced as `TS9283`, `TS9043`,
  or `TS9200`, always after a pxt-core cache-write `TypeError`, always
  succeeding on retry (`tools/make_deploy.py`'s own module docstring
  already documents the `TS9283` instance and the up-front hex-removal
  trick that keeps a failed package from looking like a stale-but-good
  build).

**Triage principle** (from the issue): distinguish these from a genuine
failure by asking **"did any `.cpp` fail to compile"** — not by
matching a specific error code, since the packaging-abort codes vary
(`TS9283`/`TS9043`/`TS9200`) and are not the defect signal themselves.

## Acceptance Criteria

- [ ] `tools/make_deploy.py`'s `build()` captures `pxt build`'s
      output and classifies the result: a genuine `.cpp`/`.h` compile
      error (a real GCC/Clang diagnostic naming a source file and a
      line) is a hard failure, reported plainly; the two documented
      benign abort shapes above are retried once automatically before
      being reported as anything.
- [ ] After one retry, if the benign-abort shape recurs and still
      produces no hex, that IS reported as a failure (the retry is
      bounded, not infinite) — the two shapes are expected to be
      transient, not chronic.
- [ ] Reintroducing a known C++14-only construct into `src/` (e.g. a
      struct with a default member initializer used in aggregate-init
      context, mirroring the original `Wire::Column` defect) into a
      scratch copy is confirmed to make the triage report a hard
      failure, not silently pass via the retry path. Do this as a
      throwaway local check during this ticket's execution (stash
      afterward — do not land a deliberately broken `src/` file).
- [ ] Reintroducing a `pxt.json` manifest omission (temporarily drop
      one `files` entry in a scratch copy) is confirmed to make the
      triage report a hard failure the same way.
- [ ] A real, non-scratch run of `tools/make_deploy.py` against this
      sprint's own final state (after tickets 001-005 land) produces a
      flashable hex, with no code change required beyond the documented
      automatic retry.
- [ ] `docs/design/design.md`'s "Host-vs-target language standard"
      section and `src/DESIGN.md` §11 (both already updated in this
      sprint's `design/` overlay — confirm the overlay content matches
      what actually shipped once this ticket's own `tools/make_deploy.py`
      changes are final) state the standing per-sprint
      build-checkpoint-ticket convention.
- [ ] `tools/DESIGN.md` (unprotected — edit directly, not through the
      overlay) documents the triage logic: what counts as a hard
      failure, what is retried, and why.
- [ ] No robot, no flashing, no live telemetry capture is performed or
      required by this ticket — producing a hex needs network access to
      the cloud compiler, not hardware. If `--flash` is exercised at
      the bench separately, that is a stakeholder action outside this
      ticket's own acceptance criteria, consistent with this sprint's
      "no ticket may require a robot" constraint.

## C++11 Gate Coverage

- **Inside the gate**: not applicable — this ticket makes no change to
  any file `test_cxx11_syntax_gate.py` covers.
- **Outside the gate**: this ticket's own subject IS the gap the C++11
  gate cannot close (`tools/make_deploy.py` triage logic and the real
  build itself operate entirely outside the host-test/gate system).
  This ticket is what proves — for this sprint's own final state —
  that `protocol.cpp`, `radio_transport.h`, `shims.cpp`'s settle-loop
  call site (ticket 004), and every other target-only change this
  sprint makes actually compile and link for both real embedded
  targets. It depends on tickets 001-005 specifically so it validates
  their combined final state, not each in isolation.

## Testing

- **Existing tests to run**: the full `uv run pytest` suite, as a
  precondition — this ticket's own real build run should follow a
  green host suite, not substitute for one.
- **New tests to write**: none in `tests/host/` (this ticket's own
  verification is the real build itself, plus the two throwaway
  scratch-copy triage checks in the Acceptance Criteria, which are
  demonstrations, not host tests — they exercise the real toolchain and
  are not meant to run under `pytest`).
- **Verification command**: `uv run pytest` (precondition), then
  `uv run python tools/make_deploy.py` (the checkpoint itself) — record
  the resulting hex's path/size in this ticket's own notes on
  completion.
