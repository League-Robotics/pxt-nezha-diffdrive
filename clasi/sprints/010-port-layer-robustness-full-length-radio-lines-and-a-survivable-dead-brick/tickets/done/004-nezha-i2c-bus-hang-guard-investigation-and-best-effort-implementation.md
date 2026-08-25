---
id: '004'
title: 'Nezha I2C bus-hang guard: investigation and best-effort implementation'
status: done
use-cases:
- SUC-002
depends-on: []
github-issue: ''
issue: unpowered-nezha-brick-wedges-program-at-boot.md
completes_issue: false
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

## Investigation Finding (2026-08-25)

**1. Which codal this project's build actually resolves.** A real build
(`uv run python tools/make_deploy.py`, run twice — once cold, once to
reconfirm) writes `.tmp/deploy-head/built/codal.json`, whose `target`
section reads:

```json
"target": {"name": "codal-microbit-v2", "branch": "v0.3.5", ...}
```

Fetching `codal-microbit-v2`'s own `target-locked.json` at tag `v0.3.5`
(`gh api repos/lancaster-university/codal-microbit-v2/contents/target-locked.json?ref=v0.3.5`)
shows the exact pinned dependency commits:

```json
"libraries": [
  {"name": "codal-core", "branch": "e6b061f2a6d8977811e3025da387d3007e5796f2", ...},
  {"name": "codal-nrf52", "branch": "1fbb7240290fe36a55c61378f5cdeb7640f3ec4a", ...},
  {"name": "codal-microbit-nrf5sdk", "branch": "4b8abc690f6c9fca6132e6db5ee13a795a263f88", ...}
]
```

