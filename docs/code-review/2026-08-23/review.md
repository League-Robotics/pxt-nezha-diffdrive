# Code Review — 2026-08-23

**Scope**: `src/` (C++ firmware + TypeScript blocks), `tools/`, `tests/host/`,
`test/`, build wiring. Code state: as-built through sprint 003 (sprints 004/005
planned, not executed).
**Method**: per [guidelines.md](../guidelines.md). Phase 0 bootstrapped and
validated the CLASI design-doc set (`docs/design/design.md` + per-root
`DESIGN.md`) and refreshed overview/specification/usecases. Six reviewers then
fanned out by dimension/subsystem; six adversarial verifiers independently
re-derived every Critical/Major finding (and sampled Minors) from source.
**Verification outcome**: 0 findings refuted outright, 1 severity downgrade
(Critical→Major), 1 half-refutation, several scenario corrections — all folded
in below. Corrections are noted inline; the verifier reports carry the proofs.

**Annexes** (full detail lives there; this report consolidates):
[correctness-kernel](raw/correctness-kernel.md) ·
[correctness-wire](raw/correctness-wire.md) ·
[correctness-blocks](raw/correctness-blocks.md) ·
[modularity-api](raw/modularity-api.md) ·
[python-tools](raw/python-tools.md) ·
[comment-audit](raw/comment-audit.md), each with a matching `verify-*.md`.

**Totals**: **0 Critical · 28 consolidated Major · ~40 Minor · comment work
order (135 items)**. Several Majors were found independently by two or three
reviewers; they are merged here with all source IDs cited.

---

## Executive summary

The layering is genuinely clean — the include/call graph matches
`src/DESIGN.md`'s claims exactly, the kernel/ports/engine separation held up
under adversarial checking, and the hardware-lore comments in the ports and
kernel are exemplary. The trouble is concentrated in four places:

1. **The `go to` geometry is wrong for large turn angles.** The
   `theta = 2·atan2` arc encoding composes badly with the ≥50° pivot-first
   split: `goToR(100,100)` misses by 115 mm on a 141 mm hop, and a target
   behind the robot degenerates to a ~359° pivot plus a 31-metre leg. Host
   tests deliberately stay under the split threshold, so this is green-but-
   untested. It affects the student block path, not just the wire.
2. **Silent dead-ends students and hosts cannot see.** The stall latch has no
   un-latch caller and no readback anywhere — 500 ms of blocked wheels
   disables the robot for the rest of the program while every API keeps
   reporting success. STATUS hardcodes `otos=0`. The `lastDone` completion
   channel is permanently inert. The documented `while (driveTick())` idiom
   exits immediately. The wire's "0 = default" cruise sentinel commands a
   full-duty lunge.
3. **Mirrored constants are already drifting.** The wire reports version
   1.0.0 against pxt.json's 1.0.10; emitLine clips at 200 bytes against the
   transports' 240; the serial RX ring is still v5-sized (128 B); the host
   harness's test doubles have drifted from production in three
   places that make three behaviors untestable.
4. **The bench-tool family has rotted against v6.** Beyond the known TLM gap
   (sprint 005), the numeric `RUN:<n>` vocabulary is a silent no-op against
   current firmware — six tools issue commands that do nothing — and five
   tools hardcode a stale venv whose `aprilcam` import fails. Seven copied
   `Cam` scaffolds (bypassing the shared one in `camlink.py`) have already
   diverged in tuple order and scoring semantics.

Two findings are **flags on the open sprint plans**, not code defects: the
radio RX path is structurally undersized for sprint 004's full-v6 goal, and
sprint 004 ticket 002's acceptance criteria assert the serial TX path needs no
concurrency guard — the confirmed WIRE-04 interleaving defect says otherwise.

---

## Major findings (consolidated, verified)

IDs `R-NN` are this report's; source annex IDs and verifier verdicts in
brackets. Ordering is by triage priority within each group, not severity rank.

