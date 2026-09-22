// nezha_board_diag_shim.cpp -- extern "C" ctypes surface for
// diffDrive::nezhaBoardDiagValue() (src/platform/nezha_port.h/.cpp),
// the free function sprint 040 ticket 001 factored out of shims.cpp's
// diagValue() switch so that ordinals 21/22/23/24/27/35-40 -- Nezha-
// only counters and wiring readbacks -- stay provable on the host once
// the board-composition seam (platform/board.h,
// platform/board_nezha.cpp) moves the switch itself behind a per-board
// hook shims.cpp cannot be compiled to exercise directly.
//
// Deliberately does NOT construct anything through board_nezha.cpp's
// own NezhaBoard singleton: that type binds its two NezhaMotorPorts
// through the DEFAULT bus argument (defaultI2CBus()), which only the
// target's platform/microbit_i2c_bus.cpp defines -- there is no host
// definition, by design (see platform/i2c_bus.h's own comment), so
// linking board_nezha.cpp itself on the host is not attempted here.
// This shim instead constructs its own pair with an EXPLICIT no-op bus
// (never touched -- see below), which is enough to prove
// nezhaBoardDiagValue()'s field mapping without any I2C traffic.
//
// Test scaffolding only: nothing under src/ knows this file exists.
#include "platform/nezha_port.h"

// NezhaMotorPort calls this between the encoder register select and
// the read (nezha_port.cpp's vfpSafeSleep(4)); the real definition
// lives in the pxt-bound vfp_guard.cpp. This shim never actually
// drives an encoder read (see NoOpBus below), but begin() calls it
// unconditionally, so it must exist to link -- same convention
// sim_robot_shim.cpp already uses for the same symbol.
namespace diffDrive {
void vfpSafeSleep(uint32_t) {}
}  // namespace diffDrive

namespace {

// Every call fails. Nothing here exercises real I2C traffic -- the
// ports below are only ever touched through their public counters and
// wiredPort()/wiredSign()/rawCount(), never begin()/tick()'d.
class NoOpBus final : public diffDrive::I2CBus {
 public:
  int write(uint16_t, const uint8_t*, int) override { return 1; }
  int read(uint16_t, uint8_t*, int) override { return 1; }
};

NoOpBus& bus() {
  static NoOpBus instance;
  return instance;
}

// One left+right pair, matching board_nezha.cpp's own NezhaBoard shape
// closely enough to exercise the SAME two-port call convention
// boardDiagValue() uses, without depending on that file at all.
struct Handle {
  diffDrive::NezhaMotorPort left{1, -1, bus()};
  diffDrive::NezhaMotorPort right{2, +1, bus()};
};

}  // namespace

extern "C" {

void* nbdCreate() { return new Handle(); }
void nbdDestroy(void* h) { delete static_cast<Handle*>(h); }

// The three plain public counters (maxDrivenStreak_/glitchCount_/
// rebaselineCount_) are poked directly rather than driven there for
// real through a live bus -- this shim's whole point is to feed
// nezhaBoardDiagValue() known field values cheaply.
void nbdSetLeftCounters(void* h, unsigned maxDrivenStreak, unsigned glitchCount,
                        unsigned rebaselineCount) {
  auto* handle = static_cast<Handle*>(h);
  handle->left.maxDrivenStreak_ = maxDrivenStreak;
  handle->left.glitchCount_ = glitchCount;
  handle->left.rebaselineCount_ = rebaselineCount;
}
void nbdSetRightCounters(void* h, unsigned maxDrivenStreak, unsigned glitchCount,
                         unsigned rebaselineCount) {
  auto* handle = static_cast<Handle*>(h);
  handle->right.maxDrivenStreak_ = maxDrivenStreak;
  handle->right.glitchCount_ = glitchCount;
  handle->right.rebaselineCount_ = rebaselineCount;
}

int nbdDiagValue(void* h, int ordinal) {
  auto* handle = static_cast<Handle*>(h);
  return diffDrive::nezhaBoardDiagValue(handle->left, handle->right, ordinal);
}

}  // extern "C"
