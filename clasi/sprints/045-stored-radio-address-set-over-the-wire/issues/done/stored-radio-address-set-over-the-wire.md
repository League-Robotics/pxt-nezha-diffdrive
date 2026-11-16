---
status: done
sprint: '045'
tickets:
- 045-001
- 045-003
---

# Stored radio address, set over the wire, kept across a re-flash

## Stakeholder request (2026-11-15)

From the robot-console radio dialog: "I can click Save, and that'll set
that as my channel and group for my robot. Then we need to make sure
that when we flash the robot again, we're going to use that channel and
group."

This is step 3 of the fleet channel map (`mbtools`
`docs/design/channel-map.md` section 1: "Robot firmware. A stored
radio-channel setting written over USB."). The console half is
robot-console `clasi/issues/select-a-free-channel-and-set-it-on-the-robot.md`.

## What exists

- At boot `setupRobot()` takes the address from `control.deviceName()`
  unless the program called `setupRadio(ch, grp)` itself
  (`blocks/program.ts`).
- Stored in flash today: calibration (`#cal.*`), the Wi-Fi address
  (`#net.ip`) and Wi-Fi credentials. `#`-prefixed settings keys are kept
  when a different program is flashed.
- No stored radio setting, and no wire command for the radio address.
  Changing the address mid-run is unverified (`src/DESIGN.md`).

## What to build

1. A stored radio address under `#`-prefixed settings keys (channel
   0-83, group 0-255).
2. Boot order: an explicit `setupRadio(ch, grp)` in the program, then
   the stored address, then the name-derived one. The boot line and
   STATUS keep reporting the address in use; STATUS or a show command
   also says where it came from (program, stored, name).
3. Run commands in the existing style (`_netshow`/`_netset`/`_netclear`):
   `_radioshow`, `_radioset <channel> <group>`, `_radioclear`. A set
   answers with the stored values so the console can read them back.
   Decide whether a set takes effect at once or at the next boot; at the
   next boot is acceptable (the console reboots the robot with
   `_reboot`), and avoids the unverified mid-run change.
4. Hardware check: set an address, reboot, confirm STATUS; flash a
   different program and the same program again, confirm the address is
   kept; clear, confirm the name-derived address returns.
5. Release, then a nezha-robot-template release built on it, so the
   console's calibration firmware carries the feature.
