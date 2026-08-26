---
id: '002'
title: 'Boot banner in test.ts: skate icon then day.revision, via the same injection
  seam'
status: open
use-cases: []
depends-on:
- '001'
github-issue: ''
issue: no-boot-banner-so-a-flash-cannot-be-confirmed.md
completes_issue: true
---
<!-- CLASI: Before changing code or making plans, review the SE process in CLAUDE.md -->

# Boot banner in test.ts: skate icon then day.revision, via the same injection seam

## Description

`test/test.ts` shows nothing at startup, so a fresh flash and a months-old
build are indistinguishable until something is commanded and the response is
reasoned about backwards. This ticket adds a boot banner: on boot, show
`IconNames.Rollerskate` (the micro:bit's skate icon), then scroll a short
version string.

**Deliberately in `test/test.ts`, NOT in `src/blocks/`.** `src/blocks/` is
the student-facing extension; a boot banner there would hijack the display
of every student program that imports it. The bench robots run `test.ts`,
which is what actually gets flashed for bench work, so that is where a
flash-verification banner belongs. This ticket must not touch anything under
`src/blocks/`.

**Version string format** — this is one of two flagged interpretations from
the stakeholder-approval gate (`get_sprint_phase("022")`), recorded here so
implementation does not silently drift from it: derived from this repo's own
`0.YYYYMMDD.n` version (e.g. `pyproject.toml`), **not** `pxt.json`'s
`1.0.10`-style version — `pxt.json`'s scheme has no day-of-month digit pair
in its minor, so it does not fit "day of month, dot, revision." Render as the
last two digits of the minor (the day of the month) then a dot then the
revision zero-padded to two digits. `0.20260826.5` renders **`26.05`**.

`test.ts` cannot read `pyproject.toml` at build time — TypeScript compiled by
MakeCode has no filesystem access to the Python project's version file. The
version string must therefore be injected by the same build-time seam ticket
001 adds to `make_deploy.py` (reading robot config and writing into the
scratch copy in `.tmp/deploy-head` before build). Do not invent a second
injection mechanism — extend the one ticket 001 built.

Showing the robot name alongside the version is worth doing if it is cheap
in the same injection pass, since ticket 001 makes builds per-robot anyway
and "which robot is this hex for" becomes a real question on the bench.

## Acceptance Criteria

- [ ] On boot, the robot displays `IconNames.Rollerskate` followed by a
      scrolled version string.
- [ ] The version string format is `DD.RR` where `DD` is the last two digits
      of this repo's `0.YYYYMMDD.n` minor version (day of month) and `RR` is
      the revision zero-padded to two digits — e.g. `0.20260826.5` → `26.05`.
      It is derived from this repo's own version source, not `pxt.json`'s
      version.
- [ ] The version string is injected into `test/test.ts` (or a file it
      includes) by the same `make_deploy.py` build-time seam ticket 001
      introduced — not read from a second, independently-invented mechanism.
- [ ] No file under `src/blocks/` is modified by this ticket, and no boot
      display code is added there.
- [ ] If cheap within the same injection pass, the robot name is also shown;
      if it turns out not to be cheap, it is acceptable to omit it and say
      so in the ticket's closing notes rather than force it.
- [ ] Any new `src/` (or `test/`, if MakeCode's manifest requires it) file
      is present in `pxt.json`'s `files` array, verified by
      `tests/host/test_pxt_manifest_completeness.py`.

## Implementation Plan

**Approach**: In `test/test.ts`'s startup path, call the skate-icon display
followed by a scroll of the injected version string. Extend ticket 001's
`make_deploy.py` injection point so it also writes the version (and
optionally robot name) into the scratch copy at `.tmp/deploy-head` before
build — the same substitution/generated-value mechanism ticket 001 chose for
the radio channel, reused rather than duplicated.

**Files likely to change**:
- `test/test.ts` — add the boot display call (icon, then scroll version).
- `tools/make_deploy.py` — extend the existing per-robot injection point
  (added in ticket 001) to also compute and inject the version string from
  this repo's `0.YYYYMMDD.n` version source.
- `pxt.json` — only if a new file is introduced.

**Testing plan**: No TypeScript in this repo is executed by any test, so
there is no way to honestly unit-test the banner's on-device behavior. Say
this plainly rather than writing a vacuous test. What can and should be
verified mechanically:
- A build-checkpoint test (or extension of ticket 001's build test) that
  asserts the injected version string is present and correctly formatted in
  the scratch copy for a given repo version.
- A text-level pin that the banner call (`IconNames.Rollerskate` followed by
  a scroll of the version) exists in `test/test.ts`, following the pattern
  `tests/host/test_run_abort_source_pin.py` already uses for source-level
  assertions — not a claim that the display was observed.
- Genuine verification (does it actually show correctly on hardware) is
  deferred to ticket 003's bench flash-and-read checkpoint.

**Documentation updates**: None expected beyond what sprint 022's
Architecture section already records, unless the injection mechanism's shape
changes from what ticket 001 established, in which case note the delta
there.
