---
id: '007'
title: tools/ provisioning helpers and documentation updates
status: done
use-cases:
- SUC-005
depends-on:
- '006'
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

- [x] A `tools/` helper can enumerate, set, and clear credential slots
      against a live board (or the host test harness, for CI) without
      hand-written wire lines.
- [x] A documented path exists for provisioning a board's whole list in
      one scripted session.
- [x] `docs/robot-connections.md` documents `WIFICRED` alongside the
      existing verb reference.
- [x] `nezha-robot-template/docs/wifi.md` is updated to describe the
      flash-backed workflow as the PRIMARY path, with the bake path
      documented as the fallback.
- [x] `scripts/redact-wifi-trace.sh` is checked (and updated if
      necessary) against the new fields; the check itself is recorded
      in this ticket, not silently skipped.
- [x] **No passphrase appears in any `tools/` log output, any example
      command in the documentation, or any test fixture this ticket
      adds** — every example SSID/password in docs uses an obviously
      placeholder value (e.g. `MyNetwork` / `hunter2example`), never a
      value copied from a real config file.
- [x] Any new/changed Python in `tools/` passes this project's existing
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

## Implementation Notes

**Helpers**: `tools/robotlink.py` grows `wificred_set()`,
`wificred_clear()`, `wificred_list()` (bare `WIFICRED` enumeration ->
`[{'slot': int, 'ssid': str, 'has_password': bool}, ...]`), and a
shared `_wificred_exchange()`. `WIFICRED` was already in `_V6_VERBS`
(ticket 005/006), so `Link.send()` attaches the sequence id
automatically, matching how every other wire-verb helper here works.
The three functions read for the FULL reply window rather than
stopping at the first `ack`-prefixed line, because the firmware sends
`ack` unconditionally BEFORE running the adapter's own merits check,
with a possible `err <code>` line following in the same burst
(`wire_handler.cpp`: `replyAck()` then `execute()` then `replyErr()`)
-- an early-return read could otherwise miss a same-burst `err`. Pinned
by `test_wificred_set_returns_both_ack_and_a_same_burst_err`.

**Scripted provisioning**: `tools/provision_wifi.py` (new) -- `--list`,
`--clear SLOT`, `--slot N --ssid ... (--password-env|--password-file)`
for one slot, and `--manifest PATH` (a local, untracked JSON list) to
provision a board's whole credential list in one session, satisfying
R6's "host tool can provision a board" framing. No `--password` flag
exists (a CLI argument is visible in `ps`/shell history); the
interactive fallback uses `getpass.getpass()` (not echoed). Carrier
selection (`--usb`/`--radio`/`--wifi`) goes through
`robotlink.open_link()` unchanged.

**Docs**: `docs/robot-connections.md` gets a new "Provisioning
credentials from a host tool (`WIFICRED`)" subsection (full grammar,
the mass-erase-on-flash warning, the `join=`/`ssid=`/`haspw=` `DBG:wifi`
fields alongside the already-documented `credsrc=`/`trunc=`, the
absent-vs-failing-module distinction, and `tools/provision_wifi.py`
usage) — re-run `tools/publish_wiki.py --all` still needed (not run by
this ticket; see final report). `nezha-robot-template/docs/wifi.md`
(separate checkout) is restructured with `WIFICRED` as the primary
path and `setupWifi()`/`secrets.ts` demoted to "Fallback"; the stale
"a wrong password and an out-of-range AP are indistinguishable" claim
(pre-dating ticket 001's `join=` field) is corrected in the same pass.

**`scripts/redact-wifi-trace.sh` — checked, not silently skipped
(AC5).** The script does not exist in this repo (it never did — it
lives in `nezha-robot-template`) and, as of that repo's commit
`b723a1d` ("Drop redact-wifi-trace.sh — the extension redacts at the
source now", 2026-09-09, same day as this sprint's own ticket 009), it
no longer exists there either: ticket 009's source-level redaction
(`WifiLink::startCommand()`'s trace-override parameter) made the
script's job structurally unnecessary, and the first build against the
`v1.20260910.1` pin failed the script's own "exactly one CWJAP send
site" assertion because that site's shape changed — confirming, on
real usage, that the script had nothing left to match. `scripts/
build.sh` in that repo keeps a comment recording where the guarantee
now lives. No action needed here beyond recording this finding, which
this note does; there is nothing to check the new `WIFICRED`/`join=`/
`ssid=`/`haspw=` fields against.

**Tests**: `tests/tools/test_robotlink.py` (9 new cases: sequencing,
wire bytes for SET/CLEAR/bare-enumeration, the ack+same-burst-err
read, enumeration parsing incl. malformed lines, and a `capsys`-based
no-leak pin) and new `tests/tools/test_provision_wifi.py` (13 cases:
password sourcing from env/file, `provision_manifest()` over one
session via a `SequencedFakePort` double that only unlocks a reply
after its request is sent, `_report()`, and `main()` end-to-end for
`--list`/`--slot`/`--manifest`/`--clear`, each with an explicit
no-password-in-stdout/stderr assertion). `uv run pytest tests/tools/
test_robotlink.py tests/tools/test_provision_wifi.py` and `uv run
ruff check tools tests` both pass. A pre-existing, unrelated ruff
finding in `tests/host/test_wifi_join_sequencer.py` (B007 unused loop
variable, committed before this ticket started, outside `tools/`) is
left as found -- out of this ticket's scope.
