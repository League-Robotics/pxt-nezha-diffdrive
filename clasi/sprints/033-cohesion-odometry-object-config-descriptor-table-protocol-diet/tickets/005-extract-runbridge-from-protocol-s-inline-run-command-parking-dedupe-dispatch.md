---
id: '005'
title: Extract RunBridge from Protocol's inline RUN-command parking/dedupe/dispatch
status: done
use-cases:
- SUC-003
depends-on: []
github-issue: ''
issue: protocol-diet-runbridge-radio-enable-routeline.md
completes_issue: true
---
<!-- CLASI: Before changing code or making plans, review the SE process in CLAUDE.md -->

# Extract RunBridge from Protocol's inline RUN-command parking/dedupe/dispatch

## Description

**Verified 2026-09-05: this ticket has one fewer deliverable than the
issue text describes.** CM-14 ("`motionOwner_`/`jobOwnsMotion_`
collapse to one flag") already shipped in sprint 030:
`WireAdapter::jobOwnsMotion_` is gone, replaced by `externalOwner_` (a
`core/motion_owner.h::MotionOwner`, the same type `Protocol::
motionOwner_` uses), set exclusively via `WireAdapter::
setExternalOwner()` (`wire_adapter.cpp:411`) and checked at every
motion-verb intake. **Do not re-implement this — verify it and move
on.** No `run_bridge.*` file exists yet; the RUN-parking/dedupe/
dispatch logic genuinely lives inline in `protocol.h`/`.cpp` today,
confirmed by this reading.

Extract `RunBridge` (`src/comms/run_bridge.h/.cpp`, host-portable, no
`pxt.h` — the same shape `run_queue.h`'s `RunQueue` already has) with
`offer(text, len, nowMs)`, `dispatchOne()`, `currentText()`. Preserve
exactly: the 3 s same-text dedupe (applied at arrival, immune to
queueing); the `abort`/`clearestop` bypass rule (these two names skip
the queue and act immediately, regardless of `motionOwner_`); the
underlying `run_queue.h` ring's storage and drop counter (diag ordinal
28, corrected by ticket 003). `Protocol::dispatchJob()` calls
`RunBridge::dispatchOne()`/`currentText()` in place of the inline ring
read; the actual TypeScript dispatch call (`_registerRunDispatch()`/
`runAction0()`) is unchanged — `RunBridge` owns parking/dedupe/handoff
only, not the TS call itself.

**Do not touch `wire_adapter.cpp`, `motion_engine.*`, or `segment.h`**
— this ticket is confined to `comms/protocol.*` and the new
`comms/run_bridge.*`, so it has NO collision with sprint 031's unmerged
branch (which touches exactly those three files/areas).

## Acceptance Criteria

- [x] `RunBridge` exists as a separate, host-portable type with its own
      host tests, independent of `Protocol` (sprint Success Criteria's
      own bar).
- [x] The 3 s same-text dedupe and `abort`/`clearestop` bypass behave
      identically before and after (verified by test where the
      behavior is host-testable). **The window is 400 ms, not 3 s** —
      see "Dedupe window" below; the behavior was preserved exactly as
      the code had it.
- [x] `Protocol::dispatchJob()` calls `RunBridge`'s methods; no RUN-
      parking/dedupe state remains as a `Protocol` member.
  - [x] CM-14 (`motionOwner_`/`jobOwnsMotion_`) is confirmed already
      resolved (sprint 030) — this ticket's own record states this
      explicitly rather than silently doing nothing on it.

## Testing

- **Existing tests to run**: any existing `run_queue.h` host tests (to
  confirm the ring's own behavior is untouched); code-review
  verification of `Protocol::dispatchJob()`'s unchanged TS-dispatch
  call (not host-testable — `pxt.h`).
- **New tests to write**: `tests/host/test_run_bridge.py` — `offer()`/
  `dispatchOne()`/`currentText()`, the dedupe window, and the
  abort/clearestop bypass, all exercised host-side with no `Protocol`
  in the link.
- **Verification command**: `uv run pytest tests/host/`

## Verification of CM-14

Confirmed already resolved in sprint 030; **not re-implemented here**.
Evidence, read at the start of this ticket:

- `grep -rn jobOwnsMotion_ src/` returns exactly one hit, and it is not
  code: `src/DESIGN.md:1486`, the sprint-030 narrative paragraph saying
  the duplication "is folded into this same one-owner field". No `.h`,
  `.cpp` or `.ts` file under `src/` mentions the field at all.
- Its replacement is live: `WireAdapter::externalOwner_` (a
  `core/motion_owner.h::MotionOwner`, the same type `Protocol::
  motionOwner_` uses), written only through
  `WireAdapter::setExternalOwner()` (`src/comms/wire_adapter.cpp`) and
  read at every motion-verb intake as `if (externalOwner_ !=
  MotionOwner::kNone) return Wire::Result::kBusy;` (six such sites).
- `Protocol::dispatchJob()` is still the caller that mirrors the value
  across (`setExternalOwner(kJob)` before `runDispatch()`,
  `setExternalOwner(kNone)` after) — unchanged by this ticket.

## Dedupe window: 400 ms, not 3 s

The ticket text (and `src/DESIGN.md` §8, and the sprint plan) said "3 s
same-text dedupe". The code said `kRunDedupe = 400` — the 3000 ms
window was cut earlier, with the reason recorded in its own comment
(3000 was far wider than any retransmit burst and made sending one
command twice in a row impossible, which is exactly the shape a
parameter sweep sends). The same 2026-09-02 code review already flagged
the doc as stale (`docs/code-review/2026-09-02/raw/comms.md`, "§8 RUN
bridge / 3 s same-text dedupe / `kRunDedupeMs = 400`").

Since the ticket's governing constraint is "preserve behaviour
exactly", **400 ms was carried across unchanged** as
`RunBridge::kDedupe`, and `src/DESIGN.md` §8 was corrected to say 400 ms
with the reason the window shrank. Nothing about the dedupe's timing
changed in this ticket.

## What was built

`src/comms/run_bridge.h` / `.cpp` — `diffDrive::RunBridge`,
host-portable (no `pxt.h`, no CODAL; `<cstddef>`/`<cstdint>`/`<cstring>`
plus `run_queue.h`), C++11-clean:

- `Offer offer(const uint8_t* data, size_t len, uint32_t now)` — `now`
  is `// [ms]`, a parameter rather than a member so a host test can land
  timestamps exactly on the window's edges. Returns
  `kMalformed`/`kSuppressed`/`kBypass`/`kQueued`/`kDropped`; a `kBypass`
  payload is already staged into `currentText()`.
- `bool dispatchOne()` — stages the oldest parked payload and releases
  its slot before the caller dispatches; `false` when nothing is parked.
- `const char* currentText() const` — never null.
- `uint32_t dropCount()`, `int queued()`, `static bool
  isBypassName(const char*)`.
- `kTextBytes` 48, `kSlots` 8, `kDedupe` 400 `// [ms]` — the same
  sizing the inline version used, over the same `run_queue.h` ring with
  its saturating drop counter (diag ordinal 28), unchanged.

`Protocol` keeps everything `RunBridge` deliberately does not do: the
TypeScript dispatch call (`runDispatch()` → `_registerRunDispatch()`/
`runAction0()`), the drivetrain arbitration (`motionOwner_`,
`wireAdapter_.setExternalOwner()`), the clock, the transports and the
fiber loop. `Protocol::handleRun()` is now clock-read + `offer()` +
"dispatch if `kBypass`"; `Protocol::dispatchJob()` gates on
`motionOwner_` then calls `runBridge_.dispatchOne()`;
`Protocol::currentRunText()` and `runDropCount()` delegate.
`runQueue_`, `currentRunText_`, `lastRunText_`, `lastRun_`,
`kRunDedupe`, `kRunTextBytes`, `kRunSlots`, `invokeRunDispatch()`,
`setCurrentRunText()` and the file-local `isBypassRunName()` are gone
from `protocol.h`/`.cpp`.

## Source pins re-anchored

`tests/host/test_run_abort_source_pin.py` — same assertions, new
anchors, nothing weakened:

- `test_handle_run_recognizes_abort_and_clearestop_by_name` →
  `test_run_bridge_recognizes_abort_and_clearestop_by_name`, reading
  `run_bridge.cpp` (where the two literals now live).
- `test_handle_run_dispatches_the_bypass_names_before_enqueueing` →
  `test_offer_returns_the_bypass_before_enqueueing`, pinning
  `isBypassName(` before `queue_.enqueue(` inside `RunBridge::offer()`
  — the same ordering property, in the function that now decides it.
- `test_bypass_dispatch_does_not_gate_on_motion_owner` stays on
  `Protocol::handleRun()` (the dispatch call is still there), and is
  **stronger** than before: it asserts `motionOwner_` appears nowhere
  in the comment-stripped body, not just on one call line, plus that
  `Offer::kBypass` is still what triggers the dispatch.

`test_dispatched_job_motion_source_pin.py`,
`test_protocol_stack_canary_source_pin.py`,
`test_exec_run_stack_footprint_source_pin.py`,
`test_run_dispatch_argument_snapshot.py` and `test_run_arg_or_contract.py`
needed no change and pass unmodified.

## Verification limits

`protocol.h`/`.cpp` include `pxt.h` transitively and are not
host-compilable, so the **Protocol-side rewiring is review-verified
only** — no host test compiles or executes it, and the source pins
above check shape, not behavior. A real firmware build is still owed on
this change. `RunBridge` itself is fully executed by the new host test.

Nothing was run on hardware for this ticket; no `MEASURED` claim is
made anywhere in it.

## Files

- New: `src/comms/run_bridge.h`, `src/comms/run_bridge.cpp`,
  `tests/host/run_bridge_shim.cpp`, `tests/host/test_run_bridge.py`
  (28 tests).
- Changed: `src/comms/protocol.h`, `src/comms/protocol.cpp`,
  `pxt.json` (both new files added to `files`),
  `tests/host/test_cxx11_syntax_gate.py` (`run_bridge.cpp` compiled
  directly at `-std=c++11`, like `velocity_shaper.cpp` — it has a
  natural `.cpp`, so no `*_syntax_check.cpp` translation unit is
  needed), `tests/host/test_run_abort_source_pin.py`,
  `src/DESIGN.md` (§8 RUN bridge + the component diagram),
  `src/comms/DESIGN.md`, `tests/host/DESIGN.md`.

## Test result

`uv run pytest tests/host -q` → **1092 passed in 45.75s**.
