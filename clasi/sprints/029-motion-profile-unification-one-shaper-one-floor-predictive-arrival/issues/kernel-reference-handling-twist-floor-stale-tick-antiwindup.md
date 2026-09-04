---
status: in-progress
sprint: 029
tickets:
- 029-001
- 029-010
---

# Kernel: twist-hold reference from the post-floor twist; freeze the position reference on a stale tick; anti-windup; rearmReferences()

Priority: **High** · Source: [code review 2026-09-02](../../../docs/code-review/2026-09-02/review.md)

Findings: MK-02, MK-03 ([motion-and-kernel](../../../docs/code-review/2026-09-02/raw/motion-and-kernel.md)), CO-02. Triage #4.
Design: [motion-profile-unification.md](../../../docs/design/motion-profile-unification.md)
section 4.5 (patches K1-K5). Corrects the diagnosis in
`../pid-error-uses-a-stale-velocity-sample-after-an-encoder-fault.md`.

## Description

Four defects in `src/core/diffdrive.cpp`, each MEASURED on the real
kernel with ideal wheels (`profile_probe.out`):

- **K1 twist-hold vs floor.** `diffdrive.cpp:599` integrates
  `twistRef_.reference` from `lambda*cmd.twist`; `applySpeedFloor()` at
  line 617 then rescales both wheels up to `vMin`. Whenever the floor
  binds, the reference lags the wheels, the error goes negative, and the
  trim brakes the turn: -11 % reverse duty at the end of a 90 deg pivot at
  cruise 100, the pivot ending 88.07 deg with the servo on vs 92.56 with it
  off; a 300 mm / 45 deg arc at cruise 100 lands at (285, 120) instead of
  (270, 112). Hardware magnitude UNVERIFIED; the two code paths feeding
  different twist values into one reference are not in doubt.
- **K2 stale tick.** With `kp = 0` the velocity error `errLeft/errRight`
  reaches the duty only through bias adaptation (tau 30 s). The +6 duty
  point kick on a frozen encoder tick (E5: 35.3 -> 41.3 %) comes from
  `positionError()` advancing `ref.reference` by `speed*dt` (92 counts) while
  `sample.position` holds; 6 * 92 = 551 counts/s = 5.1 % duty. The open
  PID issue's proposed fix (gate the velocity error on freshness) would
  change nothing on the fleet bake.
- **K3 anti-windup.** `ref.reference` accumulates unbounded; only the
  returned error is clamped (`:866-871`). Any backlog beyond `posErrMax`
  discharges in the taper (the "end bump is an I-term stall" memory).
- **K4 segment boundary.** The engine burns a neutral tick
  (`awaitingHandoffNeutral`) because the twist reference disarms only on a
  neutral step, and copies a rebase-epoch guard three times because
  `rebasePosition()` is deferred.

## Remedy

- K1: integrate the reference from the post-floor half-differential
  `0.5*(speedRight - speedLeft)`; compute headroom from the same speeds.
- K2: `positionError()` takes `fresh`; when false, return the last error
  without advancing the reference.
- K3: after updating, clamp `ref.reference` to `(position - origin) +/- posErrMax`.
- K4: `rearmReferences()`, a deferred request (same shape as
  `rebasePosition()`) that disarms both position references and the twist
  reference at the start of the next `step()`.
- K5: `cfg.vMin = 0` in `shims.cpp:ensure()` once the profile owns the floor.
- Ship as a paired change with `radio-robot-elite/src/firm/diffdrive/`
  (see `decide-the-kernel-fork.md`).

## Acceptance

- Host tests per design 9.3: floored command -> twist reference equals the
  floored half-differential; frozen tick -> reference unchanged; 50 mm lag
  -> backlog exactly `posErrMax`; `rearmReferences()` zeroes both at the
  next step.
- Probe-as-test: no negative right duty during a cruise-100 pivot; E5's
  duty step is 0.
