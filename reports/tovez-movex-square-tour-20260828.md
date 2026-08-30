# tovez — MOVE_X square tour, 2026-08-28 (bench, wheels up)

The traditional square tour and its two-panel chart, driven entirely
with **MOVE_X** (this morning's finding: MOVE_X shapes both ends of the
profile and closes the loop on distance — see
`docs/tovez-wheel-velocity-pid-20260828.md`).

![square tour, final](../captures/tovez-square-20260828/tovez_square_movex_closed2.png)

**Run 4 (the keeper): warm-up + closed-loop corners + patient waits —
closure 5.7 mm, end heading 360.9°.** Three fixes stack, each one
measured against the run before it
(`tovez-square-movex-closed2-20260828.json`):

| run | change | closure | end heading | worst leg yaw |
|---|---|---|---|---|
| 1 cold | — | 19.2 mm | 354.7° | −13.5° |
| 2 | + warm-up wiggle | 8.5 mm | 357.8° | −3.7° |
| 3 | + closed-loop corners | 24.2 mm | 360.2° | (absorbed) |
| 4 | + patient move waits | **5.7 mm** | **360.9°** | ~0° |

- **Closed-loop corners** (run 3): each pivot targets the ABSOLUTE
  cardinal heading (`h_start + n·90°`) read from telemetry, absorbing
  the previous leg's residual instead of stacking +90° on it —
  `tools/park.py`'s rule applied to the tour. This squared the shape
  and fixed the heading, but position closure got WORSE (24.2 mm):
  with the lucky cancellation between heading and position errors
  gone, the legs were exposed as running SHORT (edges 285–315 mm).
- **Patient waits** (run 4): the legs were short because the host was
  superseding MOVE_X's own final distance correction — the engine's
  correction jiggle arrives ~0.3–0.7 s AFTER the wheels first stop
  (first seen in the morning C-run), and a completion detector that
  fires on first stillness truncates it. Waiting a 0.7 s grace window
  and re-checking stillness let every leg finish: edges landed on the
  overlay and closure fell to 5.7 mm. **Any host sequencing MOVE_X
  moves back-to-back must wait out that correction phase.**

**Run 2, warm-up only:**

![square tour, warmed up](../captures/tovez-square-20260828/tovez_square_movex_warm.png)

**About run 2.** The first run (below) put
−13.5° of yaw into leg 1 and the whole square wore the skew. Adding a
net-zero warm-up (`MOVE_X 40`, `MOVE_X −40`, recording starts after)
cut leg 1's yaw to −3.7°, brought every pivot into +90.1…+90.9°, and
halved the closure: **8.5 mm, end heading 357.8°**
(`tovez-square-movex-warm-20260828.json`, chart
`tovez_square_movex_warm.png`).

| | cold (run 1) | warmed (run 2) |
|---|---|---|
| leg-1 yaw | −13.5° | **−3.7°** |
| legs 2–4 yaw | +0.1/+0.6/−0.1° | +0.1/+0.1/−0.3° |
| pivots | +92.3/+91.7/+90.4/+93.2° | **+90.9/+90.2/+90.1/+90.4°** |
| end heading | 354.7° | **357.8°** |
| closure | 19.2 mm | **8.5 mm** |

Warm motors also pivot truer — the +2%/90° over-rotation in run 1 was
mostly the cold pair, not a MOVE_X property. The residual −3.7° on the
warmed first leg says the warm-up helps but does not fully equalize
breakaway; a longer or faster warm-up, or `crawl_pulse`, is the next
knob if that matters.

**First run, cold (kept for the comparison):**

![square tour, cold](../captures/tovez-square-20260828/tovez_square_movex.png)

Route: 300 mm sides at 200 mm/s cruise, four +90° CCW pivots
(`MOVE_X 0 1571 150 10000`) — tour_chart.py's legacy origin-anchored
square. All 8 moves acked first try; each completion detected from
telemetry (wheels at rest on live frames), never a fixed sleep.
232 of 233 frames live — back-to-back MOVE_X kept the kernel stepping
the whole run, so there is no stale-freeze tail anywhere in this
capture.

**Access path** (tovez moved off the radio): tovez's USB is held open by
an mbdeploy fleet daemon (`mbdeploy serve`) on 192.168.1.149, advertised
over mDNS as `_mbserial._tcp`. `mbdeploy list --remote` finds it;
`mbdeploy connect tovez <line> --remote` speaks to it; this capture held
one raw TCP session to the advertised port (34259 — dynamic, resolve via
mDNS, do not hard-code). Connecting does NOT reset the target (measured:
`cyc` held 2276 across connects). Wire protocol is the same sequenced v6
as everywhere else.

Chart rendered with the standard tool:
`tools/tour_chart.py tovez_sq_pose.csv tovez_sq_vel.csv out.png
--side-mm 300`. The pose CSV is rebased to (0,0,0°) at the first frame
(the odometry frame held the whole day's accumulated pose, ~(5076,−2918)
mm / 683.1°, which tour_chart's ±2000 mm corrupt-sample filter would
have dropped wholesale). Rebase is a rigid change of frame, nothing
fitted.

## Numbers (capture: `captures/tovez-square-20260828/tovez-square-movex-20260828.json`)

- **Closure 19.2 mm** (of 1200 mm driven), almost entirely along the
  first-leg axis (+19.2, −0.6).
- **End heading 354.7° of 360° commanded.**
- Per-segment heading budget:

| segment | Δh believed |
|---|---|
| leg 1 | **−13.5°** |
| pivot 1 | +92.3° |
| leg 2 | +0.1° |
| pivot 2 | +91.7° |
| leg 3 | +0.6° |
| pivot 3 | +90.4° |
| leg 4 | −0.1° |
| pivot 4 | +93.2° |

Two findings sit in that table:

1. **The leg yaw is a cold-start event, not a per-leg cost.** Leg 1
   yawed −13.5° because the right wheel broke away ~0.4 s after the left
   (`vl=108,203` while `vr=0` in the first frames — the right motor had
   sat idle ~20 min). Legs 2–4, warm, injected ~zero. The square plots
   rotated ~12° against the commanded overlay because the overlay is
   anchored at the *start* heading — the same "rotated rectangle in pure
   odometry" bench signature `.claude/rules/playfield-testing.md`
   already records. A warm-up move before precision work would remove
   it.
2. **These MOVE_X pivots over-rotate ~+2%/90°** (mean +91.9°), where
   vevov's camera-truthed MOVE_X pivots ran ~0.75°/90°. UNVERIFIED
   whether that is tovez-vs-vevov, wheels-up-vs-loaded, or pivot cruise
   150 — settling it needs a loaded, camera-truthed run on the field.

Bench caveat, as always: wheels-up odometry measures the controller,
not the floor. `ox/oy ≈ 0` and `oh` barely moving in this capture are
the OTOS saying, correctly, that the *body* never moved — the honest
wheels-up discriminator, visible right on the chart as the OTOS cluster
at the origin.
