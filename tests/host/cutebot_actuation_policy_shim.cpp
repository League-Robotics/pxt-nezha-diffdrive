// cutebot_actuation_policy_shim.cpp -- extern "C" ctypes surface for
// diffDrive::CutebotActuationPolicy::decide() (sprint 040 ticket 004,
// src/platform/cutebot_actuation_policy.h/.cpp), exercised as a pure
// function -- no I2C, no CutebotDevice, no board in the link at all.
// See cutebot_hybrid_shim.cpp for the device-level integration this
// class feeds into.
//
// Test scaffolding only: nothing under src/ knows this file exists.
#include "platform/cutebot_actuation_policy.h"

extern "C" {

// phase: VelocityShaper::Phase's own declaration order (0=kAccel,
// 1=kCruise, 2=kBrake). Returns 1 if the policy chose the onboard
// (0x80) frame, 0 for PWM (0x10); *engagedOut carries the returned
// PolicyState for the next call, threading hysteresis/plateau memory
// exactly as CutebotDevice::serviceCycle() does.
int capDecide(int prevEngaged, float dutyLeft, float dutyRight,
             float tapLeft, float tapRight, int tapPhase, int tapNeutral,
             int mode, float floorMmS, int* engagedOut) {
  using diffDrive::CutebotActuationPolicy;
  CutebotActuationPolicy::PolicyState prev;
  prev.engaged = prevEngaged != 0;
  const CutebotActuationPolicy::WheelStaged duty{dutyLeft, dutyRight};
  const CutebotActuationPolicy::WheelSetpoint setpoint{
      tapLeft, tapRight,
      static_cast<diffDrive::VelocityShaper::Phase>(tapPhase),
      tapNeutral != 0};
  const CutebotActuationPolicy::Decision decision =
      CutebotActuationPolicy::decide(prev, duty, setpoint, mode, floorMmS);
  *engagedOut = decision.state.engaged ? 1 : 0;
  return decision.frame == CutebotActuationPolicy::Frame::kOnboard ? 1 : 0;
}

}  // extern "C"