### Control correctness (kernel / motion engine / ports)

**R-01 — Stall latch is an invisible dead end.** [KERN-01 ↓Critical→Major +
API-02; both CONFIRMED] `clearStallLatch()`'s only caller is a host-test shim;
no block, wire verb, or shim reaches it; `estopClear()` clears only the e-stop
latch; there is no discoverable readback (only undocumented `probe(2)`).
After 500 ms of blocked wheels the robot ignores all motion for the rest of
the program while `drive()` returns `kOk` and blocking moves "complete"
instantly. Power-cycle recovers, which is why the verifier downgraded from
Critical. *Remedy*: expose clear + readback (block, wire verb, STATUS bit),
and decide whether e-stop-clear should also clear it.

**R-02 — `goTo` geometry misses badly past the pivot-split threshold.**
[KERN-02 CONFIRMED, blast radius broadened] The arc encoding
(`theta=2·atan2(y,x)`, arc length s) is only consistent when executed as one
arc; `moveX`'s ≥50° pivot-first split executes theta then s as a straight leg:
`goToR(100,100)` → pivot 90°, drive 157 mm → ends at (0,157), 115 mm off a
141 mm target. Affects the **block** `go to`/`start go to` path
(main.ts→shims.cpp:411→moveX) as well as GO_TO_R. Host tests stay below the
threshold, so nothing catches it. *Remedy*: recompute the post-pivot leg
toward the target (or split the arc geometrically), and add host tests above
the threshold.

**R-03 — Behind-the-robot targets go the long way around.** [KERN-03
CONFIRMED, arithmetic re-derived] `GO_TO_R -100 1` → θ=6.263 rad, R=5000 mm,
s=31.3 m: a ~359° pivot then a 31-metre "straight" leg, bounded only by the
caller's timeout. *Remedy*: normalize theta to ±180° and choose the short
arc; reject or clamp pathological radii.

**R-04 — `arrive` tolerance is accepted and discarded; at-target `goTo`
pivots.** [KERN-04 CONFIRMED] The documented no-op requires float-exact
equality, which measured pose never satisfies: being 0.5 mm off can trigger
up to a 180° pivot. *Remedy*: implement the arrival-tolerance check.

**R-05 — OTOS heading seed clamps instead of wrapping.** [KERN-05 CONFIRMED]
`writePoseMm` clamps to ±32767 LSB ≡ ±179.89°; a 350° seed (0–360 camera
convention, or the deliberately-unwrapped odometry heading echoed back)
lands 170° wrong and the two pose sources start disagreed — poisoning the
drift measurement `seedPose` exists to serve. *Remedy*: wrap to ±180° before
the register write.

**R-06 — `timeout 0` on WHEELS_X: acked, never ticked, stale lease lurch.**
[KERN-06 CONFIRMED] Decode accepts 0, the tick obligation expires
immediately (nothing moves, host sees `ok`), but a wall-clock 10 s kernel
lease stays armed: the robot lurches into the stale command whenever
anything next ticks. `MOVE_X … 0` is meanwhile an instant silent no-op — the
two verbs disagree about what 0 means. *Remedy*: reject 0 (or define it
consistently) and cap/clear the lease with the obligation.

**R-07 — Brick MCU reset mid-session teleports odometry ~4 m.** [KERN-07
code-path CONFIRMED; hardware premise UNVERIFIABLE statically] The glitch
armor's two-strike rule accepts the post-reset counter discontinuity as
truth; no production path rebaselines. *Decisive bench check*: power-cycle
the brick mid-drive, watch DIAG 10/11 and pose. Cross-refs the known
boot-wedge issue but is a distinct mid-session failure.

