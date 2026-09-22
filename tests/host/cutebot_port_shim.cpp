// cutebot_port_shim.cpp -- extern "C" ctypes surface for
// diffDrive::CutebotDevice / diffDrive::CutebotMotorPort
// (src/platform/cutebot_port.h/.cpp, sprint 040 ticket 002) over a
// simulated Cutebot Pro (sim_cutebot_bus.h) -- the Cutebot analogue of
// sim_robot_shim.cpp's Nezha coverage, scoped to the raw-PWM path.
//
// Unlike sim_robot_shim.cpp (which drives the real kernel/motion
// engine over the real Nezha shaping pipeline), this shim exercises
// CutebotDevice/CutebotMotorPort DIRECTLY -- no kernel in the link --
// because this ticket's job is to prove the port's own wire behaviour
// (frame bytes, coalescing, encoder conversion, the refusal path), not
// a tour. A future ticket that wants a host hybrid tour (S9's "Sprint
// 040 ... ends with ... a host hybrid tour that closes") builds that
// separately, the way sim_tour.py sits beside sim_robot_shim.cpp today.
//
// Test scaffolding only: nothing under src/ knows this file exists.
#include <cstdint>

#include "platform/cutebot_port.h"
#include "sim_cutebot_bus.h"

// CutebotMotorPort calls this after every v2 i2cCommandSend() (the
// extension's own 1 ms busy-wait, cutebot_port.h's own header
// comment); the real definition lives in the pxt-bound vfp_guard.cpp.
// There are no fibers here and the simulated bus answers instantly, so
// this is a no-op -- same convention sim_robot_shim.cpp/
// nezha_board_diag_shim.cpp already use for the same symbol.
namespace diffDrive {
void vfpSafeSleep(uint32_t) {}
}  // namespace diffDrive

namespace {

struct Handle {
  HostSim::SimCutebotBus bus;
  diffDrive::CutebotDevice device;
  diffDrive::CutebotMotorPort left;
  diffDrive::CutebotMotorPort right;

  Handle(float tau, float breakaway, float dutyVelMax)
      : bus(tau, breakaway, dutyVelMax),
        device(bus),
        left(device, 0, +1),
        right(device, 1, +1) {}

  diffDrive::CutebotMotorPort& port(int side) {
    return side == 0 ? left : right;
  }
};

}  // namespace

extern "C" {

void* cpCreate(float tau, float breakaway, float dutyVelMax) {
  return new Handle(tau, breakaway, dutyVelMax);
}
void cpDestroy(void* h) { delete static_cast<Handle*>(h); }

int cpBegin(void* h, int side) {
  auto* handle = static_cast<Handle*>(h);
  handle->port(side).begin();
  return handle->port(side).connected() ? 1 : 0;
}

void cpRequestSample(void* h, int side) {
  static_cast<Handle*>(h)->port(side).requestSample();
}

void cpSetDuty(void* h, int side, float duty) {
  static_cast<Handle*>(h)->port(side).setDuty(duty);
}

void cpTick(void* h, int side, unsigned long long nowUs) {
  static_cast<Handle*>(h)->port(side).tick(static_cast<uint64_t>(nowUs));
}

float cpPosition(void* h, int side) {
  return static_cast<Handle*>(h)->port(side).position();
}
float cpVelocity(void* h, int side) {
  return static_cast<Handle*>(h)->port(side).velocity();
}
float cpAppliedDuty(void* h, int side) {
  return static_cast<Handle*>(h)->port(side).appliedDuty();
}
int cpConnected(void* h, int side) {
  return static_cast<Handle*>(h)->port(side).connected() ? 1 : 0;
}
unsigned long long cpSampleTime(void* h, int side) {
  return static_cast<unsigned long long>(
      static_cast<Handle*>(h)->port(side).sampleTime());
}
void cpRebaseline(void* h, int side) {
  static_cast<Handle*>(h)->port(side).rebaseline();
}
int cpWedged(void* h, int side) {
  return static_cast<Handle*>(h)->port(side).wedged() ? 1 : 0;
}
int cpWedgeSuspect(void* h, int side) {
  return static_cast<Handle*>(h)->port(side).wedgeSuspect() ? 1 : 0;
}
void cpEmergencyStop(void* h, int side) {
  static_cast<Handle*>(h)->port(side).emergencyStop();
}
int cpConfigureWiring(void* h, int side, unsigned port, int sign) {
  auto result = static_cast<Handle*>(h)->port(side).configureWiring(
      static_cast<uint8_t>(port), static_cast<int8_t>(sign));
  return static_cast<int>(result);
}
unsigned cpWiredPort(void* h, int side) {
  return static_cast<Handle*>(h)->port(side).wiredPort();
}
int cpWiredSign(void* h, int side) {
  return static_cast<Handle*>(h)->port(side).wiredSign();
}

int cpDiagValue(void* h, int ordinal) {
  auto* handle = static_cast<Handle*>(h);
  return diffDrive::cutebotBoardDiagValue(handle->left, handle->right,
                                          ordinal);
}

int cpBeginDevice(void* h) {
  // Exercises CutebotDevice::ensureProbed() directly, independent of
  // either port's own begin() -- both ports' begin() call it too, so
  // this also lets a test check the "cached after the first call"
  // property without needing a live encoder read to succeed.
  return static_cast<Handle*>(h)->device.ensureProbed() ? 1 : 0;
}
int cpIsV2(void* h) { return static_cast<Handle*>(h)->device.isV2() ? 1 : 0; }
int cpHardwareClearEncoder(void* h, int side) {
  return static_cast<Handle*>(h)->device.hardwareClearEncoder(side) ? 1 : 0;
}

unsigned cpFrameCount(void* h) {
  return static_cast<Handle*>(h)->bus.frameCount();
}
unsigned cpClearCount(void* h) {
  return static_cast<Handle*>(h)->bus.clearCount();
}
unsigned cpProbeCount(void* h) {
  return static_cast<Handle*>(h)->bus.probeCount();
}
void cpArmNack(void* h) { static_cast<Handle*>(h)->bus.armNack(); }
void cpStepPhysics(void* h, float dt) {
  static_cast<Handle*>(h)->bus.step(dt);
}
float cpBusDuty(void* h, int side) {
  return static_cast<Handle*>(h)->bus.duty(side);
}
unsigned cpLastWheelFrame(void* h, int index) {
  return static_cast<Handle*>(h)->bus.lastWheelFrame(index);
}

}  // extern "C"
