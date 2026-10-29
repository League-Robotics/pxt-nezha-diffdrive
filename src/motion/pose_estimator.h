// diffDrive::PoseEstimator -- the robot's pose from whatever sensors it has,
// and the PoseSource goToW() reads.
//
// Encoders always integrate (through an Odometry used only to difference
// them). A gyro, when present, is the heading reference; its rate bias is
// learned (GyroBiasTracker) and removed. An optical source, when present,
// supplies position. Losing a sensor drops to the next configuration with
// the output carried over, so nothing steps.
//
// Heading never re-anchors on a rejected sample: the sample is skipped,
// the output follows the encoders for that interval, and the gyro stays
// the reference for the next sample.
#pragma once

#include <cmath>
#include <cstdint>

#include "../core/heading_wrap.h"
#include "../platform/gyro_source.h"
#include "../platform/sensor_config.h"
#include "gyro_bias_tracker.h"
#include "odometry.h"

namespace diffDrive {

struct PoseEstimatorParams {
  // Encoders must stay unchanged this long before the robot counts as
  // still (the chassis keeps turning briefly after the wheels stop).
  float restDwell = 0.25f;  // [s]

  // A gyro change is believed when it agrees with the encoders' to within
  // slack + fraction of theirs.
  float gateSlack = 0.0174533f;  // [rad] 1 deg
  float gateFraction = 0.3f;     // [1]
  int confirmSamples = 3;        // consecutive consistent samples that make a
                                 // rejected jump the new reference

  int dropoutReads = 8;   // consecutive failed or stale reads that drop a sensor
  int recoverReads = 10;  // consecutive good reads that bring it back

  // Gyro frozen: identical readings while the encoders turn.
  float freezeStep = 0.00175f;  // [rad] 0.1 deg of encoder turn per read
  float freezeTurn = 0.0524f;   // [rad] 3 deg total

  // Optical increments are believed within slack + fraction of the encoder
  // distance covered over the same interval.
  float opticalSlack = 30.0f;     // [mm]
  float opticalFraction = 0.5f;   // [1]
  float opticalFreezeDistance = 40.0f;  // [mm] encoder distance the optical source
                                        // fell short by, beyond a 20% allowance
  int opticalRejectLimit = 8;     // consecutive rejected takes that drop it
  float opticalScale = 1.0f;      // [1] linear scale applied to increments

  GyroBiasParams bias;
};

class PoseEstimator : public PoseSource {
 public:
  using Output = DiffDrive::DifferentialDrive::Output;

  explicit PoseEstimator(const MotionEngine& engine,
                         const PoseEstimatorParams& params = PoseEstimatorParams())
      : params_(params), enc_(engine), bias_(params.bias) {}

  // Sensors are borrowed and must outlive the estimator. `config` is what
  // the boot probe found; a sensor the config does not name is ignored.
  void attachSensors(GyroSource* gyro, OpticalPositionSource* optical,
                     SensorConfig config) {
    gyro_ = config == SensorConfig::kEncodersOnly ? nullptr : gyro;
    optical_ = config == SensorConfig::kOptical ? optical : nullptr;
    gyroUp_ = gyro_ != nullptr;
    opticalUp_ = optical_ != nullptr;
    gyroPrimed_ = false;
  }

  // One tick. The encoders are folded in every call; the sensors are read
  // only when `sampleSensors`, so the caller sets the read cadence.
  void update(const Output& out, float dt, bool sampleSensors = true) {
    enc_.update(out);  // [s]
    const float dCentre = enc_.stepCentre();    // [mm]
    const float dHeading = enc_.stepHeading();  // [rad]
    restTime_ = (dCentre == 0.0f && dHeading == 0.0f) ? restTime_ + dt : 0.0f;
    time_ += dt;
    encoderTurn_ += dHeading;
    sinceAnchorTime_ += dt;
    sinceAnchorTurn_ += dHeading;
    sinceReadTurn_ += dHeading;
    stillTurn_ += std::fabs(dHeading);
    if (!gyroUp_) gyroTurn_ += dHeading;

    const float mid = heading_ + 0.5f * dHeading;  // [rad]
    const float stepX = dCentre * std::cos(mid);   // [mm]
    const float stepY = dCentre * std::sin(mid);   // [mm]
    x_ += stepX;
    y_ += stepY;
    heading_ += dHeading;
    pendingX_ += stepX;
    pendingY_ += stepY;
    pendingPath_ += std::fabs(dCentre);

    if (sampleSensors && gyro_ != nullptr) sampleGyro();
  }

  // Same "update() first" idiom as Odometry::seed(). The learned bias is
  // kept: it belongs to the gyro, not to the frame.
  void seed(float x, float y, float heading) {  // [mm] [mm] [rad]
    x_ = baseX_ = x;
    y_ = baseY_ = y;
    heading_ = anchorHeading_ = heading;
    sinceAnchorTime_ = sinceAnchorTurn_ = 0.0f;
    pendingX_ = pendingY_ = pendingPath_ = 0.0f;
    agree_ = 0;
  }
  void reset() { seed(0.0f, 0.0f, 0.0f); }

