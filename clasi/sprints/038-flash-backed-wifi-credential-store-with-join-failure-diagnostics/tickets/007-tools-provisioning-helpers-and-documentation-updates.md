---
id: '007'
title: tools/ provisioning helpers and documentation updates
status: open
use-cases: [SUC-005]
depends-on: ['006']
github-issue: ''
issue: wifi-credentials-live-in-flash-not-in-the-hex.md
completes_issue: true
---
<!-- CLASI: Before changing code or making plans, review the SE process in CLAUDE.md -->

# tools/ provisioning helpers and documentation updates

## Description

Give a host operator a real way to use R2/R6 without hand-crafting wire
lines, and document the new feature. In scope per the sprint plan:
`tools/` (`wifilink.py`/`robotlink.py`/`rogo`) — explicitly NOT the
robot-console host (Out of Scope).

1. Add helper(s) to `tools/wifilink.py` or `tools/robotlink.py` (match
   whichever already owns wire-verb helpers of this shape) to issue
   `WIFICRED SET`/`CLEAR` and parse the bare `WIFICRED` enumeration
   into a Python structure (list of `{slot, ssid, has_password}` — NOT
   `has_password: <the password>`, obviously).
2. A small scripted path to provision a board's whole list in one
   session (per R6's "host tool can provision a board" framing) — does
   not need to be a polished CLI; a documented function/script callable
   from a bench session is enough (a provisioning "wizard" UI is
   explicitly Out of Scope).
3. Update `docs/robot-connections.md` with the new verb and the
   provisioning workflow.
4. Update `nezha-robot-template/docs/wifi.md` to reflect that
   credentials no longer need to be baked/committed at all — the whole
   point of this sprint — while leaving `tools/make_deploy.py`'s bake
   path documented as the fallback it now is (Design Rationale #5).
5. Confirm `scripts/redact-wifi-trace.sh` (the existing leak-prevention
   tool referenced in this sprint's HARD CONSTRAINT) still does its job
   against captures containing the new `WIFICRED`/`join=`/`ssid=`/
   `haspw=` fields — it was written for the OLD `DBG:wifi` shape; a
   redaction script that doesn't know about a new field it should
   never need to redact (since none of them ever carry a password) is
   fine, but verify this explicitly rather than assuming it.

## Acceptance Criteria

- [ ] A `tools/` helper can enumerate, set, and clear credential slots
      against a live board (or the host test harness, for CI) without
      hand-written wire lines.
- [ ] A documented path exists for provisioning a board's whole list in
      one scripted session.
- [ ] `docs/robot-connections.md` documents `WIFICRED` alongside the
      existing verb reference.
- [ ] `nezha-robot-template/docs/wifi.md` is updated to describe the
      flash-backed workflow as the PRIMARY path, with the bake path
      documented as the fallback.
- [ ] `scripts/redact-wifi-trace.sh` is checked (and updated if
      necessary) against the new fields; the check itself is recorded
      in this ticket, not silently skipped.
- [ ] **No passphrase appears in any `tools/` log output, any example
      command in the documentation, or any test fixture this ticket
      adds** — every example SSID/password in docs uses an obviously
      placeholder value (e.g. `MyNetwork` / `hunter2example`), never a
      value copied from a real config file.
- [ ] Any new/changed Python in `tools/` passes this project's existing
      Python test/lint gates (`tests/tools/`).

## Implementation Plan

**Approach**: Follow the existing shape of whichever wire-verb helper
`tools/wifilink.py`/`robotlink.py` already has for a similarly-shaped
multi-line reply (if one exists — otherwise follow `rogo`'s or the
existing `FUNCS`-consuming code's pattern, since `WIFICRED`'s bare
enumeration is deliberately shaped like `FUNCS`'s).

**Files to modify**:
- `tools/wifilink.py` and/or `tools/robotlink.py` — new helper
  function(s).
- `docs/robot-connections.md`.
- `nezha-robot-template/docs/wifi.md`.
- `scripts/redact-wifi-trace.sh` — only if the check in Acceptance
  Criteria finds it needs updating.

**Testing plan**: `tests/tools/` coverage for the new helper(s)
(parsing the enumeration reply shape, building `SET`/`CLEAR` commands
correctly, and — same as every other ticket in this sprint — never
logging a password). Run the existing `tests/tools/` suite to confirm
no regression.

**Documentation updates**: This ticket IS the documentation update; see
Description above.
