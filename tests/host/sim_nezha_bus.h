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

#include <cstdint>
#include <cmath>

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
    // Frame: {0xFF, 0xF9, port, arg(dir), reg, val(pct), 0xF5, 0x00}
    if (data[0] != 0xFF || data[1] != 0xF9) return 1;
    const uint8_t port = data[2];
    if (port != 1 && port != 2) return 1;
    selected_ = port;
    if (data[4] == kRegMotorRun) {
      // `val` is magnitude percent 0..100; `arg` is the direction code.
      const float pct = static_cast<float>(data[5]) / 100.0f;
      const float signed_duty = (data[3] == kDirCcw) ? -pct : pct;
      (port == 1 ? duty1_ : duty2_) = signed_duty;
      ++writes_;
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
    wheel1_.step(duty1_, dt);
    wheel2_.step(duty2_, dt);
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

  SimWheel wheel1_;
  SimWheel wheel2_;
  float duty1_ = 0.0f;
  float duty2_ = 0.0f;
  uint8_t selected_ = 0;
  uint32_t writes_ = 0;
  uint32_t reads_ = 0;
};

}  // namespace HostSim
