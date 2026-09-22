// cutebot_hybrid_shim.cpp -- extern "C" ctypes surface for the
// sprint 040 ticket 004 hybrid-actuation path: CutebotDevice's
// per-cycle frame choice (CutebotActuationPolicy, via serviceCycle()),
// CutebotTapAdapter's sign-corrected forwarding, and
// sim_cutebot_bus.h's simulated `0x80` onboard loop -- over a real
// CutebotDevice/CutebotMotorPort pair and a simulated 0x10 slave
// (sim_cutebot_bus.h), the same pattern cutebot_port_shim.cpp
// established for the raw-PWM path (sprint 040 ticket 002).
//
// This is deliberately a SEPARATE shim/test pair from
// cutebot_port_shim.cpp/test_cutebot_port.py: that file's job is the
// port's OWN correctness (frame bytes, coalescing, encoder conversion),
// proved with onboard_pid left at its default 0 throughout; this one's
// job is the HYBRID path those tests never touch. See
// test_cutebot_actuation_policy.py (a different shim again) for the
// PURE policy function, exercised with zero I2C/device in the link at
// all.
//
// Test scaffolding only: nothing under src/ knows this file exists.
#include <cstdint>
#include <cstring>

#include "platform/cutebot_port.h"
#include "sim_cutebot_bus.h"

// See cutebot_port_shim.cpp's own comment on this symbol.
namespace diffDrive {
void vfpSafeSleep(uint32_t) {}
}  // namespace diffDrive

namespace {

struct Handle {
  HostSim::SimCutebotBus bus;
  diffDrive::CutebotDevice device;
  diffDrive::CutebotMotorPort left;
  diffDrive::CutebotMotorPort right;
  diffDrive::CutebotTapAdapter tap;

  Handle(float tau, float breakaway, float dutyVelMax)
      : bus(tau, breakaway, dutyVelMax),
        device(bus),
        left(device, 0, +1),
        right(device, 1, +1),
        tap(device, left, right) {}

  diffDrive::CutebotMotorPort& port(int side) {
    return side == 0 ? left : right;
  }
};

}  // namespace

extern "C" {

void* chCreate(float tau, float breakaway, float dutyVelMax) {
  return new Handle(tau, breakaway, dutyVelMax);
}
void chDestroy(void* h) { delete static_cast<Handle*>(h); }

void chBeginBoth(void* h) {
  auto* handle = static_cast<Handle*>(h);
  handle->left.begin();
  handle->right.begin();
}

void chSetDuty(void* h, int side, float duty) {
  static_cast<Handle*>(h)->port(side).setDuty(duty);
}

// One kernel cycle for both wheels -- same shape as
// cutebot_port_shim.cpp's Handle::cycle(). Callers drive the tap
// BEFORE this, matching motion_engine.cpp's own ordering (notifyDrive()/
// notifyNeutral() happen alongside kernel_.drive()/kernel_.neutral(),
// which is what causes the NEXT step()'s tick()s to stage the new
// duty).
void chCycle(void* h, unsigned long long nowUs) {
  auto* handle = static_cast<Handle*>(h);
  handle->left.requestSample();
  handle->left.tick(static_cast<uint64_t>(nowUs));
  handle->right.requestSample();
  handle->right.tick(static_cast<uint64_t>(nowUs));
}

// phase: 0=kAccel, 1=kCruise, 2=kBrake (VelocityShaper::Phase's own
// declaration order, velocity_shaper.h).
void chTapDrive(void* h, float left, float right, int phase) {
  static_cast<Handle*>(h)->tap.onDrive(
      left, right, static_cast<diffDrive::VelocityShaper::Phase>(phase));
}
void chTapNeutral(void* h) { static_cast<Handle*>(h)->tap.onNeutral(); }

int chSetOnboardMode(void* h, int mode) {
  return static_cast<Handle*>(h)->device.setOnboardMode(mode) ? 1 : 0;
}
int chOnboardMode(void* h) { return static_cast<Handle*>(h)->device.onboardMode(); }
int chSetOnboardFloor(void* h, float floorMmS) {
  return static_cast<Handle*>(h)->device.setOnboardFloor(floorMmS) ? 1 : 0;
}
float chOnboardFloor(void* h) { return static_cast<Handle*>(h)->device.onboardFloor(); }

float chAppliedDuty(void* h, int side) {
  return static_cast<Handle*>(h)->port(side).appliedDuty();
}
float chPosition(void* h, int side) { return static_cast<Handle*>(h)->port(side).position(); }
float chVelocity(void* h, int side) { return static_cast<Handle*>(h)->port(side).velocity(); }

void chStepPhysics(void* h, float dt) { static_cast<Handle*>(h)->bus.step(dt); }

unsigned chFrameCount(void* h) { return static_cast<Handle*>(h)->bus.frameCount(); }
unsigned chOnboardFrameCount(void* h) {
  return static_cast<Handle*>(h)->bus.onboardFrameCount();
}
int chOnboardActive(void* h) {
  return static_cast<Handle*>(h)->bus.onboardActive() ? 1 : 0;
}
float chOnboardSetpoint(void* h, int side) {
  return static_cast<Handle*>(h)->bus.onboardSetpoint(side);
}
unsigned chLastWheelFrame(void* h, int index) {
  return static_cast<Handle*>(h)->bus.lastWheelFrame(index);
}
unsigned chLastOnboardFrame(void* h, int index) {
  return static_cast<Handle*>(h)->bus.lastOnboardFrame(index);
}
float chSimWheelVelocity(void* h, int side) {
  return static_cast<Handle*>(h)->bus.wheel(side).velocity();
}

// Writes a RAW 0x80 frame directly to the simulated bus, bypassing
// CutebotDevice/CutebotActuationPolicy entirely -- the one way to
// exercise sim_cutebot_bus.h's own clamp+lag model IN ISOLATION,
// standing in for "what if the policy had a bug and sent an
// under-floor nonzero setpoint anyway" (sim_cutebot_bus.h's own header
// comment). magL/magR are the raw, UNCLAMPED wire magnitudes; dirbits
// is the same b0=left-reverse/b1=right-reverse convention as 0x10.
void chWriteRawOnboardFrame(void* h, unsigned magL, unsigned magR,
                            unsigned dirbits) {
  uint8_t frame[9] = {
      0xFF, 0xF9, 0x80, 0x05,
      static_cast<uint8_t>((magL >> 8) & 0xFF),
      static_cast<uint8_t>(magL & 0xFF),
      static_cast<uint8_t>((magR >> 8) & 0xFF),
      static_cast<uint8_t>(magR & 0xFF),
      static_cast<uint8_t>(dirbits & 0xFF)};
  static_cast<Handle*>(h)->bus.write(0x10 << 1, frame, 9);
}

// Writes a RAW 0x10 (PWM) frame directly to the bus -- for the "0x10
// cancels onboard mode in the sim" test, again bypassing CutebotDevice
// so the sim's own behaviour is what is under test, not the device's.
void chWriteRawPwmFrame(void* h, unsigned wheelSel, unsigned absL,
                        unsigned absR, unsigned dirbits) {
  uint8_t frame[8] = {0xFF, 0xF9, 0x10, 0x04,
                      static_cast<uint8_t>(wheelSel),
                      static_cast<uint8_t>(absL),
                      static_cast<uint8_t>(absR),
                      static_cast<uint8_t>(dirbits)};
  static_cast<Handle*>(h)->bus.write(0x10 << 1, frame, 8);
}

}  // extern "C"
