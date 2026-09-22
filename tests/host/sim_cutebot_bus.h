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
// SCOPE (sprint 040 ticket 002, extended by ticket 004): cmd 0x10
// (PWM), cmd 0xA0 [3]/[4] (degree reads), cmd 0x50 (hardware clear),
// the v1-style revision probe (always answering v2), and -- as of
// ticket 004 -- cmd 0x80, the onboard speed loop, simulated as a
// first-order lag on the shared SimWheel (SimWheel::stepOnboard(),
// sim_nezha_bus.h) with the 200 mm/s floor modelled per
// docs/design/cutebot-pro-support.md S1.5/S7. Every other cmd is still
// rejected, matching "reject everything else" from that same section.
//
// THE 200 mm/s CLAMP IS MODELLED HERE, ON THE RECEIVING END -- NOT
// applied by CutebotDevice before it sends (cutebot_port.cpp's
// writeOnboardFrame() ships whatever the policy decided, unclamped).
// That is deliberate: this sim's clamp models the EXTENSION's own
// clamp (design doc S1.5's `Math.max(lspeed, 200)`, read from
// ELECFREAKS' v2.ts, itself UNVERIFIED against real MCU firmware --
// S1.6), and applying it HERE means a policy bug that hands the loop an
// under-floor nonzero setpoint is still visible on the host: the
// simulated wheel moves at the clamped speed, not the buggy one, so a
// test comparing "what was sent" against "what actually happened" can
// catch it, rather than the clamp silently absorbing the bug on the
// sender's own side where nothing would ever notice.
//
// UNVERIFIED: whether a real `0x10` write actually cancels a running
// onboard loop, or whether the MCU keeps servoing until it sees an
// `0x80` zero (design doc S3.D's own "down-handoff" hazard, a sprint
// 041 bench probe). This sim ASSUMES cancellation -- see the `0x10`
// case below -- purely so a host test can exercise "handed back to PWM"
// at all; it proves nothing about which assumption is correct.
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
        // UNVERIFIED (see this file's header): a 0x10 write cancels
        // onboard mode in this sim, so step() resumes the duty-driven
        // plant from here on -- the whole reason a test can exercise
        // "handed back to PWM" without knowing whether a real board
        // agrees.
        onboardActive_ = false;
        selection_ = Selection::kNone;
        return 0;
      }
      case kCmdOnboard: {
        // NO REAL CUTEBOT GEOMETRY EXISTS YET (design doc S1.4: wheel
        // diameter, track width and encoder resolution are all
        // caliper/bench measurements for sprint 041). This sim treats
        // the wire's mm/s magnitude as a counts/s target for SimWheel
        // 1:1 -- an arbitrary but internally consistent simplification
        // that exercises the CLAMP and the LAG shape only; it is not a
        // claim about what a real Cutebot's encoder would report for a
        // given onboard-loop setpoint.
        if (paramLen != 5) return 1;
        const uint16_t magL = (static_cast<uint16_t>(data[4]) << 8) | data[5];
        const uint16_t magR = (static_cast<uint16_t>(data[6]) << 8) | data[7];
        const uint8_t dirbits = data[8];
        onboardSetpointLeft_ = clampOnboardMagnitude(magL) *
                              ((dirbits & 0x01) ? -1.0f : 1.0f);
        onboardSetpointRight_ = clampOnboardMagnitude(magR) *
                               ((dirbits & 0x02) ? -1.0f : 1.0f);
        lastOnboardFrame_[0] = static_cast<uint8_t>((magL >> 8) & 0xFF);
        lastOnboardFrame_[1] = static_cast<uint8_t>(magL & 0xFF);
        lastOnboardFrame_[2] = static_cast<uint8_t>((magR >> 8) & 0xFF);
        lastOnboardFrame_[3] = static_cast<uint8_t>(magR & 0xFF);
        lastOnboardFrame_[4] = dirbits;
        onboardActive_ = true;
        ++onboardFrameCount_;
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
  // tick, AFTER the firmware's own tick has written whatever duty (or
  // onboard setpoint) it decided on, same convention as
  // SimNezhaBus::step(). Whichever mode is active (see the `0x10`/
  // `0x80` write handlers above for how onboardActive_ flips) drives
  // BOTH wheels through that one physics path -- there is no
  // per-wheel mode split, matching the real protocol's own "one 0x10
  // or one 0x80 frame always covers both wheels" shape.
  void step(float dt) {  // [s]
    if (onboardActive_) {
      left_.stepOnboard(onboardSetpointLeft_, dt);
      right_.stepOnboard(onboardSetpointRight_, dt);
    } else {
      left_.step(dutyLeft_, dt);
      right_.step(dutyRight_, dt);
    }
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

  // ---- 0x80 onboard loop (sprint 040 ticket 004) ----
  bool onboardActive() const { return onboardActive_; }
  uint32_t onboardFrameCount() const { return onboardFrameCount_; }
  // The setpoint this sim's PHYSICS is actually driving toward -- AFTER
  // the 200 mm/s clamp below, so a test can see the clamp's effect
  // directly rather than only inferring it from the resulting wheel
  // speed.
  float onboardSetpoint(int side) const {
    return side == 0 ? onboardSetpointLeft_ : onboardSetpointRight_;
  }
  // The last shipped 0x80 frame's own PARAMS (magL hi, magL lo, magR
  // hi, magR lo, dirbits) -- the RAW, UNCLAMPED bytes CutebotDevice
  // sent, for a test that wants to prove the sender does NOT pre-clamp
  // (see this file's header) as distinct from onboardSetpoint()'s
  // already-clamped result.
  uint8_t lastOnboardFrame(int index) const { return lastOnboardFrame_[index]; }

 private:
  enum class Selection { kNone, kRevision, kDegreesLeft, kDegreesRight };

  bool consumeNack() {
    if (!nackArmed_) return false;
    nackArmed_ = false;
    return true;
  }

  // The 200 mm/s floor (design doc S1.5): 0 passes through unchanged
  // (the frame's own "stop" value); any other magnitude below 200
  // clamps UP to 200. The 500 mm/s ceiling is the same source reading's
  // "clamped to 200..500" -- modelled here too, though no acceptance
  // criterion exercises it (nothing in this sprint drives a setpoint
  // that high).
  static float clampOnboardMagnitude(uint16_t rawMagnitude) {
    const float mag = static_cast<float>(rawMagnitude);
    if (mag == 0.0f) return 0.0f;
    if (mag < 200.0f) return 200.0f;
    if (mag > 500.0f) return 500.0f;
    return mag;
  }

  // Mirrors of CutebotDevice's own constants -- duplicated deliberately
  // (see sim_nezha_bus.h's own comment on the same choice): this is a
  // SIMULATED DEVICE and must agree with the firmware only where a
  // real board would.
  static constexpr uint8_t kAddress = 0x10;
  static constexpr uint8_t kCmdWheel = 0x10;
  static constexpr uint8_t kCmdEncoder = 0xA0;
  static constexpr uint8_t kCmdClear = 0x50;
  static constexpr uint8_t kCmdOnboard = 0x80;

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

  bool onboardActive_ = false;
  float onboardSetpointLeft_ = 0.0f;   // [counts/s], post-clamp
  float onboardSetpointRight_ = 0.0f;  // [counts/s], post-clamp
  uint32_t onboardFrameCount_ = 0;
  uint8_t lastOnboardFrame_[5] = {0, 0, 0, 0, 0};
};

}  // namespace HostSim
