// sim_otos_bus.h -- SimOtosBus: a SparkFun OTOS as an I2C slave at 0x17, for
// the real OtosPort to talk to. The chip heading integrates a constant gyro
// bias against the clock the test owns; position and velocity stay at what
// was last written. Registers are the ones otos_port.cpp touches: product id
// (0x00), IMU calibration count (0x06), the pose burst (0x20, 12 bytes).
//
// Test scaffolding only: nothing under src/ knows this file exists.
#pragma once

#include <cmath>
#include <cstdint>

#include "platform/i2c_bus.h"

class SimOtosBus final : public diffDrive::I2CBus {
 public:
  static constexpr uint8_t kAddress8 = 0x17 << 1;
  static constexpr float kHeadingRadPerLsb =
      0.00549f * (3.14159265f / 180.0f);          // [rad/LSB]
  static constexpr float kOmegaRadPerLsb = 34.9f / 32768.0f;  // [rad/s/LSB]

  explicit SimOtosBus(const uint64_t* clockUs) : clockUs_(clockUs) {}

  void setPresent(bool present) { present_ = present; }
  void setBias(float bias) {  // [rad/s]
    headingBase_ = chipHeading();
    baseUs_ = *clockUs_;
    bias_ = bias;
  }
  float chipHeading() const {  // [rad]
    return headingBase_ +
           bias_ * static_cast<float>(*clockUs_ - baseUs_) * 1e-6f;
  }
  int burstReads() const { return burstReads_; }
  int poseWrites() const { return poseWrites_; }
  void failBursts(bool on) { failBursts_ = on; }

  int write(uint16_t, const uint8_t* data, int len) override {
    if (!present_ || len < 1) return 1;
    pointer_ = data[0];
    if (len == 7 && data[0] == kRegPosition) {
      ++poseWrites_;
      const int16_t h = static_cast<int16_t>(data[5] | (data[6] << 8));
      headingBase_ = static_cast<float>(h) * kHeadingRadPerLsb;
      baseUs_ = *clockUs_;
    }
    return 0;
  }

  int read(uint16_t, uint8_t* data, int len) override {
    if (!present_) return 1;
    for (int i = 0; i < len; ++i) data[i] = 0;
    if (pointer_ == kRegProductId) {
      data[0] = 0x5F;
    } else if (pointer_ == kRegPosition && len == 12) {
      if (failBursts_) return 1;
      ++burstReads_;
      long h = std::lround(chipHeading() / kHeadingRadPerLsb);
      if (h > 32767) h = 32767;
      if (h < -32767) h = -32767;
      long w = std::lround(bias_ / kOmegaRadPerLsb);
      data[4] = static_cast<uint8_t>(h & 0xFF);
      data[5] = static_cast<uint8_t>((h >> 8) & 0xFF);
      data[10] = static_cast<uint8_t>(w & 0xFF);
      data[11] = static_cast<uint8_t>((w >> 8) & 0xFF);
    }
    return 0;
  }

 private:
  static constexpr uint8_t kRegProductId = 0x00;
  static constexpr uint8_t kRegPosition = 0x20;

  const uint64_t* clockUs_;
  bool present_ = true;
  bool failBursts_ = false;
  float bias_ = 0.0f;         // [rad/s]
  float headingBase_ = 0.0f;  // [rad] chip heading at baseUs_
  uint64_t baseUs_ = 0;       // [us]
  uint8_t pointer_ = 0;
  int burstReads_ = 0;
  int poseWrites_ = 0;
};
