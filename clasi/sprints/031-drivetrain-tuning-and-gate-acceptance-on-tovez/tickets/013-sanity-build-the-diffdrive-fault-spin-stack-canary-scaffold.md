---
id: '013'
title: Sanity-build the DIFFDRIVE_FAULT_SPIN stack-canary scaffold
status: open
use-cases: [SUC-008]
depends-on: ['008']
github-issue: ''
issue: sprint-030-hardware-acceptance-needs-one-bench-session.md
completes_issue: true
---
<!-- CLASI: Before changing code or making plans, review the SE process in CLAUDE.md -->

# Sanity-build the DIFFDRIVE_FAULT_SPIN stack-canary scaffold

**Type: (b) desk work — programmer/team-lead build step. No hardware.**

## Description

Sprint 030 ticket 005 Part B's `paintStackCanary()` scaffold (compiles
to `{}` in any build without `DIFFDRIVE_FAULT_SPIN`) was
**source-reviewed only** — no ARM toolchain build was ever attempted
(`sprint-030-hardware-acceptance-needs-one-bench-session.md` item 4).
Before flashing it to real hardware (ticket 014), sanity-build it: a
consolidated-build variant (ticket 008's source) with
`DIFFDRIVE_FAULT_SPIN` enabled, confirmed to compile and produce a
distinct hex artifact.

This build is NEVER the one tuning measurements (Session B's gain/
twist-hold work, Session C's gate rerun) are taken against — see this
sprint's Migration Concerns. Keep the two hex artifacts (plain
consolidated vs. canary-enabled) clearly distinguished by filename.

## Acceptance Criteria

- [ ] The `DIFFDRIVE_FAULT_SPIN` build compiles cleanly against
      ticket 008's consolidated source.
- [ ] The canary-enabled hex is distinctly named/tagged from the plain
      consolidated hex, so ticket 014 cannot accidentally flash the
      wrong one for the wrong step.
- [ ] Closing note states this is a build-only verification — no
      hardware behavior is claimed until ticket 014 runs it.

## Testing

- **Existing tests to run**: `uv run pytest tests/host/` against the
  `DIFFDRIVE_FAULT_SPIN` build path if the host harness can exercise
  the flag (a syntax-gate-style check per `tests/host/DESIGN.md`'s
  convention for other `_syntax_check.cpp` scaffolds).
- **New tests to write**: a syntax/compile check for the
  `DIFFDRIVE_FAULT_SPIN` path if one doesn't already exist, following
  the existing `*_syntax_check.cpp` pattern in `tests/host/`.
- **Verification command**: `uv run pytest tests/host/`
