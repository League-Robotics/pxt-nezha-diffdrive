---
status: done
sprint: 008
tickets:
- 008-002
---

# Wire constants drift: kVersion says 1.0.0 (pxt.json: 1.0.10); line caps disagree

Priority: **Medium** — code review 2026-08-23, R-17 + R-21 (WIRE-01 +
MOD-01 + BLK-09 and WIRE-05; CONFIRMED by three independent reviewers).

The manual-mirror pattern has already failed everywhere it was used:

1. **kVersion (R-17)**: `protocol.cpp:63` hardcodes `"1.0.0"` beside a
   "keep in sync with pxt.json" comment; pxt.json is at `1.0.10` — ten
   bumps drifted. Every ID/VER wire reply misreports the build, defeating
   the deploy-verification flow (mbdeploy → VER check).
2. **Line caps (R-21)**: `emitLine` clips at a bare `200`
   (`protocol.cpp:92`) while the transports carry 240 (`kMaxLineBytes`,
   raised by ticket 005 for serial only); long bench result lines truncate
   silently. `radio_transport.h:118-126` still claims its cap "equals
   SerialTransport's" — false since the raise. (Precision from
   verification: the radio's own clip is currently unreachable — emitLine
   pre-clips — so the live defect is emitLine's cap plus the false parity
   comment.)
3. Same pattern at smaller scale (Minors, same fix shape): radio group
   `0x2001` duplicated unpinned (`main.ts:154` vs `protocol.cpp:85`);
   kDiag* ordinals re-declared across files.

## What to do

- Generate/check `kVersion` from pxt.json — build-time substitution or a
  host test that reads both and fails on mismatch.
- One shared line-capacity constant consumed by emitLine and both
  transports; fix the radio parity comment.
- Pin the cross-language constant pairs with drift tests (a host test can
  read main.ts as text if need be — cheap and effective).
