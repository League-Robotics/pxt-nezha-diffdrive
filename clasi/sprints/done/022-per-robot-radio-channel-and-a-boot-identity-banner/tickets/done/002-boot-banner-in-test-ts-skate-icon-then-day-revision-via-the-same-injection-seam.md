---
id: '002'
title: 'Boot banner in test.ts: skate icon then day.revision, via the same injection
  seam'
status: done
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

- [x] On boot, the robot displays `IconNames.Rollerskate` followed by a
      scrolled version string.
- [x] The version string format is `DD.RR` where `DD` is the last two digits
      of this repo's `0.YYYYMMDD.n` minor version (day of month) and `RR` is
      the revision zero-padded to two digits — e.g. `0.20260826.5` → `26.05`.
      It is derived from this repo's own version source, not `pxt.json`'s
      version.
- [x] The version string is injected into `test/test.ts` (or a file it
      includes) by the same `make_deploy.py` build-time seam ticket 001
      introduced — not read from a second, independently-invented mechanism.
- [x] No file under `src/blocks/` is modified by this ticket, and no boot
      display code is added there.
- [x] If cheap within the same injection pass, the robot name is also shown;
      if it turns out not to be cheap, it is acceptable to omit it and say
      so in the ticket's closing notes rather than force it. (It was cheap
      — see Notes below.)
- [x] Any new `src/` (or `test/`, if MakeCode's manifest requires it) file
      is present in `pxt.json`'s `files` array, verified by
      `tests/host/test_pxt_manifest_completeness.py`. (No new `src/` or
      `test/` file was introduced — see Notes below.)

## Notes (implementation report)

**Mechanism**: reused ticket 001's exact substitution mechanism, a
second pair of regex-matched placeholders
(`_BOOT_VERSION_RE`/`_BOOT_ROBOT_RE` in `tools/make_deploy.py`)
substituted into the scratch copy's `test/test.ts` by a new
`_inject_boot_banner(deploy_dir, robot)`, called from `main()`
immediately after `_inject_radio_channel()` — same seam, same
scratch-copy-only mutation, no new file. `format_boot_version()` is a
pure function (`0.YYYYMMDD.n` -> `DD.RR`); `_read_repo_version()` reads
`pyproject.toml`'s `version = "..."` line with a plain regex (no TOML
dependency for one field). Both are covered directly by
`tests/tools/test_make_deploy_boot_banner.py`, including the worked
example from this ticket's own brief (`0.20260826.5` -> `26.05`) and a
rejection test proving `pxt.json`'s `1.0.10`-shaped scheme does not
parse as a day-of-month.

**Robot name — cheap, included**: `BOOT_ROBOT` is substituted by the
same call, scrolled alongside the version (`"<robot> <DD.RR>"`) in one
`basic.showString()` call — no second display call, no extra cost.

**Checked-in placeholders**: `test/test.ts` declares `const
BOOT_VERSION = "00.00"` and `const BOOT_ROBOT = "unknown"` near the top
of the file, both visibly-fake so an unsubstituted build (this file
run directly, not through `make_deploy.py`) reads as obviously wrong
rather than silently plausible.

**Ordering, decided deliberately**: the banner call
(`basic.showIcon(IconNames.Rollerskate)` then `basic.showString(...)`)
is placed LAST in `test/test.ts`, after every button handler and every
`diffDrive.onRun(...)` registration. Registration is a handful of
synchronous, near-instant calls; `basic.showIcon()`/`basic.showString()`
BLOCK the TS main fiber for as long as they take to display (a couple
of seconds for the scroll). Reversing the order would leave a RUN:
command arriving in that window with no handler yet registered to
dispatch to. The protocol fiber's own boot banner (the wire-level
HELLO reply, `protocol.cpp`'s `Protocol::run()` -> `wireHandler_.
sendBanner()`) runs on its own separate CODAL fiber, launched from the
extension's top-level code (`blocks/motion.ts`'s `_startProtocol()`)
ahead of `test/test.ts`'s own top-level code regardless of where in
this file the display call sits — so it is unaffected by this ordering
choice either way. This reasoning is recorded in `test/test.ts`'s own
comment at the banner call site, not just here.

**A real defect found and fixed along the way**: `tsconfig.json`'s
hand-maintained `files` list did not include `pxt_modules/core/
icons.ts`, so `IconNames`/`basic.showIcon` — this tree's first use of
either — were unresolved symbols under this project's `no-default-lib`
tsconfig setup. That combination does not fail as a clean diagnostic;
`tsc --noEmit -p tsconfig.json` **crashed** (`TypeError: Cannot read
properties of undefined (reading 'get')` inside the compiler's own type
-node printer) instead of reporting "cannot find name." Confirmed via
`git stash` that the crash is new (clean exit 0 without this ticket's
`test/test.ts` changes, crash with them) and unrelated to the
substitution mechanism itself. Fixed by adding `pxt_modules/core/
icons.ts` to `tsconfig.json`'s `files` array, in the same position
`pxt_modules/core/pxt.json`'s own manifest places it (immediately after
`basic.ts`) — `tests/host/test_typescript_typecheck.py` (pre-existing,
runs `tsc --noEmit` on every `uv run pytest`) now passes and would have
caught this at the full-suite gate regardless.

**Honesty on verification**: no TypeScript in this repo is executed by
any test. `tests/host/test_boot_banner_source_pin.py` is a text-level
pin (icon-then-scroll order, placeholder shapes, ordering relative to
the last `diffDrive.onRun(...)`, a guard that `src/blocks/*.ts` never
references the banner) — it proves the source text has the shape this
ticket describes, nothing about actual on-device display behavior.
Real verification (does the banner actually show correctly, with the
right robot/version, on real hardware) is ticket 003's bench
flash-and-read checkpoint, as planned.

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
