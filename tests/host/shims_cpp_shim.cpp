// shims_cpp_shim.cpp -- extern "C" ctypes surface over the REAL src/shims.cpp
// (sprint 044 ticket 011). Everything below shims.cpp is also real: the
// kernel, motion engine, estimator, board_nezha.cpp's NezhaMotorPort pair
// and otos_port.cpp, talking I2C through tests/host/pxt_host_stub/pxt.h to a
// SimNezhaBus and a SimOtosBus. Only the protocol*() functions shims.cpp
// reaches by forward declaration are faked here (protocol.cpp is the
// fiber loop and cannot be linked).
//
// Time is the stub's: nothing runs on its own, and fiber_sleep() inside the
// real code advances the clock. rig is a process-lifetime singleton in
// shims.cpp, so each test loads its own copy of the library.
#include <cstdint>
#include <memory>

#include "pxt_host_stub/pxt.h"
#include "sim_nezha_bus.h"
#include "sim_otos_bus.h"

HostPxtState& hostPxt() {
  static HostPxtState state;
  return state;
}

HostUBit& hostUBit() {
  static HostUBit ubit;
  return ubit;
}

namespace diffDrive {

void idleSense();
void startMove(int distance, int yaw, int speed, int yawRate);
bool tickDrive();
void seedPose(int x, int y, int heading);
void setKernelValue(int field, int value);
int diagValue(int what);
int poseX();
int poseY();
int poseHeading();
int otosBegin();
bool otosRead();
int otosGet(int what);

namespace {
int gReleaseBlockCalls = 0;
}

int boardLineBits() { return -1; }
int boardLineGrey(int) { return -1; }

bool protocolTryTakeMotionOwnership() { return true; }
void protocolReleaseBlockOwnership() { ++gReleaseBlockCalls; }
void protocolEmitLine(const char*) {}
void protocolSetupWifi(const char*, const char*) {}
void protocolSetProfile(const char*) {}
void protocolSetDeviceRole(const char*, const char*) {}
const char* protocolCurrentRunText() { return ""; }
int protocolSerialDropCount() { return 0; }
int protocolRunDropCount() { return 0; }
int protocolEmitDropCount() { return 0; }
int protocolRunMalformedCount() { return 0; }
int protocolRadioRxFrameCount() { return 0; }
int protocolRadioRxAcceptedCount() { return 0; }
int protocolRadioRxOverrunDropCount() { return 0; }
int protocolRadioRxOversizeDropCount() { return 0; }

}  // namespace diffDrive

namespace {

constexpr uint8_t kNezhaAddress8 = 0x10 << 1;

int gHookFires = 0;

class HookedBus final : public diffDrive::I2CBus {
 public:
  explicit HookedBus(diffDrive::I2CBus& inner) : inner_(inner) {}

  int write(uint16_t address, const uint8_t* data, int len) override {
    if (idleOnNextWrite_) {
      idleOnNextWrite_ = false;
      ++gHookFires;
      diffDrive::idleSense();
    }
    return inner_.write(address, data, len);
  }
  int read(uint16_t address, uint8_t* data, int len) override {
    return inner_.read(address, data, len);
  }
  void idleOnNextWrite() { idleOnNextWrite_ = true; }

 private:
  diffDrive::I2CBus& inner_;
  bool idleOnNextWrite_ = false;
};

struct World {
  HostSim::SimNezhaBus nezhaBus{0.13f, 25.0f * 12.69f, 676.0f * 12.69f};
  SimOtosBus otos{&hostPxt().nowUs};
  HookedBus nezha{nezhaBus};
  HookedBus otosHook{otos};
};

World* gWorld = nullptr;

}  // namespace

extern "C" {

void scInit(int otosPresent, float biasRadPerS) {
  gHookFires = 0;
  hostPxt() = HostPxtState();
  hostPxt().nowUs = 1000000;
  delete gWorld;
  gWorld = new World();
  gWorld->otos.setPresent(otosPresent != 0);
  gWorld->otos.setBias(biasRadPerS);
  hostPxt().slaves.push_back({kNezhaAddress8, &gWorld->nezha});
  hostPxt().slaves.push_back({SimOtosBus::kAddress8, &gWorld->otosHook});
}

uint64_t scNowUs() { return hostPxt().nowUs; }
void scAdvanceUs(uint64_t us) { hostPxt().nowUs += us; }
int scFiberCount() { return static_cast<int>(hostPxt().fibers.size()); }

int scEnsure() { return diffDrive::diagValue(0); }
int scDiag(int what) { return diffDrive::diagValue(what); }
int scTick() { return diffDrive::tickDrive() ? 1 : 0; }
void scIdleSense() { diffDrive::idleSense(); }
int scHookFires() { return gHookFires; }
void scIdleSenseDuringNextNezhaWrite() { gWorld->nezha.idleOnNextWrite(); }
void scIdleSenseDuringNextOtosWrite() { gWorld->otosHook.idleOnNextWrite(); }
void scStartMove(int distance, int yaw, int speed, int yawRate) {
  diffDrive::startMove(distance, yaw, speed, yawRate);
}
void scSeed(int x, int y, int heading) { diffDrive::seedPose(x, y, heading); }
void scRebase() { diffDrive::setKernelValue(32, 1000); }
int scPoseX() { return diffDrive::poseX(); }
int scPoseY() { return diffDrive::poseY(); }
int scPoseHeading() { return diffDrive::poseHeading(); }
int scOtosBegin() { return diffDrive::otosBegin(); }
int scOtosRead() { return diffDrive::otosRead() ? 1 : 0; }
int scOtosGet(int what) { return diffDrive::otosGet(what); }

int scOtosBurstReads() { return gWorld->otos.burstReads(); }
int scOtosPoseWrites() { return gWorld->otos.poseWrites(); }
float scOtosChipHeading() { return gWorld->otos.chipHeading(); }
void scOtosSetPresent(int present) { gWorld->otos.setPresent(present != 0); }
void scOtosFailBursts(int on) { gWorld->otos.failBursts(on != 0); }
void scOtosMoveSensor(float dx, float dy) { gWorld->otos.moveSensor(dx, dy); }
void scOtosSetBias(float rate) { gWorld->otos.setBias(rate); }

}  // extern "C"
