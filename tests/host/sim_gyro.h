// sim_gyro.h -- SimGyro: a caller-driven GyroSource for host tests. The
// simulated chip integrates continuously as the test calls advance();
// readGyro() then latches (or fails to latch) what the chip holds.
//
// Impairments, all off by default:
//   bias        constant rate offset                       [rad/s]
//   wander      sinusoidal bias swing (temperature-like)   [rad/s], [s]
//   noise       white rate noise, standard deviation       [rad/s]
//   dropout     reads succeed but deliver nothing (kStale)
//   freeze      reads succeed (kOk) but the latched values never change
//   readFail    reads fail outright (kFailed), as an I2C NACK would
// Only freeze is silent; the estimator has to detect it from the data.
//
// Test scaffolding only: nothing under src/ knows this file exists.
#pragma once

#include <cmath>
#include <cstdint>

#include "platform/gyro_source.h"

class SimGyro : public diffDrive::GyroSource {
 public:
  void setPresent(bool present) { present_ = present; }
  void setBias(float bias) { bias_ = bias; }                    // [rad/s]
  void setWander(float amplitude, float period) {               // [rad/s] [s]
    wanderAmplitude_ = amplitude;
    wanderPeriod_ = period;
  }
  void setNoise(float deviation) { noise_ = deviation; }        // [rad/s]
  void setSeed(uint32_t seed) { rng_ = seed ? seed : 1u; }
  void setDropout(bool on) { dropout_ = on; }
  void setFreeze(bool on) { frozen_ = on; }
  void setReadFail(bool on) { readFail_ = on; }
  void failNextReads(int count) { failReads_ = count; }

  // Advances the chip by dt with the robot turning at trueRate.
  void advance(float dt, float trueRate) {  // [s] [rad/s]
    time_ += dt;
    trueHeading_ += trueRate * dt;
    trueRate_ = trueRate;
    chipRate_ = trueRate + bias() + noise_ * gaussian();
    chipHeading_ += chipRate_ * dt;
  }

  float bias() const {  // [rad/s] bias in effect now
    float b = bias_;
    if (wanderPeriod_ > 0.0f) {
      b += wanderAmplitude_ *
           std::sin(6.28318530718f * time_ / wanderPeriod_);
    }
    return b;
  }
  float trueHeading() const { return trueHeading_; }  // [rad]

  bool present() const override { return present_; }
  bool providesHeading() const override { return true; }
  bool providesRate() const override { return true; }
  float gyroHeading() const override { return latchedHeading_; }  // [rad]
  float gyroRate() const override { return latchedRate_; }        // [rad/s]

  diffDrive::GyroReadStatus readGyro() override {
    if (!present_) return diffDrive::GyroReadStatus::kFailed;
    if (failReads_ > 0) {
      --failReads_;
      return diffDrive::GyroReadStatus::kFailed;
    }
    if (readFail_) return diffDrive::GyroReadStatus::kFailed;
    if (dropout_) return diffDrive::GyroReadStatus::kStale;
    if (!frozen_) {
      latchedHeading_ = chipHeading_;
      latchedRate_ = chipRate_;
    }
    return diffDrive::GyroReadStatus::kOk;
  }

 private:
  uint32_t next() {
    rng_ ^= rng_ << 13;
    rng_ ^= rng_ >> 17;
    rng_ ^= rng_ << 5;
    return rng_;
  }
  float uniform() { return static_cast<float>(next() >> 8) / 16777216.0f; }
  float gaussian() {
    float sum = 0.0f;
    for (int i = 0; i < 12; ++i) sum += uniform();
    return sum - 6.0f;
  }

  bool present_ = true;
  bool dropout_ = false;
  bool frozen_ = false;
  bool readFail_ = false;
  int failReads_ = 0;
  uint32_t rng_ = 2463534242u;
  float bias_ = 0.0f;
  float wanderAmplitude_ = 0.0f;
  float wanderPeriod_ = 0.0f;
  float noise_ = 0.0f;
  float time_ = 0.0f;
  float trueHeading_ = 0.0f;
  float trueRate_ = 0.0f;
  float chipHeading_ = 0.0f;
  float chipRate_ = 0.0f;
  float latchedHeading_ = 0.0f;
  float latchedRate_ = 0.0f;
};
