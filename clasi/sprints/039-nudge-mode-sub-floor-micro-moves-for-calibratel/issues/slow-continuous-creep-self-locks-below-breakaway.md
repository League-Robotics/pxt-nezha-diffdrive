---
status: in-progress
sprint: 039
tickets:
- 039-006
---

# Slow continuous creep self-locks below breakaway (vevov reverse at 4 cm/s never moves)

## Evidence

Reported 2026-09-15 by the nezha-robot-template session (calibrateL work).
vevov was on farm node zilch, running the extension at template pin
v1.20260914.1 (build profile `calibrate-l-bench`), with the playfield
camera confirming motion. **No capture file has been handed to this repo
yet.** The numbers below are the peer's report and must get an artifact
before anyone cites them as MEASURED.

- `whileDriving(-4 cm/s, 0)` for 30 s, twice: i2cf +1246 over cyc +1251,
  and x = 0 by camera both times.
- `setWheelSpeeds(-4,-4)` for 40 ticks: i2cf +36 over cyc +40, and it did
  not move backward.
- Controls: `whileDriving(+4, 0)` moved 5.1 cm with i2cf +1, and
  `setWheelSpeeds(-10,-10)` moved -7.2 cm with i2cf +3.

## Source reading (UNVERIFIED on hardware)

- i2cf ~= cyc means the wheel was driven but its raw encoder count stayed
  the same on every tick. `NezhaMotorPort::collect()` withholds the sample
  stamp (`src/platform/nezha_port.cpp:401-406`), and `step()` counts that
  tick (`src/core/diffdrive.cpp:540-543`). This is not a bus fault. The
  duty frame is sign-symmetric (`nezha_port.cpp:296-300`).
- **Suspected lock.** K2 (`diffdrive.cpp:977`) does not integrate the
  position reference on a tick whose sample did not advance. A wheel
  stuck below breakaway therefore never accumulates position error, so
  the I-term (`fastPid`, ki 6) never winds up to break it free. What is
  left is feedforward (40 mm/s ~= 0.5 % duty), boosted to the port's 3 %
  output deadband.
- **Nothing else rescues it.**
  - The continuous-hold path passes floor 0 to the shaper
    (`src/motion/motion_engine.cpp:397`), so vFloor 70 mm/s does not
    apply.
  - `stallDemand` 510.4 counts/s (`src/shims.cpp:293`, ~400 mm/s) means
    the stall detector never arms at creep speed, so the hold runs until
    the caller's own timeout.

## Settle it

Run TLM FULL during a -4 cm/s creep on vevov. If the lock is real,
applied duty sits flat at a few % while i2cf climbs every tick. Then try
the same run with the I-term allowed to grow on driven-but-frozen ticks,
using a host sim of a stiction plant first.

## Constraints

- `src/core/diffdrive.{h,cpp}` is vendored. A fix inside K2 needs the
  paired upstream patch or a stakeholder decision
  (`.claude/rules/fiber-yield-safety.md`, related invariants). A fix at
  the MotionEngine level, such as a floor or breakaway handling for
  continuous holds, avoids that.
- `crawl_pulse` is not a known-good fix. It made end-of-leg stalls worse
  on tovez (`captures/tovez-taper-20260829/variants.json`). Creep is a
  different use, but that measurement is the prior.

Related: `nudge-mode-settle-gated-pulse-stepper-for-sub-floor-micro-moves.md`.
