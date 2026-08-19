---
status: pending
---

# Radio telemetry plane for field (untethered) runs

## Description

TLM currently streams only over USB serial, so telemetry is available
on the bench but not during untethered field runs. Stakeholder
direction (2026-08-19): field telemetry should go over the micro:bit
radio.

The fleet already has RADIOBRIDGE relay boards (getez, zavaz in the
mbdeploy registry) — the reference Protocol v5 spec's radio relay
plane (radio-robot-elite docs/protocol-v5.md) defines how robot-side
radio frames reach a host through such a bridge. Scope for this
extension: mirror the pose-only cleartext TLM record (and possibly the
DEVICE banner) onto the micro:bit radio, compatible with the existing
bridge firmware, while keeping USB serial as-is for bench work.

Open questions: radio group/channel conventions the bridges expect;
whether commands should also be accepted over radio or radio stays
telemetry-only; payload size limits vs the TLM line format.
