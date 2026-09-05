---
id: '013'
title: Sanity-build the DIFFDRIVE_FAULT_SPIN stack-canary scaffold
status: done
use-cases:
- SUC-008
depends-on:
- 008
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

- [x] The `DIFFDRIVE_FAULT_SPIN` build compiles cleanly against
      ticket 008's consolidated source.
- [x] The canary-enabled hex is distinctly named/tagged from the plain
      consolidated hex, so ticket 014 cannot accidentally flash the
      wrong one for the wrong step.
- [x] Closing note states this is a build-only verification — no
      hardware behavior is claimed until ticket 014 runs it.

## Closing Note

This ticket was executed under a CLASI OOP bypass; this note reconciles
the ticket record with work already committed on this branch.

- The `DIFFDRIVE_FAULT_SPIN` build compiles cleanly against ticket
  008's consolidated source — the first time this scaffold has ever
  been through the ARM toolchain (sprint 030 only source-reviewed it).
  Both `#ifdef` branches compile: `protocol.cpp`'s `paintStackCanary()`
  and `nezha_port.cpp`'s `diffdriveFaultReport()` spin. All 14
  nezha-diffdrive translation units built.
- The hex is distinct from the plain build and cannot be confused with
  it: `captures/session-b-20260905/tovez-1.20260904.5-faultspin.hex`
  (1,721,694 bytes, sha256
  bddf51bb1c02279beef6412690380846059128158f0b9a9b31963b7874ba0a66)
  versus the plain
  `captures/session-b-20260905/tovez-1.20260904.5-plain.hex`
  (1,721,681 bytes, sha256
  7985c551e8d202e7eeb7cff855f5a98f7b74bb026b573ccdd3217b302f25ea29).
  It also self-identifies on the wire: `kProfile` is baked as
  `tovez-faultspin`, so `ID` distinguishes the two builds.
- This is a BUILD-ONLY verification. No hardware behaviour is claimed;
  ticket 014 runs it.
- Implementation: `tools/make_deploy.py` gained `--fault-spin`, which
  builds in its own scratch copy (`.tmp/deploy-faultspin`) and injects
  `#define DIFFDRIVE_FAULT_SPIN 1` ahead of the includes in the two
  translation units that carry a branch, refusing loudly if a file has
  no branch, already defines it, or is missing. `_inject_profile()`
  gained an optional suffix. Pinned by 19 tests in
  `tests/tools/test_make_deploy_fault_spin.py`. Full suite was 1270
  passed at the time. Commit cd8eb61.

Note `captures/` is gitignored; the paths above are committed and
readable via `git show`.

## Testing

- **Existing tests to run**: `uv run pytest tests/host/` against the
  `DIFFDRIVE_FAULT_SPIN` build path if the host harness can exercise
  the flag (a syntax-gate-style check per `tests/host/DESIGN.md`'s
  convention for other `_syntax_check.cpp` scaffolds).
- **New tests to write**: a syntax/compile check for the
  `DIFFDRIVE_FAULT_SPIN` path if one doesn't already exist, following
  the existing `*_syntax_check.cpp` pattern in `tests/host/`.
- **Verification command**: `uv run pytest tests/host/`