**R-08 — Cross-fiber stop lands in the kernel's settle window ~⅓ of the
time.** [BLK-01 CONFIRMED, timing re-derived] `stopMove()`/`stop()` from
another fiber (or `isMoving()` polling at a move deadline) can hit the
8 ms settle window of `step()`; the stop is staged but not delivered, wheels
hold last duty until the watchdog (~100–150 ms) — reintroducing the measured
+9–13°/turn overshoot the settle logic was built to kill. *Remedy*: deliver
staged neutral inside `step()`'s settle path, or make the stop path push duty
directly.

**R-09 — Continuous-mode odometry integrates one giant chord.** [BLK-05
CONFIRMED; scenario corrected to an unconditional tick loop, e.g.
testrig.ts:118–120] In velocity mode nothing calls `odomUpdate()` (all nine
call sites are move-path or pose-read); the next pose read integrates the
entire interval as one chord — after a driven full circle, pose reports ~the
path length instead of ~0. *Remedy*: fold `odomUpdate()` into the continuous
tick path.

### API contract (blocks and wire)

**R-10 — The documented continuous-drive idiom stops the robot in 150 ms.**
[API-01 CONFIRMED — the review's top API finding] `driveTick()` returns
*move-engine* state; `driveTwist()`/`wheelsV()` first cancel the move planner,
so the documented `while (diffDrive.driveTick())` loop exits on its first
iteration and the watchdog stops the robot. All four documentation sites
(README ×2, spec §4.2, UC-002) prescribe the broken idiom; testrig.ts
quietly uses a different, working one; no in-tree program uses the documented
form. *Remedy*: decide the contract (return "keep ticking" in velocity mode,
or a separate `driveHold()` idiom), then fix code+docs together.

**R-11 — `cruise 0` "configured default" = full-duty ~875 mm/s lunge.**
[BLK-03 + API-03 CONFIRMED] All four motion verbs resolve the documented
0-sentinel to `fullDutyVelocity` ≈ 875 mm/s — 1.5× the speed the project's own
bench notes call unusable. Upstream's vendored-away comment (recovered during
the comment audit from radio-robot: `fullDutyVelocity = 0` ⇒ "uncalibrated →
VELOCITY refused") shows the sentinel originally meant *refuse*, not *floor
it*. *Remedy*: resolve 0 to `defaultSpeed`-equivalent (or reject), and add a
`default_cruise` config field.

**R-12 — Simulator turns 10× too slowly on `set wheel speeds`.** [BLK-06
CONFIRMED two ways] A stray `/10` in the sim body (main.ts:804) disagrees
dimensionally and with `_driveTwist`'s correct sim math. Students tune a turn
in the simulator and get 10× the rotation on hardware.

**R-13 — Simulator never latches e-stop.** [BLK-07 CONFIRMED] Hardware
refuses at two layers after `emergency stop`; the sim refuses nothing, so the
UC-011 "forgot to clear" trap — called out in the use cases as the classic
student pitfall — is invisible exactly where students develop.

**R-14 — `rotationalSlip` is tuned-but-untunable.** [API-06 CONFIRMED]
Getter-only, hard-coded 0.952 (measured for vevov); not in `setGeometry`, not
in `kFields`, no block. The only palette knob that changes turn geometry is
`set track width` — which the design docs explicitly forbid using for slip.
A different chassis cannot be calibrated without recompiling.

**R-15 — `runArgCount()` missing the null guard its sibling has.** [BLK-02
CONFIRMED, narrowed] main.ts:233 dereferences `runParts` unguarded; any call
before the first RUN event is the documented panic-980 boot death. Narrowing:
any top-level `onRun`/`onRunCommand` registration disarms it via
`ensureRunState()`, so only programs using `runArgCount` without registering
a handler are exposed. One-line fix.

**R-16 — The numeric `RUN:<n>` vocabulary is silently dead.** [BLK-04 + PY-01
CONFIRMED] The v6 dispatch matches RUN by exact *name*; `testrig.ts`'s
catch-all stores the argument, never the name; so every numeric command from
`otos_bench.py` and five bench tools does nothing, with no error anywhere.
Updates the filed `testfiles-are-not-type-checked-testrig-is-broken` issue
(whose quoted type error is now stale) with a worse fact: it compiles-ish and
does nothing.

### Wire plumbing

**R-17 — Wire reports version 1.0.0; the extension is 1.0.10.** [WIRE-01 +
MOD-01 + BLK-09 + comment audit; CONFIRMED ×3] `protocol.cpp:63`'s manual
mirror drifted ten bumps ago despite its "keep in sync" comment — exactly the
landmine `src/DESIGN.md` §10 predicts. Defeats deploy verification (the
`mbdeploy`/DIAG flow relies on VER). *Remedy*: generate the constant from
pxt.json at build time, or check it in a host test.

**R-18 — Motion timeouts above 2^31 ms wrap; the move dies at ~150 ms.**
[WIRE-02 CONFIRMED, wrap re-derived] `parseUint32` admits `4294967295`; the
deadline arithmetic wraps negative; the obligation never arms and the
watchdog kills the acked move — the ticket-011 starvation bug resurrected for
large timeouts. One added pytest parameter would have caught it. *Remedy*:
cap timeout at decode.

**R-19 — Serial RX ring is still v5-sized: 128 B against 240 B lines.**
[WIRE-03 CONFIRMED, phrasing softened] During wire-driven motion the fiber
drains every ~24 ms (~276 B/window at 115200); a near-max line plus anything
else in the window drops bytes deterministically enough that reliability-layer
resends re-enter the same failure. *Remedy*: size the ring ≥ 2× max line.

**R-20 — Two fibers write one serial port with no guard, and `send()`
returns are ignored.** [WIRE-04 CONFIRMED, serial half] `emitLine` (TS fiber)
and protocol-fiber replies/keepalives interleave or silently drop.
**Sprint-004 flag**: ticket 002's AC explicitly declares serial needs no
guard — that AC is wrong as written and should be amended before execution.

**R-21 — `emitLine` clips at a bare 200 while the transports carry 240.**
[WIRE-05 CONFIRMED, precision fix: the radio's own clip is currently
unreachable — emitLine pre-clips] Long test-result lines truncate silently;
the parity comment at `radio_transport.h:118` restates an equality that
stopped being true when ticket 005 raised serial only. *Remedy*: single
shared line-capacity constant.

**R-22 — STATUS hardcodes `otos=0` even when the OTOS is live.** [WIRE-06 +
API-04 CONFIRMED] Same session: `engineGoToW` gates on `otos.connected()`
while STATUS swears there is no OTOS — a confidently-wrong field that will
misroute sprint-005 host gating. Fold into the filed
`status-lost-diag-numeric-surface` issue.

**R-23 — Hosts have no motion-completion signal.** [WIRE-07 CONFIRMED as
landmine] `lastDone()`/`lastDoneReason()` are permanently inert (documented
decision); with R-22, STATUS `active`-flicker is the only completion
evidence. Neither sprint 004 nor 005 plans completion work; sprint 005's
closed-loop tooling will need one. *Remedy*: DONE event or truthful
STATUS-done fields, planned into 005.

### Tooling and tests

**R-24 — Five tools hardcode a stale venv; camera loss is silent.** [PY-02 +
PY-04 CONFIRMED by re-running the import probe] The AprilTags/.venv
interpreter no longer imports `aprilcam` (pipx one does); every spawn uses
`stderr=DEVNULL`; `tour_watch` checks `cam.err` once at +1.5 s, `tour_run`
discards camlink's `ERR` lines entirely and its never-invalidated `latest`
lets `place()` re-seed the world frame from a frozen pose. Recorders produce
camera-less sessions that look like "robot invisible".

**R-25 — The host harness's doubles have drifted from production in three
load-bearing places.** [PY-03 CONFIRMED both sides] (a) harness STATUS
`wedge` reads the *latched* fields, hardware DIAG reads *suspect* (ordinals
6/7); (b) the `setWheelsTimed` double calls `kernel.drive()` directly,
skipping `MotionEngine::wheelsV()`'s `cancelMove()`; (c) `getConfigValue`
truncates where production rounds. Three behaviors no test can currently
catch — the "mirrors field-for-field" comments are false. *Remedy*: re-sync
doubles + a drift test that compiles both against one contract.

**R-26 — The tour/truth family is scaffold-copied and already diverging.**
[PY-05 + MOD-02 CONFIRMED, spot-verified] 7 copied `Cam` wrappers (bypassing
the shared `Cam` in camlink.py:48) with two incompatible `latest` tuple
orders; 8 `wrap()`s; 6 playfield-constant blocks; 4 corner scorers whose
outputs already disagree (console "SW 31.3cm" vs chart "SW=unobserved" for
the same run); a 2-way venv-path fork. Sprint 005's planned `tlm.py` covers
none of it. *Remedy*: `tools/camproc.py` + `tools/field.py` alongside tlm.py;
route everything through robotlink/camlink.

### Design / planning

**R-27 — Radio RX is structurally undersized for sprint 004's goal.** [DES-01
CONFIRMED with nuance] 64-byte ×2 single-slot, single-fragment RX against
240-byte v6 lines; the sprint plan mentions the limit once as an accepted
caveat and schedules zero capacity work; the caveat's "single-fragment"
phrasing hides the clamp-to-parseable-prefix hazard. Amend sprint 004 before
execution.

