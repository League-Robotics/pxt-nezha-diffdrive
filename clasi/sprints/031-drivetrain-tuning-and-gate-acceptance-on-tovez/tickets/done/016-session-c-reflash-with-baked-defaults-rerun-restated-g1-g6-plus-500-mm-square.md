---
id: '016'
title: 'Session C: reflash with baked defaults; rerun restated G1-G6 plus 500 mm square'
status: done
use-cases:
- SUC-001
- SUC-002
- SUC-005
- SUC-007
depends-on:
- '007'
- '014'
- '015'
github-issue: ''
issue: tovez-drivetrain-tuning-and-restated-acceptance-bars.md
completes_issue: true
---
<!-- CLASI: Before changing code or making plans, review the SE process in CLAUDE.md -->

# Session C: reflash with baked defaults; rerun restated G1-G6 plus 500 mm square

**Type: (a) hardware/playfield — team-lead executes personally. Final
session; closes out the sprint's Success Criteria.**

## Description

Flash ticket 015's baked-defaults build (confirmed to be the plain
build, not the canary variant — see ticket 014's reflash-back).
Pre-flight as usual (lights, camera, AprilTag 1, tag 52). Using ticket
007's consolidated `tests/playfield/turn_calibration.py`, run:

1. G1-G6 against the restated bars (G1 mean|err| ≤ 1.0°/sd ≤ 1.0° with
   ≥ 20-sample fixes; G2 ≤ 10 mm endpoint; G3-G6 unchanged).
2. A 500 mm square, three laps, confirming closure under the 10.8 mm
   baseline.
3. A repeat of the 600 mm leg heading check (six legs, both
   directions) as a final confirmation of ticket 012's twist-hold/
   `travel_calib` bake, now running on the REBUILT firmware rather than
   the live-`SET` values from Session B.

This is the sprint's closing measurement — every Success Criteria bullet
in `sprint.md` should be answered, pass or `UNVERIFIED`, by this
ticket's closing note.

## Acceptance Criteria

- [ ] tovez confirmed running ticket 015's baked-defaults build before
      any gate is run.
- [ ] G1-G6 all pass against the restated bars, capture cited per gate,
      using the consolidated `turn_calibration.py` program.
- [ ] 500 mm square, three laps, closes under 10.8 mm.
- [ ] Six of six 600 mm legs (both directions) hold heading within 1°
      on the REBUILT firmware (confirms the bake, not just the live
      `SET` value from Session B).
- [ ] Every constant that changed this sprint is confirmed baked in
      `shims.cpp` and/or `radio-robot-lib/config/robots/tovez.json`
      with its capture cited — this sprint's own Success Criteria,
      quoted verbatim.
- [ ] Any bar not met is recorded as such, with what was tried — not
      silently rounded up to a pass.

## Testing

- **Existing tests to run**: N/A — final hardware acceptance session.
- **New tests to write**: none.
- **Verification command**: N/A (hardware ticket).

## Closing note (team-lead, 2026-09-05)

Session run personally over zilch's serial socket
(`192.168.4.52:46011`), camera-truthed throughout. Full record and every
MEASURED citation: `captures/session-b-20260905/notes.md`; per-gate
captures under `captures/session-b-20260905/ticket016/`.

**Every gate was run. Every gate FAILED.** Recording that plainly rather
than rounding anything up, per this ticket's last acceptance criterion.

| gate | bar | measured | verdict |
|---|---|---|---|
| G1 | mean\|err\| <= 1.0 deg, sd <= 1.0 deg | 1.531 / 1.775 deg | FAIL |
| G2 | mean endpoint <= 10 mm | 54.78 mm (1/6 within) | FAIL |
| G3 | length err +-3.0 mm; peak <= cruise x1.05 | -4.7 mm; 121 on a 100 command | FAIL |
| G4 | first-tick <= v_floor; accel <= 1.5x; decel <= 2.0x | 36.0 PASS; 787.9 FAIL; 490.7 PASS | FAIL |
| G5 | peak <= 210; rise <= 600 | 226; 784.6 | FAIL |
| G6 | closure <= 10.8 mm | 48 / 15 / 103 mm | FAIL |
| AC #4 | 6/6 legs within 1 deg | 0 of 6; mean 3.19 deg | FAIL |

