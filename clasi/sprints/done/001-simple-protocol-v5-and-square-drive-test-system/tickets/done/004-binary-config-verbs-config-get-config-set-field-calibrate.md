---
id: '004'
title: Binary config verbs (CONFIG, GET_CONFIG, SET_FIELD, CALIBRATE)
status: done
use-cases:
- SUC-003
depends-on:
- '001'
- '002'
github-issue: ''
issue: implement-simple-protocol-v5.md
completes_issue: true
---
<!-- CLASI: Before changing code or making plans, review the SE process in CLAUDE.md -->

# Binary config verbs (CONFIG, GET_CONFIG, SET_FIELD, CALIBRATE)

## Description

Implement `CONFIG`, `GET_CONFIG`, `SET_FIELD`, `CALIBRATE`. `CONFIG`
and `SET_FIELD` write one or more `ConfigField` values via the
existing `setKernelValue`-equivalent path; `GET_CONFIG` reads back the
current value of one field via a new getter (the read-back counterpart
`setKernelValue` doesn't currently have) and sends a synchronous binary
`CFG` reply — the one binary reply this sprint keeps, per sprint.md's
Architecture (unaffected by the TLM-simplification deviation, since
`GET_CONFIG` was never carried by the ack ring even in the full spec).
`CALIBRATE` is accepted and parsed but performs no calibration — this
hardware has no OTOS sensor (documented no-op, spec-consistent — see
sprint.md Design Rationale). Reference: protocol-v5.md §6.1, §6.2.

## Acceptance Criteria

- [x] `CONFIG`, `GET_CONFIG`, `SET_FIELD`, `CALIBRATE` registered in
      the verb registry as binary verbs.
- [x] `CONFIG` accepts one or more `(field-number, value)` pairs, with
      `field-number` matching the existing `ConfigField` enum ordinals
      (0-14, see `main.ts`), and applies each via the existing
      `setKernelValue`-equivalent path.
- [x] `SET_FIELD` accepts exactly one `(field-number, value)` pair and
      applies it the same way.
- [x] `GET_CONFIG` accepts one field-number, reads its current value
      via a new getter added to `shims.cpp` (the read-back counterpart
      to the existing `setKernelValue`), and sends a synchronous
      binary `CFG` reply (COBS+CRC framed, reusing ticket 001's codec
      for the outbound direction) carrying that value.
- [x] `GET_CONFIG`'s reply reflects the true current value regardless
      of whether it was last set via the wire (`CONFIG`/`SET_FIELD`)
      or via a MakeCode `set config` block in the same running
      program — both paths converge on the same underlying kernel
      `Config` state.
- [x] An out-of-range field-number for `GET_CONFIG`/`SET_FIELD`/`CONFIG`
      does not crash the protocol loop (implementer's choice: silently
      ignore the pair, or reply an error on `GET_CONFIG` only — no ack
      plane exists for `CONFIG`/`SET_FIELD` per Open Question 1, so
      those two have no error-reporting path regardless).
- [x] `CALIBRATE` is recognized and parsed but performs no calibration
      and touches no motor output; no reply is sent (fire-and-forget,
      consistent with every binary arm except `GET_CONFIG`).
- [x] No changes to `diffdrive.h`/`diffdrive.cpp` (vendored kernel).

## Implementation Plan

**Approach**: Add a `getConfigValue(field)` counterpart to
`shims.cpp`'s existing `setKernelValue(field, value)`, reading from
the same kernel `Config` the setter writes (via the kernel's existing
config accessor, the same one `setKernelValue`'s switch statement
already references for a couple of its cases, e.g. `k.config()`).
Register the four verbs' handlers in the Protocol/Comms module.

**Files to create/modify**: `shims.cpp` (additive getter), the
Protocol/Comms module (handlers, including the `CFG` binary reply
path).

**Testing plan**: Desk-check a `GET_CONFIG` round trip against a value
just set via `SET_FIELD`/`CONFIG` in the same session. No automated
test harness exists in this repo. Hardware bench verification deferred
to the stakeholder via `mbdeploy`/"zetuv"
(`test-on-microbit-zetuv-via-mbdeploy.md`).

**Documentation updates**: None beyond code comments; note in the PR
that `GET_CONFIG` is the one verb this sprint keeps a binary reply for,
per sprint.md's Architecture section.