**R-28 — Vendoring from radio-robot was lossy.** [comment verifier, upstream
fetched] Five comments in `diffdrive.h` are truncated mid-sentence (one —
`fullDutyVelocity` 0-means-refuse — encodes the contract R-11 tripped over);
upstream path has moved (`src/firm/diffdrive/`), and two audit replacements
named a nonexistent repo. *Remedy*: re-diff the vendored kernel against
upstream; restore full comments; document the real upstream path in
`src/DESIGN.md` provenance.

---

## Minor findings

~40 items, itemized in the annexes; recurring themes: duplicated constants
(`0x2001` radio group unpinned in main.ts:154 vs protocol.cpp:85; kDiag*
re-declared; DIAG case-25 spliced between the 23/24 comment and its cases),
float→int cast UB at the wire boundary (host/target sign split, WIRE-08),
under-initialized `[18]` verb tables that make add-a-verb fail loudly but
remove-a-verb compile silently (WIRE-09, narrowed to unrecognized-verb/HELP
paths), `make_deploy.py`'s `endswith('test.ts')` filter silently excluding
testrig.ts, unguarded divides in truth tools, a dead `microphone` dependency
in pxt.json, a tsconfig file set that cannot type-check main.ts, dead
`maxNudges`, and `goToWorld`'s exported JSDoc still promising the repeat-
until-arrival behavior the one-pass rewrite removed (contradicts the
camera-is-diagnostics doctrine).

