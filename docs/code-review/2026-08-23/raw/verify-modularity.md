# Adversarial Verification — modularity-api.md Majors (2026-08-23)

Verifier scope: refute-or-confirm the Major findings API-01..API-06,
MOD-01, MOD-02, DES-01, plus two Minor spot-checks. Every verdict below
was re-derived from the working tree, not from the reviewer's citations.
API-02's kernel-side half (KERN-01) and API-03's block-side half (BLK-03)
are owned by other verifiers; only the API-surface halves are judged here.

## Verdict table

| ID | Verdict | Justification (one line) |
|----|---------|--------------------------|
| API-01 | **CONFIRMED** | Re-derived the whole chain: `setWheelSpeeds` → `wheelsV()` → `cancelMove()` (`motion_engine.cpp:21`), `tickDrive()` returns `serviceMove()` which returns `false` when `!move_.active` (`motion_engine.cpp:200`, `shims.cpp:470,544`) — the documented `while (diffDrive.driveTick())` idiom is false on first evaluation at all four doc sites, and the simulator body is identically broken (`_setWheels` sets `simMoveActive = false`, `main.ts:805`). |
| API-02 | **CONFIRMED** (API-surface half) | `clearStallLatch`'s only callers anywhere are `tests/host/kernel_shim.cpp:105` (host tests) — no shim, no `//%`, no block, no wire verb; `estopClear()` clears only `estopLatch_` (`diffdrive.cpp:374-376`); one caveat: `probe(2)` *can* technically read `stallHalted` but its own doc comment omits index 2, so no discoverable readback exists. |
| API-03 | **CONFIRMED** (API-design half) | The wire grammar's own quoted contract is "Pass 0 for the configured default" (`shims.cpp:330-332`, `wire_adapter.cpp:278-281`), and the resolution is `10795 / (10/0.8102)` ≈ 874.6 mm/s — the full-duty ceiling; `kFields` (`wire_adapter.cpp:88-104`) has no `default_cruise` to configure anything saner; bench note "60 cm/s … produced unusable runs" confirmed at `test/test.ts:229-230`. |
| API-04 | **CONFIRMED** | `out.otos = false` unconditional (`wire_adapter.cpp:226`) while `engineGoToW()` gates on `otos.connected()` (`shims.cpp:889-896`) through the very same forward-declaration seam; `diagValue()`'s switch (cases 0–25, `shims.cpp:679-714`) has no OTOS ordinal; STATUS prints the constant as `otos=%d` (`wire_handler.cpp:633`). |
| API-05 | **CONFIRMED** (one sub-claim corrected) | Core holds: `updateMove()` runs `serviceMove()` with **no** `kernel.step()` (`shims.cpp:415-425`), so no duty ever reaches the motors and the watchdog port-stops ≤ ~150 ms — zero distance from the palette-obvious composition; but the "spins for duration + 1500 ms until `expired`" detail is **wrong**: the watchdog also calls `r.engine.endMove()` (`shims.cpp:633`), clearing `move_.active`, so `isMoving()` goes false at the watchdog stop, not at the deadline. Severity Major stands (trap is unchanged; only the hang duration was overstated). |
| API-06 | **CONFIRMED** | `rotationalSlip()` is getter-only ("Read-only for now", `motion_engine.h:174-178`), hard-coded 0.952 (`motion_engine.h:346`); repo-wide grep finds no setter on any surface; `setGeometry` takes trackWidth/travelCalib only (`shims.cpp:753-758`); `kFields` has zero geometry entries; the only palette turn knob is `set track width` (`main.ts:700`) — the exact knob the header's own doctrine forbids using for this. |
| MOD-01 | **CONFIRMED** | `src/protocol.cpp:63` `kVersion = "1.0.0"` vs `pxt.json:3` `"version": "1.0.10"`; nothing generates or pins either. |
| MOD-02 | **CONFIRMED** (two inventories fully re-counted, one bonus) | Interpreter fork exact: `tour_run.py:31` = pipx aprilcam venv vs `tour_square.py:20`/`tour_practice.py:32`/`turn_sweep.py:31`/`tour_closedloop.py:29`/`tour_watch.py:31` = `AprilTags/.venv` (2 environments); `DOTS`/`ORDER` exactly 6 sites as listed; Cam scaffold count of 7 also holds (`tour_run.py:46`, `tour_practice.py:48` — `CamProc`, not `:50` —, `tour_watch.py:48`, `tour_square.py:27`, `turn_sweep.py:43`, `tour_closedloop.py:46`, `pivot_truth.py:32`), and `tools/camlink.py:48` already defines a shared `Cam` class the seven copies bypass — the finding is if anything understated. |
| DES-01 | **CONFIRMED** (one nuance) | All sizes re-verified: `rxLine_[64]` (`radio_transport.h:139`), clamp-truncate at `radio_transport.cpp:60`, drop-on-unconsumed `:61`, MORE-fragment drop `:56`, `rxLineBuf_[64]` (`protocol.h:224`), TX cap 200 (`radio_transport.h:126`), grammar max 240 (`wire_handler.h:275`), packet size raised to 250 (`pxt.json:44`). Nuance: sprint 004's plan *mentions* the limit once — SUC-001's postcondition "modulo the existing single-fragment RX size limit" — but plans no capacity work (ticket 001, the RX-routing ticket, says nothing about buffer sizes), and that phrase itself under-describes the hazard: with 250-byte packets a *single* fragment can carry ~246 payload bytes, which `onDatagram()` clamps to a still-parseable 64-byte prefix — the exact case the serial path was widened to 240 to avoid. The prior radio-RX issue is closed (`clasi/issues/done/radio-rx-command-plane-run-over-bridge.md`), so no open artifact covers this. |
| MOD-03 (spot) | **CONFIRMED** (sampled entries) | `wheelSpeed()` (`shims.cpp:938`): zero callers, prose-only references; `rxFrames_`/`rxAccepted_`: never **incremented** anywhere (not even `radio_transport.cpp`) and never read — deader than claimed; `driveTwistTimed`: comments only, while its sibling `setWheelsTimed` is alive (`wire_adapter.cpp:257`), so the reviewer's line was drawn correctly. |
| MOD-05 (spot) | **CONFIRMED** | `RUN_EVENT_SOURCE = 0x2001` (`main.ts:154`) vs `kRunEventSource = 0x2001` (`protocol.cpp:85`), unpinned; `kDiag*` re-declared at `wire_adapter.cpp:132-141` against `shims.cpp`'s switch; the `case 25` splice between the "23/24" comment and cases 23/24 is exactly as described (`shims.cpp:709-712`). |