  // The optical source was re-seeded: take the next gyro reading as the new
  // reference instead of reading the jump as a step.
  void reprime() { gyroPrimed_ = false; }

  float x() const override { return x_; }              // [mm] world frame
  float y() const override { return y_; }              // [mm] world frame
  float heading() const override { return heading_; }  // [rad] unwrapped
  bool hasHeadingReference() const override { return gyroUp_; }
  bool tracksMotion() const override { return true; }

  SensorConfig config() const {
    if (!gyroUp_) return SensorConfig::kEncodersOnly;
    return opticalUp_ ? SensorConfig::kOptical : SensorConfig::kGyroOnly;
  }
  bool atRest() const { return restTime_ >= params_.restDwell; }

  float biasRate() const { return bias_.rate(); }  // [rad/s]
  const GyroBiasTracker& bias() const { return bias_; }
  uint32_t rejectedCount() const { return rejected_; }  // gyro + optical
  uint32_t stepCount() const { return steps_; }  // jumps taken as the new reference
  const PoseEstimatorParams& params() const { return params_; }

 private:
  bool consistent(float change, float expected) const {  // [rad] [rad]
    return std::fabs(change - expected) <=
           params_.gateSlack + params_.gateFraction * std::fabs(expected);
  }

  void dropGyro() {
    gyroTurn_ += sinceAnchorTurn_;
    gyroUp_ = false;
    opticalUp_ = false;
    recovered_ = 0;
  }

  void sampleGyro() {
    const GyroReadStatus status = gyro_->readGyro();
    if (status != GyroReadStatus::kOk) {
      recovered_ = 0;
      if (++silent_ >= params_.dropoutReads && gyroUp_) dropGyro();
      return;
    }
    silent_ = 0;
    const float raw = gyro_->gyroHeading();  // [rad]
    const float rate = gyro_->gyroRate();    // [rad/s]
    const bool unchanged = gyroPrimed_ && raw == previousRaw_ && rate == previousRate_;
    if (!unchanged) stillTurn_ = 0.0f;

    if (!gyroPrimed_) {
      gyroPrimed_ = true;
      anchor(raw);
      previousRaw_ = raw;
      previousRate_ = rate;
      return;
    }
    if (!gyroUp_) {
      if (unchanged && frozenDown_) {
        recovered_ = 0;
      } else {
        frozenDown_ = false;
        if (++recovered_ >= params_.recoverReads) {
          gyroUp_ = true;
          opticalUp_ = optical_ != nullptr;
          anchor(raw);
          baseX_ = x_;
          baseY_ = y_;
          pendingX_ = pendingY_ = pendingPath_ = 0.0f;
        }
      }
      previousRaw_ = raw;
      previousRate_ = rate;
      sinceReadTurn_ = 0.0f;
      return;
    }
    if (unchanged && stillTurn_ > params_.freezeStep) {
      if (stillTurn_ > params_.freezeTurn) {
        frozenDown_ = true;
        dropGyro();
      }
      return;
    }

    const float change = wrapRadians(raw - anchorRaw_);  // [rad]
    if (atRest() && sinceAnchorTurn_ == 0.0f) {
      holdAtRest(change);
    } else if (consistent(change, sinceAnchorTurn_)) {
      acceptMoving(change);
    } else {
      rejectJump(raw);
    }
    previousRaw_ = raw;
    previousRate_ = rate;
    sinceReadTurn_ = 0.0f;
    if (optical_ != nullptr) sampleOptical(raw);
  }

  void anchor(float raw) {
    anchorRaw_ = raw;
    anchorHeading_ = heading_;
    sinceAnchorTime_ = sinceAnchorTurn_ = 0.0f;
    agree_ = 0;
  }

  // Still: the true rate is zero, so the whole change is bias (or a step).
  // The heading is held and the change is not folded into the output.
  void holdAtRest(float change) {  // [rad]
    const float plausible = bias_.params().maxRate * sinceAnchorTime_ +
                            params_.gateSlack;  // [rad]
    if (std::fabs(change) <= plausible) {
      bias_.observeRest(change, sinceAnchorTime_);
      gyroTurn_ += change;
    } else {
      ++steps_;
      gyroTurn_ += sinceAnchorTurn_;
    }
    anchorRaw_ = wrapRadians(anchorRaw_ + change);
    anchorHeading_ = heading_;
    sinceAnchorTime_ = sinceAnchorTurn_ = 0.0f;
    agree_ = 0;
  }

  void acceptMoving(float change) {  // [rad]
    heading_ = anchorHeading_ + change - bias_.rate() * sinceAnchorTime_;
    gyroTurn_ += change;
    anchorRaw_ = wrapRadians(anchorRaw_ + change);
    anchorHeading_ = heading_;
    sinceAnchorTime_ = sinceAnchorTurn_ = 0.0f;
    agree_ = 0;
    bias_.observeMotion(time_, gyroTurn_, encoderTurn_);
  }