## Comment hygiene (work order)

854 comment blocks audited across 59 files: **11 DELETE · 123 REWRITE · 1 ADD
· ~719 KEEP** (~16% noise, bimodal: kernel/ports/tools near-exemplary; the
wire-layer headers are sprint transcripts). Worst: `serial_transport.h` (83%
noise — describes the retired v5/COBS link and a `readLine()` that no longer
exists), `wire_adapter.h` (71% — 108-line ticket chronicle), `tests/host/
README.md` (60% — claims the wire/motion modules "don't exist yet").

Spot-verification: all 11 DELETEs safe; **8 of 16 sampled REWRITEs would have
lost load-bearing content** (worst: a slip-derivation shortcut that would bait
a future re-measurer into "correcting" 0.952→0.915). **Cleanup protocol**:
apply [comment-audit.md](raw/comment-audit.md) *with*
[verify-comments.md](raw/verify-comments.md)'s corrections; any unsampled
REWRITE gets the same load-bearing check before applying; the five truncated
`diffdrive.h` comments are restored from the upstream text quoted in the
verifier report. The audit's 5-anti-pattern section (ticket-archaeology
headers, reviewer-justification essays, stale cross-layer claims, diff
restatement, orphaned comments) should feed the coding-guidelines doc.

## Design assessment

