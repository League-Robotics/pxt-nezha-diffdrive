// sim_nezha_brick_shim.cpp -- extern "C" ctypes surface for
// HostSim::SimNezhaBus ALONE (no kernel, no NezhaMotorPort), so
// test_sim_nezha_bus_brick_opcodes.py can send byte-exact brick frames
// and watch the simulated wheel. Sprint 042 ticket 003. The whole-stack
// shim (sim_robot_shim.cpp) exposes the same frame-log counters for
// tests that drive the real port.
#include <cstdint>

#include "sim_nezha_bus.h"

extern "C" {

void* nbCreate(float tau, float breakaway, float dutyVelMax) {
  return new HostSim::SimNezhaBus(tau, breakaway, dutyVelMax);
}
void nbDestroy(void* h) { delete static_cast<HostSim::SimNezhaBus*>(h); }

// Writes one 8-byte frame to address 0x10; returns the bus status.
int nbWrite(void* h, const uint8_t* frame) {
  return static_cast<HostSim::SimNezhaBus*>(h)->write(0x10 << 1, frame, 8);
}
// Selects `port` is implicit in the last write; reads that port's counts.
int nbReadCounts(void* h, int32_t* out) {
  uint8_t b[4];
  const int r = static_cast<HostSim::SimNezhaBus*>(h)->read(0x10 << 1, b, 4);
  if (r != 0) return r;
  *out = static_cast<int32_t>(
      static_cast<uint32_t>(b[0]) | (static_cast<uint32_t>(b[1]) << 8) |
      (static_cast<uint32_t>(b[2]) << 16) | (static_cast<uint32_t>(b[3]) << 24));
  return 0;
}
void nbStep(void* h, float dt) {
  static_cast<HostSim::SimNezhaBus*>(h)->step(dt);
}
void nbSetOwnedRunDegPerPercent(void* h, float v) {
  static_cast<HostSim::SimNezhaBus*>(h)->setOwnedRunDegPerPercent(v);
}
float nbPosition(void* h, int port) {
  return static_cast<HostSim::SimNezhaBus*>(h)->wheel(
      static_cast<uint8_t>(port)).position();
}
float nbVelocity(void* h, int port) {
  return static_cast<HostSim::SimNezhaBus*>(h)->wheel(
      static_cast<uint8_t>(port)).velocity();
}
int nbMoveLive(void* h, int port) {
  return static_cast<HostSim::SimNezhaBus*>(h)->moveLive(
             static_cast<uint8_t>(port)) ? 1 : 0;
}
int nbHasTarget(void* h, int port) {
  return static_cast<HostSim::SimNezhaBus*>(h)->hasTarget(
             static_cast<uint8_t>(port)) ? 1 : 0;
}
int nbSpeedStore(void* h, int port) {
  return static_cast<HostSim::SimNezhaBus*>(h)->speedStore(
      static_cast<uint8_t>(port));
}
uint32_t nbFrameCount(void* h) {
  return static_cast<HostSim::SimNezhaBus*>(h)->frameCount();
}
int nbFrame(void* h, uint32_t i, uint8_t* out) {
  return static_cast<HostSim::SimNezhaBus*>(h)->frameBytes(i, out) ? 1 : 0;
}
uint32_t nbFrames60(void* h, int port) {
  return static_cast<HostSim::SimNezhaBus*>(h)->frames60(
      static_cast<uint8_t>(port));
}
uint32_t nbFrames60WhileLive(void* h, int port) {
  return static_cast<HostSim::SimNezhaBus*>(h)->frames60WhileLive(
      static_cast<uint8_t>(port));
}
uint32_t nbViolations1D(void* h) {
  return static_cast<HostSim::SimNezhaBus*>(h)->violations1D();
}

}  // extern "C"
