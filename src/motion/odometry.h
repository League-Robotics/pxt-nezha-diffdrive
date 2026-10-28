// diffDrive::Odometry -- the robot's dead-reckoned pose, and the
// PoseSource MotionEngine::goToW() reads when no OTOS is fitted.
//
// READS MUTATE ODOMETRY: this class never advances itself, and shims.cpp's
// pose reads call update() first, so a pose read DOES advance odometry.
// That is load-bearing, not incidental -- see DESIGN.md before changing it.
#pragma once

#include <cmath>
#include <cstdint>

#include "../core/heading_wrap.h"
#include "../core/heading_wrap.h"
#include "motion_engine.h"

namespace diffDrive {

class Odometry : public PoseSource {
 public:
  // Geometry is read from `engine` fresh on every update(), so `engine`
  // must outlive this object and be declared before it.
  explicit Odometry(const MotionEngine& engine) : engine_(engine) {}

  // Folds one kernel Output into the frame. Diffs against the last Output
  // consumed and re-stamps it, so a tick with no encoder movement is a
  // no-op -- safe to call unconditionally.
  void update(const DiffDrive::DifferentialDrive::Output& out) {
    // A rebase re-anchors the wheel positions to a new software zero: an
    // intentional discontinuity, so this sample cannot be diffed against
    // the last one. Same handling as the very first call. This is the
    // codebase's only reader of positionEpochLeft/Right.
    const bool rebased =
        primed_ && (out.positionEpochLeft != positionEpochLeft_ ||
                    out.positionEpochRight != positionEpochRight_);
    if (!primed_ || rebased) {
      consume(out);
      primed_ = true;
      return;
    }
    const float cpm = engine_.countsPerMm();                     // [counts/mm]
    const float dLeft = (out.positionLeft - posLeft_) / cpm;      // [mm]
    const float dRight = (out.positionRight - posRight_) / cpm;   // [mm]
    consume(out);
    const float dCenter = 0.5f * (dLeft + dRight);                // [mm]
    const float dHeading =
        (dRight - dLeft) / engine_.effectiveTrackWidth();         // [rad]
    const float midHeading = heading_ + 0.5f * dHeading;          // [rad]
    x_ += dCenter * std::cos(midHeading);
    y_ += dCenter * std::sin(midHeading);
    heading_ += dHeading;
  }

  // Zeroes the frame. The wheel baseline is deliberately untouched:
  // callers call update() first, so pending motion is folded in and then
  // discarded with the frame rather than reappearing as a later jump.
  void reset() { seed(0.0f, 0.0f, 0.0f); }

  // Declares the frame from an external fix -- same "update() first" idiom.
  void seed(float x, float y, float heading) {  // [mm] [mm] [rad]
    x_ = x;
    y_ = y;
    heading_ = heading;
    anchored_ = false;
  }

  // Pull heading onto an absolute heading sensor (the OTOS gyro) after
  // the fact; position keeps integrating encoder distance along it. The
  // first sample after a seed only anchors the two frames. A sample whose
  // change disagrees with the encoders' by more than 1 deg + 30% (a
  // frozen or lifted sensor) is dropped and the next one re-anchors, so
  // a bad sensor costs only its own drift, never a heading jump.
  void fuseHeading(float sensor) {  // [rad] sensor's own frame, wrapped
    if (anchored_) {
      const float sensorStep = wrapRadians(sensor - lastSensor_);
      const float encoderStep = heading_ - lastHeading_;
      if (std::fabs(sensorStep - encoderStep) <=
          kFuseSlack + kFuseFraction * std::fabs(encoderStep)) {
        heading_ += wrapRadians(sensor + offset_ - heading_);
      } else {
        anchored_ = false;
      }
    }
    if (!anchored_) {
      offset_ = heading_ - sensor;
      anchored_ = true;
    }
    lastSensor_ = sensor;
    lastHeading_ = heading_;
  }

  float x() const override { return x_; }  // [mm] world frame
  float y() const override { return y_; }  // [mm] world frame

  // [rad] world frame, CCW+, UNWRAPPED -- one of the two conventions
  // PoseSource permits. Do not difference two reads across implementations.
  float heading() const override { return heading_; }

 private:
  void consume(const DiffDrive::DifferentialDrive::Output& out) {
    posLeft_ = out.positionLeft;
    posRight_ = out.positionRight;
    positionEpochLeft_ = out.positionEpochLeft;
    positionEpochRight_ = out.positionEpochRight;
  }

  static constexpr float kFuseSlack = 0.0174533f;  // [rad] 1 deg
  static constexpr float kFuseFraction = 0.3f;

  const MotionEngine& engine_;
  bool anchored_ = false;
  float offset_ = 0.0f;       // [rad] odometry heading - sensor heading
  float lastSensor_ = 0.0f;   // [rad]
  float lastHeading_ = 0.0f;  // [rad]
  float x_ = 0.0f, y_ = 0.0f;  // [mm] world frame
  float heading_ = 0.0f;       // [rad] world frame, CCW+, unwrapped
  float posLeft_ = 0.0f, posRight_ = 0.0f;  // [counts] last consumed
  bool primed_ = false;
  uint32_t positionEpochLeft_ = 0, positionEpochRight_ = 0;
};

// The selection rule engineGoToW() (shims.cpp) applies. Extracted from its
// one call site only so a host test can exercise it against two fakes.
inline PoseSource& selectPoseSource(bool primaryConnected, PoseSource& primary,
                                    PoseSource& fallback) {
  return primaryConnected ? primary : fallback;
}

}  // namespace diffDrive
