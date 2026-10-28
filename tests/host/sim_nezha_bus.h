// sim_nezha_bus.h -- HostSim::SimNezhaBus: a simulated Nezha brick that
// RESPONDS to the bytes firmware actually wrote.
//
// This is the second implementation of `diffDrive::I2CBus` (the first
// is `platform/microbit_i2c_bus.cpp`), and it is the whole reason that
// interface exists. It parses the real 8-byte 0xFF/0xF9 frame
// `NezhaMotorPort::writeFrame()` emits and answers `readEncoderRaw()`
// with real little-endian counts -- so the firmware under test is the
// REAL `NezhaMotorPort`, with its sigma-delta duty quantizer, output
// deadband, write throttle, reversal dwell and encoder glitch armor all
// executing, rather than a `FakeMotor` substituted above them.
//
// Ported in shape (not in formula) from radio-robot-elite's
// `src/firm/platform/host/sim_plant.{h,cpp}` and
// `src/tests/sim/plant/wheel_plant.{h,cpp}`. The two-layer split is
// theirs and is kept: this class owns the wire PROTOCOL only; the
// physics lives in `SimWheel` below. Their own reason for responding
// rather than predicting applies verbatim -- a bus that just parses the
// real frame cannot desync from the firmware, which the write-count
// predictor it replaced could and did.
//
// WHAT THIS BUYS, concretely. `NezhaMotorPort::writeShapedDuty()` holds
// a REVERSING wheel at commanded zero for a full `reversalDwell_`
// (100 ms shipped) before writing the new direction. A pivot reverses
// exactly one wheel, so that wheel starts ~100 ms after the other --
// and no host harness in this repo could observe it, because every one
// of them substitutes `FakeMotor` at the `DiffDrive::Motor` interface,
// above the shaping layer. MEASURED tovez 2026-09-05,
// reports/tovez-square-tour-20260905/square_vel.csv: on pivot 1 the
// reversing wheel reads -26 mm/s while the forward wheel is already at
// +82 on a +-100 command.
//
// ADDRESSING. `NezhaMotorPort` talks to one brick (`kAddress` 0x10)
// that fans out to four motor PORTS; the port number is byte 2 of the
// write frame, and the encoder read is a bare 4-byte read whose meaning
// is "the port selected by the most recent write". That is the real
// protocol's own statefulness, reproduced here rather than smoothed
// over -- `selected_` below is exactly that latch, and a read before
// any write is an error (returns non-zero), the same way an unselected
// real brick answers nothing useful.
#pragma once

#include <algorithm>
#include <cstdint>
#include <cmath>
#include <vector>

#include "platform/i2c_bus.h"

namespace HostSim {

// One wheel's physics: duty -> velocity -> position, with first-order
// actuation lag and breakaway stiction. Deterministic; no RNG, no
// wall-clock read, so run A == run B exactly.
//
// `tau` and `breakaway` are PLANT parameters and must be fitted to a
// real robot before any number this produces means anything about that
// robot -- see this header's own warning in the harness docstring, and
// sprint 031 ticket 011, where a host model asserted three PID
// candidates held both bars and hardware held neither, because its
// per-wheel residual was hypothesized rather than measured.
class SimWheel {
 public:
  // countsPerRev-independent: the port's own unit is 0.1 deg of shaft
  // rotation per count (nezha_port.h), and `dutyVelMax` is expressed in
  // those counts per second, so nothing here needs a wheel radius.
  SimWheel(float tau, float breakaway, float dutyVelMax)
      : tau_(tau), breakaway_(breakaway), dutyVelMax_(dutyVelMax) {}

  // `duty` is the SIGNED fraction the brick was told to run at, already
  // through the port's quantizer and sign handling.
  void step(float duty, float dt) {  // [-1,1] [s]
    const float target = duty * dutyVelMax_;  // [counts/s]
    // Breakaway: a wheel at rest needs |target| at or above the
    // threshold to start, and drops back to rest below half of it
    // (hysteresis, so a wheel hovering at the threshold does not
    // chatter). Same shape as radio-robot-elite's WheelPlant and as
    // this repo's own LaggedRig.
    if (!moving_ && std::fabs(target) >= breakaway_) moving_ = true;
    if (moving_ && std::fabs(target) < 0.5f * breakaway_) moving_ = false;
    const float want = moving_ ? target : 0.0f;
    if (tau_ <= 0.0f) {
      velocity_ = want;
    } else {
      const float a = dt / (tau_ + dt);
      velocity_ += a * (want - velocity_);
    }
    position_ += velocity_ * dt;
  }