  // The output stays on the encoders. Only a jump that then holds steady
  // for confirmSamples becomes the new reference, and the gyro turn it
  // skipped is credited from the encoders so the bias fit sees no step.
  void rejectJump(float raw) {  // [rad]
    ++rejected_;
    const float sinceRead = wrapRadians(raw - previousRaw_);  // [rad]
    agree_ = consistent(sinceRead, sinceReadTurn_) ? agree_ + 1 : 0;
    if (agree_ < params_.confirmSamples) return;
    ++steps_;
    gyroTurn_ += sinceAnchorTurn_;
    anchor(raw);
  }

  void sampleOptical(float raw) {  // [rad]
    float dx = 0.0f, dy = 0.0f;  // [mm]
    const bool got = optical_->takeOpticalIncrement(dx, dy);
    if (!got) {
      recovered_ = 0;
      if (++noFix_ >= params_.dropoutReads && opticalUp_) opticalUp_ = false;
      return;
    }
    noFix_ = 0;
    if (atRest()) {
      baseX_ = x_;
      baseY_ = y_;
      pendingX_ = pendingY_ = pendingPath_ = 0.0f;
      return;
    }
    const float turn = wrapRadians(heading_ - raw);  // [rad]
    const float c = std::cos(turn);
    const float s = std::sin(turn);
    const float scale = params_.opticalScale;
    const float ix = scale * (c * dx - s * dy);  // [mm]
    const float iy = scale * (s * dx + c * dy);  // [mm]

    deficit_ = std::fmax(0.0f, deficit_ +
                                   (1.0f - kOpticalAllowance) *
                                       std::hypot(pendingX_, pendingY_) -
                                   std::hypot(ix, iy));
    if (deficit_ > params_.opticalFreezeDistance && opticalUp_) {
      opticalUp_ = false;
      recovered_ = 0;
    }
    const float error = std::hypot(ix - pendingX_, iy - pendingY_);  // [mm]
    const bool agrees =
        error <= params_.opticalSlack + params_.opticalFraction * pendingPath_;
    if (opticalUp_) {
      if (agrees) {
        baseX_ += ix;
        baseY_ += iy;
        rejectRun_ = 0;
      } else {
        ++rejected_;
        baseX_ += pendingX_;
        baseY_ += pendingY_;
        if (++rejectRun_ >= params_.opticalRejectLimit) {
          opticalUp_ = false;
          recovered_ = 0;
        }
      }
      x_ = baseX_;
      y_ = baseY_;
    } else {
      recovered_ = (agrees && deficit_ == 0.0f) ? recovered_ + 1 : 0;
      if (recovered_ >= params_.recoverReads) {
        opticalUp_ = true;
        rejectRun_ = 0;
      }
      baseX_ = x_;
      baseY_ = y_;
    }
    pendingX_ = pendingY_ = pendingPath_ = 0.0f;
  }

  static constexpr float kOpticalAllowance = 0.2f;  // [1]

  PoseEstimatorParams params_;
  Odometry enc_;
  GyroBiasTracker bias_;
  GyroSource* gyro_ = nullptr;
  OpticalPositionSource* optical_ = nullptr;
  bool gyroUp_ = false, opticalUp_ = false;
  bool gyroPrimed_ = false, frozenDown_ = false;

  float x_ = 0.0f, y_ = 0.0f;  // [mm]
  float heading_ = 0.0f;       // [rad]
  float time_ = 0.0f;          // [s]
  float restTime_ = 0.0f;      // [s]
  float encoderTurn_ = 0.0f;   // [rad] cumulative
  float gyroTurn_ = 0.0f;      // [rad] cumulative, steps excluded

  float anchorRaw_ = 0.0f;       // [rad] last gyro reading folded in
  float anchorHeading_ = 0.0f;   // [rad] output at that reading
  float sinceAnchorTime_ = 0.0f; // [s]
  float sinceAnchorTurn_ = 0.0f; // [rad] encoder turn
  float previousRaw_ = 0.0f;     // [rad] last fresh reading, folded in or not
  float previousRate_ = 0.0f;    // [rad/s]
  float sinceReadTurn_ = 0.0f;   // [rad] encoder turn since that reading
  float stillTurn_ = 0.0f;       // [rad] encoder turn while readings repeat

  float baseX_ = 0.0f, baseY_ = 0.0f;  // [mm] output as of the last optical take
  float pendingX_ = 0.0f, pendingY_ = 0.0f;  // [mm] encoder motion since then
  float pendingPath_ = 0.0f;                 // [mm]
  float deficit_ = 0.0f;                     // [mm]

  int silent_ = 0, noFix_ = 0, agree_ = 0, recovered_ = 0, rejectRun_ = 0;
  uint32_t rejected_ = 0, steps_ = 0;
};

}  // namespace diffDrive
