---
status: pending
---

# A flash that mass-erases wipes the stored radio address, calibration and Wi-Fi address

Found 2026-11-15 by sprint 045 ticket 003 on tovez
(`captures/sprint045-stored-radio-20261115/notes.md`, finding 2).

`#`-prefixed settings survive a flash only when the flash leaves the
settings pages alone. `mbdeploy deploy tovez` did not: its erase step
failed with firmware running (pyocd `0x67` at address 0, or a probe
timeout), and the recovery in mbtools `flashlogic.flash_hex` is a CTRL-AP
mass erase, which clears the whole chip. The stored radio address was
gone after each such flash. The mass-erase runs were not kept as capture
files; what is captured is the other half: a sector-erase flash of a hex
trimmed to 0x1000..0x80000 keeps the address (`06-flash_b.txt`,
`08-flash_a.txt`, then `07-`, `09-`).

So the stakeholder goal of sprint 045 ("when we flash the robot again,
we're going to use that channel and group") holds in the firmware but
not through the normal flash path on a board that takes the mass-erase
recovery. Stored calibration and the stored Wi-Fi address are lost the
same way.

## To settle

- How often the console's flash takes the mass-erase path: only on the
  self-locking boards (0x67), or on any board whose firmware is running.
  tovez is not one of the boards first listed as self-locking.
- Which side fixes it. Options:
  1. mbtools: flash without a mass erase when the board allows it
     (connect under halt, sector erase, skip sector 0 and UICR when they
     are identical), keeping mass erase as the last resort and saying so
     in the flash result.
  2. mbtools or the console: read the stored settings before a flash that
     will mass-erase (`_radioshow`, `_calshow`, `_netshow`) and write them
     back after.
  3. The console: after any flash, write the registry's reserved channel
     back with `_radioset` and reboot. Covers the radio address only.
- Whether the flash result should report that the settings store was
  erased, so the console can warn.

The fix is not in this repo. It belongs to mbtools (`flashlogic`) and
robot-console; this file records the evidence where it was measured.