**The sprint's Success Criteria are NOT met.** That is the headline and
it should not be softened.

### What the session did establish

1. **tovez had no turn calibration at all.** `stop_distance` 0 and a
   slip that left every pivot 5.1% short. Correcting `rotational_slip`
   to a VERIFIED 0.962 cut G1's mean\|err\| 3x, 4.604 -> 1.531 deg.
   **Recommended bake: `rotational_slip = 0.962`** (tigez's
   independently measured value is 0.9617).
2. **The real defect is that tovez's wheels are not matched** -- left
   step lag 0.168 s vs right 0.096 s, corroborated by four independent
   gates. Filed as
   `clasi/issues/tovez-wheels-are-not-matched-and-lag-is-chassis-wide.md`.
   No per-wheel config field exists, so this sprint could not have
   fixed it with the knobs it had. This is the most valuable output of
   the session and it reframes the next one.
3. **`wire_get()` returns stale readings**, so every gate banner's
   "(live)" config values may be wrong. Filed as
   `clasi/issues/wire-get-returns-a-stale-reading.md`. Worked around
   here by verifying the slip with a raw read before driving.
4. **G5's fail-closed fix is confirmed on hardware** -- all 8 trials
   travelled 20.8-23.1 cm where the pre-fix gate passed on 0.02 cm.

### Deviations from this ticket as written, stated explicitly

- **Ticket 014 (its dependency) was never run**, so the canary-vs-plain
  reflash-back it was meant to confirm did not happen. Instead the
  board carries commit 38808e1 = ticket 015's bake PLUS ticket 017's
  ownership fix, which is a strict superset of what AC #1 asks for. No
  canary build was ever flashed to this board, so AC #1's real concern
  (that a canary build is not left on the robot) is satisfied by
  construction, not by 014's procedure.
- **AC #5 (every constant that changed this sprint confirmed baked) is
  NOT verified.** `twist_hold_gain` 4.0 is confirmed in `shims.cpp` and
  resident; `rotational_slip` 0.962 was set LIVE this session and is
  **not baked anywhere** -- it is lost on the next power cycle. Baking
  it is a source edit and belongs in a ticket.
- **G6 needed `--margin 14`.** Its 25 cm default cannot admit a 500 mm
  square on an 89.3 cm field (50 + 2x25 = 100 cm needed). The worst
  corner still cleared the rail by 17.6 cm.
- **G2's arc 1 hit the 9000 ms timeout.** Whether that is a stall or
  simply too short a budget is UNVERIFIED; the discriminating re-run at
  a longer timeout was not done.

### Recommendation

Do not close sprint 031 as successful. The measurement work is
complete and the findings are strong, but no acceptance bar was met.
The per-wheel asymmetry issue should drive the next sprint, and
`rotational_slip = 0.962` should be baked before any further tuning so
the next session does not start from an unknown value again.

## Closing note, part 2 (team-lead, 2026-09-05, late) -- what changed after the first close-out

The first closing note above stands as the record of the gate run. After
the stakeholder's postmortem direction (`docs/sprint-031-postmortem.md`)
the following landed, in order:

1. **The "wheel lag mismatch" finding is withdrawn** (postmortem 2.1) --
   an encoder sampling-order artifact, not a physical mechanism. The
   issue is retitled `tovez-straight-legs-curve-and-twist-hold-cannot-see-it.md`.
2. **Discriminator runs** (`captures/session-b-20260905/discriminator-20260905{,-v2}/`)
   showed the leg yaw is a start-of-leg BREAKAWAY on direction reversal,
   variable and sign-inconsistent (the same command from the same pose:
   -1.37 then +4.59 deg), worst on forward-after-reverse (up to 8.9 deg),
   largely invisible to the encoders. Not a constant curvature; not
   fixable by any twist-hold gain.
