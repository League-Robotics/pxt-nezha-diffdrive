# src — the DiffDrive extension

**Owner:** Eric Busboom · **Last reviewed:** 2026-08-26 · **Status:** in-flux (as-built through sprint 016 — sprints 004-016 all closed and merged. Wire hardening and tests that can fail (sprint 008): timeout reject/clamp unified across all six motion verbs, `kVersion`/line-cap/`RUN_EVENT_SOURCE`/`kDiag*` single-sourced or drift-tested, the `WaHandle` test doubles re-synced to production, the post-move settle loop extracted into a host-testable `MotionEngine` helper, `TLM AUTO`/`BUFFER` given defined semantics, and a triage-aware `make_deploy.py` plus a standing per-sprint build-checkpoint-ticket convention closing the target-viability gap. The wire's motion-completion channel resolved, §5 (sprint 005). `main.ts` split into six cohesion-sized modules under `blocks/` (sprint 012), then `src/` regrouped into five dependency-layer subdirectories (sprint 013) — see §1.)

`src/` is grouped into five subdirectories by dependency layer —
`core/`, `motion/`, `platform/`, `comms/`, `blocks/` — plus `shims.cpp`
and this document at the top level (sprint 013; see §1's table for the
exact mapping). The directory split is coarse (five buckets for eleven
layers), so each subdirectory carries only a thin `DESIGN.md` pointing
back into the matching section below — `src/core/DESIGN.md`,
`src/motion/DESIGN.md`, `src/platform/DESIGN.md`,
`src/comms/DESIGN.md`, `src/blocks/DESIGN.md` — while this document
still carries the logical subsystem breakdown, and the fine-grained
per-file behavioral and design detail, as sections. Global conventions
(units
ladder, CCW sign, mirroring, the ×1000 config convention, protocol
versioning, the tick model) live in
[`docs/design/design.md`](../docs/design/design.md) and are assumed
throughout.

## 1. Layer map and layering rules

From the bottom up, with each layer's *verified* include discipline —
these are enforced by nothing but convention plus the host test
harness (which fails to link if a "host-portable" file grows a CODAL
dependency), so treat them as invariants:

| Layer | Files | May include |
|---|---|---|
| Kernel | `core/diffdrive.h/.cpp` | `<cstdint>`/`<cmath>`/`<algorithm>` only — **no I2C, no CODAL, no MakeCode, no geometry** |
| Motion engine | `motion/motion_engine.h/.cpp` | `diffdrive.h` + libc only — host-portable |
| Heading wrap (sprint 006) | `core/heading_wrap.h` | libc only — host-portable, no project includes at all |
| Encoder glitch armor (sprint 006) | `core/encoder_glitch_armor.h` | libc only — host-portable, no project includes at all |
| Encoder pose source (sprint 006) | `platform/encoder_pose_source.h` | `motion_engine.h` + libc only — host-portable |
| Wire grammar | `comms/wire_handler.h/.cpp` | libc only — host-portable, no project includes at all |
| Wire adapter | `comms/wire_adapter.h/.cpp` | `wire_handler.h` + libc — host-portable; reaches hardware only through forward-declared `shims.cpp` free functions |
| Transports | `comms/serial_transport.*`, `comms/radio_transport.*` | CODAL (`pxt.h` in the .cpp) — know bytes and framing, **nothing** about verbs, grammar, or motion |
| Hardware ports | `platform/nezha_port.*`, `platform/otos_port.*`, `platform/platform_ports.h` | `pxt.h` + the port interfaces they implement — know I2C/CODAL, nothing about blocks or the wire; `nezha_port.cpp` additionally calls into `encoder_glitch_armor.h` and `otos_port.cpp` into `heading_wrap.h`, both above (a dependency on a lower, host-portable layer, not membership in this one) |
| Protocol composition | `comms/protocol.h/.cpp` | everything above — the CODAL fiber that plumbs transports into the wire stack |
| Shim + blocks | `shims.cpp`, `blocks/sim.ts`, `blocks/run.ts`, `blocks/pose.ts`, `blocks/stop.ts`, `blocks/world.ts`, `blocks/motion.ts` (sprint 012: split from a single `main.ts` — see §9; sprint 013: `.ts` files grouped into `blocks/`) | everything — the composition root and the student-facing API |

Cross-cutting convention: `shims.cpp` has **no header**. Its C++
callers (`protocol.cpp`, `wire_adapter.cpp`) reach it via same-package
forward declarations that must stay signature-compatible with the real
definitions; the host harness supplies its own test-double definitions
of the same signatures. This is what keeps `wire_adapter.cpp` and
`shims.cpp` decoupled while sharing one `MotionEngine` singleton.

**Include-path rule (sprint 013).** Every `#include "X"` naming a file
under one of these subdirectories is qualified relative to `src/`'s
root (e.g. `motion_engine.h` including the kernel needs
`#include "../core/diffdrive.h"`, not a bare `#include "diffdrive.h"`)
— the project's builds (`-I src` in both the PXT cloud build and
`tests/host/`'s syntax-gate/shared-lib helpers) resolve
`#include "..."` relative to the including file's own directory, not
the project root.

## 2. Kernel — `core/diffdrive.h/.cpp` (`DiffDrive::DifferentialDrive`)

**Responsibility.** The closed-loop wheel-speed control law: per-cycle
PID + accel feedforward, per-wheel accel/decel correction curves,
slow adaptive bias, twist-hold trim, lambda authority scaling, speed
floor, crawl-pulse sub-breakaway dithering, stall/deficit latches,
lease-based command expiry, e-stop, and lock-free publication of a
diagnostics `Output` snapshot. Counts-native: 1 count = 0.1° shaft.

**Key data structures.** `Config` (staged/active pair, sequence-count
handoff), `Command` (mode neutral/velocity/raw-duty + lease
`validUntil`), `WheelSample`, `PositionRef`/`TwistRef` (integrated
command references the position-error and twist-hold terms compare
against), `Output` (published via an even/odd `outSeq_` counter so
readers never block the stepper).

**Public interface.** Fluent `setXxx()` config setters / `setConfig`;
`begin()`; `drive(velocity, twist, lease)` / `driveDuty()` /
`neutral()` / `estop()` / `estopClear()` / `emergencyStopMotors()` /
`clearStallLatch()` / `rebasePosition()`; `output()`; `step()` — and
`start()`, which launches the kernel's own paced fiber but is
**deliberately not called anywhere in this package** (see §9, tick
model). Refusals surface as a `Status` return plus a latched
`lastError()`.

**Ports it defines** (the complete surface a platform implements):
`Motor` (staged duty writes, split-phase encoder sampling, immediate
emergency stop), `Clock`, `Sleeper`, `FiberLauncher` (optional — a
host that owns its loop drives `step()` directly).

**Dependencies.** None. This is the bottom of the stack.

**Invariants.**
- *Vendored, synced copy*: extracted from the radio-robot firmware
  (`src/firm/control/`); a fidelity suite in that repo holds the two
  byte-for-byte to the same control law. Fix kernel bugs in both
  repos, never only here.
- Each `step()` runs split-phase encoder sampling:
  `requestSample()` → 4 ms settle sleep → `tick()` per wheel. Anything
  that lands other I2C traffic inside that settle window destroys the
  sample (see §7, bus discipline).
- Commands carry a lease; an expired lease means neutral on every
  subsequent step. `kLeaseMax` = 1 h.

## 3. Motion engine — `motion/motion_engine.h/.cpp` (`diffDrive::MotionEngine`)

**Responsibility.** The two-primitive reduction the whole motion
surface is built on (canonical spec: `radio-robot-lib`
`motion-api.md` §2): everything is a constant-ratio wheel segment.
Owns chassis geometry (`travelCalib`, `trackWidth`, `rotationalSlip`)
and the move engine — end-of-move taper, acceleration ramp,
wrong-way abort, pivot-then-straight splitting, deadline backstop.

**Public interface.**
- Primitives: `wheelsV(left, right, duration)` — velocity hold whose
  `duration` **is** the kernel lease; `wheelsX(left, right, cruise,
  timeout)` — per-wheel distances, ratio-locked so both wheels finish
  together, dead-reckoned lease capped by `timeout`.
- Reductions: `moveX(distance, rotation, cruise, timeout)` (a
  |rotation| ≥ 50° with nonzero distance splits into pivot-then-
  straight, one caller-visible call, one shared deadline);
  `moveV(vx, omega, duration)`; `goToR(x, y, speed, arrive, timeout)`
  (single-shot, no supervisory re-solve). **Sprint 006**: `goToR` now
  owns its own split decision instead of inheriting `moveX`'s generic
  one — `moveX`'s pivot-then-straight split reissues the arc's own
  `(s, theta)` as pivot-then-straight, which reaches a different
  endpoint than the blended arc whenever the split threshold fires
  (the arc-length `s` is not the chord length except in the limit);
  `goToR` above the threshold instead issues pivot = `atan2(y, x)`
  (the line-of-sight bearing) then chord = `hypot(x, y)` straight,
  which reaches `(x, y)` exactly by construction. `theta` is
  normalized to the short arc (±180°) before the split decision, so a
  behind-the-robot target pivots at most ~180° instead of the long way
  around. `arrive` is now honored as a radial no-op gate
  (`hypot(x, y) <= arrive` returns without issuing a segment) — still
  single-shot, no supervisory re-solve; a caller wanting repeat-until-
  arrival re-issues `goToR()` itself, unchanged from before.
  `goToW(pose, …)` (reads a caller-supplied `PoseSource` **once**,
  rotates world delta into the body frame, delegates to `goToR`) is
  unaffected by this change other than inheriting `goToR`'s corrected
  geometry.
- Move servicing: `serviceMove()` — one advance per control cycle
  while active: rescales taper/ramp, re-issues `kernel_.drive()`
  **every tick** with a rolling 500 ms lease (gating on scale change
  would let the lease expire in steady phases), checks completion
  margins (10 counts dist; 4 counts yaw pure-turn, 10 in an arc),
  deadline, stall, and wrong-way (signed yaw progress <
  −3×margin). `endMove()`, `isMoveActive()`, `progress()` (0..1000),
  `wrongWayCount()`, and the per-tour shaping setters
  (`setDistTaper`/`setYawTaper`/`setDistFloor`/`setTurnFloor`/
  `setRampMs`).
- Geometry: `countsPerMm() = 10 / travelCalib`;
  `effectiveTrackWidth() = trackWidth / rotationalSlip`, a method,
  deliberately never cached. **Sprint 007**: `rotationalSlip` gains
  `setRotationalSlip(float)`, validated `>0` exactly like
  `setTrackWidth()`/`setTravelCalib()` (invalid values silently
  ignored, prior value retained) — closing the one geometry field that
  had a getter but no setter (API-06: the doctrine already named
  `rotationalSlip` as the only correct turn-calibration knob, but no
  caller anywhere could reach it). Reachable from `shims.cpp` through
  the existing generic `ConfigField`/`kFields` mechanism (§5, §9), not
  a new dedicated `setGeometry()`-style shim — this field is a
  one-time chassis-calibration constant for a non-reference kit, not a
  value tuned as routinely as `trackWidth`/`travelCalib`.
- `PoseSource` — the three-read world-pose port (`x()/y()/heading()`),
  implemented by `OtosPort` on hardware, `EncoderPoseSource` on
  hardware without an OTOS (sprint 006, §7/§9), and `FakePoseSource`
  in tests. `MotionEngine` holds no `PoseSource` of its own; it is
  passed per `goToW()` call, which is what makes the class
  host-testable with no OTOS in the link. **Sprint 006**: the
  interface's `heading()` contract can no longer state a single wrap
  convention now that two hardware implementations disagree by
  construction — `OtosPort` reports heading wrapped to (−π, π] (the
  chip's own int16 register), `EncoderPoseSource` reports the same
  unwrapped heading `shims.cpp`'s odometry already carries. Both are
  contractually valid because `goToR()`/`goToW()` consume `heading()`
  only through `cos()`/`sin()` (wrap-invariant); the header comment now
  says so explicitly instead of asserting one universal convention —
  a caller that ever *differences* two `heading()` reads (rather than
  taking their cos/sin) must not assume a shared wrap convention across
  implementations.

**Key state.** `MoveState` (segment targets in counts, ramp start,
pending second phase, one `deadline` spanning both phases). Geometry
defaults are the vevov bake: `travelCalib` 0.7878 mm/deg, `trackWidth`
114.2 mm, `rotationalSlip` 0.952 — each with the measurement history
in the field comments.

**Dependencies.** Holds references to a caller-owned kernel and
`Clock` (the ramp and timeout need wall time independent of kernel
stepping). Owns **no odometry** — pose stays a `shims.cpp`/Rig
concern; callers update it around `serviceMove()`.

**Invariants.**
- `wheels_*` and every reduction **clears the planner first** — at
  most one move-engine move is ever active (motion-api.md §6).
- Never adjust `trackWidth` to fix a turn; the correction lives in
  `rotationalSlip` (see the system doc's geometry doctrine).
- The CCW sign convention is not re-derived from cable order anywhere
  in this file; host tests pin it.
- Only a **pure turn** tapers on yaw — in an arc the distance taper
  already scales twist by the same factor; an independent yaw taper
  double-counts (measured: legs pinned at the 25% floor, 2026-08-22).

## 4. Wire grammar — `comms/wire_handler.h/.cpp` (`Wire::WireHandler`)

**Responsibility.** Protocol v6's ASCII line-grammar mechanics plus
the reliability layer. `feed()` reassembles arbitrary byte blocks into
lines (240-byte ceiling; overlong lines are discarded whole, never
truncated into a parseable prefix), tokenizes in place on spaces (no
allocation, no `std::string`), enforces case-as-direction (commands
UPPERCASE, replies lowercase), and dispatches an 18-entry verb table:
HELLO, PING, ID, VER, STATUS, HELP, GET, SET, TLM, WHEELS_X, WHEELS_V,
MOVE_X, MOVE_V, GO_TO_R, GO_TO_W, STOP, ESTOP, RUN. **Sprint 007**:
`kCommandTable`'s size is now derived (`static const VerbEntry
kCommandTable[];`, defined with a deduced size plus a `static_assert`
pinning the expected count) instead of the size being hand-written
twice (declaration and definition both said `[18]`) — closing WIRE-09:
removing a verb without updating both `[18]`s used to compile silently
and zero-fill the vacated slot, which `strcmp()`s a `nullptr` on the
first lookup that reaches it (a hard fault on the robot, for every
command). No verb is added, removed, or reordered by this change — the
18 names above are unchanged; only how the array's size is spelled
changes. **Sprint 008**: the six motion verbs' `timeout`/`duration`
fields (`WHEELS_X`/`WHEELS_V`/`MOVE_X`/`MOVE_V`/`GO_TO_R`/`GO_TO_W`) now
pass through one shared decode-time clamp before any verb-specific
decode logic runs: `0` is rejected (`kRange`), and any value above
2^31−1 is silently clamped to 2^31−1. This closes WIRE-02/KERN-06
(R-06 — `WHEELS_X`/`MOVE_X` disagreeing about what `0` means, and a
`WHEELS_X … timeout 0` leaving a stale kernel lease armed with no
motion obligation tracking it) and WIRE-10/KERN-10-adjacent (R-18 — a
timeout above 2^31 wrapping the deadline arithmetic negative and
re-triggering the ticket-011 starvation-kill pattern for an input class
no prior test reached). Enforcing this once, at decode, in
`wire_handler.cpp`, rather than six times in each `wire_adapter.cpp`
handler, is deliberate: every downstream consumer (`WireAdapter`'s own
obligation-window math, `MotionEngine::wheelsX()`'s lease-clamp
arithmetic, the kernel's `drive()` lease) now only ever sees an
in-range value, so none of them individually needs to reason about `0`
or overflow — reject (not clamp) was the deliberate choice for the `0`
case specifically (sprint 008).

**Reliability layer.** Every sequenced verb carries a mandatory
trailing `#<id>`, strictly incrementing from 1. Handler state is
exactly one field — `expectedNext_` (2026-08-26: `gapOutstanding_` is
deleted with the telemetry ack piggyback, below) — with **no
clock or timer anywhere** in the class. `dispatch()` resolves the id
first: in-order ids decode **before** any reply (decode failure nacks
the same id and does not advance — "decode failure is a NAK"); stale
retransmits re-ack without re-executing; gaps nack and stall the
stream until the missing id arrives. Merits rejections (verb decoded,
adapter refused) ack-and-advance plus `err <code> #<id>` — kept
sharply distinct from decode failures. `lastDone`/`lastDoneReason` are
polled fresh off the Adapter on every ack/nack, never cached.
HELLO/PING/ESTOP/HELP/ID/VER/STATUS are unsequenced, intercepted before
id resolution. The rule (agreed with radio-robot-lib, protocol.md's
owner, 2026-08-27): **a verb is sequenced iff its correctness depends on
its position in the stream** -- either executing it twice changes the
robot, or answering it out of order yields a wrong answer. ID/VER/HELP
answer session constants; STATUS is the out-of-band diagnostic a
DESYNCED host must be able to send. GET stays sequenced despite being
read-only, because SET mutates what it reads. All unsequenced verbs take
the PING posture (forgiving of any trailing content), never HELLO's
strict zero-arity -- strict would make `ID #1` wrong-arity, and an
unsequenced verb has no ack to anchor an err against, so the reply would
be silence.

Note HELLO is a session RESET, not a liveness probe: it sets
expectedNext_ = 1, so firing it at a live session desyncs it. PING says
"alive"; STATUS says "alive, and here is where the sequence stands"
(next=/done=/reason=); HELLO says "start over".
(HELP joined this set 2026-08-27: it is the verb a human types first,
so answering it must not depend on knowing the grammar being asked
about; it is forgiving of any trailing content, like PING, and its
listing is emitted as several short lines so a marginal radio hop can
deliver it);
HELLO resets the sequence state (a reconnecting host's resync) but
never touches Adapter state. **There is no unsolicited ack/nack of any
kind (2026-08-26, stakeholder direction: "an ack or a nack is only a
response to a message, not a beacon").** The `emitReliability()`
keepalive — sprint 004 ticket 003's split, still riding as
`emitTelemetry()`'s third write after sprint 024 ticket 001 removed
its free-running form — is deleted outright: `emitTelemetry(const
Snapshot&)` emits a fresh `thdr <col>...` when one is due plus
`t <v>...` for the given frame, and nothing else. A subscriber that
wants to know whether its last command landed sends a command (e.g.
`STATUS`) and reads that command's own ack; a lost ack/nack heals via
the host's own retransmit or poll. The **application** still supplies
the frame cadence (protocol.cpp, 50 ms) for a TLM-subscribed host
(see §8's Fiber loop).

**`Adapter` seam.** The pure-virtual contract behind every verb:
identity/now/status, the six motion verbs (angles arrive as float
milliradians), estop/stop, GET/SET field delegation, TLM mode,
lastDone channel, and RUN's raw-token pass-through. Satisfied by
`WireAdapter` in production and `WireMockAdapter` in tests.

**`Column`/`Snapshot` value types (sprint 004 ticket 004; ticket 007's
correction).** `Column` (one telemetry value: `name`, `value`, `hex`)
and `Snapshot` (a borrowed array of `Column` plus a count) carry
default member initializers, which makes `Column` a non-aggregate
under C++11 — even though `tests/host/` compiles at C++20, where the
same rule does not disqualify it. `Column` therefore keeps an explicit
`Column() = default;` plus a 3-argument converting constructor so the
~20 `columns_[i++] = {"name", value, hex};` call sites in
`WireAdapter::buildSnapshot()` (§5) compile identically on both
standards, without dropping the NSDMIs (needed so a default-constructed
`Column columns_[kMaxSnapshotColumns]` never holds indeterminate
values) or touching any already-correct call site. `Snapshot` shares
the exact same defect under C++11 but is deliberately left unfixed: no
call site anywhere brace-initializes one (every site
default-constructs, then assigns `.columns`/`.count`), so it is a
latent structural twin, not a live one. This constructor pair is not a
style choice — see §11 for why silently removing it breaks the robot
build while every host test stays green.

**Invariants.**
- Decode functions are pure (no adapter call, no sink write); execute
  functions run only after the ack is already on the wire.
- Known, pinned characterization: an embedded NUL truncates the line
  at C-string comparisons (e.g. `PING\0extra` == `PING`); the one
  guarded case is a NUL as the first non-space byte (memory-safety,
  counted malformed).
- Duplicate-id handling has no error code by design — strict
  sequencing makes a duplicate structurally unreachable.

**Dependencies.** `Sink` (one `write()` per reply line, `\n`
included) and `Adapter`. Nothing else — host-portable by construction.

## 5. Wire adapter — `comms/wire_adapter.h/.cpp` (`diffDrive::WireAdapter`)

**Responsibility.** The concrete `Wire::Adapter` for this robot. All
six motion verbs have real effect: WHEELS_V → `setWheelsTimed()`
(duration ceiling 5000 ms, shared by MOVE_V — "a dead host cannot mean
a runaway"); WHEELS_X/MOVE_X/MOVE_V/GO_TO_R/GO_TO_W → the
`engineXxx()` forwards onto the `MotionEngine` singleton. `cruise`/
`speed` handling is uniform: negative → `kRange`; zero → the
configured default via `engineDefaultCruiseMmS()`, refused `kRange` if
that too is unconfigured. **Sprint 007**: `engineDefaultCruiseMmS()`
no longer derives from `fullDutyVelocity` (the kernel's ~875 mm/s
100%-duty rail) — it now reads a new, independently configured
`defaultCruiseMmS_` field (`shims.cpp` Rig state, seeded 150 mm/s to
match the block layer's own `defaultSpeed`), closing R-11/BLK-03/API-03:
the wire's "0 = configured default" convenience sentinel and the
kernel's unrelated "0 = uncalibrated, refuse" sentinel on
`fullDutyVelocity` were two different meanings of zero collapsed onto
one field — a spec-following host sending `cruise 0` got the fastest,
least-controlled move the robot can make instead of a sane default.
The four verb handlers' refusal-on-`<=0` logic above is **unchanged**;
only the value it reads changed. **Sprint 006**:
GO_TO_W no longer answers `kUnimplemented` for "no OTOS connected" —
`engineGoToW()` now falls back to `EncoderPoseSource` on any robot
without a live OTOS (§7/§9), so this handler always dispatches to
`MotionEngine::goToW()`. `mradToRad()`
here is the **single** place wire milliradians become radians.
GET/SET map snake_case wire names 1:1 onto the `ConfigField` ordinals
(`kFields` table) — 15 through sprint 006, **18 as of sprint 007**:
`default_cruise` (ordinal 15, backed by the new `shims.cpp` Rig field
above, not `kernel.config()`), `rotational_slip` (ordinal 16, backed
by `MotionEngine::setRotationalSlip()`/`rotationalSlip()`, §3), and
`stall_clear` (ordinal 17, a write-triggered action wearing a
config-field's clothes: `SET stall_clear <nonzero>` calls
`DifferentialDrive::clearStallLatch()`, already existed, previously
had no caller anywhere in the package outside a test shim; its GET
side is a convenience readback of `stallHalted`, not a stored value —
alongside the pre-existing STATUS `flags` bit 2 and `probe(2)`, now
documented, this is the third independent way to read the stall
latch's state). `stall_clear` is deliberately **not** a new top-level
wire verb and is **not** folded into `clearEmergencyStop()`/`ESTOP`
(§9) — the stall latch and the e-stop latch are semantically distinct
fault classes, same principle sprint 006 established for
`deliverStopNow()` deliberately not touching `estopLatch_`. STATUS
packs diag booleans into a local
`flags` word and, since sprint 004 ticket 004, an honest `otos=`
(`otosGet(7) != 0`, replacing a hardcoded `false` that predated any
wire-reachable OTOS check — R-22/WIRE-06) plus a decimal `i2cf=` fault
count sourced from the same `diagValue(8)` call the telemetry `i2cf`
column reads (see the Telemetry projection paragraph below), so the
two can never disagree. `onRun()` is an honest `kUnknown` — the real
by-name test trigger is protocol.cpp's MessageBus RUN bridge, a CODAL
mechanism this host-portable class must never touch.

**Motion-obligation tracking.** This class sees every accepted motion
verb, so it records `now + duration/timeout` as a deadline and exposes
`hasLiveMotionObligation()` for protocol.cpp's fiber to poll — that
fiber owns the actual `tickDrive()` call. Armed by **all six** motion
handlers (ticket 012 fixed a real ticket-011 bug where only WHEELS_V
armed it and every other verb's move starved and was watchdog-stopped
almost immediately). The clock arrives as a plain C function pointer
(`NowMsFn`), nullptr on hosts with no clock (obligation then always
false — honest). **Sprint 008**: the `duration`/`timeout` value every
handler reads here is now guaranteed already in-range (nonzero, ≤
2^31−1) by `wire_handler.cpp`'s shared decode-time clamp (§4) — no
handler here changed its own logic; the values arriving at
`motionObligationDeadlineMs_ = nowMs_() + timeout` simply can no longer
be `0` or large enough to matter for wraparound. **Sprint 016 ticket
003**: this flag used to clear in exactly two places, `onEstop()` and
`onStop()` — a goal-directed move (MOVE_X/GO_TO_R/GO_TO_W) that reached
its own goal long before its declared `timeout` left it armed anyway,
so protocol.cpp's fiber kept ticking the kernel for the rest of that
window regardless. `resolvePendingIfDue()` and `forceResolvePending()`
(the motion-completion machinery immediately below) now clear it too,
the moment either one commits a resolution — the natural-completion
path that was the actual gap.

**Telemetry projection (sprint 004 ticket 004).** `buildSnapshot()`
returns a `const Wire::Snapshot&` into a member (mirroring
radio-robot-lib's own `DiffDriveAdapter::buildSnapshot()`), built from
five more forward-declared `shims.cpp` reads: `poseX`/`poseY`/
`poseHeading` (each **mutates** odometry as a side effect — load-
bearing, not an accident to optimize away, since nothing else advances
odometry between moves and the 50 ms telemetry tick is what keeps pose
current); `otosGet` (a **cache-only** read — the protocol fiber must
never trigger a fresh OTOS sample, since an I2C transaction interposed
in the Nezha encoder's select→read settle window destroys the encoder
sample; `otosGet(0)`/`otosGet(1)` are 0.1 mm, `otosGet(2)` is already
centidegrees — do not also divide it); and `wheelSpeed`. POSE's 12
columns (`seq now flags x y h ox oy oh vl vr i2cf`) are always
present; FULL adds 8 more (`cyc posl posr dutl dutr lexc wrng cycovr`)
only in `TlmMode::kFull`. **Sprint 008**: `TlmMode::kAuto` and
`TlmMode::kBuffer`'s previously-undocumented fall-through to POSE's
column set is now a stated decision, not an accident:
`TlmMode::kAuto` is a documented alias for `TlmMode::kPose` (same 12
columns, same cadence — matches the pre-existing de facto behavior
exactly, so no wire-visible change), while `TlmMode::kBuffer` refuses
at the `TLM` verb itself (`kUnimplemented`) rather than silently
emitting POSE's columns — no buffering mechanism exists anywhere in
this codebase to give "buffer" real, narrower semantics yet, and
refusing is more honest than emitting a column set no one specified.
`telemetryEnabled()` (`mode_ !=
TlmMode::kOff`) lets protocol.cpp skip building a Snapshot at all for
a session with no subscriber (see §8's Fiber loop). `computeFlags()`
(wire_adapter.cpp, anonymous namespace) is now the single source both
`status()` and `buildSnapshot()` read, so STATUS's `flags=`/`i2cf=`
and the telemetry `flags`/`i2cf` columns can never drift apart.

**Motion-completion resolution (sprint 005 ticket 004).**
`lastDone()`/`lastDoneReason()` are the wire's completion channel, not
an inert surface: `armPendingMotion(id, goalDirected)` arms on every
accepted motion verb; `resolvePendingReason()` is the pure decision
(an estop/stall diag flag wins outright regardless of verb kind;
otherwise a goal-directed verb — MOVE_X/GO_TO_R/GO_TO_W — resolves
once `engineMoveActive()` goes false, `kStop` if the wire-side lease
was still live at that point or `kTimeout` if it had already elapsed;
a non-goal-directed verb resolves purely from that same lease);
`resolvePendingIfDue()` commits the result into `lastDoneId_`/
`lastDoneReason_` lazily, the moment either accessor is next polled;
`forceResolvePending()` handles the two edges a fresh command's own
arming can't wait for (an explicit STOP, or a later command
superseding a still-pending earlier one — `kAborted`). Both accessors
call `resolvePendingIfDue()` before returning, so polling either one
alone is enough to notice a completion.

**Dependencies.** `wire_handler.h`; `shims.cpp` free functions by
forward declaration only (`stopAll`, `estopAll`, `setWheelsTimed`,
`setKernelValue`, `getConfigValue`, `diagValue`, `engineWheelsX`,
`engineMoveX`, `engineDefaultCruiseMmS`, `engineMoveV`, `engineGoToR`,
`engineGoToW`, and — sprint 004 ticket 004 — `poseX`, `poseY`,
`poseHeading`, `otosGet`, `wheelSpeed`). Holds no kernel/engine/Rig
reference of its own.

## 6. Transports — `comms/serial_transport.*`, `comms/radio_transport.*`

**SerialTransport.** Owns the raw USB-serial byte stream and 0x0A
line delimiting; explicit `(buffer, length)` pairs, never
`ManagedString`. `begin()` grows CODAL's default ~20-byte serial rings
to `kRingBytes` (sprint 004 tickets 006/007). That number is a real
ceiling, not a tuning choice: codal-core's `setRxBufferSize()`/
`setTxBufferSize()` (`inc/driver-models/Serial.h`) take a `uint8_t`
size, capping at 255. `kRingBytes{255}` leaves only ~15 bytes of
headroom above one full 240-byte line — enough for one maximal line
plus a little slack, **not** enough to hold two full lines
concurrently. Ticket 006's original intent (`2 * kMaxLineBytes` = 480)
silently truncated to 224 on assignment — *below* `kMaxLineBytes`
itself, defeating the resize with nothing but an easy-to-miss
`-Woverflow` warning as the signal — which is why the constant changed
under ticket 007 and is now brace-initialized so a future edit that
overflows it again is a compile error, not a repeat of the same silent
truncation. `tryReadLine()` (the one Protocol uses) never sleeps:
drains buffered bytes into a 240-byte partial-line accumulator across
calls. `kMaxLineBytes` = 240 is deliberately kept equal to
`WireHandler::kMaxLineBytes` so this transport is never the tighter
cap (a 201–239-byte line would otherwise be truncated one layer below
the tested discard-whole-line guarantee). `writeLine()`'s two-writer
guard (sprint 004 ticket 006) is a **bounded retry inside the call
itself**: a second caller finding the guard held sleeps `fiber_sleep(2)`
and checks again, up to `kMaxSendAttempts = 5`, before giving up and
counting a drop — deliberately a *different* policy from
`RadioTransport::sendLine()`'s drop-and-retry-once below (the sprint's
architecture review explicitly approved keeping the two distinct:
serial has no caller whose loss is "fine" the way telemetry's
self-healing `seq` gap makes radio's drop acceptable). The drop
counter is exposed at diag ordinal 26 (`probe(26)`/`diagValue(26)`,
`shims.cpp`).

**RadioTransport.** Frames wire lines for the fleet's RADIOBRIDGE
relay: `[SEQ][FLAGS][LEN][payload]` fragments (START/MORE/END flags),
a TX-only port of the fleet's robot-side radio driver. Radio enable is
lazy (group 10 by default, channel 4 — vevov's fleet assignment —
power 7). Group is the one field a student program can change, via
`setGroup()`/the blocks layer's "set radio group" block (sprint 021
ticket 005). The supported path is calling it from `on start`, before
the radio has come up: `setGroup()` just stores the value, and
`ensureRadioReady()` reads it during lazy bring-up. Calling it after
the radio is already armed re-applies immediately via
`uBit.radio.setGroup()` so the call is not a silent no-op, but whether
that re-apply actually changes what an already-armed radio receives on
is UNVERIFIED on this hardware — no test of that path has been run.
Channel and power stay fixed constexpr values with no settable
surface. RX is
a single-fragment command plane: `tryReceiveLine()` consumes a flag
set by the MICROBIT_RADIO_EVT_DATAGRAM handler — `datagram.recv()` is
**only** called inside that handler because polling an empty queue
kills the program within two polls (measured; CODAL EmptyPacket
refcounting). Multi-fragment inbound reassembly is deliberately out of
scope. Send-path scratch buffers are members, not stack locals — the
protocol fiber's 2 KB stack overflowed and hard-faulted with them on
the stack (measured). Those buffers are no longer single-fiber-only
(sprint 004 ticket 002): the protocol fiber (via `RadioSink::write()`)
and the TS fiber (via `Protocol::emitLine()`) both call `sendLine()`
now, guarded by a `sending_` bool — the second caller in returns
`false` untouched. `emitLine()` retries once after `fiber_sleep(2)`;
`RadioSink::write()` ignores the drop by design (a lost `t` frame
self-heals via the next `seq` gap). Not host-testable (this file
includes `pxt.h`); verified by code review, first exercised live at
the bench. **Sprint 008**: `kMaxPayloadBytes`'s own doc comment
previously claimed it was "sized the same as SerialTransport's bound"
— false since ticket 005 (sprint 004) raised `SerialTransport`'s
`kMaxLineBytes` to 240 while this constant stayed 200; the comment now
states the true relationship: `kMaxPayloadBytes` is deliberately the
**tighter** of the two transports' caps, and `protocol.cpp`'s
`emitLine()` (§8) now names this constant directly instead of
re-declaring its own bare `200` literal, so the two can never drift
apart silently again the way they already had (WIRE-05/R-21). The
*value* is unchanged — still 200, still radio's real capacity ceiling
— this sprint single-sources the constant, it does not raise radio's
capacity: that is `radio-rx-capacity-fragmentation.md`'s scope (sprint
010), which also already tracks the adjacent, still-open finding that a
legal `FULL`-mode telemetry frame can itself reach up to 239 bytes,
above this same cap (§10's Open Questions).

**Layering.** Both know bytes and framing only — no verbs, no COBS,
no semantics. Siblings under Protocol, deliberately uncoupled from
each other.

## 7. Hardware ports — `platform/nezha_port.*`, `platform/otos_port.*`, `core/heading_wrap.h`, `core/encoder_glitch_armor.h`, `platform/platform_ports.h`

**NezhaMotorPort** (`DiffDrive::Motor` over I2C 0x10). The
write-shaping pipeline is not styling — each stage guards a measured
hardware failure: exact-zero short-circuit (the brick latches its last
commanded speed across MCU resets, so stop is never shaped, throttled,
or slewed); stopNotTaken re-write; reversal dwell through zero (an
instant H-bridge flip latches the 0x46 encoder readback — the
"encoder wedge"); sigma-delta integer-percent quantizer whose carry is
discarded on zero so a stopped wheel cannot creep; min-write throttle
+ slew, both bypassed for stops. Encoder sampling is split-phase
(select 0x46 → 4 ms settle → read), counts never device-reset —
rebaseline is a software offset (`rebaseline()`, offset-only, no bus
traffic).

**`EncoderGlitchArmor` (`encoder_glitch_armor.h`, sprint 006 — new
host-portable module).** The raw-counts plausibility decision that used
to live entirely inside `NezhaMotorPort::collect()` — implausible-jump
rejection, two-strike accept — extracted into a small header with no
`pxt.h`/I2C dependency, alongside `motion_engine.h` in spirit: a pure
function of `(rawCounts, lastGoodRaw, rejectPending)` returning one of
three decisions (`kAccept` — plausible, integrate as motion;
`kAcceptAsRebaseline` — a second consecutive self-consistent reading
after an implausible jump, but now treated as *the counter restarted*,
not *the wheel teleported*; `kRejectPending` — first implausible
reading, hold and wait for a second). This changes KERN-07/R-07's
existing two-strike behavior: previously the second consistent reading
was accepted as a real ~4 m position jump; now that same trigger is
routed to `kAcceptAsRebaseline`, which `NezhaMotorPort::collect()` (the
thin, hardware-only caller) turns into an offset re-anchor
(`encOffset_ = raw`, matching the existing manual `rebaseline()`'s own
software-offset technique) instead of an integrated jump — position
stays continuous, velocity reads as the (small) real motion during the
gap rather than a multi-m/s spike. `NezhaMotorPort` is the only
caller; the class is otherwise unaware of I2C, CODAL, or the kernel.
Host-tested directly (no fakes needed — it has no hardware dependency
to fake); see §11 for this module's C++11 syntax-gate coverage.

**OtosPort** (SparkFun OTOS, I2C 0x17; implements `PoseSource`).
Ported verbatim from the reference firmware: register map, distinct
velocity LSB scales (decoding velocity with the position constants
reads 2× high / 11.1× low — measured), boot-time zeroing of the
chip's offset **and** scalar registers (the chip survives nRF resets
and silently inherits a previous session's values — measured 42.7 mm
pivot circle from a stale arm). The lever arm is applied in
**software** on every read/seed; the chip's own offset register is
held at zero — applying both double-corrects. **Sprint 006**:
`setPose()` now wraps the heading channel into (−π, π] before handing
it to `writePoseMm()`'s quantizer — the chip's heading register is a
wrap-mandatory quantity (full scale ±π) that `writePoseMm()` was
clamping like a length (x/y keep the clamp; only the heading channel
gains a wrap). A seed heading of 350° (a 0–360° convention source, or
the deliberately-unwrapped odometry heading echoed back through
`seedPose()`) now lands at the equivalent −10° instead of clamping to
+179.89°, keeping the OTOS and encoder pose sources agreed at seed
time — the disagreement `seedPose()`'s own drift-measurement contract
depends on not existing yet. **Host-testability note**: `otos_port.h`
includes `pxt.h` unconditionally (§1), so `OtosPort` itself cannot be
compiled into any host test — there is no existing seam that exercises
its I2C-bound methods host-side. The wrap math therefore needs the same
treatment as `EncoderGlitchArmor` below: a tiny host-portable helper
(`heading_wrap.h` — one pure function, no dependencies at all, smaller
in scope than `encoder_glitch_armor.h`) that `setPose()` calls and that
a host test exercises directly, proving the same LSB round-trip
(350° → −10°) the real register write would produce without needing
I2C in the link.

**`EncoderPoseSource` (`encoder_pose_source.h`, sprint 006 — new
host-portable module).** A second `PoseSource` implementation over
`shims.cpp`'s existing dead-reckoned odometry (`Rig::x/y/heading`), for
robots with no OTOS fitted — most of the fleet (the OTOS is on vevov
only). Three-method port, same shape as `OtosPort`: holds const
references to the Rig's already-computed `x`/`y`/`heading` floats and
returns them verbatim — it does not compute odometry itself. It is
constructed as a `Rig` member (or otherwise lifetime-tied to `Rig`'s
own lazy-singleton, process-lifetime instance) so the references it
holds never outlive their target — the same lifetime relationship
`MotionEngine`'s own `kernel_`/`clock_` references already have to
their `Rig`-owned targets; this is not a dangling-reference risk so
long as no `EncoderPoseSource` is ever constructed with a shorter
lifetime than `Rig` itself. It does not need its own epoch-tracking for the "epoch-guarded rebaseline"
motion-api.md §3.6 calls for, because it reads the same Rig-local state
`odomUpdate()` already produces, and `EncoderGlitchArmor` above already
makes that state continuous across a detected brick-reset — the
guarantee is inherited, not re-implemented. Heading is reported
unwrapped, matching `shims.cpp`'s existing odometry contract (§3's
`PoseSource` note on the two implementations' differing wrap
conventions). Host-portable and host-tested the same way
`FakePoseSource` already is.

**Bus discipline (system invariant).** The Nezha brick and the OTOS
share one I2C bus. Every OTOS transaction must run on the same fiber
that ticks the kernel; an OTOS read interposed in the encoder's
select→read settle window destroys the encoder sample.

**platform_ports.h.** One-line CODAL implementations of
`Clock`/`Sleeper`/`FiberLauncher`
(`system_timer_current_time_us`/`fiber_sleep`/`schedule`/
`create_fiber`).

## 8. Protocol composition — `comms/protocol.h/.cpp` (`diffDrive::Protocol`)

**Responsibility.** The CODAL fiber that plumbs bytes between the
transports and the v6 wire stack — it knows nothing of the grammar
itself. Composition by NSDMI in declaration order: `SerialSink`/
`RadioSink` (each strips the trailing `\n` WireHandler supplies,
because its own transport appends its own), a single `WireAdapter`
(constructed with a placeholder identity; `run()` installs the real
one via `setIdentity()` once the fiber is executing — the proven-safe
time to call `microbit_friendly_name()`/`microbit_serial_number()`),
then **two** `Wire::WireHandler` instances — `wireHandler_` (serial)
and `wireHandlerRadio_` (radio, sprint 004 ticket 001) — composed over
that **same** `WireAdapter` instance, not two adapters. Each handler
still keeps its own `expectedNext_` (a plain instance
member) — the whole point: two independent hosts share one robot's
adapter state without one transport's sequence gap nacking the
other's next command.

**Fiber loop (`run()`).** Sends the boot banner unsolicited
(byte-identical to HELLO's reply), then forever: poll serial
`tryReadLine()` — lines with the literal `RUN:` prefix go to the
legacy MessageBus bridge, everything else is `feed()`'d to
`wireHandler_`; poll radio RX the same way (sprint 004 ticket 001,
closing sprint 003's own Open Question 4) — lines with the literal
`RUN:` prefix go to the same legacy bridge, preserved unchanged as a
fallback, everything else — the full v6 grammar — is `feed()`'d to
`wireHandlerRadio_` instead; every 50 ms, if
`wireAdapter_.telemetryEnabled()`, call `wireAdapter_.buildSnapshot()`
**once** and hand that same `Snapshot` reference to both handlers'
`emitTelemetry(snapshot)` (sprint 004 tickets 003/004) — building it
twice would double-advance `seq_` and mutate odometry twice, and would
report different `seq`/`now` to serial vs radio for what should read
as the same instant; with telemetry off (the boot default, or on any
tick where no host has subscribed), the tick emits nothing at all —
2026-08-26: `emitReliability()` is deleted (no unsolicited ack/nack on
any path; §"Reliability layer" above); and while
`wireAdapter_.hasLiveMotionObligation()`, call `tickDrive()` itself
(the fiber is the tick source for wire-issued motion), else
`fiber_sleep(5)`.

**RUN bridge (legacy, deliberately preserved).** `RUN:<name>[:<arg>…]`
parks the payload in a 4-slot ring (MessageBus events queue; a
one-minute test handler must not have its text overwritten by the next
burst) and raises event source 0x2001 with the slot as the value;
`run.ts` reads it back via `runCommandText()` (sprint 012: this shim
body itself lives in `sim.ts`, called cross-file — see §9) and
dispatches by name on the handler's own fiber. 3 s same-text dedupe
absorbs hosts repeating commands to survive the single-slot radio
buffer (measured: one 3×-repeated RUN ran three consecutive pivots).
**Sprint 008**: the literal event source `0x2001` above and `run.ts`'s
own (sprint 012: formerly `main.ts`'s)
`RUN_EVENT_SOURCE = 0x2001` are two independent hand-typed copies of
the same MessageBus event id (WIRE-01-adjacent minor, R-21) — now
pinned by a drift test that reads both source files as text and fails
if they diverge, rather than single-sourced across the TS/C++ boundary
(no shared-constant mechanism crosses that boundary today; a drift test
is the same shape sprint 004/006/007 already use for cross-language
pairs like this).

**`emitLine()`** writes one caller-supplied line to **both**
transports — test results must come back over radio because USB only
reaches the bench stand, where the wheels are off the ground.
**Sprint 008**: its cap now names `RadioTransport::kMaxPayloadBytes`
directly instead of re-declaring its own bare `200` literal (WIRE-05/
R-21) — this constant is deliberately the **tighter** of the two
transports' caps (radio's, not serial's 240), chosen so a line this
call clips never depends on which transport happens to carry it; the
previous bare literal was numerically correct but disconnected from
that rationale, which is what let it read as merely stale once ticket
005 raised serial's own cap independently. `kMaxPayloadBytes` itself
moves from `private` to `public` on `RadioTransport` to make this
reference possible — a one-line access-specifier change with no
encapsulation cost (it stays a compile-time constant, still used
in-class to size `payloadBuf_`. Note that `RadioTransport`'s other
size/framing constants — `kFrameHeaderBytes`, `kGroup`, `kChannel`,
`kTransmitPower` — remain `private`, and only `kMaxPayloadBytes` was
moved: nothing outside the class needs to name the others, so widening
them would be access-loosening without a caller to justify it).
Single-sourcing the name, not the value, closes the drift risk without
touching radio's actual capacity (sprint 010's scope, §6). Since
sprint 004 ticket
002, the radio half checks `RadioTransport::sendLine()`'s bool return:
`false` means its re-entrancy guard fired against the protocol fiber's
own concurrent `RadioSink::write()`, and — because this is the one
caller whose loss is user-visible (a test's own recorded result) —
this retries once after `fiber_sleep(2)` before giving up silently,
not in a loop.

**Lifecycle.** Lazy singleton `protocol()`, started by a top-level
`_startProtocol()` call the moment the extension's compiled code loads
— never a global constructor (uBit.init ordering). **Sprint 012**: the
call site lives in `motion.ts` (formerly `main.ts`); the shim body it
calls lives in `sim.ts`. This is the one load-time file-order
constraint the sprint 012 split has to satisfy — `sim.ts` must be
listed before `motion.ts` in `pxt.json`'s `files` array, or this call
resolves to nothing the moment the namespace loads. Identity
constants: drivetrain "diffdrive", profile injected per-robot at deploy
time by `tools/make_deploy.py` (the checked-in literal is an un-baked
placeholder, never a real fleet robot name -- see `protocol.cpp`'s own
`kProfile` comment), version. **Sprint
008**: `kVersion` no longer hand-mirrors `pxt.json`'s version as a
literal that can silently drift (it had, by ten version bumps —
WIRE-01/MOD-01/BLK-09, R-17) — it is now single-sourced or drift-tested
against `pxt.json` (the specific mechanism is a build-time-feasibility
call made during ticket execution) so `ID`/`VER`'s wire reply can no longer misreport the build a
host is actually talking to, restoring the `mbdeploy` → `VER`
deploy-verification flow's own precondition.

**Telemetry gap (closed, sprint 004; consumer retrofit closed, sprint
005).** The old periodic cleartext `TLM:` line was retired with v5 and
had no v6 replacement through sprint 003. Sprint 004 built the
replacement: ticket 003 added the `thdr`/`t` frame mechanics (§4's
`emitTelemetry()`/`emitReliability()` split); ticket 004 wired the
real projection (§5's `WireAdapter::buildSnapshot()`) so a `t` frame
actually carries live pose/OTOS/wheel-speed/fault-count data once a
host subscribes via `TLM`. `tools/tlm.py` (sprint 005) now decodes
this frame directly — header tracking, seq-gap loss counting with
7-bit wraparound, orphan-frame accounting, CSV + meta sidecar output,
two fail-loud guards — with its own test suite
(`tests/tools/test_tlm.py`); this firmware never emits the old `TLM:`
prefix again, and nothing in `tools/` still depends on it.

## 9. Shim + blocks — `shims.cpp`, `blocks/sim.ts`, `blocks/run.ts`, `blocks/pose.ts`, `blocks/stop.ts`, `blocks/world.ts`, `blocks/motion.ts`

**shims.cpp** is the composition root and the MakeCode-facing C++
surface. The lazy-singleton `Rig` composes: two `NezhaMotorPort`s
(left M1 `-1`, right M2 `+1` — vevov wiring), the CODAL ports, the
kernel (tovez-bake defaults + `twistHoldGain` 2.0, cadence 24 ms),
and the `MotionEngine` (declared **after** the kernel — member init
follows declaration order). `ensure()` calls `kernel.begin()` but
**not** `kernel.start()` — the pure tick model — and launches the one
background fiber this file owns, the starvation watchdog.

Pieces the kernel deliberately does not contain:

- **Odometry** (`odomUpdate`): differential dead-reckoning from
  kernel `Output` positions using the engine's geometry
  (`countsPerMm`, `effectiveTrackWidth`), midpoint-heading
  integration into Rig-local `x/y/heading`. **Sprint 006**: `tickDrive()`
  now folds `odomUpdate()` into **every** tick unconditionally, not
  only while a move-engine move is (was) active — continuous-mode
  driving (`setWheels`/`driveTwist` under a `while (tickDrive())` loop)
  previously updated pose only on the next explicit pose read, which
  integrated the whole driven interval as one straight chord regardless
  of actual curvature (UC-009's "pose is always live-updated from
  odometry regardless of command mode" was aspirational, not true,
  before this fix). `updateMove()`'s own odometry gate (only while a
  move is active) is unchanged — that path is move-engine polling, not
  continuous-mode driving, and stays correct as-is.
- **Tick engine** (`tickDrive()`): one `kernel.step()` +
  `serviceMove()` on the caller's fiber, then absolute-deadline
  self-pacing to the kernel's configured 24 ms cadence (re-anchored
  after gaps). A cooperative-fiber `stepBusy` flag serializes
  concurrent tickers. **Sprint 008**: on the tick that ends a move,
  `tickDrive()` now calls a new `MotionEngine` settle helper instead of
  running its own inline loop — the helper steps the kernel up to 12
  times, breaking early once both wheels measure at rest, identical
  behavior to the loop it replaces (measured: without this step, the
  neutral never reached the motors before the `while (tickDrive())`
  caller exited, +9–13° per turn). `tickDrive()` still calls
  `odomUpdate(r)` once, itself, immediately after the helper returns —
  folding coast counts into Rig-local odometry stays a `shims.cpp`
  concern, unmoved by this extraction; only the settle/rest *decision*
  (how many steps, when to stop) crossed into `motion_engine`, which
  needed nothing more than the already-host-portable
  `kernel.step()`/`kernel.output()` surface to make that decision. This
  is a narrower cut than sprint 003 ticket 013's own note anticipated
  ("extracting cleanly would mean moving odometry ownership into
  motion_engine too") — that concern applies to extracting the whole
  settle-then-integrate behavior as one unit; it does not apply once the
  settle decision and the odometry fold are kept as two separate calls,
  which is what this sprint does. The extracted helper is now
  **host-tested directly** (exercised via `motion_engine_shim.cpp`
  extended with `meSettleToRest`/`meArmSettleProfile`, plus
  `fake_ports.h`'s `FakeSleeper::onSleep` hook sprint 006 added, reused
  here to script a decaying velocity profile across the helper's own
  internal step loop — `kernel_shim.cpp` has no `MotionEngine` instance
  to call the method on, so this ticket extended the existing
  `motion_engine_shim.cpp` instead, per its own header comment: "extend
  this file's function list, don't invent a second shim") — closing the
  gap sprint 003's own regression test could only argue for by proxy. No
  new fiber or ticker is introduced; the one-fiber-ticks-a-move
  constraint (§4/§8) is unaffected — `tickDrive()` is still the loop's
  only caller.
  **Sprint 007**: `tickDrive()`'s
  return value changes from raw post-`serviceMove()` move-engine state
  to `commandLooksActive(r)` (the same helper the starvation watchdog
  below already used and proved correct in production — move-engine
  active **or** nonzero applied duty), closing R-10/API-01: the
  documented `while (diffDrive.driveTick())` continuous-drive idiom
  (README, spec §4.2, UC-002) exited on its first iteration, because
  `wheelsV()`/`wheelsX()` clear the move planner before `tickDrive()`
  is ever called, so raw move-engine state read `false` immediately.
  `commandLooksActive()`'s existing "or nonzero applied duty" clause is
  exactly what a continuous-mode command needs; for a position-mode
  move's final tick, the settle loop just above already drives
  `appliedDutyLeft/Right` to zero before this function returns, so the
  documented "a move's final tick still returns false, ending the loop
  on the same call that finishes the move" behavior is preserved with
  no new logic. No doc site's prose changes meaning.
- **Stall latch clear + readback** (new, sprint 007): the kernel's
  `clearStallLatch()` and `Output.stallHalted` already existed and were
  already correct (R-01/API-02's finding was a **missing caller**, not
  missing kernel logic) — `clearStallLatch()`'s only caller anywhere in
  the package was a host-test shim, and the only readback was an
  undocumented `probe(2)`. Two thin new `shims.cpp` forwards close
  this: `clearStall()` (calls `kernel.clearStallLatch()`) and
  `isStalled()` (returns `kernel.output().stallHalted`), each reachable
  from a dedicated Drive-group block (`clearStallLatch()`,
  `isStalled()`) parked next to `emergencyStop()`/`clearEmergencyStop()`
  — and, on the wire, `stall_clear`'s new `kFields`/`ConfigField`
  ordinal (§5) reaches the same `clearStallLatch()` call via
  `setKernelValue()`'s ordinal 17. Deliberately **not** folded into
  `clearEmergencyStop()`/`ESTOP` — same principle sprint 006 established
  for `deliverStopNow()` deliberately not touching `estopLatch_`: the
  stall latch and the e-stop latch are semantically distinct fault
  classes, and blurring their clear paths would reintroduce the
  ambiguity that decision fixed for a different pair.
- **Stop delivery** (sprint 006, new): `stopAll()`/`endMove()`
  (`stop`/`stop move`) and `updateMove()`'s own move-completion branch
  (the `isMoving()`/`move progress` poller's path, which can end a move
  at its deadline without ever calling `tickDrive()`) now each also
  call a small shared helper that pushes an immediate, port-level
  zero write to both motors — the exact same primitive the starvation
  watchdog already uses (`Motor::emergencyStop()`, tick-independent,
  never touches the kernel's e-stop latch) — in addition to staging
  `kernel.neutral()` as before. This closes R-08/BLK-01: previously a
  stop/move-completion issued from a fiber other than the one currently
  inside `kernel.step()`'s ~8 ms settle window staged a neutral that
  was not delivered to the motors until that settle window's step()
  returned *and* another tick ran — which, if the tick loop had already
  exited (exactly the case when the completing/stopping call is what
  ended it), meant no further step() ran at all until the ~100–150 ms
  starvation watchdog fired. The fix adds no new fiber/ticker (the
  "one ticker per move" invariant, `settle-tick-loop-is-not-host-
  testable`, is unaffected) and does not touch the vendored kernel
  (`diffdrive.{h,cpp}` stay byte-unchanged, so no cross-repo resync is
  needed) — it is entirely a `shims.cpp`-level composition reusing an
  existing, already-proven primitive.
- **Starvation watchdog**: every ~50 ms, if something looks active
  (`isMoveActive()` or nonzero applied duty) and no tick has run for
  ~100 ms, it calls `kernel.neutral()`, `engine.endMove()`, and
  port-level `emergencyStop()` on both motors — a *resumable soft
  stop* that never touches the e-stop latch, so a fresh tick resumes
  motion with no clear step. Unchanged this sprint; the stop-delivery
  fix above reuses this same port-level primitive rather than adding a
  new mechanism.
- **Wire bridges**: `setWheelsTimed`/`driveTwistTimed` (duration =
  lease), the six `engineXxx()` forwards, `engineDefaultCruiseMmS()`,
  `diagValue()` (the DIAG/STATUS ordinal table),
  `getConfigValue`/`setKernelValue` (the ×1000 table, 15→18 ordinals as
  of sprint 007 — see §5), `probe()`, taper/ramp setters, `wheelSpeed()`.
  **Sprint 007**: `engineDefaultCruiseMmS()` no longer derives from
  `fullDutyVelocity`; it returns a new `defaultCruiseMmS_` Rig field
  (seeded 150 mm/s), settable/gettable through `setKernelValue`/
  `getConfigValue` ordinal 15 (§5). `diagValue(2)` (`stallHalted`,
  already existed) gains a name in `probe()`'s doc comment instead of
  staying an undocumented magic index. `diagValue()`'s own switch has
  its spliced `case 25` (between the "23/24" comment and cases 23/24)
  reordered — a reader trap, no behavior change.
- **OTOS surface**: a lazy singleton **separate from Rig** (usable
  without starting the drive), `otosBegin/otosRead/otosGet/otosZero/
  otosCalibrate/otosSetOffset`, `seedPose()` (writes **both** pose
  sources so their later divergence is the drift being measured — now
  correctly agreed at seed time for any heading, per §7's OTOS heading-
  wrap fix). **Sprint 006**: `engineGoToW()` no longer refuses when the
  OTOS is not connected — it now selects `OtosPort` when connected,
  `EncoderPoseSource` otherwise (§7), in this one place, and always
  dispatches to `MotionEngine::goToW()`. This closes
  `no-encoder-odometry-posesource-fallback`: GO_TO_W (and the block
  API's world-pose moves that route through it) is no longer a no-op
  on the fleet's OTOS-less robots (tovez, gopiv, zeguz) — it drives on
  dead-reckoned odometry instead, a materially weaker (drifting)
  promise than the OTOS gives, which the ticket's own documentation
  update states plainly rather than leaving the two verbs looking
  identical.

**The TypeScript side** owns the student units and the block API
(groups Drive, Move, Pose, World, Setup), the browser-simulator
fallback bodies (a kinematic stand-in that mirrors the tick engine's
24 ms pacing), and the RUN dispatcher. **Sprint 012** split this out of
a single `main.ts` into six cohesion-sized modules. Current structure:

- **`motion.ts`** — the `ConfigField` enum, the two movement-default
  `let`s (`defaultSpeed`/`defaultYawRate`) and their Setup-group
  setters (`setDefaultSpeed`, `setDefaultYawRate`, `setTrackWidth`,
  `setWheelCalibration`, `setConfigValue`), continuous-mode drive
  (`setWheelSpeeds`, `driveTwist`, `driveTick` — Drive/Move groups),
  position-mode move (`move`, `goTo`, `startMove`, `startGoTo`,
  `isMoving`, `moveProgress`, `stopMove`, `whileMoving`,
  `whileGoingTo` — Move group), and the namespace's one load-time
  side-effecting statement, the top-level `_startProtocol()` call.
- **`pose.ts`** — `poseX`, `poseY`, `heading`, `resetPose` (Pose
  group). Reads local (encoder-odometry) pose only; never touches the
  world/OTOS sensor.
- **`stop.ts`** — `stop`, `emergencyStop`, `clearEmergencyStop`,
  `isStalled`, `clearStallLatch` (Drive group). Owns the two
  independent fault latches (e-stop, stall) and nothing else.
- **`world.ts`** — OTOS world-pose tracking (`startWorldTracking`,
  `worldTrackingReady`, `seedPose`, `readWorld`, `worldX`/`Y`/
  `Heading`, `calibrateWorldSensor`, `setWorldSensorOffset`) and
  `goToWorld` with its own tuning state (`arriveTolCm`,
  `turnFirstDeg`) and private `tickedMove()` runner (World group).
- **`run.ts`** — the RUN command dispatcher: the no-initialiser state
  block (`runParts`/`runNames`/`runHandlers`/`runAnyHandlers`/
  `runWired`), `ensureRunState()`, `RUN_EVENT_SOURCE`,
  `wireRunDispatch()`, `onRun`/`onRunCommand` (Move group in the
  toolbox, despite being dispatch machinery — the block `group=` and
  the module boundary diverge here), and the block-hidden
  `runArg`/`runArgText`/`runArgCount`. Fully
  self-contained: nothing outside this file reads or writes its state.
- **`sim.ts`** — every `//% shim=`-annotated function's TypeScript
  body: the kinematic browser-simulator state (`simX`/`simY`/
  `simHeading`/`simVel`/`simYawRate`/…) and its per-tick integration
  (`simIntegrate()`), the shim bodies that give the browser real
  motion/pose/stop behaviour (`_setWheels`, `_driveTwist`,
  `_startMove`, `_updateMove`, `_tickDrive`, `_progress`, `_endMove`,
  `_stopAll`, `_estopAll`, `_estopClear`, `_poseX`/`Y`/`Heading`,
  `_resetPose`, `_seedPose`), and the no-op stand-ins for shim-only
  surface with no browser model at all (`_clearStallLatch`,
  `_isStalled`, `_setGeometry`, `_setKernelValue`, `_startProtocol`,
  `probe`, `setTaperWindows`/`Floors`/`RampMs`, `otosBegin`/`Read`/
  `Get`/`Zero`/`Calibrate`/`SetOffset`, `emitLine`, `runCommandText`).
  The issue that proposed this split named a `sim.ts` row and a
  separate `shims.ts` row; verified against the real file, that
  boundary does not exist — nearly every `//% shim=` function's body
  *is* the simulator fallback, interleaved throughout, not two
  contiguous halves — so they are one module here.

Notable design points, all measured the hard way and unchanged by the
sprint 012 split (module attribution updated to the file each now
lives in):

- Continuous-mode commands (`setWheelSpeeds`/`driveTwist`, `motion.ts`)
  only move the robot while a `while (diffDrive.driveTick())` loop
  ticks; blocking moves tick internally. **Sprint 007**: this is now
  true in fact, not only in prose — `driveTick()`'s return contract fix
  above is what makes it true; the simulator's own `_tickDrive()`
  (`sim.ts`) gets the same fix (returns "does anything still look
  commanded" — sim move active, or nonzero `simVel`/`simYawRate` —
  instead of raw sim move-engine state) so the browser and hardware
  idioms match. `startMove`/`startGoTo` + polling does **not** advance
  a move by itself — a documented tick-model gap, unchanged this
  sprint.
- **Sprint 007, simulator/hardware parity** (`sim.ts`): `_setWheels`'
  sim body drops a stray `/10` in its yaw-rate term
  (`(right-left)/10/track` → `(right-left)/track`) that made simulator
  turns 10× slower than hardware for the same `set wheel speeds` call
  (R-12/BLK-06) — the formula now matches `_driveTwist`'s own,
  already-correct sim math. A `simEstopped` flag, set in `_estopAll()`
  and cleared in `_estopClear()`, gates `_setWheels`/`_driveTwist`/
  `_startMove` (checked, no-op while set) — mirroring hardware's
  intake-time refusal (`checkCommandable()`'s `estopLatch_` gate) so
  `emergency stop` now refuses further motion in the browser exactly
  as it does on hardware (R-13/BLK-07); previously the simulator
  refused nothing, so the UC-011 "forgot to clear" trap was invisible
  exactly where students develop.
- **Sprint 007**: `runArgCount()` (`run.ts`) gains the null guard its
  sibling `runArgText()` already had (`if (!runParts) return 0`) —
  closing R-15/BLK-02, a documented silent-boot-death (panic 980) class
  for any call before the first RUN event registers a handler.
- `goToWorld()` (`world.ts`) is this project's own TS-level closed-loop
  heuristic (one pass, pivot-first beyond 12°, curvature capped at
  25°, residual error inherited by the next hop) — deliberately a
  separate call path from the wire's GO_TO_W/`MotionEngine::goToR`
  plain reduction. The OTOS is read here, between moves only.
- The `run*` state arrays (`run.ts`) are declared **with no
  initialisers** — namespace initialisers run after a test file's
  top-level code, so an initialiser both crashes early registration
  (silent boot death, panic 980) and would wipe handlers already
  registered. **Sprint 012 preserves this verbatim** — it does not
  become the split's file-order problem (see below); it is a
  same-file, self-contained pattern regardless of which file `run.ts`'s
  content lives in.
- PXT traps pinned in comments: never write the word "radio" followed
  by a dot in prose (dependency scanner) — the one comment threading
  this today, `emitLine()`'s, moves to `sim.ts` unchanged; `//%` must
  sit immediately above the signature in every file, not just the
  original one; shims max out at two int args (TS9200 compiler
  assert).
- **New (sprint 012): the split's one load-time file-order
  constraint.** Splitting one file into six means functions in one
  module now call non-exported helpers declared in another — e.g.
  `pose.ts`'s `poseX()` calling `sim.ts`'s `_poseX()`. This relies on
  TypeScript's documented multi-file-namespace merging: files that
  reopen the same `namespace` and compile as one Program (which is how
  PXT's `files` list works) share one merged scope, exported or not.
  Every one of those references in this split is a function-**body**
  reference — resolved when the function is *called*, after every
  file has already loaded — so file order does not matter for it. The
  **one** exception is `motion.ts`'s top-level `_startProtocol()`
  call (§8's Lifecycle paragraph): that statement executes the moment
  `motion.ts` loads, so `sim.ts`'s `_startProtocol` definition must
  already exist — `sim.ts` must be listed before `motion.ts` in
  `pxt.json`'s `files` array. No other cross-file reference in this
  split has a load-time ordering requirement. Verified empirically
  during sprint 012 (ticket 001's own real `pxt build`), not merely
  argued for.

## 10. Open questions / known limitations

- **(Resolved, sprint 005)** ~~`tools/`'s bench scripts still parse the
  old cleartext `TLM:` prefix (see §8's Telemetry gap paragraph); the
  v6 `thdr`/`t` frames sprint 004 built are real but nothing in
  `tools/` consumes them yet.~~ `tools/tlm.py` is a 430-line `thdr`/`t`
  decoder with its own 522-line test suite (`tests/tools/test_tlm.py`)
  — see §8.
- **(Resolved, sprint 005)** ~~`WireAdapter::lastDone()`/
  `lastDoneReason()` permanently inert — hosts cannot observe motion
  completion via the reliability channel.~~ The resolution machine
  (`armPendingMotion`, `resolvePendingReason`, `resolvePendingIfDue`,
  `forceResolvePending`, `engineMoveActive`) is built; hosts observe
  motion completion via `lastDone()`/`lastDoneReason()` — see §5.
- Radio RX is a single 64-byte fragment slot with no multi-fragment
  reassembly (sprint 004 closed the *grammar* question, not the
  *capacity* one). **(Resolved, sprint 010)** ~~An inbound line longer
  than one fragment is clamped to a parseable prefix rather than
  reassembled or rejected, which can execute as a different, shorter,
  legal command, not merely drop one — and radio's own TX cap
  (`kMaxPayloadBytes` = 200) is already provably exceedable by a
  legal, if pathological, telemetry frame (up to 239 bytes
  measured).~~ An inbound line longer than one fragment is now
  REJECTED outright (`radioRxLineFits()`, `radio_transport.h`), never
  clamped to a shorter, silently-executable prefix; `kMaxPayloadBytes`
  was raised from 200 to 240 and is drift-tested against the wire's
  own line ceiling (`tests/host/test_wire_constants_drift.py`). The
  239-byte pathological worst case that used to exceed the old 200
  now fits under 240 — with exactly 1 byte of headroom, thin, not
  comfortable (`tests/host/test_wire_telemetry_frame.py`). Filed as
  `clasi/issues/radio-rx-capacity-fragmentation.md`, closed by sprint
  010.
- **(Resolved, sprint 008)** ~~The post-move settle loop is
  hardware-only-tested.~~ Its bounded-iteration/break-on-rest decision
  is now a `MotionEngine` helper, host-tested directly (§9). Remaining,
  narrower gap: `odomUpdate(r)` itself and the loop's actual
  `kernel.step()` calls against real hardware are still only ever
  exercised by flashing — this sprint host-tests the *decision logic*,
  not the physical settle behavior, which is the same boundary every
  other host-portable extraction in this document draws.
- **(Resolved, sprint 008)** ~~`protocol.cpp`'s `kVersion` is a manual
  mirror of `pxt.json` and can drift.~~ Single-sourced or drift-tested
  against `pxt.json` (§8) — ten version bumps had drifted at the time
  this was fixed (WIRE-01/R-17).
- **(New, sprint 008)** `TlmMode::kBuffer` now refuses
  (`kUnimplemented`) rather than falling through to POSE's columns
  (§5) — a real behavior change for any host that was unknowingly
  relying on the old fall-through, though none is known to exist. A
  future sprint that gives BUFFER real, narrower semantics changes this
  refusal into an implementation, not a widening of an existing
  contract.
- **(New, sprint 008)** The target-viability gap
  (`host-tests-compile-newer-standard-than-target.md`) is addressed by
  a standing per-sprint build-checkpoint-ticket *convention* (§11;
  `docs/design/design.md`'s matching update), not by a hard automated
  gate in `close_sprint` — that tool is CLASI-server code outside this
  project's own source tree, so no ticket here can wire a gate into it.
  This closes the gap procedurally (every future sprint's own planner
  is expected to include the ticket) rather than mechanically
  (nothing currently prevents a sprint from being planned without one);
  flagged for the team-lead/stakeholder as a process decision worth
  revisiting if a sprint ever ships without its checkpoint ticket.
- **(Resolved, sprint 006)** ~~The encoder-odometry `PoseSource`
  fallback for OTOS-less robots is explicitly not built; GO_TO_W
  refuses on such robots.~~ `EncoderPoseSource` (§7) now serves that
  role; GO_TO_W dispatches on every robot regardless of OTOS presence
  (§9). Remaining caveat: the fallback carries no drift/uncertainty
  signal back to the caller — a GO_TO_W served by encoders is silently
  a weaker promise than one served by the OTOS, distinguishable today
  only by reading STATUS's `otos=` flag before calling, not by
  anything GO_TO_W itself returns.
- `EncoderGlitchArmor`'s rebaseline-on-discontinuity path (§7) is
  built and host-tested against the *code path* KERN-07 identified,
  but the *hardware premise* — whether a Nezha brick MCU reset actually
  restarts the 0x46 counter near zero — remains unconfirmed absent a
  bench run; see `brick-reset-odometry-teleport.md` and sprint 006's
  bench-checklist ticket.
- **(New, sprint 007)** The review's Design assessment names a broader
  opportunity this sprint deliberately does not build: e-stop, the
  stall latch, the starvation watchdog's soft-stop, and lease expiry
  are four distinct "robot is off" states a student currently
  distinguishes only by reading separate readbacks; a single unified
  "why won't it move" surface could retire the whole class. Excluded
  this sprint because the watchdog's soft-stop is **deliberately
  non-latching** (§9) while the other three latch/expire — a unified
  reporter needs to represent that asymmetry correctly, which is a new
  design question (enum? bitmask? which ordinals feed it?) this
  sprint's research did not narrow down enough to ticket safely. Three
  of the four states are now independently readable after this sprint
  (e-stop: STATUS flags bit 1; stall: STATUS flags bit 2 / DIAG
  ordinal 2 / `stall_clear` GET, §5/§9; the settle loop's own
  stop-delivery fix, sprint 006) — a future sprint would design the
  aggregation, not invent readbacks from scratch. **(Update, sprint
  016)** §12 now documents all five underlying stop mechanisms
  (including the two this entry didn't originally name — the
  port-level immediate write and lease expiry) and which entry points
  deliver each. That is a documented enumeration, not the aggregation
  itself — the single unified readback surface this entry describes
  remains future work.
- **(New, sprint 007)** `default_cruise`'s seed value (150 mm/s,
  matching the block layer's `defaultSpeed`) is a planning-time choice,
  not a measured one — if a bench host's own idea of a sane default
  differs from the block layer's, this is the constant to revisit.
- **(New, sprint 007)** `pxt.json`'s `microphone` dependency's true
  purpose is genuinely unknown — two independent code-review passes
  found no reference to it anywhere in `src/`/`test/`, and disagreed
  with each other on whether that means it is dead. Documented, not
  deleted (`specification.md` §2); flagged here in case the stakeholder
  has out-of-band knowledge this review process cannot see from source
  alone.

## 11. Host-vs-target language standard (a standing build-gate constraint)

`tests/host/` compiles this package's portable C++ at `-std=c++20`
(`tests/host/test_kernel_harness.py`); both real embedded targets — the
legacy mbed-classic/yotta build and the codal-microbit-v2 build — compile
at `-std=c++11`, baked into the pxt-microbit target's own yotta/CMake
toolchain files and not overridable from this project's `pxt.json`. A
green host suite is therefore **not evidence of target viability**: any
C++14/17/20-only construct in `src/` compiles and passes on the host
side while silently failing to compile for the robot at all, with no
signal from the test suite. The confirmed instance is §4's
`Column`/`Snapshot` paragraph — a struct with default member
initializers is not a C++11 aggregate, and ~20 brace-initialization
call sites in `WireAdapter::buildSnapshot()` (§5) compiled and passed
253 host tests while failing every real target build
(`clasi/issues/host-tests-compile-newer-standard-than-target.md`,
sprint 008 — filed after sprint 004 ticket 005 could not produce a
flashable hex against that fully green suite).

Sprint 004 ticket 007 narrowed the gap for `src/` specifically: a
`-std=c++11 -fsyntax-only` compile gate
(`tests/host/test_cxx11_syntax_gate.py`) now runs, as part of the host
suite, over the four translation units that do not include `pxt.h` and
are therefore syntax-checkable this way — `diffdrive.cpp`,
`motion_engine.cpp`, `wire_handler.cpp`, `wire_adapter.cpp`. This
closes the specific defect class ticket 007 fixed for those four files
going forward, but it is a syntax-only check on a subset of files, not
a substitute for actually building the hex: the CODAL-facing files
(`protocol.*`, `*_transport.*`, the hardware ports, `shims.cpp`) still
need `pxt.h` and are not covered by this gate at all, and a *linkable*
target build — not merely syntax-valid C++11 — is only ever proven by
the sprint checkpoint that actually builds a flashable hex.

**Sprint 006** adds three new host-portable headers with no `pxt.h`
dependency of their own — `heading_wrap.h`, `encoder_glitch_armor.h`,
and `encoder_pose_source.h` (§7) — to this same gate, via a small
dedicated syntax-check translation unit each (none has a natural
`.cpp` of its own the way `motion_engine.h` rides along with
`motion_engine.cpp`). This is the gate's coverage growing by the three
files this sprint adds that are eligible for it; it does **not**
narrow the gap for the files this sprint actually changes that remain
ineligible — `shims.cpp` (stop delivery, continuous-mode odometry
fold, `EncoderPoseSource`/`OtosPort` selection wiring) and
`nezha_port.cpp`/`otos_port.cpp` (the hardware-port callers of the
three new headers) all still include `pxt.h` and stay outside this
gate, exactly as `src/DESIGN.md`'s pre-sprint-006 text already said.
`otos_port.cpp` is a sharper instance of this than the rest: with
`heading_wrap.h`'s wrap math extracted and gate-covered, the entirety
of `otos_port.cpp`'s OWN code (the I2C calls, the LSB quantization
call site) is still completely untested outside a real chip — there is
no host seam for `OtosPort` at all, extracted helper or not. A green
host suite for this sprint's `shims.cpp`/port changes is, as always,
not evidence they compile for the robot — only the sprint's own
flashable-hex checkpoint proves that.

**Sprint 008** closes the *centerpiece* gap this section documents —
not by widening the syntax gate further (the settle-loop extraction's
new logic lands as a method on the already-gate-covered `MotionEngine`
class, defined in `motion_engine.cpp`, so no new file and no new gate
registration are needed — a deliberately simpler choice than sprint
006's three new headers, since `motion_engine.cpp` already composes the
kernel reference the new method needs and was already portable, unlike
`otos_port.cpp`/`nezha_port.cpp`, which had no portable home to extract
into without building one) — but by formalizing what this section has
said all along in different words: "a *linkable* target build... is
only ever proven by the sprint checkpoint that actually builds a
flashable hex." Sprints 004 and 007 each proved that sentence true by
accident (their own last ticket happened to run `make_deploy.py`, and
each time that accident is what caught the sprint's own defect). This
sprint makes the accident a rule: every sprint that touches
build-eligible source now includes a mandatory, always-last
build-checkpoint ticket (see `docs/design/design.md`'s matching
update), and `tools/make_deploy.py` itself gains the triage
this section's own "known-benign, tolerate a retry" caveats needed —
distinguishing a real `.cpp` compile failure from the legacy V1
hex-merge failure and the nondeterministic `TS9283`/`TS9043`/`TS9200`
packaging abort, retrying only the latter automatically. This still
does not turn the syntax gate into something it isn't: the gate proves
syntax validity for four portable files plus their extracted-header
siblings; the checkpoint proves the whole package actually links for
both real targets. Both are needed; neither substitutes for the other.

## 12. Sprint 016 — stop taxonomy

Five "make it stop" mechanisms exist across three layers (kernel,
motion engine, shim/wire); each is individually defensible, but
nothing previously stated which one a given entry point delivers. That
gap is exactly why `shims.cpp::endMove()` shipped for several sprints
calling `deliverStopNow()` alone, unpaired with `kernel.neutral()` — a
defect this sprint fixed (see the entry-point table below). Two
properties distinguish the five: **(a)** does it write to the motor
ports immediately (tick-independent), or only *stage* a command that
needs a subsequent `kernel.step()` to reach the motors, and **(b)**
once delivered, does it persist on its own across further `step()`s,
or can a still-live earlier command (a long lease, a continuous-drive
velocity) re-assert itself unless something else also holds it down.

**Mechanisms:**

| Mechanism | Immediate or staged? | Entry point(s) | Persists across subsequent `step()`s? | Requires clearing to resume? |
|---|---|---|---|---|
| `kernel.neutral()` (`core/diffdrive.cpp:365-369`) | Staged — overwrites `command_`; the motors are zeroed only on the next `step()` | `MotionEngine::endMove()` (`motion/motion_engine.cpp:103-106`, conditional on `move_.active`); `MotionEngine::serviceMove()`'s move-completion branch (`motion/motion_engine.cpp:451`, unconditional — natural end, timeout, stall, wrong-way, or e-stop); `shims.cpp::stopAll()` (`shims.cpp:767`); `shims.cpp::endMove()` free function (`shims.cpp:755`, unconditional as of this sprint); starvation watchdog (`shims.cpp:726`) | Yes, once a `step()` delivers it — holds until a new `drive()`/`driveDuty()` overwrites `command_` | No (not a latch) |
| `NezhaMotorPort::emergencyStop()` (`platform/nezha_port.cpp:125-130`) | Immediate — writes zero duty straight to the port, tick-independent | `deliverStopNow()` (`shims.cpp:272-275`), called from `stopAll()` (`shims.cpp:771`), `endMove()` (`shims.cpp:758`), and `updateMove()`'s move-end path (`shims.cpp:505`); the starvation watchdog's direct calls (`shims.cpp:728-729`); `DifferentialDrive::emergencyStopMotors()`'s own internal calls (`core/diffdrive.cpp:381-382`) | **No — momentary.** `command_`/the lease are untouched; the very next `step()` re-commands from them unless paired with `kernel.neutral()` or an e-stop latch | N/A (not a latch) |
| `kernel.estop()` (`core/diffdrive.cpp:371-373`) | Staged — sets `estopLatch_ = true` only; no motor write | `DifferentialDrive::estop()`, called from `shims.cpp::estopAll()` (`shims.cpp:778`) — always paired there with `emergencyStopMotors()` | Yes — re-checked on every `step()` (`core/diffdrive.cpp:485`) regardless of `command_` | Yes — `kernel.estopClear()` (`core/diffdrive.cpp:375-377`), forwarded by `shims.cpp::estopClear()` (`shims.cpp:783`) |
| `kernel.emergencyStopMotors()` (`core/diffdrive.cpp:379-383`) | Both — an immediate port zero on both motors (same primitive as row 2) **and** `estopLatch_ = true` as a side effect, undocumented at the header (`core/diffdrive.h:200`) | `shims.cpp::estopAll()` (`shims.cpp:779`), reached from the `emergency stop` block (`blocks/stop.ts:21-25`) and the wire's ESTOP verb (`WireAdapter::onEstop()`, `comms/wire_adapter.cpp:494-499`) | Yes — same latch as row 3 | Yes — same `estopClear()` path |
| Lease expiry (`core/diffdrive.cpp:475-483`) | Staged — a passive per-`step()` check (`cmd.validUntil` vs. the kernel clock), not a caller-invoked action | Not an entry point a caller invokes. `MotionEngine::serviceMove()` reissues a rolling 500 ms lease every tick while a move is active (`motion/motion_engine.cpp:388`), so an abandoned move degrades within 500 ms of servicing stopping; the wire's `WHEELS_V`/`WHEELS_X`/`MOVE_V` verbs set the lease to the caller's full requested duration once, at command time (`kWheelsVDurationCeiling`, `comms/wire_adapter.h:59`) | Yes, once triggered — forces `effective = kModeNeutral` on every subsequent `step()` until a new `drive()`/`driveDuty()` call | No explicit clear — a fresh lease-bearing command resumes motion |

**Row 2 is the one that misleads, and it is this sprint's own
finding.** `deliverStopNow()` alone — an immediate, port-level zero
write — is momentary, not a stop: it does not touch `command_` or any
latch, so a still-live kernel command (a long continuous-drive lease,
in particular) re-asserts a nonzero duty on the very next `step()`.
Every production call site pairs it with `kernel.neutral()` (row 1) or
an e-stop latch (rows 3/4) for exactly this reason — `shims.cpp::
endMove()` calling `deliverStopNow()` unpaired was the gap; it now
also calls `kernel.neutral()` unconditionally (below).

**Entry points:**

| Entry point | Mechanism(s) delivered | Survives the next `step()`? |
|---|---|---|
| `stop` block / wire STOP → `stopAll()` (`shims.cpp:764-772`) | `engine.endMove()` + `kernel.neutral()` (staged) + `deliverStopNow()` (immediate) | Yes |
| `emergency stop` block / wire ESTOP → `estopAll()` (`shims.cpp:775-780`) | `engine.endMove()` + `kernel.estop()` + `kernel.emergencyStopMotors()` (latch + immediate) | Yes, robustly — latched until `estopClear()` |
| `stop move` block → `endMove()` free function (`shims.cpp:743-759`) | `engine.endMove()` (stages neutral only if a move-engine move was active) + an unconditional `kernel.neutral()` (this sprint's fix) + `deliverStopNow()` | Yes — the unconditional `kernel.neutral()` is what now also stops a continuous-drive command, not only a move-engine move |
| Starvation watchdog (`watchdogEntry()`, `shims.cpp:718-731`) | `kernel.neutral()` + `engine.endMove()` + an immediate port zero on both motors | Yes, but non-latching — a fresh `drive()`/`tickDrive()` call resumes motion immediately; re-fires every ~50 ms while abandonment persists |
| `updateMove()`'s move-end path (`shims.cpp:487-507`, via `MotionEngine::serviceMove()`) | `serviceMove()`'s own `kernel.neutral()` on move completion/timeout/stall/wrong-way/e-stop (`motion/motion_engine.cpp:451`) + `deliverStopNow()` when the move was active and just ended (`shims.cpp:505`) | Yes — same staged-plus-immediate pairing as `stopAll()`/`endMove()` |

No structural change — this section is documentation-only. Every
citation above was checked against this sprint's final source, not
carried over from planning notes.
