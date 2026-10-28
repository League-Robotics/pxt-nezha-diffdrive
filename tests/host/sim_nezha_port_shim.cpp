// sim_nezha_port_shim.cpp -- extern "C" ctypes surface for ONE real
// NezhaMotorPort on M1 wired to HostSim::SimNezhaBus, for
// test_nezha_port_position_move.py (sprint 042 ticket 004). No kernel:
// the test plays the kernel's part (setDuty each tick, then tick()).
// A freeze switch sits between port and bus so a test can hold the
// encoder reply constant mid-move (wedge / frozen-read tests).
#include <cstdint>
#include <cstring>

#include "platform/nezha_port.h"
#include "sim_nezha_bus.h"

namespace diffDrive {
void vfpSafeSleep(uint32_t) {}  // pxt-bound on target; no fibers here
}  // namespace diffDrive

namespace {

class FreezeBus final : public diffDrive::I2CBus {
 public:
  explicit FreezeBus(HostSim::SimNezhaBus& inner) : inner_(inner) {}
  int write(uint16_t a, const uint8_t* d, int n) override {
    return inner_.write(a, d, n);
  }
  int read(uint16_t a, uint8_t* d, int n) override {
    if (frozen && haveLast) {
      std::memcpy(d, last, 4);
      return 0;
    }
    const int r = inner_.read(a, d, n);
    if (r == 0) {
      std::memcpy(last, d, 4);
      haveLast = true;
    }
    return r;
  }
  bool frozen = false;
 private:
  HostSim::SimNezhaBus& inner_;
  uint8_t last[4] = {0, 0, 0, 0};
  bool haveLast = false;
};

constexpr uint64_t kTickUs = 24000;  // [us] the kernel's control period

struct Rig {
  HostSim::SimNezhaBus bus;
  FreezeBus wire;
  diffDrive::NezhaMotorPort port;
  uint64_t now = 0;  // [us]
  Rig(float tau, int fwdSign)
      : bus(tau, 0.0f, 11500.0f), wire(bus),
        port(1, static_cast<int8_t>(fwdSign), wire) {}
};

Rig* R(void* h) { return static_cast<Rig*>(h); }

}  // namespace

extern "C" {

void* npCreate(float tau, int fwdSign) { return new Rig(tau, fwdSign); }
void npDestroy(void* h) { delete R(h); }
void npBegin(void* h) { R(h)->port.begin(); }

// One kernel cycle: select, tick (collect + write), then the physics.
void npTick(void* h) {
  Rig* r = R(h);
  r->now += kTickUs;
  r->port.requestSample();
  r->port.tick(r->now);
  r->bus.step(static_cast<float>(kTickUs) / 1e6f);
}
void npSetDuty(void* h, float d) { R(h)->port.setDuty(d); }
void npEmergencyStop(void* h) { R(h)->port.emergencyStop(); }
int npBeginMove(void* h, float delta, float dps) {
  return R(h)->port.beginMove(delta, dps) ? 1 : 0;
}
int npHardStop(void* h) { return R(h)->port.hardStop() ? 1 : 0; }
int npMoveLive(void* h) { return R(h)->port.moveLive() ? 1 : 0; }
int npDriven(void* h) { return R(h)->port.driven() ? 1 : 0; }
int npSupports(void* h) { return R(h)->port.supportsPositionMove() ? 1 : 0; }
float npQuantum(void* h) { return R(h)->port.positionQuantum(); }
float npLastMoveCounts(void* h) { return R(h)->port.lastMoveCounts(); }
float npPosition(void* h) { return R(h)->port.position(); }
float npVelocity(void* h) { return R(h)->port.velocity(); }
float npApplied(void* h) { return R(h)->port.appliedDuty(); }
int npWedged(void* h) { return R(h)->port.wedged() ? 1 : 0; }
int npWedgeSuspect(void* h) { return R(h)->port.wedgeSuspect() ? 1 : 0; }
void npFreeze(void* h, int on) { R(h)->wire.frozen = on != 0; }
// The simulated wheel's true position [counts] and brick state.
float npWheelPos(void* h) { return R(h)->bus.wheel(1).position(); }
float npWheelVel(void* h) { return R(h)->bus.wheel(1).velocity(); }
int npBusMoveLive(void* h) { return R(h)->bus.moveLive(1) ? 1 : 0; }
uint32_t npFrameCount(void* h) { return R(h)->bus.frameCount(); }
int npFrame(void* h, uint32_t i, uint8_t* out) {
  return R(h)->bus.frameBytes(i, out) ? 1 : 0;
}
uint32_t npFrames60(void* h) { return R(h)->bus.frames60(1); }
uint32_t npFrames60WhileLive(void* h) { return R(h)->bus.frames60WhileLive(1); }
uint32_t npViolations1D(void* h) { return R(h)->bus.violations1D(); }
void npClearLog(void* h) { R(h)->bus.clearFrameLog(); }

}  // extern "C"

extern "C" {
uint32_t npGlitchCount(void* h) { return R(h)->port.glitchCount_; }
}
