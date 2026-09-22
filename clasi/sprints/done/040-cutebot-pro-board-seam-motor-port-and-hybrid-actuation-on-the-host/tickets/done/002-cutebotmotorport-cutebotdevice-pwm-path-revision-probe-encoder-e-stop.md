---
id: '002'
title: 'CutebotMotorPort + CutebotDevice: PWM path, revision probe, encoder, e-stop'
status: done
use-cases:
- SUC-002
depends-on:
- '001'
github-issue: ''
issue: cutebot-pro-board-seam-and-hybrid-port.md
completes_issue: true
---
<!-- CLASI: Before changing code or making plans, review the SE process in CLAUDE.md -->

# CutebotMotorPort + CutebotDevice: PWM path, revision probe, encoder, e-stop

## Description

Depends on ticket 001 (the board seam must exist so
`DIFFDRIVE_BOARD_CUTEBOT_PRO` has somewhere to plug in). Implement the
Cutebot Pro's raw-PWM actuation path only — the `0x80` onboard-loop
path and the actuation policy are ticket 004; this ticket proves the
same category of correctness the Nezha port already has, one board
level down.

Per `docs/design/cutebot-pro-support.md` §1.2 (v2 wire frames), §2.1
(the port), §3.A (what to watch), and §7 (host testing):

- `src/platform/cutebot_port.h/.cpp`: `CutebotMotorPort final : public
  DiffDrive::Motor`, implementing all 14 calls
  (`begin`/`requestSample`/`setDuty`/`emergencyStop`/`tick`/
  `position`/`velocity`/`appliedDuty`/`connected`/`sampleTime`/
  `rebaseline`/`wedged`/`wedgeSuspect`, `src/core/diffdrive.h:25-44`)
  against a shared `CutebotDevice` object both wheels' ports bind to
  (the Cutebot takes both wheels' duties in ONE `0x10` frame, so one
  wheel's `tick()` stages, the other's ships).
