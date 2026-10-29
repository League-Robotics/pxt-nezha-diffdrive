// sim_optical.h -- SimOptical: an OpticalPositionSource for host tests that
// behaves like the OTOS chip. The chip sits on a lever arm behind the pivot
// and integrates translation with its OWN heading, so its x/y frame is
// rotated by the gyro's accumulated error; takeOpticalIncrement() returns
// the centre-referenced change the way OtosPort does (arm removed with the
// chip's heading).
//
// Impairments, all off by default:
//   scale       linear scale error                           [1]
//   freeze      reads succeed but the centre never changes
//   dropout     takes report no new fix
//   jump        the chip position jumps once and stays there  [mm]
//
// Test scaffolding only: nothing under src/ knows this file exists.
#pragma once

#include <cmath>

#include "platform/gyro_source.h"

class SimOptical : public diffDrive::OpticalPositionSource {
 public:
  void setPresent(bool present) { present_ = present; }
  void setArm(float x, float y) { armX_ = x; armY_ = y; }  // [mm] body frame
  void setScale(float scale) { scale_ = scale; }
  void setFreeze(bool on) { frozen_ = on; }
  void setDropout(bool on) { dropout_ = on; }
  void jump(float dx, float dy) { sensorX_ += dx; sensorY_ += dy; }  // [mm]

  // The robot centre moved by (dx, dy) and now faces `heading`; the chip's
  // heading is `chipHeading`.
  void advance(float dx, float dy, float heading, float chipHeading) {
    // [mm] [mm] [rad] [rad]
    const float newArmX = std::cos(heading) * armX_ - std::sin(heading) * armY_;
    const float newArmY = std::sin(heading) * armX_ + std::cos(heading) * armY_;
    if (!primed_) {
      armDx_ = newArmX;
      armDy_ = newArmY;
      primed_ = true;
    }
    const float sensorDx = dx + (newArmX - armDx_);  // [mm]
    const float sensorDy = dy + (newArmY - armDy_);  // [mm]
    armDx_ = newArmX;
    armDy_ = newArmY;
    const float error = chipHeading - heading;  // [rad]
    if (!frozen_) {
      sensorX_ += scale_ * (std::cos(error) * sensorDx - std::sin(error) * sensorDy);
      sensorY_ += scale_ * (std::sin(error) * sensorDx + std::cos(error) * sensorDy);
    }
    chipHeading_ = chipHeading;
  }

  bool opticalPresent() const override { return present_; }
  bool opticalValid() const override { return present_; }

  bool takeOpticalIncrement(float& dx, float& dy) override {
    dx = 0.0f;
    dy = 0.0f;
    if (dropout_) return false;
    if (frozen_) return baselined_;
    const float centreX = sensorX_ - (std::cos(chipHeading_) * armX_ -
                                      std::sin(chipHeading_) * armY_);
    const float centreY = sensorY_ - (std::sin(chipHeading_) * armX_ +
                                      std::cos(chipHeading_) * armY_);
    const bool baselined = baselined_;
    if (baselined) {
      dx = centreX - takenX_;
      dy = centreY - takenY_;
    }
    takenX_ = centreX;
    takenY_ = centreY;
    baselined_ = true;
    return baselined;
  }

 private:
  bool present_ = true;
  bool frozen_ = false;
  bool dropout_ = false;
  bool primed_ = false;
  bool baselined_ = false;
  float armX_ = -43.0f, armY_ = 2.0f;  // [mm]
  float scale_ = 1.0f;
  float sensorX_ = 0.0f, sensorY_ = 0.0f;  // [mm]
  float armDx_ = 0.0f, armDy_ = 0.0f;      // [mm]
  float chipHeading_ = 0.0f;               // [rad]
  float takenX_ = 0.0f, takenY_ = 0.0f;    // [mm]
};