- **Layering: clean.** Include/call graph verified against `src/DESIGN.md` §1;
  no violations in either direction. The kernel/ports/engine boundaries are
  real and held under adversarial reading.
- **Doc set: bootstrapped and validating.** `clasi design validate` passes;
  overview/specification/usecases refreshed to as-built reality in Phase 0.
  One doc defect found post-bootstrap (tools/DESIGN.md's "RUN: path still
  works") has been corrected in place.
- **Structural risks**: the manual-mirror pattern (R-17/R-21 and the TS↔C++
  constant pairs) is the design's weakest habit — every mirrored constant
  found had either drifted or lacked a guard; the fix is single-source or
  drift tests, case by case. Second: silent-refusal-as-policy (stall latch,
  e-stop, cruise sentinel, STATUS otos) is defensible per-decision but has
  compounded into an API where the robot can be "off" for five different
  reasons a student cannot distinguish; a single visible "why won't it move"
  surface (STATUS/DIAG/block reporter) would retire the whole class.

## Sprint plan flags (act before execution)

1. **Sprint 004 ticket 002**: AC wrongly asserts serial TX needs no
   concurrency guard (R-20 contradicts it).
2. **Sprint 004**: no RX-capacity work despite the full-v6-over-radio goal
   (R-27); the accepted caveat under-describes the hazard.
3. **Sprint 005**: needs a motion-completion signal (R-23) and should extend
   its tlm.py consolidation to the camera/field scaffolds (R-26); its
   closed-loop tooling will also hit R-22's false `otos=0`.

## Proposed issues for triage

Groupings below are proposals; nothing filed yet.

| # | Proposed issue | Covers | Priority |
|---|---|---|---|
| 1 | goTo geometry: pivot-split miss, long-way arcs, dead `arrive` | R-02 R-03 R-04 | High |
| 2 | Stall latch: expose clear + readback; unify "why won't it move" | R-01 (+design note) | High |
| 3 | Wire timeout hardening: reject 0, cap 2^31, unify verb semantics | R-06 R-18 | High |
| 4 | Stop-delivery race in settle window | R-08 | High |
| 5 | driveTick contract: fix idiom in code+docs | R-10 | High |
| 6 | cruise==0 sentinel → safe default | R-11 | High |
| 7 | Continuous-mode odometry chord error | R-09 | Med |
| 8 | OTOS seed heading wrap | R-05 | Med |
| 9 | Simulator parity: 10× turn, e-stop latch | R-12 R-13 | Med |
| 10 | Wire constants: kVersion single-source, line-cap constant | R-17 R-21 | Med |
| 11 | Serial transport: RX ring size + TX serialization (amend 004-002) | R-19 R-20 | Med |
| 12 | Host-harness double drift + drift test | R-25 | Med |
| 13 | Tools link-layer consolidation (venv, Cam, field, ERR handling) | R-24 R-26 | Med |
| 14 | Numeric RUN vocabulary — fold into testfiles issue | R-16 (update existing) | Med |
| 15 | STATUS truthfulness — fold into status-lost-diag issue | R-22 (update existing) | Med |
| 16 | Motion-completion signal for hosts (plan into 005) | R-23 | Med |
| 17 | Brick-reset teleport: bench check + rebaseline | R-07 | Med |
| 18 | rotationalSlip setter | R-14 | Low |
| 19 | runArgCount guard (+ shim Minors batch) | R-15 + Minors | Low |
| 20 | Comment cleanup per work order + guidelines doc | audit + verify | Low |
| 21 | Upstream re-diff of vendored kernel | R-28 | Low |
