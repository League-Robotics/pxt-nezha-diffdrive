---
status: in-progress
sprint: '022'
tickets:
- 022-002
---

# The robot shows nothing on boot, so there is no way to confirm which build is actually on it

Priority: **Medium** — but it is the direct cause of repeated lost bench time,
because "did the flash take?" currently has no cheap answer.

## The problem

`test/test.ts` displays nothing at startup. A freshly flashed robot and a robot
carrying a months-old build look identical until you command something and
reason backwards from its behaviour.

That has burned real sessions. Sprint 018 ticket 003 had to establish firmware
identity indirectly — send a verb that exists in no earlier build and check for
a reply, then send a bogus verb and check for silence — purely to prove a flash
had landed. And on 2026-08-26 a robot that answered the protocol but never moved
took several rounds of measurement to explain, during which "is this even the
build I think it is?" could not be ruled out at a glance.

## What to change

On boot, `test/test.ts` shows an icon and then scrolls a short version string,
so the operator can read the build off the display.

- **Icon**: `IconNames.Rollerskate` (the micro:bit's skate icon).
- **Version string**: derived from this repo's `0.YYYYMMDD.n` version — the last
  two digits of the minor (the day of the month) then a dot then the revision,
  zero-padded to two digits. For `0.20260826.5` that is **`26.05`**.

Deliberately in `test/test.ts`, NOT in the extension. `src/blocks/` is
student-facing; a boot banner there would hijack the display of every student
program that ever imports this extension. The bench robots run `test.ts`, which
is what gets flashed, so that is where a flash-verification banner belongs.

The version has to reach the program somehow — `test.ts` cannot read
`pyproject.toml`. `make_deploy.py` already builds from a scratch copy
(`sync()` into `.tmp/deploy-head`), so injecting it there is the natural seam,
and it is the same seam the per-robot radio channel needs
(`firmware-hardcodes-one-radio-channel-for-a-multi-channel-fleet.md`). Doing
both through one mechanism is preferable to two.

Worth showing the robot name too if it is cheap, since the channel work makes
builds per-robot anyway and "which robot is this hex for" becomes a real
question.
