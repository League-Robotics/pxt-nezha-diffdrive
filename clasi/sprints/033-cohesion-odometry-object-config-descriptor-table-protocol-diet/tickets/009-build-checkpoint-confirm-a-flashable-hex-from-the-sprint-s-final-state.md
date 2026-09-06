---
id: 009
title: 'Build checkpoint: confirm a flashable hex from the sprint''s final state'
status: in-progress
use-cases: []
depends-on:
- '001'
- '002'
- '003'
- '004'
- '005'
- '006'
- '007'
- 008
github-issue: ''
issue: ''
completes_issue: true
---
<!-- CLASI: Before changing code or making plans, review the SE process in CLAUDE.md -->

# Build checkpoint: confirm a flashable hex from the sprint's final state

## Description

Per `src/DESIGN.md` §11's standing convention (established sprint 008):
every sprint that touches build-eligible source ends with a mandatory,
always-last build-checkpoint ticket, because the host test suite
compiles this project's portable C++ at `-std=c++20` while both real
embedded targets compile at `-std=c++11` — a green host suite is not
evidence a change actually compiles for the robot (a struct with
default member initializers is the confirmed historical instance of
this gap). This sprint touches `src/shims.cpp`, `src/motion/`,
`src/platform/`, `src/comms/`, and `src/blocks/motion.ts` across
tickets 001-008 — squarely build-eligible source.

Run `tools/make_deploy.py` (triage-aware: it distinguishes a real
`.cpp` compile failure from the two documented benign abort shapes —
the legacy V1 hex-merge failure and the nondeterministic
`TS9283`/`TS9043`/`TS9200` packaging abort — and retries the latter
once automatically) against the sprint's own final state (after ticket
008 lands) and confirm a flashable hex results. This is a **desk
build**, not a bench/flash/drive session — this sprint is pure-software
and this ticket does not fly the robot. If the build fails for a real
(non-benign) reason, that is this ticket's finding to report, not
something to route around.

Also confirm, as part of this same checkpoint: `ConfigField`'s
generator (ticket 003) has actually been run and its output matches
the checked-in TS file (the drift test is necessary but this is the
one point in the sprint where a human/agent should also eyeball the
generated diff before it ships); and that `tests/host/` passes in full
(the standing full-suite run `close_sprint` itself will also perform —
running it here catches a failure before that gate rather than at it).

## Acceptance Criteria

- [ ] `tools/make_deploy.py` produces a flashable hex from the sprint's
      final state (after ticket 008).
- [ ] Any build abort is triaged as benign (retried once, per
      `make_deploy.py`'s own logic) or reported as a real defect — not
      silently ignored.
- [ ] `ConfigField`'s generated output (ticket 003) matches the
      checked-in TS file at this final state.
- [ ] The full `tests/host/` suite passes.
- [ ] No hardware acceptance is claimed by this ticket — it is a desk
      build/test checkpoint only.

## Testing

- **Existing tests to run**: full `tests/host/` suite (all tickets'
  additions included); `tests/host/test_no_units_in_identifiers_source_pin.py`
  (must be clean of the `wifi_link` exclusion, ticket 008).
- **New tests to write**: none — this ticket verifies, it does not add
  coverage.
- **Verification command**: `uv run pytest tests/host/ && uv run python tools/make_deploy.py`