## Notes

### API-01 — detail of the re-derivation

The highest-stakes claim, so re-derived end to end rather than sampled:

1. `setWheelSpeeds(l, r)` (`main.ts:106-108`) → `_setWheels` →
   `setWheels()` (`shims.cpp:247-251`) → `engine.wheelsV(..., kLeaseMax)`.
2. `wheelsV()` first line: `cancelMove()` (`motion_engine.cpp:20-21`,
   comment cites motion-api.md S6) → `move_.active = false`.
3. `driveTick()` (`main.ts:139-141`) → `tickDrive()` (`shims.cpp:449-545`)
   → returns `moveActive`, the value of `r.engine.serviceMove()`
   (`shims.cpp:470`, `return moveActive` at `:544`).
4. `serviceMove()` line 1: `if (!move_.active) return false;`
   (`motion_engine.cpp:200`).

So after any `setWheelSpeeds`/`driveTwist`, the first `driveTick()`
executes exactly one kernel step and returns `false`; the loop body never
runs; ~100–150 ms later `watchdogEntry()` (`shims.cpp:624-637`,
`kWatchdogTimeoutUs = 100000`) port-stops the wheels because
`commandLooksActive()` sees nonzero applied duty. "Twitches and stops" is
the literal behavior.

Documented-idiom sites, each re-read: `README.md:8, 32-35, 70-80`
(two full worked examples of the broken form, one with a loop body);
`specification.md` §4.2 (line 90); `usecases.md` UC-002 step 4 (line 56);
doc comments on `setWheelSpeeds` (`main.ts:93`), `driveTwist` (`:113`),
`driveTick` (`:131`). Counter-evidence checked as instructed:
`test/testrig.ts:118-120` uses a **bare** `diffDrive.driveTick()` inside
`basic.forever()` gated on `rigDrumMmps != 0` — the working continuous
pattern; `test/test.ts:24`'s `while (diffDrive.driveTick())` follows
`startMove()` (move engine active → returns true), as do all in-tree
`while (_tickDrive())` uses (`main.ts:249, 262, 359, 374, 642` — all
position-mode). No in-tree program uses the documented continuous-mode
idiom. The simulator is bit-identical in contract: `_setWheels`/
`_driveTwist` set `simMoveActive = false` (`main.ts:805, 813`) and
`_tickDrive` returns `simMoveActive` (`:849-868`), so the failure
reproduces in the browser too.

