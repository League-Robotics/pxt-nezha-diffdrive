---
id: '005'
title: Hardware verification on vevov over zavaz
status: open
use-cases: []
depends-on:
- '001'
- '002'
- '003'
- '004'
github-issue: ''
issue: derive-each-micro-bit-s-radio-channel-group-from-its-five-letter-name.md
completes_issue: true
---
<!-- CLASI: Before changing code or making plans, review the SE process in CLAUDE.md -->

# Hardware verification on vevov over zavaz

## Description

Link-level hardware proof that the whole chain (firmware derivation,
`make_deploy`'s silicon gate and summary line, `robotlink`'s derived `!CG`)
actually works end to end on real silicon: vevov, derived **channel 37 /
group 43**, over the zavaz relay. **No commanded motion** — this is a link
check, not a driving test, so none of `.claude/rules/playfield-testing.md`'s
geofence/path-check machinery applies. Still run this from the bench stand
or a safe area, not mid-playfield, out of habit.

**The negative control is the point of this ticket, not an optional
extra.** A robot that answers `PING` on the new pair could simply be
answering on *both* the old and new pair (e.g. if the firmware change
didn't actually take, or a stale hex is still flashed) — proving nothing
changed. Only silence on the old `!CG 4 10` after confirmed life on the new
pair demonstrates the channel actually moved.

## Hard Constraint: `!CG` only — never `!N`

**Every relay tune in this ticket uses `!CG <channel> <group>`. Do not use
`!N <name>`, even though it looks like the more natural verb for a
name-derived scheme.** This is a hard constraint, not a preference.

microbit-radio-relay's shipping `!N` (branch `named-links`, HEAD `b6c8651`)
implements a **different algorithm** from this sprint's derivation — a
`h*31+b mod 65521` hash, present in both
`server/src/mbrelay/naming.py:61` and `source/relay/RadioRelay.cpp:777`.
Computed 2026-08-30 by running both mappings across the full 3125-name
space against that source (not a hardware measurement — a source reading,
per `.claude/rules/measurement-citations.md`): **the two mappings agree on
0 of 3125 names.** `!N vevov` would tune the relay to `(20, 212)` while
vevov actually sits on `(37, 43)` — producing a silent robot, which
`.claude/rules/playfield-testing.md` documents as one of the most expensive
symptoms to misdiagnose on this rig (see "The robot is OFF — check this
first" and the STATUS-looks-healthy trap in that file).

`!CG` takes explicit numbers and is unaffected by which relay firmware is
running. Remove this constraint only once microbit-radio-relay has migrated
`!N` to `docs/radio-addressing.md`'s scheme.

## Acceptance Criteria

- [ ] Build and flash: `uv run python tools/make_deploy.py --robot vevov
      --flash` completes, and the deploy-summary line (ticket 003) prints
      the derived pair — confirm it reads **`channel=37 group=43`** (or
      equivalent phrasing), not any other value. If it does not, STOP —
      that is a defect in ticket 001-003's work, not something to work
      around here.
  - [ ] Confirm the run went through ticket 003's silicon gate on its
        **match-and-proceed path, not the warn-and-continue path.** With
        `--flash` and a board attached, ticket 003 defines only two
        outcomes: hard failure (mismatch or unreadable silicon) or a
        proceeding build that confirms the read name. The warn-and-continue
        path only exists for a no-`--flash` build with nothing attached —
        seeing it here would mean the gate did not actually check anything,
        which is itself a defect to report, not proceed past.
- [ ] Positive control: tune zavaz to the derived pair
      (`!CG 37 43`), then:
  - [ ] `PING` -> `pong <n>` (per `.claude/rules/playfield-testing.md`,
        `PING` is unsequenced and is the correct liveness probe — do not
        use `HELLO` for this; see next bullet).
  - [ ] `ID` names `vevov` in its reply.
  - [ ] `HELLO` is sent **at most once, at session start only** (to sync
        the wire sequence for anything sequenced you might send later) —
        it is a session RESET, not a liveness probe
        (`.claude/rules/playfield-testing.md`, "v6 wire commands MUST
        carry a sequence id"). Do not fire it again mid-session to "check"
        anything.
  - [ ] Identity is read from `HELLO`'s banner / the `ID` reply, **never**
        from `mbdeploy probe`'s cached ROLE column (that column is a stale
        registry, not a live read — same rule file, "`mbdeploy probe`'s
        ROLE column is a cached registry, not a live read").
- [ ] **Negative control (mandatory).** Retune zavaz to the OLD pair
      (`!CG 4 10`) and confirm the board is **silent** — no `pong` to
      `PING`, no reply to `ID`/`HELLO`. Try at least 2-3 times over a few
      seconds before concluding silence (a single missed reply on a lossy
      link is not evidence; per `wire_acceptance.py`'s own doc comment,
      "absence of a reply is NOT evidence of absence" on a single try —
      the torture-pool measurement of 66-83% per-line delivery is the
      relevant base rate to keep in mind even though this is zavaz, not
      the torture pool). Record what was actually observed (replies or
      silence, and how many attempts).
- [ ] Every `MEASURED` claim written into the capture file names its
      artifact per `.claude/rules/measurement-citations.md` — the capture
      file itself IS the artifact for most of these, so "MEASURED vevov
      2026-08-30, captures/radio-addressing-<date>.md: ..." is the correct
      citation shape; do not write "measured" without naming where the
      output is recorded.
- [ ] `captures/radio-addressing-<date>.md` is created (repo convention —
      see e.g. `captures/vevov-wheel-scale-20260828.md`,
      `captures/otos-run-handler-i2c-hang-20260828.md` for the existing
      markdown-capture shape in this directory) recording:
  - the exact commands run and raw wire output (or a faithful transcript)
    for the build/flash, the positive control, and the negative control;
  - the deploy-summary line's printed channel/group;
  - explicit confirmation (or, if it happened, an honest report of a
    failure) for each of the three checks above.
- [ ] Do **not** retune getez. It is out of scope for this sprint (sprint
      doc's "Out of Scope" section) and forbidden by
      `.claude/rules/playfield-testing.md` — the torture:8760 relay pool
      depends on getez staying on channel 3.
- [ ] Every tune command run in this ticket (positive control, negative
      control) is `!CG <channel> <group>` with explicit numbers. `!N` is
      not sent at any point — see "Hard Constraint" above.

## Implementation Plan

### Approach

This ticket is a verification run, not a code change — no source files are
modified. Sequence:

1. Confirm tickets 002-004 are done and their host tests pass (this
   ticket's `depends-on` already encodes that ordering; do not start this
   ticket if any of them is still open).
2. Room lights: confirm the Shelly at `192.168.1.122` reports `output:
   true` before doing anything camera-adjacent — not required for this
   link-only check (no camera use), but check anyway per
   `.claude/rules/playfield-testing.md`'s standing habit if the bench area
   shares the field's lighting.
3. `uv run python tools/make_deploy.py --robot vevov --flash`. Watch for
   the deploy-summary line; record it verbatim.
4. Open a serial/relay session to zavaz (`tools/robotlink.py`'s
   `open_link(radio=True)` now defaults to deriving vevov's own pair per
   ticket 004 — using it here is a legitimate way to run the positive
   control, since it exercises the exact code path ticket 004 changed; a
   manual `!CG 37 43` typed by hand is an equally valid, more manual
   verification of the same fact if preferred).
5. Run the positive control (PING/ID, single HELLO at session start only).
6. Retune to `!CG 4 10` (either manually or by constructing the legacy
   pair by hand — `robotlink.py` no longer has `ZAVAZ_CHANNEL`/
   `ZAVAZ_GROUP` constants after ticket 004, so this step is necessarily
   manual/explicit, which is appropriate for a negative control you want
   full control over).
7. Run the negative control; record silence (or, if not silent, stop and
   report — do not paper over an unexpected positive result).
8. Write the capture file.

### Files to Create

- `captures/radio-addressing-<date>.md` (use today's actual run date).

### Files to Modify

None — no source changes in this ticket.

### Testing Plan

- **Existing tests to run**: none (no source changed); optionally re-run
  `uv run pytest tests/host/test_radio_address_derivation.py
  tests/tools/test_radio_address.py` as a final sanity check immediately
  before flashing, to confirm the branch's host-testable logic is still
  green going into a hardware run.
- **New tests to write**: none — this ticket's "test" is the hardware
  capture itself, not an automated test.
- **Verification**: the capture file's content, cross-checked against this
  ticket's acceptance criteria above.

### Documentation Updates

None beyond the capture file itself. If this run surfaces anything
surprising (e.g. an unexpected reply during the negative control, a
mismatch between the deploy-summary pair and 37/43), do not silently patch
it into this ticket's plan — stop, record what was observed, and raise it
to the team-lead per the Exception Protocol / guard-block posture used
elsewhere in this sprint's tickets.
