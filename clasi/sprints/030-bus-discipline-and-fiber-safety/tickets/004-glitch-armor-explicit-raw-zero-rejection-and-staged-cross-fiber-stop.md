---
id: '004'
title: 'Glitch armor: explicit raw-zero rejection and staged cross-fiber stop'
status: open
use-cases: [SUC-004]
depends-on: ['001']
github-issue: ''
issue: code-review/glitch-armor-reject-raw-zero-and-staged-cross-fiber-stop.md
completes_issue: true
---
<!-- CLASI: Before changing code or making plans, review the SE process in CLAUDE.md -->

# Glitch armor: explicit raw-zero rejection and staged cross-fiber stop

## Description

**Correction to the issue's own path citation**: `EncoderGlitchArmor`
lives in `src/core/encoder_glitch_armor.h` (confirmed by directory
listing), not `src/platform/` as the issue text says — a stale path
from before sprint 013's directory regroup. The class and the fix
below are unaffected; only the doc citation is wrong.

`deliverStopNow()` (`src/shims.cpp:336`) and the starvation watchdog
write the motor register from whichever fiber calls them, by design
(sprint 006) — a genuine safety path. The 0x46 encoder counter is
never device-reset (`nezha_port.cpp:378-379`'s comment); a destroyed
sample (a bus collision — the exact hazard ticket 001 closes — or a
brick power-up before the first real read) reads back as raw `0`.
`EncoderGlitchArmor::evaluate()` (`core/encoder_glitch_armor.h:107-130`)
currently rejects only `|raw - lastGood| > kMaxDeltaCounts` (5000) —
confirmed still the only check, no `raw == 0` special case exists. For
the first ~40 cm of travel after a brick power-up, while
`lastGoodRaw_` is still small, a destroyed `0` reading sits within
`kMaxDeltaCounts` of the last good value and is silently accepted as
`kAccept` — position jumps toward 0 and back, and `odomUpdate()`
integrates both directions as real motion.

## Remedy

- In `EncoderGlitchArmor::evaluate(int32_t raw)`: add a check ahead of
  the existing magnitude comparison — `if (primed_ && raw == 0 &&
  lastGoodRaw_ != 0) { rejectPending_ = false; lastRejectedRaw_ = raw;
  return Decision::kRejectPending; }` (or equivalent; match the class's
  existing state-update conventions for `kRejectPending` exactly — see
  the existing magnitude branch for the pattern to mirror). This fires
  **unconditionally** on `raw == 0` with a nonzero `lastGoodRaw_`,
  regardless of magnitude — do not gate it behind the existing `mag >
  kMaxDeltaCounts` check, since the whole point is to catch a
  destroyed-zero read that would otherwise pass the magnitude test.
  A genuine counter restart (two consistent implausible readings, zero
  or otherwise) must still reach `kAcceptAsRebaseline` through the
  existing two-strike path — do not special-case zero out of that path
  entirely, only skip the magnitude gate for the FIRST implausible
  zero reading.
- Depends on ticket 001 (`BusGuard`): when `BusGuard` is held (i.e. a
  step is in progress), change `deliverStopNow()`/the watchdog's motor
  write to a *staged* stop — set a `pendingStop_` flag on `Rig` instead
  of writing across the guard, delivered by the busy fiber itself at
  the same point `tickDrive()` already delivers a post-move settle
  stop (`shims.cpp` around line 608's `deliverStopNow()` call and the
  `wasActive && !moveActive` settle block). When the guard is NOT held
  (the overwhelming majority of stops), keep the existing immediate
  write — no staging, no added latency for the common path.
  `deliverStopNow()` deliberately still does not touch `estopLatch_`
  (unchanged from sprint 006 — do not conflate the two fault classes).

## Acceptance Criteria

- [ ] `test_encoder_glitch_armor.py`: a raw 0 immediately after a
      nonzero good value is rejected (`kRejectPending`), for both a
      small-magnitude and large-magnitude `lastGoodRaw_` (proving the
      new check is not gated behind the magnitude comparison).
- [ ] `test_encoder_glitch_armor.py`: the existing two-strike
      rebaseline case (two consistent implausible non-zero readings)
      is unaffected; a new case confirms two consistent implausible
      **zero** readings still reach `kAcceptAsRebaseline` on the
      second one.
- [ ] A host test (using ticket 001's `BusGuard` test seam) confirms a
      stop requested while the guard is held is staged, not written
      immediately, and is delivered by the time the guard next clears;
      a stop requested while the guard is clear is written immediately,
      unchanged from today.
- [ ] `deliverStopNow()` still does not touch `estopLatch_`.
- [ ] Hardware (optional, team-lead judgment): a cold-power-up bench
      run shows no position jump in the first ~40 cm of travel —
      MEASURED citation against the pre-fix reproduction if run.

## Testing

- **Existing tests to run**: `tests/host/test_encoder_glitch_armor.py`
  (extend, do not replace); `tests/host/encoder_glitch_armor_syntax_check.cpp`
  via `test_cxx11_syntax_gate.py`; any existing `deliverStopNow()`/
  watchdog host coverage.
- **New tests to write**: the raw-zero-rejection cases and the
  zero-vs-zero rebaseline case in `test_encoder_glitch_armor.py`; the
  staged-vs-immediate stop test described above (depends on ticket
  001's `BusGuard` test seam existing).
- **Verification command**: `uv run pytest
  tests/host/test_encoder_glitch_armor.py tests/host/test_cxx11_syntax_gate.py`
  during implementation; full `uv run pytest` at `close_sprint`.
