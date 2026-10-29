// sensor_config_shim.cpp -- extern "C" ctypes surface for SimGyro
// (sim_gyro.h) and probeSensorConfig() (src/platform/sensor_config.h).
//
// Test scaffolding only: nothing under src/ knows this file exists.
#include "platform/gyro_source.h"
#include "platform/sensor_config.h"
#include "sim_gyro.h"

namespace {

class FakeOptical : public diffDrive::OpticalPositionSource {
 public:
  bool present = false;
  bool opticalPresent() const override { return present; }
  bool opticalValid() const override { return present; }
  bool takeOpticalIncrement(float& dx, float& dy) override {
    dx = 0.0f;
    dy = 0.0f;
    return false;
  }
};

struct Handle {
  SimGyro gyro;
  FakeOptical optical;
};

Handle* as(void* handle) { return static_cast<Handle*>(handle); }

}  // namespace

extern "C" {

void* sgCreate() { return new Handle(); }
void sgDestroy(void* handle) { delete as(handle); }

void sgSetPresent(void* handle, int present) {
  as(handle)->gyro.setPresent(present != 0);
}
void sgSetOpticalPresent(void* handle, int present) {
  as(handle)->optical.present = present != 0;
}
void sgSetBias(void* handle, float bias) { as(handle)->gyro.setBias(bias); }
void sgSetWander(void* handle, float amplitude, float period) {
  as(handle)->gyro.setWander(amplitude, period);
}
void sgSetNoise(void* handle, float deviation) {
  as(handle)->gyro.setNoise(deviation);
}
void sgSetSeed(void* handle, uint32_t seed) { as(handle)->gyro.setSeed(seed); }
void sgSetDropout(void* handle, int on) { as(handle)->gyro.setDropout(on != 0); }
void sgSetFreeze(void* handle, int on) { as(handle)->gyro.setFreeze(on != 0); }
void sgSetReadFail(void* handle, int on) {
  as(handle)->gyro.setReadFail(on != 0);
}
void sgFailNextReads(void* handle, int count) {
  as(handle)->gyro.failNextReads(count);
}

void sgAdvance(void* handle, float dt, float trueRate) {
  as(handle)->gyro.advance(dt, trueRate);
}

// 0 ok, 1 failed, 2 stale
int sgRead(void* handle) {
  return static_cast<int>(as(handle)->gyro.readGyro());
}
float sgHeading(void* handle) { return as(handle)->gyro.gyroHeading(); }
float sgRate(void* handle) { return as(handle)->gyro.gyroRate(); }
float sgTrueHeading(void* handle) { return as(handle)->gyro.trueHeading(); }
float sgBias(void* handle) { return as(handle)->gyro.bias(); }

// 0 optical, 1 gyro-only, 2 encoders-only
int sgProbe(void* handle) {
  Handle* h = as(handle);
  return static_cast<int>(
      diffDrive::probeSensorConfig(&h->gyro, &h->optical));
}
int sgProbeWithoutGyro(void* handle) {
  return static_cast<int>(
      diffDrive::probeSensorConfig(nullptr, &as(handle)->optical));
}
int sgProbeWithoutOptical(void* handle) {
  return static_cast<int>(diffDrive::probeSensorConfig(&as(handle)->gyro, nullptr));
}

}  // extern "C"