  // The brick reports a signed 32-bit count. Truncation toward zero is
  // the real device's behaviour and is what the port's glitch armor
  // sees, so it is reproduced rather than rounded.
  int32_t reportedCounts() const {
    return static_cast<int32_t>(position_);
  }

  float velocity() const { return velocity_; }   // [counts/s]
  float position() const { return position_; }   // [counts]

  // Zeroes the accumulated position only -- velocity/moving_ state is
  // untouched, matching a real encoder's hardware-zero register (cmd
  // 0x50 on the Cutebot Pro's own wire; see
  // tests/host/sim_cutebot_bus.h, sprint 040 ticket 002). Added for
  // that simulator; SimNezhaBus itself never calls this (the Nezha
  // brick's own hardware-zero path was never modelled here).
  void resetPosition() { position_ = 0.0f; }

  // Onboard speed-loop simulation (sprint 040 ticket 004,
  // sim_cutebot_bus.h's `0x80` handling): a first-order lag DIRECTLY to
  // a commanded velocity, bypassing the duty->target->breakaway
  // pipeline step() uses above -- this models a controller that closes
  // its OWN loop on the wheel (the Cutebot Pro's onboard PID), not our
  // own duty-driven plant. `setpointCountsPerS` is whatever the caller
  // decided to send, already through (or deliberately bypassing, to
  // exercise a policy bug -- see sim_cutebot_bus.h's own header) the
  // 200 mm/s floor; this method does not know about that floor at all.
  // Reuses `tau_` as a stand-in lag constant -- UNVERIFIED against a
  // real Cutebot's onboard-loop dynamics, no bench numbers exist yet
  // (sprint 041). `moving_` is kept roughly honest (>= half the
  // breakaway threshold) so a caller that later resumes step() sees a
  // `moving_` flag consistent with the velocity this method leaves
  // behind -- UNVERIFIED whether a real handoff back to PWM behaves
  // anything like this; see sim_cutebot_bus.h's own comment on the
  // "0x10 cancels onboard mode" assumption this exists to support.
  // Kinematic drive for the brick's OWN position/speed loop (sprint 042
  // ticket 003): the motor, not our duty, sets the velocity, so this
  // bypasses duty -> target -> breakaway and the lag entirely. The
  // caller (SimNezhaBus's brick model) owns the velocity profile.
  void driveKinematic(float velocityCountsPerS, float dt) {  // [counts/s][s]
    velocity_ = velocityCountsPerS;
    position_ += velocity_ * dt;
    moving_ = velocity_ != 0.0f;
  }

  // Lands exactly on `counts` (the end of a position move) and rests.
  void settleAt(float counts) {  // [counts]
    position_ = counts;
    velocity_ = 0.0f;
    moving_ = false;
  }

  void stepOnboard(float setpointCountsPerS, float dt) {  // [counts/s][s]
    if (tau_ <= 0.0f) {
      velocity_ = setpointCountsPerS;
    } else {
      const float a = dt / (tau_ + dt);
      velocity_ += a * (setpointCountsPerS - velocity_);
    }
    position_ += velocity_ * dt;
    moving_ = std::fabs(velocity_) >= 0.5f * breakaway_;
  }

 private:
  float tau_;          // [s]
  float breakaway_;    // [counts/s]
  float dutyVelMax_;   // [counts/s] at |duty| == 1
  float velocity_ = 0.0f;
  float position_ = 0.0f;
  bool moving_ = false;
};

class SimNezhaBus final : public diffDrive::I2CBus {
 public:
  // Ports are 1-based (M1..M4); only the two this robot uses are
  // modelled. `left`/`right` here are PORT indices, not sides -- which
  // port is which side is the firmware's business (`fwdSign`/the
  // per-robot motor bake), and getting that wrong is exactly the bug
  // the tovez motor bake exists to fix, so this class does not encode
  // an opinion about it.
  SimNezhaBus(float tau, float breakaway, float dutyVelMax)
      : wheel1_(tau, breakaway, dutyVelMax),
        wheel2_(tau, breakaway, dutyVelMax) {}

