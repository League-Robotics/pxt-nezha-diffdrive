---
status: pending
---

# `RUN pulse` silently shadows a student handler of the same name

Sprint 039 ticket 001 added the diagnostic pulse primitive as
`RUN pulse <ampLeft> <ampRight> <widthTicks>`, handled synchronously in
C++ (`WireAdapter::execPulse`). `WireAdapter::onRun` matches the name
**before** the registry lookup, unconditionally
(`src/comms/wire_adapter.cpp`, the `std::strcmp(name, "pulse")` branch).

That precedence is deliberate and correct: the characterization gate
needs the primitive reachable whether or not any TypeScript handler has
bound anything, and it needs a same-round-trip result, which the async
RUN path cannot give.

The gap is the collision, not the precedence. A program calling
`diffDrive.onRun("pulse", ...)` gets:

- its handler never invoked, with no error at registration or at call
  time;
- `FUNCS` listing its handler, because the listing comes from the
  registry, while the wire executes the C++ one instead.

So the listing and the behaviour disagree, which is exactly the failure
mode the surrounding code comments say the registry check exists to
prevent ("a wrong name used to look exactly like a dead robot").

Nothing registers `pulse` today. The nezha-robot-template programs use
`call`, `linea`, `nudge` and `sweep`. It is a live trap for the next
program that picks the name, and `pulse` is a plausible student choice.

## Options

1. Reserve the name explicitly: refuse or warn at registration when a TS
   program binds a name the C++ layer intercepts, so the conflict
   surfaces where it is created.
2. Mark reserved names in the `FUNCS` listing, so the listing stops
   disagreeing with what the wire does.
3. Registry first, C++ fallback. Cheapest, but it loses the guarantee
   that the diagnostic is always reachable, so it is the weakest option
   for the characterization gate.

Prefer 1 plus 2. Whichever is chosen, pin it with a host test in the
style of `tests/host/test_wire_motion_verbs.py`.

Out of scope for sprint 039 tickets 001-002 (stakeholder approved those
two only). Found by team-lead review of ticket 001, 2026-09-15.
