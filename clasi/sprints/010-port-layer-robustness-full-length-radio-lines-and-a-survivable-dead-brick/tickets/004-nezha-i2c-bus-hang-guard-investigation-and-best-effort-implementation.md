---
id: '004'
title: 'Nezha I2C bus-hang guard: investigation and best-effort implementation'
status: open
use-cases: ['SUC-002']
depends-on: []
github-issue: ''
issue: unpowered-nezha-brick-wedges-program-at-boot.md
completes_issue: false  # Investigation ticket -- may not fully resolve
  # the bus-hang question (see Description). The issue stays open past
  # this sprint if the finding below requires target-level work outside
  # this project's own source tree.
---
<!-- CLASI: Before changing code or making plans, review the SE process in CLAUDE.md -->

# Nezha I2C bus-hang guard: investigation and best-effort implementation

## Description

**This is an investigation ticket, not a known fix** — sprint.md's own
Requirements are explicit that none of the three candidate directions
(a codal I2C timeout option; a pre-flight bus probe with a bounded wait;
guarding the priming path) is confirmed, and this ticket's job is to
narrow them with real evidence before committing to an implementation.

**What the original issue described**: `NezhaMotorPort::begin()`'s
three-sample encoder-priming loop (`src/nezha_port.cpp:48-75`,
`writeFrame()`/`readEncoderRaw()` over `uBit.i2c`) never returning
against an unreachable brick, freezing CODAL's cooperative scheduler
entirely (no TLM, no PING reply, boot banner is the last output). This
was **not** what reproduced in the same session's bench work — see
`unpowered-nezha-brick-wedges-program-at-boot.md`'s own correction — but
the issue itself states the original wedge scenario "remains
unreproduced and may still be real on a genuinely unpowered brick."