  // ---- diffDrive::I2CBus ----
  int write(uint16_t address, const uint8_t* data, int len) override {
    if (address != (kAddress << 1) || len != 8 || data == nullptr) return 1;
    // Frame: {0xFF, 0xF9, port, arg(dir), reg, val(hi), mode, lo}
    if (data[0] != 0xFF || data[1] != 0xF9) return 1;
    const uint8_t port = data[2];
    const uint8_t reg = data[4];
    // 0x1D is the motor reset, which bricked a real motor
    // (docs/knowledge/2026-10-27-nezha-brick-opcodes.md section 6). It
    // is NOT a command firmware may emit: the bus rejects it, does not
    // forward it, and counts it so a test can assert the count is 0.
    if (reg == kRegMotorReset) {
      ++violations1D_;
      return 1;
    }
    // Port 0 means "all ports" on the brick; only the brick opcodes
    // below accept it (legacy 0x60 keeps its exact old contract).
    const bool brickOp = reg == kRegSpeedStore || reg == kRegMove ||
                         reg == kRegStop;
    if (port == 0 && !brickOp) return 1;
    if (port > 2) return 1;
    FrameRecord rec;
    for (int i = 0; i < 8; ++i) rec.bytes[i] = data[i];
    rec.moveLive = port == 0 ? (moveLive(1) || moveLive(2)) : moveLive(port);
    frames_.push_back(rec);
    if (port != 0) selected_ = port;
    const uint16_t value =
        static_cast<uint16_t>((data[5] << 8) | data[7]);  // hi, lo
    if (reg == kRegMotorRun) {
      // `val` is magnitude percent 0..100; `arg` is the direction code.
      const float pct = static_cast<float>(data[5]) / 100.0f;
      const float signed_duty = (data[3] == kDirCcw) ? -pct : pct;
      ++frames60_[port];
      if (rec.moveLive) ++frames60WhileLive_[port];
      runCommand(port, data[5], data[3] == kDirCcw, signed_duty);
      ++writes_;
    } else if (brickOp) {
      for (uint8_t p = 1; p <= 2; ++p) {
        if (port != 0 && port != p) continue;
        if (reg == kRegSpeedStore) {
          // A store only; it does not retarget a live move or run.
          speedStore_[p] = value;
        } else if (reg == kRegMove) {
          startMove(p, data[6], value, data[3] == kDirCcw);
        } else {  // kRegStop
          hardStop(p);
        }
      }
    }
    return 0;
  }

  int read(uint16_t address, uint8_t* data, int len) override {
    if (address != (kAddress << 1) || len != 4 || data == nullptr) return 1;
    if (selected_ == 0) return 1;  // nothing selected yet -- see header
    const int32_t counts =
        (selected_ == 1 ? wheel1_ : wheel2_).reportedCounts();
    const uint32_t u = static_cast<uint32_t>(counts);
    data[0] = static_cast<uint8_t>(u & 0xFF);
    data[1] = static_cast<uint8_t>((u >> 8) & 0xFF);
    data[2] = static_cast<uint8_t>((u >> 16) & 0xFF);
    data[3] = static_cast<uint8_t>((u >> 24) & 0xFF);
    ++reads_;
    return 0;
  }

  // Advance the physics. Called by the harness once per simulated tick,
  // AFTER the firmware's own tick has written whatever duty it decided
  // on -- so a duty written this tick takes effect over the next
  // interval, which is what the real brick does.
  void step(float dt) {  // [s]
    for (uint8_t p = 1; p <= 2; ++p) {
      SimWheel& w = p == 1 ? wheel1_ : wheel2_;
      if (brick_[p].mode == BrickMode::kLegacy) {
        w.step(p == 1 ? duty1_ : duty2_, dt);
      } else {
        stepBrick(p, w, dt);
      }
    }
  }