3. **Live sweep** (`.../gain-sweep-20260905/`): `twist_hold_gain 20`
   worse (max 17 deg); `v_floor 150` fewer breakaway events, same worst
   case (8.9); `accel 800` 1.35 / 3.45 deg over 8 legs; and then the
   **fleet default, accel 400 / decel 400: 0.76 / 1.01 deg** (run 1,
   n=4; replication in `accel400b/`, n=8 combined: mean 1.06 deg, max 2.55, all eight legs under 3 deg). That last number
   is the one that matters: every gate and sweep before it had run
   under `test/test.ts:335 openLoopProfile()`'s `setLimits(300, 300,
   200, 90)`, entered by the ticket 017 `RUN:straight:8` check and never
   cleared. Student block programs never enter that profile.
4. **Ticket 018**: `rotational_slip` 0.962 baked for tovez (replacing a
   wrong 1.01 from 09-04) via `tovez.json` firmware_bake.
5. **Ticket 019**: `straight_trim` field (wire ordinal 38, default 0)
   plus the host-harness proof that twist hold is blind to an
   encoder-invisible curvature. tovez's trim stays 0 -- the field is
   for a CONSTANT mismatch, which tovez's yaw is not.
6. **Ticket 020**: dispatched to bake accel 800, then REDIRECTED when
   the fleet-default run came in. Final content: `accel` becomes a
   per-robot bake key, tovez baked EXPLICITLY at the fleet default 400
   (so the path is exercised and the value is on record), `openLoopProfile()`'s literals move from 300/300
   to the fleet default 400/400 so a RUN verb no longer degrades every
   later move, and `tools/field_dance.py`'s hardcoded `SET accel/decel
   400` is reconciled with the bake path. Commits `4acbaa3` + `dc6ebf0` here, `0f7c5c8` + `dd6ac0f` in
   radio-robot-lib (not pushed); 158 tools tests + 15 syntax-gate tests
   pass. Final `openLoopProfile()`: `setLimits(400, 400, 200, 90)`.
7. **Ticket 014** closed as DEFERRED (never run); procedure carried in
   `clasi/issues/stack-canary-scan-deferred-from-sprint-031.md`.

### Release build verification -- 1.20260905.1 (018 + 019 + 020)

Built from clean (`shutil.rmtree('.tmp/deploy-head')` first -- the
checkpoint had refused a cached build twice), commit `dc6ebf0`:

- hex `captures/session-b-20260905/tovez-1.20260905.1-release.hex`,
  1,730,964 bytes, sha256
  `697083933d4cd4094372c5dfd57e92492811bd408971422027e9d6ffead0d7a0`
- scratch source proved before flashing: `rotationalSlip_ = 0.962f`,
  `kVersion = "1.20260905.1"`, `float accel = 400.0f`, `straight_trim`
  in `kFields`, `openLoopProfile()` = `setLimits(400, 400, 200, 90)`
- flashed `mbdeploy deploy tovez --remote --hex ...`: erased and
  programmed 418,816 bytes, identical 0 (no mass erase needed)

**Wire check, no `SET` ever sent this session** (`release-verify/`,
`verify_release.py`):

```
HELLO -> device NEZHA2 robot tovez 2314287040
ID    -> id diffdrive tovez 1.20260905.1 tovez
GET rotational_slip -> 0.962000   OK   (the ticket 018 bake, from power-on)
GET straight_trim   -> 0.000000   OK   (ticket 019 field present, default)
GET accel           -> 400.000031 OK   (ticket 020, fleet default explicit)
RELEASE WIRE CHECK: PASS
```

**Four 600 mm legs on the release build, no live SETs**
(`release-verify/legs.log`, `sweep_release_leg*.json`): camera dh
+0.44 / -2.08 / +2.38 / -0.92 deg -> mean|dh| 1.46, max 2.38. Every leg
under 3 deg, consistent with the 400/400 sweep (1.06 / 2.55, n=8) and
against the 300/300 profile's 3.62 / 7.61 the earlier gates ran under.

**Field dance** (`release-verify/dance.log`, first run after the flash
and a net-zero warm-up): +90 -> +86.5 (PASS), +180 -> -171.9 (+8.1,
FAIL), +90 -> +89.5 (PASS); drives 19.2 / 39.7 / 19.6 cm (all PASS,
bearing within 1 deg); home closure 1.2 cm (PASS, best of the night).
Convention correct in every step; one pivot magnitude out. Re-run from
mid-field (`release-verify/dance2.log`): +88.7 / **-171.9 again (+8.1)** /
+89.5; drives 19.5 / 39.5 / 19.7; home 1.8 cm. The +180 error is
repeatable to 0.1 deg. Together with the 1.01-slip dance earlier in the
evening it fits an AFFINE pivot law, actual ~ 1.027 * cmd - 7 deg
(postmortem 3b; radio-robot-lib's 2026-07-29 note found the same shape):
`rotational_slip` 0.962 zeroes it at 90 deg, the common student turn,
and leaves +8 deg at 180. The constant term is `stop_distance` / a
pivot-fitted `lag`, unmeasured on tovez -- carried to the next sprint
with this two-point fit as the starting data.

**G1 on the release build** (`release-verify/g1/`): 12 alternating +-90 deg
pivots, 20-sample rest fixes, nothing set live: errors -1.74 / -0.35 /
-2.91 / -1.65 / -5.58 / -0.53 / -3.16 / +1.10 / -1.49 / +1.66 / -0.43 /
+2.10 -> **mean|err| 1.892 deg, sd 2.091** (research bar FAIL; student
bar <= 3 deg met). The +90 turns run ~2.5 deg short on average, the -90
turns ~0.4 deg long -- a small direction asymmetry on top of the affine
law above. Consistent with the 1.531 / 1.775 measured with the same
slip set live earlier (`ticket016/g1-slip0962/`); the bake reproduces
the live result from power-on.


### Release criteria for the student firmware (restated 2026-09-05, late)

The research bars (G1 sd <= 1.0 deg, G2 10 mm, G6 10.8 mm, G3 peak
x1.05) are recorded FAILED above and carried to
`clasi/issues/tovez-straight-legs-curve-and-twist-hold-cannot-see-it.md`.
What students need, and where tovez stands on the release build:

| what | bar | measured (release config) | status |
|---|---|---|---|
| 90 deg pivot | mean\|err\| <= 3 deg | 1.89 deg mean, sd 2.09 (12 pivots) (release build; 1.53 deg live-set earlier) | **met** |
| 600 mm forward leg, after a pivot | \|dh\| <= 3 deg | +0.44 (release build); 0.5-1.6 at 400/400 (n=3) | **met** |
| 600 mm forward leg, after a REVERSE | \|dh\| <= 3 deg | +2.38 (release build); +0.58 / -2.33 at 400/400 | **met** (was 4.6-8.9 under the 300/300 RUN profile) |
| `RUN` verbs / blocks drive | drives | 7.54 cm on `RUN:straight:8` | **met** (ticket 017) |
| WHEELS_V step | moves, no oscillation | 20.8-23.1 cm, 8/8 | **met** |
| 500 mm square, one lap | closure <= 50 mm | 15 / 48 / 103 mm | 2 of 3 |

The reversal yaw that looked unfixable under the 300/300 RUN profile
is inside the student bar at the fleet default the release ships with.
The square (2 of 3 laps under 50 mm) was measured under the 300/300
profile and is expected to improve; UNVERIFIED on the release build.

### Final hex (after ticket 019 suite fix `185cdd2`)

The hex that was field-verified above (`tovez-1.20260905.1-release-fieldverified.hex`,
sha256 `697083933d4c...d7a0`) predates 019 suite fix `185cdd2`, which
added `ConfigField.StraightTrim = 38` to `src/blocks/motion.ts` and
condensed four comment blocks -- no C++ behaviour change. The branch tip
was rebuilt from clean and reflashed as `tovez-1.20260905.1-release.hex`
(1,730,919 bytes, sha256
`932134f9aee569bfc3b68f3d93af1849fab03ad8aacf6f3c60d2a527a9b0372a`),
programmed 418,816 bytes, and re-passed the wire check with no `SET`
sent (slip 0.962 / trim 0 / accel 400 from power-on, `ID 1.20260905.1`).
Field runs were not repeated; the kernel is byte-identical in intent
and the wire-visible config is identical. Full suite: 1330 passed.
`review_sprint_pre_close(031)`: passed.