**Platform-level finding from sprint planning (web research, cited in
sprint.md's Architecture, Step 6 Design Rationale — verify against this
project's own resolved build before relying on it):**
codal-nrf52's changelog records "NRF52I2C: Introduce transaction
timeout" (v0.2.33) and "NRF52I2C::waitForStop: recover from hang"
(v0.2.58); codal-microbit-v2's changelog records "Stabilize I2C
communications between NRF52 and KL27 DAPLINK chip when running on
battery power (#130)" (v0.2.32). See
[codal-microbit-v2 Changelog](https://github.com/lancaster-university/codal-microbit-v2/blob/master/Changelog.md)
and [issue #130](https://github.com/lancaster-university/codal-microbit-v2/issues/130).
This project's `pxt.json` carries no explicit codal version pin (the
MakeCode target build resolves it), so **it is not yet known** whether
the version this project actually builds against includes this upstream
work. If it does, the "permanent hang" premise may already be
platform-bounded (to some multi-second delay per stuck call, not
infinite) — changing this ticket's job from "add a timeout" to "confirm
the platform's existing bound and make the resulting delay graceful
rather than a silent, unexplained freeze." If it does not, a software
guard is still needed, and the "pre-flight probe" candidate direction is
weaker than it first appears: a probe would use the *same* blocking I2C
primitive `begin()`'s own priming reads already use, so on a true
clock-stretch bus lockup it hangs exactly as long as the read it was
meant to guard.

**Two call sites this ticket must cover, per sprint.md's own Goals**
(a boot-only guard is not a fix): `DifferentialDrive::begin()` →
`NezhaMotorPort::begin()`'s one-time priming loop
(`src/diffdrive.cpp:263-265`), and the steady-state per-tick
`requestSample()`/`tick()` → `collect()` I2C path
(`src/diffdrive.cpp:495-510`), which recurs every ~24 ms once something
ticks the kernel.

## Acceptance Criteria

- [ ] **Research finding, written into this ticket or a linked note**:
      which codal-nrf52/codal-microbit-v2 release this project's actual
      MakeCode build resolves (determined at build time — check the
      resolved target's own version metadata or changelog during a real
      or scratch build), and whether that release includes the
      transaction-timeout/`waitForStop` work cited above.
- [ ] If the finding confirms the platform already bounds a stuck I2C
      call: document the confirmed bound (approximate wall-clock time
      per call), and assess whether `begin()`'s current 3-sample × 2-motor
      priming sequence (up to 6 sequential I2C write/read pairs) produces
      an acceptable worst-case boot delay under that bound, or whether it
      should short-circuit earlier (e.g., stop attempting further samples
      after the first hard failure) — implement the short-circuit if the
      finding justifies it; this is a small, low-risk, reviewable change
      to `nezha_port.cpp::begin()`.
- [ ] If the finding cannot confirm platform-level bounding (version
      unconfirmable without a bench-flashed build, or confirmed absent):
      document that explicitly, and do **not** invent a software-level
      timeout mechanism speculatively — escalate as an Open Question
      (already seeded in sprint.md) rather than ship unverified
      complexity.
- [ ] Either way, confirm and document (do not silently assume) that the
      steady-state path's existing error handling — `collect()`'s
      `readEncoderRaw()` failure sets `connected_ = false` and leaves
      `sampleTimeUs_` unchanged, and `DifferentialDrive::step()` already
      increments `i2cFaultCount_` when a sample doesn't refresh
      (`src/diffdrive.cpp:507-510`) — degrades correctly *once a call
      returns*, whatever the call's own latency turns out to be. This
      criterion is checkable by re-reading the existing code path; no
      hardware needed.
- [ ] No change to `diffdrive.{h,cpp}` (the vendored kernel) is made in
      this ticket. If the investigation concludes `Motor::begin()`/
      `tick()` needs an explicit bounded-wait contract (a kernel-level,
      cross-repo change), document that conclusion as an Open Question
      for the stakeholder rather than implementing it here — this was
      explicitly left open, not assumed, by sprint.md's own Scope.
- [ ] This ticket's acceptance does **not** require a robot. Any code
      change lands reviewed and (where the change is in a host-portable
      file) tested; the bus-hang guarantee itself is proven at the bench
      by ticket 005.

## Implementation Plan

**Approach.** Research first (confirm the resolved codal version and its
I2C driver behavior), then make the smallest defensible code change the
finding justifies — or none, if the finding is inconclusive without
hardware access, in which case this ticket's output is the written
finding plus the sharpened Open Question for ticket 005/the stakeholder.

**Files that may be modified**, contingent on the finding:
- `src/nezha_port.cpp` — `begin()`'s priming loop, only if a low-risk
  short-circuit is justified.
- `src/nezha_port.h` — only if new state (e.g. a "priming attempted but
  failed" flag distinct from `connected_`) is needed to support the
  above.

**Explicitly out of scope for this ticket**: `src/diffdrive.{h,cpp}`
(vendored kernel — see Acceptance Criteria); any change to
`shims.cpp::ensure()`'s call sequence beyond what a confirmed low-risk
`nezha_port.cpp` change requires.

**C++11 gate coverage — OUT of gate.** `nezha_port.h`/`.cpp` include
`pxt.h` and are not part of the `-std=c++11` syntax gate's four-file
coverage (`src/DESIGN.md` §11); `shims.cpp` is likewise out. Any change
here is invisible to that gate and to every host test by construction —
only a real build (ticket 007's checkpoint) proves it compiles for the
target.

**Testing plan.**
- Not host-testable, by construction: the actual I2C bus-hang behavior
  (`nezha_port.cpp` requires `pxt.h`; no existing seam fakes a truly
  non-returning I2C call the way `FakeMotor` fakes a cleanly-reporting
  disconnected one).
- If a `begin()` short-circuit is implemented, review it against the
  existing code path by inspection (this ticket's acceptance criteria
  are about the change compiling cleanly and being reviewed, not a host
  test asserting hardware timing).
- The actual guarantee — that a physically unreachable brick degrades
  rather than hangs, at both call sites — is confirmed at the bench by
  ticket 005, which this ticket's findings directly inform.

**Documentation updates.** Findings feed the sprint's design overlay
(`clasi/sprints/010-.../design/DESIGN.md`) if they change the
architecture's stated Open Question; otherwise recorded in this ticket
only.
