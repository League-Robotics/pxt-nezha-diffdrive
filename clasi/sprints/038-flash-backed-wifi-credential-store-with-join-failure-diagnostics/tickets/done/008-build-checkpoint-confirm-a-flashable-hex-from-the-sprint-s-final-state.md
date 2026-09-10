---
id: 008
title: 'Build checkpoint: confirm a flashable hex from the sprint''s final state'
status: done
use-cases: []
depends-on:
- '007'
github-issue: ''
issue:
- wifi-join-failure-does-not-say-why.md
- wifi-credentials-live-in-flash-not-in-the-hex.md
completes_issue: true
---
<!-- CLASI: Before changing code or making plans, review the SE process in CLAUDE.md -->

# Build checkpoint: confirm a flashable hex from the sprint's final state

## Description

Standing convention since sprint 008
(`docs/design/design.md`, "Host-vs-target language standard" section):
every sprint that touches build-eligible `src/` code carries a
mandatory, ALWAYS-LAST build-checkpoint ticket that runs
`tools/make_deploy.py` (triage-aware: distinguishes a real `.cpp`
compile failure from the two documented benign abort shapes — the
legacy V1 hex-merge failure and the nondeterministic `TS9283`/`TS9043`/
`TS9200` packaging abort — and retries the latter once automatically)
and confirms a flashable hex results from the sprint's own final
state. This closes the gap the host-only `-std=c++11` syntax gate
cannot: a green host suite does not prove the real embedded target
compiles (host tests compile portable C++ at `-std=c++20`; both real
targets are `-std=c++11`), and `close_sprint` itself does not run a
real build.

This sprint adds new translation units (`wifi_credential_store.{h,cpp}`,
`wifi_flash_port.{h,cpp}`, `wifi_join_sequencer.{h,cpp}`) that MUST be
present in `pxt.json`'s `files` list — sprint 006's own investigation
found a `pxt.json` manifest omission that silently blocks every hex
while the host-only syntax gate stays green, so this is not a
theoretical concern for this specific sprint.

## Acceptance Criteria

- [x] `tools/make_deploy.py` runs against the sprint's final `master`-
      bound state (after ticket 007) and produces a flashable hex.
- [x] Every new translation unit this sprint added is confirmed present
      in `pxt.json`'s `files` list (explicit check, not assumed from
      the build succeeding — a stale manifest and a stale build cache
      can both mask this, per
      `.claude/rules/measurement-citations.md`'s own worked example of
      exactly this failure mode).
- [x] Any benign abort (legacy V1 hex-merge, or the `TS9283`/`TS9043`/
      `TS9200` packaging class) is retried per `make_deploy.py`'s
      existing triage, and the outcome is recorded, not silently
      re-run until green without comment.
- [x] If the build genuinely fails on a real `.cpp` compile error not
      caught by the host `-std=c++11` syntax gate (the known gap this
      checkpoint exists to catch), it is reported and fixed here —
      this ticket does not close with a broken build.
- [x] The resulting hex is not flashed to a fleet board as part of THIS
      ticket unless the team-lead separately decides to (this ticket's
      job is "a flashable hex exists," not "the fleet is now running
      it" — that's the sprint's own closing decision, informed by
      ticket 004's confirmed flash-page address if it differs from
      what shipped in earlier tickets).

## Implementation Plan

**Approach**: Run `tools/make_deploy.py` exactly as prior sprints'
build-checkpoint tickets have (sprint 004 ticket 005, sprint 007 ticket
008, sprint 008's own standing practice) — no new tooling needed unless
this sprint's new files reveal a gap in the existing triage logic, in
which case fix `make_deploy.py` itself as part of this ticket.

**Files to modify**: `pxt.json` (if the `files` list check in
Acceptance Criteria finds an omission — expected to already be correct
if tickets 002/005 each updated it as their own tickets said to, but
this checkpoint is exactly where a missed one gets caught).

**Testing plan**: The build itself is the test. No new automated test
is expected from this ticket beyond what `make_deploy.py` already
runs.

**Documentation updates**: None required.


## Result — team-lead, 2026-09-10

`tools/make_deploy.py --robot gopiv` at the sprint's final commit built
cleanly (`.tmp/deploy-head/built/binary.hex`) and flashed to gopiv over
the network. The board came up and answered on its own WiFi link:

```
id diffdrive gopiv 1.20260910.2 gopiv
WIFICRED SET 0 "Busboom Mesh" "fake pass phrase" #1   -> ack 1
WIFICRED #2                                          -> wificred 0 1 Busboom Mesh
DBG:wifi state=5 ip=192.168.1.218 ... credsrc=0 join=- haspw=1 ssid=Busboom Mesh
```

Artifacts: `captures/wifi-credential-store-20260909/final-hw3.log` and
that directory's `notes.md`. Full suite at this commit: 2074 passed
(`tests/tools/test_field_dance_accel_bake.py` ignored — it needs a
camera daemon that is not running here).
