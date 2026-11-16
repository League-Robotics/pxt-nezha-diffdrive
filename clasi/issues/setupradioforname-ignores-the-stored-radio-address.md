---
status: pending
---

# `setupRadioForName()` ignores the stored radio address

Found 2026-11-15 on tigez (`captures/radiostore-contract-20261115/notes.md`).

`setupWifiForName()` uses a Wi-Fi address stored from the console in place
of the name-derived one. `setupRadioForName()` does not look at the stored
radio address, so a program that calls it after `setupRobot()` puts the
radio back on the name-derived channel every boot. nezha-robot-template
did exactly that; the line was removed in its release v0.20261116.3.

A student program using the "setup radio channel for robot" block still
overrides a channel the console stored. Decide whether the block should
use the stored pair when the name is the micro:bit's own, as the Wi-Fi
block does, and report the source as `stored` when it does.
