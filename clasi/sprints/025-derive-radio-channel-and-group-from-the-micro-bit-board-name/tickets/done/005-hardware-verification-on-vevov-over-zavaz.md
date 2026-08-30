---
id: '005'
title: Hardware verification on vevov over zavaz
status: done
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

## Target substitution: gopiv/torture, not vevov/zavaz (recorded 2026-08-30)

**The stakeholder redirected this ticket's hardware target from vevov/zavaz
to gopiv, over the torture:8760 mbrelay pool, at dispatch time.** vevov and
zavaz were not connected/reachable in this session; tovez was on local USB
but is explicitly out of scope (not the target, must not be touched).

Everywhere below that says "vevov" / "zavaz" / "channel 37 / group 43" /
"channel 4 / group 10", read it as:

| original (vevov/zavaz) | substituted (gopiv/torture) |
|---|---|
| vevov | gopiv |
| derived pair 37/43 | derived pair **47/60** (n=1461) |
| zavaz (dedicated USB relay) | torture:8760 pooled relay service (round-robin; never getez) |
| old pair `!CG 4 10` | old pair **`!CG 5 10`** (`radio-robot-lib/config/robots/gopiv.json` `connection.radio_channel=5`, firmware group 10, the legacy hand-allocated convention) |

Why gopiv is still a valid substitute for this ticket's purpose: it is a
bench test rig (one motor, no wheels, never on the playfield), so there is
no motion/geofence risk either way, and it is on real silicon reachable
right now, which vevov was not. The chain being proven (firmware
self-addressing + `make_deploy`'s silicon gate/summary line + a relay
retuned with explicit `!CG`) is robot-agnostic.

**Known gap surfaced by this substitution**: ticket 003's silicon gate
(`_verify_robot_silicon()`) calls `mbdeploy.devices.read_board_name()`,
which needs local SWD/pyOCD access. gopiv is reached only over the network
(`mbdeploy connect/deploy --remote`), so the gate cannot read its silicon at
all and — correctly, per its own warn-vs-fail design for a no-`--flash`
build with nothing locally attached — falls back to a WARN, not a hard
match/fail. This means the silicon gate provides no protection for a
remote-only board; identity for gopiv in this ticket is established solely
by `HELLO`/`ID` over `mbdeploy connect --remote`, which is a live read of
the board's own banner (the correct authority per
`.claude/rules/identity-comes-from-hardware-not-config.md`), just not via
the gate's own SWD path. This is a real gap in ticket 003's coverage for
remote boards, worth a follow-up ticket/issue, not something fixed here.

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

- [x] Build and flash: **substituted** `uv run python tools/make_deploy.py
      --robot gopiv` (no `--flash` — see "Target substitution" above for
      why) then `mbdeploy deploy --remote gopiv --hex <path>`, completes,
      and the deploy-summary line (ticket 003) prints the derived pair —
      confirmed it reads **`channel=47 group=60`** (gopiv's derived pair,
      not vevov's 37/43). See `captures/radio-addressing-20260830.md`
      section 2.
  - [x] Confirmed the silicon gate's behaviour on the path this
        substitution actually exercises: **warn-and-continue**, not
        match-and-proceed — correct for a no-`--flash` build with no
        *locally* attached board (gopiv is remote-only). This is NOT the
        match-and-proceed path the original vevov criterion describes,
        because that path requires local SWD, which a remote board never
        has; recorded as a real coverage gap for remote boards (capture
        section 2/6), not a defect fixed in this verification-only ticket.
- [x] Positive control: tune (a torture:8760 pool relay) to the derived
      pair (`!CG 47 60`), then:
  - [x] `PING` -> `pong <n>` (4/4). See capture section 4.
  - [x] `ID` names `gopiv` in its reply.
  - [x] `HELLO` sent once, at session start only.
  - [x] Identity read from `HELLO`'s banner / the `ID` reply, never from
        `mbdeploy probe`'s cached ROLE column (not used anywhere in this
        run).
- [x] **Negative control (mandatory).** Retuned (a torture:8760 pool
      relay) to gopiv's OLD pair (`!CG 5 10`) and confirmed the board is
      **silent** — no `pong` to `PING` (4 attempts), no reply to `ID`/
      `HELLO` (6 attempts total). See capture section 5.
- [x] Every `MEASURED` claim written into the capture file names its
      artifact per `.claude/rules/measurement-citations.md`.
- [x] `captures/radio-addressing-20260830.md` created, recording the exact
      commands and raw output for the build/flash, positive control, and
      negative control; the deploy-summary line; and explicit
      confirmation of each of the three checks above.
- [x] getez was **not** retuned. The negative control's first pool
      allocation came back getez; the script refused to `!CG` it and
      reconnected instead, landing on `zetog`. See capture section 5.
- [x] Every tune command run in this ticket is `!CG <channel> <group>`
      with explicit numbers. `!N` was not sent at any point.

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
