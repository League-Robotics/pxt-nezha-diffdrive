---
status: pending
sprint: '031'
---

# Sprint 030's four deferred hardware acceptance items need one scripted bench session

Sprint 030 ("Bus discipline and fiber safety") closed with every host
test green (847/847) but **four acceptance criteria explicitly
UNVERIFIED**, because no board was assigned to that session. None of
them failed — none of them were run.

They should go in **one scripted session**, batched with sprint 031's
tovez bench work rather than run piecemeal. Per
`.claude/rules/hardware-tickets-run-them-yourself` this is team-lead
work, not programmer dispatch.

## The four items

### 1. Ticket 001 — the bus-ownership guard actually protects the bus

A wire-issued OTOS read scripted to land **mid-drive** must no longer
corrupt the encoder sample. Watch that `i2cf` does not climb across the
run.

Source: `clasi/sprints/done/030-bus-discipline-and-fiber-safety/tickets/done/001-*.md`

### 2. Ticket 002 — the fiber-identity check actually stops the second fiber

Two checks:

- A **button-handler tour during a live `RUN` job** no longer corrupts
  the shared `lineBuf_`.
- A **block-side `startMove()` during a live wire obligation** is
  refused (`kBusy`) rather than silently superseding it.

Source: `.../tickets/done/002-*.md`

### 3. Ticket 004 — raw-zero rejection actually stops the teleport

A **cold power-up** run must show no odometry position jump in the
first ~40 cm. This one needs a **pre-fix repro run as the baseline**
plus a post-fix run — without the baseline the post-fix run proves
nothing, since a clean cold start is also what a working robot looks
like. Camera and encoder logs are the artifact.

Source: `.../tickets/done/004-*.md`

### 4. Ticket 005 Part B — the protocol fiber's stack high-water mark

Under a tour-plus-radio-`RUN` scenario:

1. Build with `DIFFDRIVE_FAULT_SPIN` to enable the `paintStackCanary()`
   scaffold (it compiles to `{}` in any other build).
2. Flash, run `RUN:tour` with a radio `RUN` issued mid-tour.
3. Halt with pyOCD, scan `currentFiber->stack_bottom .. stack_top` for
   the first non-`0xA5` byte.
4. Pass bar: comfortably under the fiber's documented 2 KB.

The full step-by-step recipe is written into ticket 005 itself.

Note the canary scaffold is **source-reviewed only** — no ARM toolchain
build was attempted, so sanity-build it before trusting the flash.

Source: `.../tickets/done/005-*.md`

## Recording the results

Every result goes in per `.claude/rules/measurement-citations.md`: name
the **capture artifact, board and date**, or record **UNVERIFIED** with
what was tried. An unchecked box with a runnable recipe is a
respectable outcome; an invented number is not.

Remember `captures/` is gitignored — `git add -f` the artifacts, or the
citation points at nothing from a fresh clone.