  // ---- brick model (sprint 042 ticket 003) ----------------------------
  // What the real brick does with the opcodes sniffed on 2026-10-27.
  // Every number is cited to docs/knowledge/2026-10-27-nezha-brick-opcodes.md
  // (the "doc"); constants say which row they were fitted to. The model
  // is opt-in by construction: a port stays in the legacy duty path
  // (sim_tour.py's numbers) until a 0x70/0x5F arrives, or a 0x60 arrives
  // while a move/run is live.

  // Degrees per second per 0x60 percent when 0x60 is the motor's own
  // speed loop (doc section 1: 11.5 deg/s per percent, ESP32 rig
  // motor-characterization.md, not copied). 0 (default) keeps 0x60 on
  // the legacy duty path when no move is live.
  void setOwnedRunDegPerPercent(float degPerSecPerPct) {  // [deg/s]
    ownedRunScale_ = degPerSecPerPct;
  }

  // 0x77 value last stored for the port [deg/s].
  uint16_t speedStore(uint8_t port) const { return speedStore_[port]; }

  // Test hook: pin a port's wheel (a jammed or blocked shaft). The brick
  // keeps trying (its mode and target stand) but the shaft does not turn.
  void setBlocked(uint8_t port, bool blocked) { blocked_[port] = blocked; }

  // A position move, a timed run, or an owned 0x60 run is in progress.
  bool moveLive(uint8_t port) const {
    const Brick& b = brick_[port];
    return b.mode == BrickMode::kMove || b.mode == BrickMode::kTimed ||
           b.mode == BrickMode::kRun;
  }
  // Position target of a live position move [counts, 0.1 deg]; 0 if none.
  float moveTarget(uint8_t port) const { return brick_[port].target; }
  bool hasTarget(uint8_t port) const {
    return brick_[port].mode == BrickMode::kMove;
  }

  // ---- frame log -------------------------------------------------------
  uint32_t frameCount() const {
    return static_cast<uint32_t>(frames_.size());
  }
  // Byte-exact copy of accepted frame `index` into out[8]; false if out
  // of range.
  bool frameBytes(uint32_t index, uint8_t* out) const {
    if (index >= frames_.size() || out == nullptr) return false;
    for (int i = 0; i < 8; ++i) out[i] = frames_[index].bytes[i];
    return true;
  }
  // Was a move/run live on that frame's port when the frame arrived.
  bool frameMoveLive(uint32_t index) const {
    return index < frames_.size() && frames_[index].moveLive;
  }
  // 0x60 frames the port received, in total / while a move was live.
  uint32_t frames60(uint8_t port) const { return frames60_[port]; }
  uint32_t frames60WhileLive(uint8_t port) const {
    return frames60WhileLive_[port];
  }
  // Frames carrying 0x1D that the bus rejected. Must stay 0.
  uint32_t violations1D() const { return violations1D_; }
  void clearFrameLog() {
    frames_.clear();
    for (int i = 0; i < 3; ++i) frames60_[i] = frames60WhileLive_[i] = 0;
  }

  const SimWheel& wheel(uint8_t port) const {
    return port == 1 ? wheel1_ : wheel2_;
  }
  float duty(uint8_t port) const { return port == 1 ? duty1_ : duty2_; }
  uint32_t writes() const { return writes_; }
  uint32_t reads() const { return reads_; }

 private:
  // Mirrors of NezhaMotorPort's own constants. Duplicated deliberately
  // rather than reaching into the class: this is a SIMULATED DEVICE and
  // must agree with the firmware only where the real brick would, so a
  // firmware-side constant change should break this simulator loudly
  // (a test asserts they still match) rather than silently follow it.
  static constexpr uint8_t kAddress = 0x10;
  static constexpr uint8_t kRegMotorRun = 0x60;
  static constexpr uint8_t kDirCcw = 2;
  static constexpr uint8_t kRegSpeedStore = 0x77;
  static constexpr uint8_t kRegMove = 0x70;
  static constexpr uint8_t kRegStop = 0x5F;
  static constexpr uint8_t kRegMotorReset = 0x1D;  // rejected, never emitted

