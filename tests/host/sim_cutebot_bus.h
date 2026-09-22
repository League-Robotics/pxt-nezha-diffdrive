// sim_cutebot_bus.h -- HostSim::SimCutebotBus: a simulated Cutebot Pro
// that RESPONDS to the real v2 wire bytes CutebotDevice actually
// writes, the same way sim_nezha_bus.h's SimNezhaBus does for the
// Nezha brick -- see that file's own header comment for the general
// argument (a bus that parses the real frame cannot desync from the
// firmware the way a write-count predictor could).
//
// SOURCE READING, not MEASURED (.claude/rules/measurement-citations.md):
// the frame shapes modelled below are transcribed from
// docs/design/cutebot-pro-support.md SS1.1-1.2, itself read from
// ELECFREAKS' own extension. This simulates the PROTOCOL, never a real
// board's timing or plant.
//
// SCOPE (sprint 040 ticket 002): cmd 0x10 (PWM), cmd 0xA0 [3]/[4]
// (degree reads), cmd 0x50 (hardware clear), and the v1-style revision
// probe -- always answering v2. The 0x80 onboard speed-loop simulation
// docs/design/cutebot-pro-support.md S7 describes is ticket 004's,
// once the path exists to simulate; every other cmd is rejected here,
// matching "reject everything else" from that same section.
//
// PHYSICS. Reuses SimWheel from sim_nezha_bus.h UNCHANGED -- its native
// unit (0.1 deg per count, matching the kernel's own convention) is
// reinterpreted here as "kernel counts", and the wire's own unit
// (whole DEGREES, per cutebot_port.h's "degrees x 10 = counts") is
// produced by dividing by 10 on the way out, truncating toward zero
// exactly the way a real 1-degree-LSB encoder would lose the same
// fraction a Nezha 0.1-deg-LSB one would not. `tau`/`breakaway`/
// `dutyVelMax` are plant parameters and mean nothing about a real
// Cutebot until fitted on the bench -- same caveat as sim_nezha_bus.h.
#pragma once

#include <cstdint>

#include "platform/i2c_bus.h"
#include "sim_nezha_bus.h"  // reuse HostSim::SimWheel

namespace HostSim {

class SimCutebotBus final : public diffDrive::I2CBus {
 public:
  SimCutebotBus(float tau, float breakaway, float dutyVelMax)
      : left_(tau, breakaway, dutyVelMax),
        right_(tau, breakaway, dutyVelMax) {}

  // ---- diffDrive::I2CBus ----
  int write(uint16_t address, const uint8_t* data, int len) override {
    if (address != (kAddress << 1) || data == nullptr) return 1;
    if (consumeNack()) return 1;

    // Revision probe: the v1-style fixed 7-byte frame
    // (main.ts readHardVersion(), S1.1) -- NOT a v2 frame.
    if (len == 7 && data[0] == 0x99 && data[1] == 0x15) {
      selection_ = Selection::kRevision;
      ++probeCount_;
      return 0;
    }

    // v2 frames: FF F9 cmd len params...
    if (len < 4 || data[0] != 0xFF || data[1] != 0xF9) return 1;
    const uint8_t cmd = data[2];
    const uint8_t paramLen = data[3];
    if (len != 4 + static_cast<int>(paramLen)) return 1;

    switch (cmd) {
      case kCmdWheel: {
        if (paramLen != 4) return 1;
        const uint8_t wheel = data[4];
        const uint8_t absL = data[5];
        const uint8_t absR = data[6];
        const uint8_t dirbits = data[7];
        if (wheel > 2) return 1;
        if (wheel == 0 || wheel == 2) {
          const float pct = static_cast<float>(absL) / 100.0f;
          dutyLeft_ = (dirbits & 0x01) ? -pct : pct;
        }
        if (wheel == 1 || wheel == 2) {
          const float pct = static_cast<float>(absR) / 100.0f;
          dutyRight_ = (dirbits & 0x02) ? -pct : pct;
        }
        lastWheelFrame_[0] = wheel;
        lastWheelFrame_[1] = absL;
        lastWheelFrame_[2] = absR;
        lastWheelFrame_[3] = dirbits;
        ++frameCount_;
        selection_ = Selection::kNone;
        return 0;
      }
      case kCmdEncoder: {
        if (paramLen != 1) return 1;
        const uint8_t sel = data[4];
        if (sel == 3) { selection_ = Selection::kDegreesLeft; return 0; }
        if (sel == 4) { selection_ = Selection::kDegreesRight; return 0; }
        return 1;  // only the degree reads are modelled this ticket
      }
      case kCmdClear: {
        if (paramLen != 1) return 1;
        const uint8_t wheel = data[4];
        if (wheel == 0) left_.resetPosition();
        else if (wheel == 1) right_.resetPosition();
        else return 1;
        ++clearCount_;
        selection_ = Selection::kNone;
        return 0;
      }
      default:
        return 1;  // reject everything else -- see this file's header
    }
  }