So this project's flashed firmware (the `mbcodal-binary.hex` variant —
the one this hardware actually runs, per `make_deploy.py`) is built
against `codal-nrf52` commit `1fbb7240` (2025-05-21, "Merge pull
request #56 ... Audio refactor").

**2. Does that commit include the two cited upstream fixes?** Searched
`codal-nrf52`'s commit history directly (`gh api
search/commits?q=repo:lancaster-university/codal-nrf52+...`) and found
both commits the sprint's own research named:

- `e1c428ab` (2021-06-30) — "NRF52I2C: Introduce transaction timeout":
  *"Prevent permanant freeze of a device in rare cases of an I2C bus
  hang. Abort after several seconds if an ongoing transaction does not
  complete."*
- `c14ade41`/`dff3021b` (2022-01-20 / 2022-04-19 merge) —
  "NRF52I2C::waitForStop: recover from hang".

`gh api repos/lancaster-university/codal-nrf52/compare/<fix>...1fbb7240`
for both returns `"behind_by": 0` — i.e. both fix commits are strict
ancestors of the pinned build commit, no divergence. **Both fixes are
confirmed present in the firmware this project actually builds and
flashes.**

**3. What the confirmed bound actually is.** Read
`source/NRF52I2C.cpp::waitForStop()` at the pinned commit directly
(`gh api .../contents/source/NRF52I2C.cpp?ref=1fbb7240...`):

```cpp
// Approximate maximum time, in 10us units, to wait for STOPPED or SUSPENDED event
#define NRF52I2C_TIMEOUT10US 1000000
// Approximate maximum time, in 10us units, to wait after an error
// for RESUME/STOP tasks to trigger STOPPED, before proceeding to a deeper reset of the bus
#define NRF52I2C_TIMEOUT10US_STOP 100000
```

`waitForStop()` busy-spins checking for either the expected completion
event OR an error event; once `locked > NRF52I2C_TIMEOUT10US`
(1,000,000 × ~10us ≈ **10s**) it force-triggers RESUME/STOP and waits
up to `NRF52I2C_TIMEOUT10US_STOP` more iterations (100,000 × ~10us ≈
**1s**) for that recovery to land, then — if even that doesn't land —
calls `redirect()` to fully re-initialize the peripheral. **Confirmed
bound: ~11 seconds worst case for one stuck I2C call to return an
error, not an indefinite hang.** This directly answers sprint.md's Open
Question #1 ("the single biggest unknown gating any further dead-brick
implementation work").

**Caveat, stated plainly (not confirmed, flagged for ticket 005):** the
~10s branch above only fires when *neither* the expected event *nor* an
error event ever posts. The NRF52 TWIM peripheral's own
`NRF_TWIM_EVENT_ERROR` is checked on *every* spin iteration, not just
after the timeout — so a plain "no device present, bus floats/NACKs"
condition (arguably the more literal reading of "unpowered brick")
plausibly resolves through that fast error path, not the ~10s one. The
documented "wedged bus, mid-transaction lockup" scenario (a device that
partially engages then hangs, e.g. holding a clock line) is the
scenario that actually needs the full ~10s+1s ceiling. Both are now
bounded either way, but *which* path a real unpowered/disconnected
brick hits — and therefore how close to instant vs. ~11s the observed
delay actually is — is not something code inspection can settle. This
is exactly what ticket 005's bench check should measure and record.

**4. Implementation.** Given the confirmed ~11s/call ceiling, the
original `begin()` loop's "try all 3 samples regardless of an earlier
failure" shape was still a real problem: up to 3 sequential hard
failures per motor (~33s) and up to 6 across both wheels in
`DifferentialDrive::begin()` (~66s) before the robot ever reports
`connected()==false` and lets the starvation watchdog / protocol fiber
run. That is not the *unbounded* hang the issue described, but it is
still a real, user-visible near-minute stall — not an acceptable boot
delay. Implemented the short-circuit `begin()`'s ticket text itself
proposed: `break` out of the sample loop on the first hard
`writeFrame()`/`readEncoderRaw()` failure, in
`src/nezha_port.cpp::begin()`. This caps one motor's own worst case to
a single attempt (~11-22s) instead of three, and both wheels combined
to ~22-44s instead of ~66-132s. See that function's own header comment
for the full derivation. No new state was needed in `nezha_port.h`
(`connected_` already correctly ends up `false` whether `good` samples
came from 1 failed attempt or 3) and `diffdrive.{h,cpp}`/`shims.cpp`
were not touched — the steady-state path needs no code change (see
Acceptance Criteria below).

**Honest trade-off, not hidden:** the short-circuit also removes the
old loop's tolerance for a single transient mid-sequence blip (e.g.
sample 1 fails on a cold-boot brownout but samples 2-3 would have
succeeded) — previously that still produced a good median-of-2 boot;
now that motor reports `connected()==false`. There is no bench evidence
either way on how often this actually occurs on real hardware. Flagged
for ticket 005 to watch: does a *healthy* brick occasionally fail this
way on cold boot in practice?

**5. Real-build verification.** `uv run python tools/make_deploy.py`
succeeded (attempt 2 — the known-benign V1 hex-merge `srec_cat`
failure plus a `TS9200` packaging abort, both documented as
retry-and-succeed in `tools/make_deploy.py`'s own triage). Final hex:
`.tmp/deploy-head/built/mbcodal-binary.hex`, 1,395,296 bytes.
`nezha_port.cpp` compiled with zero new warnings — the one warning it
produces (`comparison between signed and unsigned integer expressions`
at `tick()`'s `identicalReadsDriven_ > maxDrivenStreak_`) is pre-existing
and outside this ticket's changed lines.

**For the team-lead / sprint.md maintenance:** this finding directly
answers sprint.md Step 7's first Open Question ("Which codal-nrf52/
codal-microbit-v2 release this project's MakeCode build actually
resolves... ticket 004's first action item, and the single biggest
unknown gating any further dead-brick implementation work"). Per this
project's design-doc rule, tickets/programmers must not edit
`clasi/sprints/010-.../design/DESIGN.md` or `sprint.md`'s Architecture
directly — recommending that Open Question be marked resolved (codal-nrf52
`1fbb7240`, both cited fixes confirmed present, ~11s/call bound) in a
future architecture pass.

## Acceptance Criteria

- [x] **Research finding, written into this ticket or a linked note**:
      which codal-nrf52/codal-microbit-v2 release this project's actual
      MakeCode build resolves (determined at build time — check the
      resolved target's own version metadata or changelog during a real
      or scratch build), and whether that release includes the
      transaction-timeout/`waitForStop` work cited above.
      **DONE — see "Investigation Finding" below.** A real `pxt build`
      (`uv run python tools/make_deploy.py`) resolves
      `codal-microbit-v2` branch `v0.3.5`
      (`.tmp/deploy-head/built/codal.json`'s `target.branch`), whose own
      `target-locked.json` pins `codal-nrf52` at commit `1fbb7240`
      (2025-05-21). That commit is a confirmed descendant (GitHub
      compare API, `behind_by: 0` both ways) of BOTH cited upstream
      fixes: "NRF52I2C: Introduce transaction timeout" (`e1c428a`,
      2021-06-30) and "NRF52I2C::waitForStop: recover from hang"
      (`dff3021`/`c14ade4`, 2022-01/04). Both are included.
- [x] If the finding confirms the platform already bounds a stuck I2C
      call: document the confirmed bound (approximate wall-clock time
      per call), and assess whether `begin()`'s current 3-sample × 2-motor
      priming sequence (up to 6 sequential I2C write/read pairs) produces
      an acceptable worst-case boot delay under that bound, or whether it
      should short-circuit earlier (e.g., stop attempting further samples
      after the first hard failure) — implement the short-circuit if the
      finding justifies it; this is a small, low-risk, reviewable change
      to `nezha_port.cpp::begin()`.
      **DONE.** Confirmed bound: `NRF52I2C_TIMEOUT10US` (1,000,000, in
      ~10us units) ≈ 10s per stuck transaction before codal-nrf52
      force-recovers the bus, plus up to `NRF52I2C_TIMEOUT10US_STOP`
      (100,000 units) ≈ 1s waiting for that recovery's own STOP —
      roughly **11s worst case per I2C call**, not infinite. The
      original loop tried all 3 samples regardless of an earlier
      failure (up to ~33s/motor, ~66s for both wheels in
      `DifferentialDrive::begin()`); implemented a short-circuit —
      `break` on the first hard `writeFrame()`/`readEncoderRaw()`
      failure — capping one motor's worst case to ~11-22s. See
      `src/nezha_port.cpp::begin()`'s new header comment for the full
      derivation and the honestly-stated trade-off (loses tolerance for
      a single transient mid-loop blip; ticket 005 should watch for
      it). Verified compiling clean via a real build (attempt 2,
      known-benign V1 hex-merge + TS9200 retry, per
      `tools/make_deploy.py`'s own triage) —
      `.tmp/deploy-head/built/mbcodal-binary.hex`, 1,395,296 bytes.
- [x] If the finding cannot confirm platform-level bounding (version
      unconfirmable without a bench-flashed build, or confirmed absent):
      document that explicitly, and do **not** invent a software-level
      timeout mechanism speculatively — escalate as an Open Question
      (already seeded in sprint.md) rather than ship unverified
      complexity.
      **N/A — the finding DID confirm platform-level bounding** (see
      above), so this branch of the criterion does not apply; recorded
      here for completeness rather than left unchecked, since the
      ticket's own "either way" framing makes exactly one of these two
      branches apply per run.
- [x] Either way, confirm and document (do not silently assume) that the
      steady-state path's existing error handling — `collect()`'s
      `readEncoderRaw()` failure sets `connected_ = false` and leaves
      `sampleTimeUs_` unchanged, and `DifferentialDrive::step()` already
      increments `i2cFaultCount_` when a sample doesn't refresh
      (`src/diffdrive.cpp:507-510`) — degrades correctly *once a call
      returns*, whatever the call's own latency turns out to be. This
      criterion is checkable by re-reading the existing code path; no
      hardware needed.
      **CONFIRMED by re-reading `src/diffdrive.cpp`.** `collect()`
      (`nezha_port.cpp:199-250`): on `readEncoderRaw()` failure, sets
      `connected_ = false`, returns without touching `sampleTimeUs_`.
      `DifferentialDrive::refreshSample()` (`diffdrive.cpp:732-753`)
      mirrors `motor.connected()` into `sample.connected` every call and
      only advances `sample.sampleTime` when `motor.sampleTime()`
      actually changed. `step()` (`diffdrive.cpp:504-511`) compares
      each wheel's `sampleTime` before/after `refreshSample()` and
      increments `i2cFaultCount_` if either didn't advance — exactly as
      stated. The steady-state path (`requestSample()`/`tick()` inside
      `step()`, `diffdrive.cpp:496-502`) has no retry loop to
      short-circuit — it is one write + one read per tick already, so
      the platform's own ~11s-per-call bound is the only thing capping
      its latency, and that bound is confirmed present (see above). No
      code change needed here; this criterion is satisfied by
      inspection, matching the ticket's own testing plan.
- [x] No change to `diffdrive.{h,cpp}` (the vendored kernel) is made in
      this ticket. If the investigation concludes `Motor::begin()`/
      `tick()` needs an explicit bounded-wait contract (a kernel-level,
      cross-repo change), document that conclusion as an Open Question
      for the stakeholder rather than implementing it here — this was
      explicitly left open, not assumed, by sprint.md's own Scope.
      **Confirmed: `diffdrive.{h,cpp}` untouched.** The investigation
      did NOT conclude a kernel-level bounded-wait contract is needed —
      the platform-level bound already covers both call sites, so no
      Open Question escalation on this point is required. (A separate,
      narrower observation — an unpowered brick's real failure path is
      more likely a fast NACK than the ~10s silent-timeout path, unconfirmed
      without hardware — is noted below and left for ticket 005's bench
      check, not escalated as a kernel-contract question.)
- [x] This ticket's acceptance does **not** require a robot. Any code
      change lands reviewed and (where the change is in a host-portable
      file) tested; the bus-hang guarantee itself is proven at the bench
      by ticket 005.
      **Confirmed.** The `begin()` short-circuit is a control-flow-only
      change inside a function that already requires `pxt.h`
      (`writeFrame()`/`readEncoderRaw()` call `uBit.i2c` directly) — it
      is outside the C++11 host syntax gate by construction
      (`tests/host/test_cxx11_syntax_gate.py`'s own header comment names
      `nezha_port.{h,cpp}` explicitly as out of gate). No pure logic was
      extracted to a host-testable header: unlike sprint 006/008/010's
      `heading_wrap.h`/`encoder_glitch_armor.h`/`encoder_pose_source.h`/
      ticket 001's `radioRxLineFits()`, this change has no standalone
      decision worth its own header — it is two `break` statements in an
      existing loop, reviewed by inspection and verified compiling via a
      real build (see above). No robot was used or required.

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