  // Motor dynamics. Both fitted, not derived; UNVERIFIED beyond the
  // rows named.
  // Acceleration/deceleration of the motor's speed loop [counts/s^2]
  // (1 count = 0.1 deg): 4200 deg/s^2, fitted to the 0x60-0 ramp rows
  // of doc section 5a (mb_probe_stops1.csv, how=0): v^2/2a gives
  // 157/57/14/3.5/1.0 deg at 100/60/30/15/8 % against measured
  // 141/58/15/3.9/0.9 deg. Also used to accelerate into a move or run.
  static constexpr float kAccel = 42000.0f;
  // Deceleration of 0x60 0 DURING a position move [counts/s^2]:
  // 2200 deg/s^2, fitted to doc section 3 rule 1 (46 deg more travel at
  // 450 deg/s, micro:bit rig 2026-10-27; source microbit-comparison.md
  // section 6, run log not copied).
  static constexpr float kMoveStopDecel = 22000.0f;
  // 0x5F: velocity goes linearly to zero over this time [s]. Fitted to
  // the how=1 rows of doc section 5a (mb_probe_stops1.csv): travel =
  // v * 0.0103 s (11.9 deg at 1150 deg/s measured 11.9; 6.8 at 690
  // measured 6.8).
  static constexpr float kHardStopTime = 0.0206f;
  // Free-speed ceiling [counts/s]: 980 deg/s, doc section 5b
  // (mb_probe_fine1.csv, 1000/1100/1200 -> 977.8/981.4/990.8 deg/s).
  static constexpr float kSpeedCeiling = 9800.0f;

  enum class BrickMode : uint8_t {
    kLegacy,  // duty path, exactly as before ticket 003
    kIdle,    // brick owns the wheel, at rest (a move finished)
    kMove,    // position target
    kTimed,   // 0x70 mode 3
    kRun,     // 0x60 as the motor's speed loop (opt-in scale)
    kHard,    // 0x5F stopping
  };
  struct Brick {
    BrickMode mode = BrickMode::kLegacy;
    float target = 0.0f;       // [counts]
    float vCmd = 0.0f;         // [counts/s] signed cruise speed
    float timeLeft = 0.0f;     // [s] timed run
    float decel = kAccel;      // [counts/s^2] used while stopping
    float hardRate = 0.0f;     // [counts/s^2] 0x5F
  };
  struct FrameRecord {
    uint8_t bytes[8];
    bool moveLive;
  };

  SimWheel& wheelRef(uint8_t port) { return port == 1 ? wheel1_ : wheel2_; }

  static float cruise(uint16_t store) {  // [counts/s]
    return std::min(static_cast<float>(store) * 10.0f, kSpeedCeiling);
  }

  void startMove(uint8_t port, uint8_t mode, uint16_t n, bool reverse) {
    Brick& b = brick_[port];
    SimWheel& w = wheelRef(port);
    const float sign = reverse ? -1.0f : 1.0f;
    const float v = cruise(speedStore_[port]);
    if (mode == 3) {
      b.mode = BrickMode::kTimed;
      b.vCmd = sign * v;
      b.timeLeft =
          (10.0f * static_cast<float>(n) - 3.0f) * 0.1f;  // [s] doc section 2
      if (b.timeLeft < 0.0f) b.timeLeft = 0.0f;
    } else {
      // Modes 0/1: turns (3600 counts each); mode 2: integer degrees
      // (10 counts each). A second 0x70 supersedes from the CURRENT
      // position (doc section 3 rule 3).
      const float counts = static_cast<float>(n) * (mode == 2 ? 10.0f : 3600.0f);
      b.mode = BrickMode::kMove;
      b.target = w.position() + sign * counts;
      b.vCmd = v;
    }
    b.decel = kAccel;
  }

  void hardStop(uint8_t port) {
    Brick& b = brick_[port];
    SimWheel& w = wheelRef(port);
    b.mode = BrickMode::kHard;
    b.hardRate = std::fabs(w.velocity()) / kHardStopTime;
  }