  int read(uint16_t address, uint8_t* data, int len) override {
    if (address != (kAddress << 1) || data == nullptr) return 1;
    if (consumeNack()) return 1;
    switch (selection_) {
      case Selection::kRevision:
        if (len != 1) return 1;
        data[0] = 0x02;  // anything != 1 means v2
        return 0;
      case Selection::kDegreesLeft:
      case Selection::kDegreesRight: {
        if (len != 4) return 1;
        const SimWheel& w =
            (selection_ == Selection::kDegreesLeft) ? left_ : right_;
        // Truncation toward zero -- the same integer-degree loss a real
        // 1-deg-LSB encoder would have that the Nezha's 0.1-deg one
        // does not; see this file's header.
        const int32_t degrees = w.reportedCounts() / 10;
        const uint32_t u = static_cast<uint32_t>(degrees);
        data[0] = static_cast<uint8_t>(u & 0xFF);
        data[1] = static_cast<uint8_t>((u >> 8) & 0xFF);
        data[2] = static_cast<uint8_t>((u >> 16) & 0xFF);
        data[3] = static_cast<uint8_t>((u >> 24) & 0xFF);
        return 0;
      }
      default:
        return 1;  // nothing selected yet
    }
  }

  // Advance the physics -- called by the harness once per simulated
  // tick, AFTER the firmware's own tick has written whatever duty it
  // decided on, same convention as SimNezhaBus::step().
  void step(float dt) {  // [s]
    left_.step(dutyLeft_, dt);
    right_.step(dutyRight_, dt);
  }

  // NACKs the NEXT bus transaction only (write OR read, whichever
  // comes first), then clears itself -- a test arms this right before
  // the call it wants to fail, e.g. after a successful requestSample()
  // and before the tick() whose collect() should see the failure.
  void armNack() { nackArmed_ = true; }

  uint32_t frameCount() const { return frameCount_; }  // 0x10 writes shipped
  uint32_t clearCount() const { return clearCount_; }  // 0x50 writes shipped
  uint32_t probeCount() const { return probeCount_; }  // revision probes seen
  float duty(int side) const { return side == 0 ? dutyLeft_ : dutyRight_; }
  const SimWheel& wheel(int side) const { return side == 0 ? left_ : right_; }

  // The last shipped 0x10 frame's own PARAMS (wheel, absL, absR,
  // dirbits) -- the exact bytes CutebotDevice::shipFrame() sent, for
  // tests that want to assert on the wire encoding directly rather
  // than through the physics `duty()` it produces.
  uint8_t lastWheelFrame(int index) const { return lastWheelFrame_[index]; }

 private:
  enum class Selection { kNone, kRevision, kDegreesLeft, kDegreesRight };

  bool consumeNack() {
    if (!nackArmed_) return false;
    nackArmed_ = false;
    return true;
  }

  // Mirrors of CutebotDevice's own constants -- duplicated deliberately
  // (see sim_nezha_bus.h's own comment on the same choice): this is a
  // SIMULATED DEVICE and must agree with the firmware only where a
  // real board would.
  static constexpr uint8_t kAddress = 0x10;
  static constexpr uint8_t kCmdWheel = 0x10;
  static constexpr uint8_t kCmdEncoder = 0xA0;
  static constexpr uint8_t kCmdClear = 0x50;

  SimWheel left_;
  SimWheel right_;
  float dutyLeft_ = 0.0f;
  float dutyRight_ = 0.0f;
  Selection selection_ = Selection::kNone;
  uint32_t frameCount_ = 0;
  uint32_t clearCount_ = 0;
  uint32_t probeCount_ = 0;
  bool nackArmed_ = false;
  uint8_t lastWheelFrame_[4] = {0, 0, 0, 0};
};

}  // namespace HostSim