- `CutebotDevice`: the 0x10 slave's session state — the revision probe
  (`99 15 01 00 00 00 88`, cached for the session, §1.1) run once at
  the first `begin()`; v2 frame encode
  (`FF F9 <cmd> <len> <params...>`, §1.2) for cmd `0x10` (wheel,
  abs% L, abs% R, dirbits) coalescing both wheels' staged duties into
  one write per kernel cycle; cmd `0xA0 [3]`/`[4]` + a 4-byte read for
  each wheel's accumulated degrees, converted to kernel counts
  (degrees ×10 = counts, matching the Nezha port's "1 count = 0.1°"
  convention); cmd `0x50` to zero an encoder (`rebaseline()` stays a
  software offset, no bus traffic, exactly like `NezhaMotorPort` —
  `0x50` is for a real hardware zero, not used by `rebaseline()`); the
  per-board `diffdrive_emergency_stop` frame for a Cutebot (writes the
  `0x10` zero-PWM frame with no dependency on any object, mirroring
  `nezha_port.cpp:52-65`'s fault-context contract).
- A failed read (simulated NACK in this sprint) holds the previous
  `sampleTime()` rather than fabricating a zero velocity — the same
  contract `NezhaMotorPort`/`src/DESIGN.md` §7 states for the Nezha
  port ("a port whose read FAILS must hold `sampleTime()`, not report
  velocity zero").
- The 1 ms post-write busy-wait the ELECFREAKS extension uses after
  every `i2cCommandSend()` (§1.2) must go through
  `diffDrive::vfpSafeSleep()` (`src/platform/vfp_guard.h`), never a
  spin or a raw `fiber_sleep()` — per
  `.claude/rules/fiber-yield-safety.md`, any CODAL-facing sleep not
  routed through the guard is a defect
  `test_vfp_guard_source_pin.py`-style pinning should catch.
- `configureMotor`'s Cutebot behaviour (§10.2, the open stakeholder
  question this sprint resolves): `CutebotMotorPort::configureWiring()`
  accepts a sign change (flips which physical direction is "forward"
  for that wheel) and **refuses** any request that would change which
  physical wheel a side addresses (the Cutebot's wheels are fixed to
  the one 0x10 slave — there is no second port to move to). Route the
  refusal through the wire's existing `Result` refusal-code path
  (`src/DESIGN.md` §4's `kBadArg`/`kRange`/etc. taxonomy), not a silent
  no-op; pick the specific code and record the choice in this ticket's
  own completion notes as **stakeholder-reviewable** — it resolves an
  explicitly open design-doc question, not a settled convention.
- Host testing (`docs/design/cutebot-pro-support.md` §7):
  `tests/host/sim_cutebot_bus.h` — a fake 0x10 slave answering v2
  frames, the revision probe, `0xA0 [3]/[4]` in degrees from a shared
  `SimWheel` (reuse the existing Nezha sim's physics class), and `0x50`
  clears. (The `0x80` onboard-loop simulation is ticket 004's, once the
  path exists to simulate.) `cutebot_port_shim.cpp` +
  `test_cutebot_port.py`: frame bytes and direction bits for every sign
  combination, the coalesced two-wheel write (exactly one `0x10` frame
  per kernel cycle — not two), degrees-to-counts conversion,
  `rebaseline()`, `emergencyStop()` bytes, `connected()` and held
  `sampleTime()` on a simulated NACK, and the `configureWiring()`
  sign-flip/port-refusal behaviour above.

## Acceptance Criteria

- [x] `CutebotMotorPort` implements all 14 `DiffDrive::Motor` calls;
      `test_cutebot_port.py` exercises every one against
      `sim_cutebot_bus.h`.
- [x] Exactly one `0x10` frame is shipped per kernel cycle for a pair
      of `CutebotMotorPort`s (proven by counting frames the sim bus
      receives across one `tick()` of both wheels), never two.
- [x] Encoder degrees ×10 = counts conversion is exact and covered for
      both positive and negative directions.
- [x] A simulated NACK on the encoder read holds the previous
      `sampleTime()` and does not report a fabricated zero velocity.
- [x] `emergencyStop()` and the fault-context
      `diffdrive_emergency_stop` frame for the Cutebot board are pinned
      by a source-level test analogous to the Nezha frame's own
      pinning.
- [x] `configureWiring()` accepts a sign-only change and refuses a
      port-changing request via the existing `Result` refusal-code
      path, covered by `test_cutebot_port.py`; the chosen refusal code
      is documented in this ticket's completion notes as a
      stakeholder-reviewable choice.
- [x] No CODAL sleep in the new code bypasses `vfpSafeSleep()`/
      `vfpSafeYield()`.
- [x] Full host suite stays green; ticket 001's byte-identical-Nezha
      guarantee is unaffected (no shared file touched by both tickets
      regresses the other's acceptance criteria).

## Completion Notes

**Files added.** `src/platform/cutebot_port.h`/`.cpp` (`CutebotDevice`
+ `CutebotMotorPort`, fully host-portable -- no `pxt.h` anywhere, not
even guarded); `src/platform/board_cutebot.cpp` (the Cutebot half of
ticket 001's board seam, mirroring `board_nezha.cpp`'s shape exactly:
`CutebotBoard` singleton, the four `board.h` hooks, and
`diffdrive_emergency_motor_stop()` for a single "wheel=both" zero
frame). Test scaffolding: `tests/host/sim_cutebot_bus.h` (v2 frames,
the v1-style revision probe answering v2, `0xA0 [3]/[4]` degree reads
from a reused `SimWheel`, `0x50` clears via a new
`SimWheel::resetPosition()`, single-shot NACK injection, raw
last-frame-byte capture, reject-everything-else); `tests/host/
cutebot_port_shim.cpp` + `tests/host/test_cutebot_port.py` (21 tests:
frame bytes/dirbits for all four duty-sign combinations plus a
separate fwdSign-flip test, exactly-one-frame-per-cycle including the
"only one side ticked" negative case, exact degrees->counts conversion
both directions via a zero-lag/zero-breakaway deterministic plant,
`rebaseline()` no-bus-traffic, `emergencyStop()` byte content, the
NACK/held-sampleTime contract, `wedged()`/`wedgeSuspect()` always
false, `configureWiring()`'s sign-accept/port-refuse/out-of-range/
no-op paths, `hardwareClearEncoder()`, the diag-value wiring ordinals,
and the revision-probe-runs-once cache); `tests/host/
test_board_cutebot_source_pin.py` (the Cutebot analogue of
`test_board_seam_source_pin.py`, since `board_cutebot.cpp` is not
host-compilable for the same reason `board_nezha.cpp` isn't -- its
singleton binds through the target-only default `I2CBus` argument).

**Files modified.** `src/comms/protocol.cpp` (`kRole` gains an
`#elif DIFFDRIVE_BOARD == DIFFDRIVE_BOARD_CUTEBOT_PRO` branch,
`"CUTEBOTPRO"`, ahead of the existing `#error`; the Nezha branch's text
is untouched, so `test_setdevicerole_precedence_source_pin.py`'s
existing pin needed no edit); `pxt.json` (`files` gains the three new
platform paths); `tools/make_deploy.py` (`EXPECTED_CPP_FILES` gains
`board_cutebot.cpp` and `cutebot_port.cpp` -- both are always compiled
regardless of `DIFFDRIVE_BOARD`, since PXT builds every listed file and
the `#if` inside each `board_*.cpp` is the only switch; the Cutebot
motor bake key itself is out of scope, per this ticket's own
non-negotiable); `tests/DESIGN.md` (the pxt-bound exclusion count moves
from eleven to twelve, a new row for `board_cutebot.cpp`, and a
paragraph explaining `cutebot_port.cpp` is NOT in that table -- it has
no `pxt.h` route at all, unlike `nezha_port.cpp`); `tests/host/
test_cxx11_syntax_gate.py` (`cutebot_port.cpp` added to the portable
compile list, since it is fully host-portable); `tests/host/
sim_nezha_bus.h` (`SimWheel::resetPosition()` added, additive-only, for
the Cutebot sim's `0x50` support -- no existing Nezha test touches it).

**The `WiringResult` / "wire's existing Result refusal-code path"
decision (STAKEHOLDER-REVIEWABLE, this ticket's own open question).**
The ticket text names `src/comms/wire_handler.h`'s `Wire::Result`
taxonomy directly, but `src/DESIGN.md` S1's layer table is explicit
that the "Hardware ports" layer (`platform/`) may know I2C/CODAL and
"nothing about blocks or the wire" -- so `cutebot_port.h` including
`comms/wire_handler.h` and returning a literal `Wire::Result` would
invert that dependency direction (platform/ depending on comms/, which
nothing else in this codebase does). Resolution: `cutebot_port.h`
declares its own `enum class WiringResult : uint8_t { kOk,
kUnimplemented }` -- a platform-local mirror of the SAME two codes,
with no include, so a future caller sitting above both layers could
map it 1:1 with no semantic translation. `CutebotMotorPort::
configureWiring(uint8_t port, int8_t sign)` returns this type;
`board_cutebot.cpp`'s `boardConfigureWiring()` (void, per ticket 001's
own fixed hook signature) calls it and discards the result -- nothing
today reads a `configure motor` outcome back through the wire in the
first place, since `shims.cpp`'s `configureMotor()` is itself a void
MakeCode block shim with no `Wire::Result` anywhere in its own call
chain (confirmed by reading `configureMotor()`, `boardConfigureWiring()`,
and `NezhaMotorPort::configureWiring()`, all void, end to end). So
"discarded at the fixed hook, available at the port" is not a
regression versus today's behavior; it is the same reach the Nezha
path already has. `test_cutebot_port.py`'s `test_configure_wiring_*`
tests call `CutebotMotorPort::configureWiring()` directly and assert on
its `WiringResult`.

The SPECIFIC code chosen for a port-changing request is
`kUnimplemented`, not `kBadArg`/`kRange`: the requested port number is
a well-formed value in the wire's own Nezha-style 1..4 vocabulary (not
malformed input) and is not literally out of any declared range (every
value 1-4 is individually valid elsewhere) -- it fails only because
this board has nothing a second port could mean. `kUnimplemented` is
the taxonomy's own code for "well-formed request, not supported here."
An out-of-range SIGN (anything but +1/-1) is a free no-op (`kOk`),
matching `NezhaMotorPort::configureWiring()`'s own precedent for an
invalid field ("Out-of-range ignored, no-change free").

**What is a source reading vs proven on the host.** Every wire-frame
byte layout, the revision probe's exact bytes, the 1 ms post-write
wait, and the `0x80` clamp are SOURCE READINGS of ELECFREAKS' own
extension (per `docs/design/cutebot-pro-support.md`'s own citation),
transcribed into `cutebot_port.h`'s header comment and cited as such,
never as MEASURED. What IS proven on the host, by compiling and running
the real `CutebotDevice`/`CutebotMotorPort` against
`sim_cutebot_bus.h`'s real byte-level frame parser (not a `FakeMotor`
above the wire, the same argument `sim_nezha_bus.h`'s own header makes
for the Nezha port): the exact frame bytes and dirbit encoding for
every duty-sign combination and for an `fwdSign_` flip; that
exactly one `0x10` write happens per two-wheel cycle, never two, and
zero when only one side has ticked; the degrees-to-counts conversion,
exactly, both directions, through a deterministic (zero-lag,
zero-breakaway) plant so there is no floating slack to explain away;
`rebaseline()`'s no-bus-traffic software-only re-anchor;
`emergencyStop()`'s exact single-wheel zero-frame bytes;
`configureWiring()`'s three-way decision (sign accepted, port refused,
same-value free no-op) and its `WiringResult`; and the revision-probe
run-once-per-session cache. NOT proven on the host, and left for a
real board: whether the revision probe genuinely needs no post-write
settle (UNVERIFIED in `cutebot_port.cpp`'s own comment); the sign
convention for a real Cutebot's `left`/`right` mount (`board_cutebot.cpp`'s
`+1`/`+1` defaults are placeholders, called out in that file's own
comment); whether a v1 board actually shows up (`isV2()` is recorded
but nothing branches on it yet); and everything `0x80`/hybrid-actuation
related, which is out of this ticket's scope by design (the tap and
policy are later tickets; this ticket leaves `CutebotDevice`'s own API
-- `stageDuty()`/`selectDegrees()`/`readSelectedDegrees()` -- as the
seam that work adds to, without needing to reshape any of it).

**Seam left for the `0x80` path.** `CutebotDevice` owns the ONE
low-level write primitive (`writeV2Frame()`) every future command
(including a future `0x80` onboard-loop write) would go through for
its 1 ms guarded wait; `stageDuty()`'s both-sides-staged gate is
already the coalescing point a hybrid actuation policy would sit
behind, choosing which frame shape to ship instead of always shipping
`0x10`. Nothing in `CutebotMotorPort`'s own `Motor` interface needed
reshaping to leave that seam open.

**Full-suite result.** `uv run pytest tests/host tests/tools -q
--ignore=tests/tools/test_field_dance_accel_bake.py` -- **2169
passed**, MEASURED this session. This ticket's own new tests are 31
of those (`test_cutebot_port.py`: 21; `test_board_cutebot_source_pin.py`:
10, both counted via `--collect-only`); the remainder are pre-existing
and green, including every test ticket 001 added. The ignored file
needs a live AprilCam daemon and is pre-existing/unrelated, per ticket
001's own notes on it.

**Not attempted / left for later tickets.** The `0x80` onboard-loop
path, the `WheelCommandTap`, the actuation policy, and their
`sim_cutebot_bus.h` onboard-loop simulation (ticket 004); the
`geometry.firmware_bake.board` bake key (ticket 005); a real-hardware
build/flash checkpoint for the Cutebot half specifically (a later
from-clean full build, per ticket 001's own deferred checkpoint).

## Testing

- **Existing tests to run**: full `uv run pytest`; ticket 001's
  byte-identity/host-suite checks re-run to confirm this ticket adds
  code without disturbing the Nezha path.
- **New tests to write**: `cutebot_port_shim.cpp` / `test_cutebot_port.py`
  (see Description); `tests/host/sim_cutebot_bus.h` as a shared fixture
  for this and later tickets (004, 006).
- **Verification command**: `uv run pytest tests/host/test_cutebot_port.py`
  during development, full `uv run pytest` before completion.