  // 0x60 handling. `pctRaw` is the unsigned percent byte.
  void runCommand(uint8_t port, uint8_t pctRaw, bool reverse,
                  float signedDuty) {
    Brick& b = brick_[port];
    (port == 1 ? duty1_ : duty2_) = signedDuty;
    if (b.mode == BrickMode::kLegacy) {
      if (ownedRunScale_ > 0.0f && pctRaw != 0) {
        b.mode = BrickMode::kRun;
        b.vCmd = (reverse ? -1.0f : 1.0f) * static_cast<float>(pctRaw) *
                 ownedRunScale_ * 10.0f;
        b.decel = kAccel;
      }
      return;
    }
    if (pctRaw != 0) {
      // A nonzero 0x60 takes the wheel over; the old target is gone.
      if (ownedRunScale_ > 0.0f) {
        b.mode = BrickMode::kRun;
        b.vCmd = (reverse ? -1.0f : 1.0f) * static_cast<float>(pctRaw) *
                 ownedRunScale_ * 10.0f;
        b.decel = kAccel;
      } else {
        b.mode = BrickMode::kLegacy;  // wheel velocity carries over
      }
      return;
    }
    // 0x60 0: ramp to rest at v^2/2a and drop the target (doc section 3
    // rule 1). If the brick already holds the wheel at rest there is
    // nothing to ramp, so release to the duty path.
    if (moveLive(port) || b.mode == BrickMode::kHard) {
      b.decel = b.mode == BrickMode::kMove ? kMoveStopDecel : kAccel;
      b.mode = BrickMode::kRun;
      b.vCmd = 0.0f;
    } else {
      b.mode = BrickMode::kLegacy;
    }
  }

  static float slew(float v, float want, float rate, float dt) {
    const float dv = rate * dt;
    if (want > v + dv) return v + dv;
    if (want < v - dv) return v - dv;
    return want;
  }

  void stepBrick(uint8_t port, SimWheel& w, float dt) {
    Brick& b = brick_[port];
    if (blocked_[port] && b.mode != BrickMode::kLegacy) {
      w.driveKinematic(0.0f, dt);
      return;
    }
    float v = w.velocity();
    switch (b.mode) {
      case BrickMode::kMove: {
        const float rem = b.target - w.position();
        const float dir = rem >= 0.0f ? 1.0f : -1.0f;
        // Speed that still lets the motor stop on the target.
        const float vStop = std::sqrt(2.0f * kAccel * std::fabs(rem));
        const float want = dir * std::min(b.vCmd, vStop);
        v = slew(v, want, kAccel, dt);
        const float next = w.position() + v * dt;
        if ((b.target - next) * rem <= 0.0f ||
            (std::fabs(b.target - next) < 1.0f && std::fabs(v) < 50.0f)) {
          w.settleAt(b.target);
          b.mode = BrickMode::kIdle;
          return;
        }
        break;
      }
      case BrickMode::kTimed: {
        v = slew(v, b.vCmd, kAccel, dt);
        b.timeLeft -= dt;
        if (b.timeLeft <= 0.0f) {
          b.mode = BrickMode::kRun;  // ramp to rest after the run ends
          b.vCmd = 0.0f;
          b.decel = kAccel;
        }
        break;
      }
      case BrickMode::kRun:
        v = slew(v, b.vCmd, b.vCmd == 0.0f ? b.decel : kAccel, dt);
        if (b.vCmd == 0.0f && v == 0.0f) {
          b.mode = BrickMode::kIdle;
        }
        break;
      case BrickMode::kHard:
        v = slew(v, 0.0f, b.hardRate, dt);
        if (v == 0.0f) b.mode = BrickMode::kIdle;
        break;
      case BrickMode::kIdle:
        v = 0.0f;
        break;
      case BrickMode::kLegacy:
        break;
    }
    w.driveKinematic(v, dt);
  }

  SimWheel wheel1_;
  SimWheel wheel2_;
  float duty1_ = 0.0f;
  float duty2_ = 0.0f;
  uint8_t selected_ = 0;
  uint32_t writes_ = 0;
  uint32_t reads_ = 0;
  float ownedRunScale_ = 0.0f;
  uint16_t speedStore_[3] = {0, 0, 0};
  Brick brick_[3];
  bool blocked_[3] = {false, false, false};
  std::vector<FrameRecord> frames_;
  uint32_t frames60_[3] = {0, 0, 0};
  uint32_t frames60WhileLive_[3] = {0, 0, 0};
  uint32_t violations1D_ = 0;
};

}  // namespace HostSim
