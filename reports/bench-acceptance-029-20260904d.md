# Sprint 029 ticket 007 — bench acceptance session, 2026-09-04d (tovez)

Robot under test: **tovez**, firmware `1.20260903.1` (unchanged this
session — the 09:38 reflash that carries ticket 010's K1 fix was
already done before this session started; `HELLO` confirmed `device
NEZHA2 robot tovez 2314287040`), reached over tovez's own on-robot
**`zilch` Pi's lossless TCP serial daemon** (`zilch.local:43671`, this
session's own new carrier — see §0), not the lossy torture radio relay
prior sessions used. No `geometry.firmware_bake` block exists for
tovez in `radio-robot-lib/config/robots/tovez.json` — this session's
measurements (what few there are) still run against this repo's own
compiled defaults, unbaked.

**Verdict: BLOCKED at the mandatory first gate, again — but with real,
useful new evidence.** `field_dance.py --tcp` FAILED. Per the ticket's
own mandatory ordering, no other commanded motion was sent this
session: no lag remeasurement, no G1-G6, no `stop_distance`/
`omega_floor`. Unlike the two prior FAILs, this one is not
ambiguous or wedge-confounded — it cleanly separates into two
findings: pivots are now close to passing (a real, large improvement,
consistent with ticket 010's K1 fix), and drives fail with a new,
consistent ~90° bearing defect that was not previously characterized
this cleanly. All capture files referenced below are in
`captures/bench-acceptance-029-20260904d/` (force-added; `captures/`
is gitignored).

---

## 0. New this session: a lossless TCP carrier

Every prior tovez session in this ticket drove over the torture radio
relay (`tools/fieldlink.FieldLink`), which is documented as 66-83%
per-line lossy. tovez carries its own on-robot Pi Zero (`zilch`)
running the mbdeploy serial daemon — a direct, lossless TCP pipe to
the board's USB serial that does not reset the board on connect.

`tools/fieldlink.py` gained `TcpFieldLink(hostport)`, sharing a new
`_SequencedLink` base class with the existing `FieldLink` so both
carriers expose the identical `unseq`/`seqd`/`hello`/`close` contract.
`tools/field_dance.py` gained a `--tcp host:port` flag that selects
`TcpFieldLink` instead of the default `FieldLink(CH, GRP)`; the default
(no `--tcp`) behavior is unchanged. Host coverage:
`tests/tools/test_fieldlink.py` (5 tests, real loopback TCP sockets, no
hardware) — all pass; `tests/tools/test_robotlink.py`,
`test_field.py`, `test_camlink.py` re-run clean (80 passed, no
regressions).

Port resolution is dynamic — re-resolve every session:

```
$ dns-sd -L tovez _mbserial._tcp local.
tovez._mbserial._tcp.local. can be reached at zilch.local.:43671
```

Cross-checked with `mbdeploy list --remote` (`ENUM 2  tovez ... zilch`).

## 1. Link, lights, camera — PASS

Shelly `Switch.GetStatus`: `output: true`. AprilTag 1: world
(−0.05, −0.09) cm — reads (0, 0) within noise. AprilTag 52 (tovez):
world (42.78, 12.86) cm at session start, well inside the usable
envelope (|x| ≤ 55, |y| ≤ 32.6). `camlink.py --register tovez`
succeeded, from the same still-UNVERIFIED mount entry
(`captures/bench-acceptance-029-20260904d/camlink-register.log`).

Raw TCP connect + `PING` sanity check
(`captures/bench-acceptance-029-20260904d/link-probe.log`): connects
clean, `pong 757919`.

Kernel kick (`kick.log`): pre-kick `STATUS` read `ready=0 ... cyc=0`
(expected, never-ticked after the 09:38 flash); `RUN:clearestop` →
`ESTOP:cleared`; 2 mm `MOVE_X` kick → `ack 1 0 none`; post-kick
`STATUS` → `ready=1 active=0 connL=1 connR=1 otos=1 wedge=0 i2cf=2
cyc=126`. `i2cf` was already 2 right after the kick alone.

## 2. `field_dance.py --tcp zilch.local:43671` — FAILED

Full transcript: `captures/bench-acceptance-029-20260904d/field-dance.log`.

| step | expected | measured | err | result |
|---|---|---|---|---|
| turn +90° | +90.0° | +91.5° | +1.5° | PASS |
| turn +180° | +180.0° | −170.4° | +9.6° | **FAIL** |
| turn +90° | +90.0° | +90.0° | −0.0° | PASS |
| drive +20 cm | 20.0 cm | 16.9 cm | −3.1 cm | **FAIL** (bearing off +87°) |
| drive −40 cm | 40.0 cm | −35.5 cm | −75.5 cm | **FAIL** (bearing off +91°) |
| drive +20 cm | 20.0 cm | 17.7 cm | −2.3 cm | **FAIL** (bearing off +86°) |
| returned home | 0.0 cm | 3.1 cm | +3.1 cm | PASS |

Net heading drift over the three pivots: +14.2° (+4.7°/pivot).
Post-dance camera fix: tag 52 at (41.70, 9.76) cm — safe, well inside
margin. Post-dance `STATUS`: `ready=1 active=0 connL=1 connR=1 otos=1
wedge=0 i2cf=53 cyc=2103 tlm=off next=1 done=10 reason=timeout` —
healthy, `cyc` advanced normally throughout (no repeat of the
2026-09-04c telemetry-staleness bug in this simple check; this was not
a targeted re-test of that bug).

**Two distinct findings, not one:**

1. **Pivots improved sharply.** +14.2° net drift over three pivots is
   close to a clean run and a large improvement over 2026-09-04's
   +47.6…+57.6°/pivot and 2026-09-04c's mixed 2-pass/1-miss-by-14°.
   Consistent with ticket 010's K1 fix addressing (at least part of)
   the pivot-accuracy defect this ticket's design §7 question was
   asking about — though a single 3-pivot dance is not a substitute
   for the 12-pivot G1 gate.
2. **Drives now show a new, cleanly-characterized ~90° bearing
   defect.** All three drives failed with consistent bearing error
   (+87°, +91°, +86°) — actual travel direction roughly perpendicular
   to where the camera-tracked heading said "forward"/"backward"
   should be — while magnitude tracked commanded distance reasonably
   (16.9/35.5/17.7 cm vs 20/40/20 cm commanded), unlike the
   wildly-inconsistent, much-larger errors seen in both prior FAILs.
   This reads as a real, repeatable directional defect specific to
   straight-line `MOVE_X` moves — not measurement noise, not a
   wedge/frozen-telemetry artifact (the dance safely returned home,
   `i2cf`/`STATUS` behaved normally).

Neither finding is confirmed against firmware source — no kernel or
motion-engine file was read or touched this session. These are bench
observations for the next session or `radio-robot-elite` firmware
engineering to chase, not diagnoses.

## 3. Not attempted this session

Per the ticket's mandatory ordering ("It must PASS... If it fails,
stop driving, capture, and report — do not proceed to gates"), the
dance FAIL stopped this session here:

| Item | Status |
|---|---|
| `lag` re-measurement | NOT ATTEMPTED — blocked |
| G1 (pivot accuracy) | NOT ATTEMPTED — blocked |
| G2 (arc endpoint) | NOT ATTEMPTED — blocked |
| G3 (straight) | NOT ATTEMPTED — blocked |
| G4 (jerk) | NOT ATTEMPTED — blocked |
| G5 (continuous WHEELS_V) | NOT ATTEMPTED — blocked |
| G6 (square tour) | NOT ATTEMPTED — blocked |
| `stop_distance` | NOT ATTEMPTED — blocked |
| `omega_floor` | NOT ATTEMPTED — blocked |

2026-09-04c's `SET lag 0.126` is **not** known to still be in effect —
this is a fresh boot (flashed 09:38) and no `SET lag` was sent this
session; the compiled default (`lag=0.0`) applies unless a future
session re-sends it.

## 4. Docs

- `src/DESIGN.md` §3: appended a 2026-09-04d paragraph after the
  2026-09-04c one, recording the carrier change, the dance table, and
  both findings above, cited to this session's captures.
- `docs/design/specification.md` §11: appended a short paragraph after
  the 2026-09-04c `MotionLimits`/G1/G5 writeup noting this session's
  dance FAIL and pointing at `src/DESIGN.md` §3 for the full account —
  no `MotionLimits` field values changed (nothing new was measured
  this session, the compiled-default table itself is unchanged).

## 5. Root cause of the ~90° drive-bearing defect — NOT a firmware defect

**Superseding §5's original framing.** The "new, cleanly-characterized
~90° bearing defect" reported above was tooling, not firmware. Found by
the team-lead after this session ended, confirmed and fixed in a
same-day continuation session
(`captures/bench-acceptance-029-20260904d/notes.md` §5 has the full
account and timeline).

Two things stacked:

1. **`tools/field_dance.py`'s `pose()` double-added the fixed +90°
   AprilCam convention.** `tools/camlink.py` registers a robot tag with
   `mount_yaw_rad = -pi/2 + residual`, so the aprilcam daemon's reported
   `yaw_rad` for a REGISTERED tag already IS the robot's heading
   (`tools/field.py`'s own `robot_heading_from_tag_yaw()` docstring
   already said not to add 90 again on a registered reading) —
   `field_dance.py`'s `pose()` did it anyway. A pivot's PASS/FAIL
   survives this (heading deltas cancel a constant offset); every
   drive's bearing came out rotated by the extra +90° — exactly this
   session's +87°/+91°/+86° pattern.
2. **tovez's tag plate is physically mounted ~180° from the fleet
   convention** (its "up" points robot-rearward, not forward). MEASURED
   2026-09-04, `captures/bench-acceptance-029-20260904d/
   heading-probe.log`: with the tag registered at the fleet's normal
   0°-residual convention, a 5 cm `MOVE_X 50 0 100 5000` probe displaced
   the tag 4.87 cm at bearing +11.4° while the daemon reported yaw
   −165.8° for the same pose — `bearing − reported_yaw = +177.3°`.

**Fix**: `tools/field.py` gained `pose_from_registered_samples()` (reads
a registered sample's `yaw_rad` unchanged); `field_dance.py`'s `pose()`
now calls it instead of double-correcting. Every other `tools/*.py`
tag-yaw consumer was audited and found clean (rotation-only tools use
heading deltas, immune either way; every absolute-heading tool already
reads the registered daemon value directly). `tools/field_calibration.json`'s
tovez entry now carries `mount_yaw_residual_deg: 180.0` (the measured
physical mount finding) and a matching `mount_x_cm` sign flip. New
tests pin the fix (`tests/tools/test_field.py`); the existing TL-11
regression guard in `tests/tools/test_camlink.py` was widened to accept
a residual near 0° or ±180° while still rejecting one near ±90°.
`.claude/rules/tag-yaw-is-the-front-edge-not-the-hat.md` gained a
"registered vs raw: who adds the 90" section documenting this class of
bug and the tovez finding.

**Verification on real hardware, same-day continuation session**:
after a pre-flight-checked reposition toward field centre (13.3 cm from
the east margin was too tight for the longer moves later gates need),
`field_dance.py --tcp` was run TWICE. Both runs still print `DANCE
FAILED`, but the failure shape changed completely: every bearing error
is now ≤4° (was 86-91°) — the drive-bearing defect is gone, confirmed
on hardware, not just by source reading. What remains is a real,
repeatable MAGNITUDE undershoot specific to the LONGER move in each
pair (180° pivot lands ~9-9.6° short both runs; 40 cm reverse drive
lands ~4.6-4.7 cm short both runs) while the shorter 90° pivots and
20 cm drives in the same runs pass comfortably. This is an ACCURACY
finding, not a CONVENTION one, and is exactly what this ticket's own
`stop_distance`/`omega_floor` measurements and G1-G6 gates exist to
characterize — not a new defect to chase separately. Full table and
citations: `captures/bench-acceptance-029-20260904d/notes.md` §5
(`field-dance-refit-run1.log`, `field-dance-refit-run2.log`,
`reposition-to-center.log`, `post-refit-dance-status.log`).

## 6. What a human needs to do next

1. **The ~90° drive-bearing lead is closed** — it was tooling plus a
   physically-reversed tag plate, both fixed and verified above. Do not
   re-open it as a firmware suspect.
2. **New priority: the magnitude-undershoot-on-longer-moves pattern**
   (180° pivot, 40 cm drive) found in the two dance re-runs above. G1
   uses only 90° pivots (which already pass cleanly here), so G1 itself
   may well pass; a dedicated look at 180°-class pivots and >30 cm
   drives is the more targeted next step, alongside the ticket's own
   `stop_distance`/`omega_floor` measurements.
3. Once the dance passes cleanly (or the undershoot is understood well
   enough to proceed per the ticket's ordering), resume at lag
   re-measurement, then G1/G5, then the rest of G1-G6.
4. tovez's `field_calibration.json` mount entry (`lever_cm`,
   `parallax_k`) is still UNVERIFIED — pivots are close enough now
   (≤3.1° each) that a lever-triple fit is worth attempting once a
   session is not otherwise blocked.
5. `firmware_bake`/`pivot_overrun_mm`→`stop_distance_mm` rename in
   `radio-robot-lib/config/robots/tovez.json` (design §12 open question
   2, flagged in every prior session) is still outstanding and still
   cannot be done from this repo.
6. The still-open 2026-09-04c G5 sign-reversal defect and the
   STATUS/TLM staleness bug remain separate, unresolved leads — keep
   them distinct from both items above when triaging.

## Ticket status

Left `status: in-progress`. Real, useful progress this continuation
session: the ~90° drive-bearing defect is now root-caused (tooling, not
firmware), fixed, and verified twice on real hardware — a load-bearing
result, since it means the sprint's motion-profile work (K1's fix,
ticket 010) is not implicated in any remaining directional error. A
new, well-characterized, purely-magnitude accuracy finding (longer
pivots/drives undershoot) replaces it as the open lead. The ticket's
core deliverable (dance passing cleanly, G1-G6, `stop_distance`/
`omega_floor` measured and baked) is still not met.