### API-02 — the probe(2) caveat

The finding's "no student-facing surface can even see it" is very
slightly overstated: `probe()` is an exported (non-palette) function and
`probe(2)` → `diagValue(2)` → `out.stallHalted` (`shims.cpp:684`). But
`probe`'s own doc comment (`main.ts:957-961`) lists only indices
10/11/12/13/14/15/6/7 — index 2 is undocumented tribal knowledge — and
there is no named reporter, no palette block, no error surface. The
substantive claim (only latched fault with no recovery operation on any
runtime surface; wire sees it via STATUS flags bit 2,
`wire_adapter.cpp:121,239`, but cannot clear it; the sole clear path
`clearStallLatch()` → `clearStallReq_` is reachable only from the host
test harness) is fully verified. `resetAdaptiveState()` clears
`stallLatched_` (`diffdrive.cpp:765`) but the only `stallHalted_ = false`
in the tree is the `clearStallReq_` path (`diffdrive.cpp:457`).

### API-05 — the corrected sub-claim

The watchdog does more than port-stop: `shims.cpp:632-635` runs
`kernel.neutral()` **and** `engine.endMove()` **and** both port
`emergencyStop()`s. `endMove()` → `cancelMove()` → `move_.active = false`
(`motion_engine.cpp:64-72`), so the next `isMoving()` poll returns false.
The student's polling loop therefore exits ~150 ms in — it does **not**
spin against `duration + 1500 ms` as the finding's scenario says (that
would require the watchdog to leave the move engine armed, which it
deliberately does not). This matters for accuracy of the eventual issue
text but not for severity: the shipped palette pair still drives zero
distance under its obvious composition, the failure is silent in block
view, and `moving?` remains a state-advancing reporter
(`updateMove()` reissues kernel leases via `serviceMove()`,
`motion_engine.cpp:261-271`). Major stands.

### DES-01 — what "the sprint plan doesn't cover RX capacity" precisely means

The plan is not entirely silent: SUC-001's postcondition concedes the
radio host gets serial parity "modulo the existing single-fragment RX
size limit" (`sprint.md:680-681`). But (a) that is an accepted caveat,
not planned work — no phase, ticket, or acceptance criterion touches
`rxLine_`/`rxLineBuf_` sizing, and ticket 001 (the RX-routing ticket) has
no capacity language at all; (b) the caveat's phrasing is itself
misleading, since the binding limit is not "one fragment" (~246 payload
bytes at the raised 250-byte packet size) but the 64-byte buffers, and
the failure mode is clamp-truncation to a parseable prefix
(`radio_transport.cpp:60`) — the precise hazard `serial_transport.h`'s
240-byte sizing note exists to prevent; and (c) the single-slot
`rxReady_` drop (`:61`) plus MORE-drop (`:56`) against a strict `#id`
sequence is nowhere discussed. The reviewer's characterization
("covers the TX re-entrancy hazard but not RX capacity") is accurate:
tickets 002/004/005 all address TX (re-entrancy guard, 200-byte TX cap),
none address RX.

### Hunt results — what the reviewer missed

Nothing that overturns a verdict. Two small strengthening facts surfaced
during verification (recorded here, not as new findings, per charter):
`tools/camlink.py:48` already holds a shared `Cam` class the seven script
copies ignore (MOD-02 is understated), and `rxFrames_`/`rxAccepted_` are
never incremented at all, not merely never read (MOD-03's entry is
understated). Incidentally re-confirmed in passing: the `diagValue` doc
comment's "protocol.cpp is the only caller" is false
(`WireAdapter::status()` and `probe()` also call it — MOD-09's claim),
and cases 14/15 return raw counts/s against the "floats are scaled ×100"
comment (already in the reviewer's correctness hand-offs).
