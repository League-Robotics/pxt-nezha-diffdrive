// pose_estimator_shim.cpp -- extern "C" ctypes surface for
// src/motion/pose_estimator.h. Handle-plus-free-functions shape, "peXxx"
// prefix (tests/host/DESIGN.md S2).
//
// The handle carries a true robot: peDrive() moves two wheels, derives the
// encoder Output the kernel would publish, advances SimGyro and SimOptical
// from the same truth, and ticks the estimator. peOutput() instead feeds a
// raw scripted Output (no sensors) for the Odometry golden comparison.
//
// peReplay() is the third drive path: recorded encoder counts and gyro
// heading, plus an optical increment, fed straight in (no true robot).
//
// Test scaffolding only: nothing under src/ knows this file exists.
#include <cmath>
#include <cstdint>
#include <new>

#include "core/diffdrive.h"
#include "fake_ports.h"
#include "motion/motion_engine.h"
#include "motion/pose_estimator.h"
#include "sim_gyro.h"
#include "sim_optical.h"

namespace {

class ScriptedOptical : public diffDrive::OpticalPositionSource {
 public:
  void add(float dx, float dy) { add(dx, dy, dx, dy); }
  void add(float dx, float dy, float rawDx, float rawDy) {
    pendingX_ += dx;
    pendingY_ += dy;
    pendingRawX_ += rawDx;
    pendingRawY_ += rawDy;
  }
  bool opticalPresent() const override { return true; }
  bool opticalValid() const override { return true; }
  bool takeOpticalIncrement(float& dx, float& dy, float& rawDx,
                            float& rawDy) override {
    dx = pendingX_;
    dy = pendingY_;
    rawDx = pendingRawX_;
    rawDy = pendingRawY_;
    pendingX_ = pendingY_ = pendingRawX_ = pendingRawY_ = 0.0f;
    return true;
  }

 private:
  float pendingX_ = 0.0f, pendingY_ = 0.0f;  // [mm]
  float pendingRawX_ = 0.0f, pendingRawY_ = 0.0f;  // [mm]
};

struct Handle {
  FakeMotor left;
  FakeMotor right;
  FakeClock clock;
  FakeSleeper sleeper;
  FakeFiberLauncher launcher;
  DiffDrive::DifferentialDrive kernel;
  diffDrive::MotionEngine engine;
  SimGyro gyro;
  SimOptical optical;
  ScriptedOptical scripted;
  diffDrive::PoseEstimator estimator;

  int sampleEvery = 1;  // peRunMove reads the sensors every Nth tick
  uint32_t tick = 0;
  float trackError = 1.0f;  // true track width / the engine's
  float posLeft = 0.0f, posRight = 0.0f;  // [counts]
  float truthX = 0.0f, truthY = 0.0f, truthHeading = 0.0f;  // [mm] [rad]

  Handle()
      : kernel(left, right, clock, sleeper, launcher),
        engine(kernel, clock),
        estimator(engine) {
    gyro.setWrap(true);
  }
};

Handle* as(void* handle) { return static_cast<Handle*>(handle); }

}  // namespace

extern "C" {

void* peCreate() { return new Handle(); }
void peDestroy(void* handle) { delete as(handle); }

void peSetGeometry(void* handle, float travelCalib, float trackWidth,
                   float rotationalSlip) {  // [mm/deg] [mm] [1]
  Handle* h = as(handle);
  h->engine.setTravelCalib(travelCalib);
  h->engine.setTrackWidth(trackWidth);
  h->engine.setRotationalSlip(rotationalSlip);
}
void peSetTrackError(void* handle, float ratio) { as(handle)->trackError = ratio; }

// 0 optical, 1 gyro-only, 2 encoders-only
void peAttach(void* handle, int config) {
  Handle* h = as(handle);
  h->estimator.attachSensors(&h->gyro, &h->optical,
                             static_cast<diffDrive::SensorConfig>(config));
}

void peAttachScripted(void* handle, int config) {
  Handle* h = as(handle);
  h->estimator.attachSensors(&h->gyro, &h->scripted,
                             static_cast<diffDrive::SensorConfig>(config));
}

void peGyroBias(void* handle, float v) { as(handle)->gyro.setBias(v); }
void peGyroWander(void* handle, float a, float p) { as(handle)->gyro.setWander(a, p); }
void peGyroNoise(void* handle, float v) { as(handle)->gyro.setNoise(v); }
void peGyroSeed(void* handle, uint32_t v) { as(handle)->gyro.setSeed(v); }
void peGyroDropout(void* handle, int on) { as(handle)->gyro.setDropout(on != 0); }
void peGyroFreeze(void* handle, int on) { as(handle)->gyro.setFreeze(on != 0); }
void peGyroReadFail(void* handle, int on) { as(handle)->gyro.setReadFail(on != 0); }
void peGyroStep(void* handle, float delta) { as(handle)->gyro.stepHeading(delta); }
void peGyroGlitch(void* handle, float offset) { as(handle)->gyro.setGlitch(offset); }
void peGyroLatency(void* handle, float seconds) { as(handle)->gyro.setLatency(seconds); }

// Rebuilds the estimator with a different maxPlausibleRate [rad/s]; 0 makes
// every in-motion disagreement a glitch, which is the pre-ticket-012 gate.
// Call before peAttach().
void peSetMaxPlausibleRate(void* handle, float rate) {
  Handle* h = as(handle);
  diffDrive::PoseEstimatorParams params;
  params.maxPlausibleRate = rate;
  h->estimator.~PoseEstimator();
  new (&h->estimator) diffDrive::PoseEstimator(h->engine, params);
}

void peOpticalScale(void* handle, float v) { as(handle)->optical.setScale(v); }
void peOpticalFreeze(void* handle, int on) { as(handle)->optical.setFreeze(on != 0); }
void peOpticalDropout(void* handle, int on) { as(handle)->optical.setDropout(on != 0); }
void peOpticalJump(void* handle, float dx, float dy) { as(handle)->optical.jump(dx, dy); }

// Wheel speeds [mm/s] held for dt [s].
void peDrive(void* handle, float dt, float speedLeft, float speedRight,
             int sampleSensors) {
  Handle* h = as(handle);
  const float cpm = h->engine.countsPerMm();
  const float dLeft = speedLeft * dt;    // [mm]
  const float dRight = speedRight * dt;  // [mm]
  h->posLeft += dLeft * cpm;
  h->posRight += dRight * cpm;
  const float dCentre = 0.5f * (dLeft + dRight);
  const float dHeading =
      (dRight - dLeft) / (h->engine.effectiveTrackWidth() * h->trackError);
  const float mid = h->truthHeading + 0.5f * dHeading;
  const float dx = dCentre * std::cos(mid);
  const float dy = dCentre * std::sin(mid);
  h->truthX += dx;
  h->truthY += dy;
  h->truthHeading += dHeading;
  h->gyro.advance(dt, dHeading / dt);
  h->optical.advance(dx, dy, h->truthHeading, h->gyro.chipHeading());

  DiffDrive::DifferentialDrive::Output out;
  out.positionLeft = h->posLeft;
  out.positionRight = h->posRight;
  h->estimator.update(out, dt, sampleSensors != 0);
}

// A hand moves the robot with the wheels still: it translates at (vx, vy)
// [mm/s] and turns at omega [rad/s] for dt [s]. Truth moves, the sensors see
// it, the encoders do not.
void peHand(void* handle, float dt, float vx, float vy, float omega,
            int sampleSensors) {
  Handle* h = as(handle);
  const float dHeading = omega * dt;
  const float mid = h->truthHeading + 0.5f * dHeading;
  const float dx = (vx * std::cos(mid) - vy * std::sin(mid)) * dt;
  const float dy = (vx * std::sin(mid) + vy * std::cos(mid)) * dt;
  h->truthX += dx;
  h->truthY += dy;
  h->truthHeading += dHeading;
  h->gyro.advance(dt, omega);
  h->optical.advance(dx, dy, h->truthHeading, h->gyro.chipHeading());
  DiffDrive::DifferentialDrive::Output out;
  out.positionLeft = h->posLeft;
  out.positionRight = h->posRight;
  h->estimator.update(out, dt, sampleSensors != 0);
}

// A scripted Output, no sensors read.
void peOutput(void* handle, float dt, float positionLeft, float positionRight,
              uint32_t epochLeft, uint32_t epochRight) {
  DiffDrive::DifferentialDrive::Output out;
  out.positionLeft = positionLeft;
  out.positionRight = positionRight;
  out.positionEpochLeft = epochLeft;
  out.positionEpochRight = epochRight;
  as(handle)->estimator.update(out, dt, false);
}

// Recorded wheel counts, the chip heading [rad, unwrapped] it would latch,
// and the optical centre movement [mm] since the previous call.
void peReplay(void* handle, float dt, float positionLeft, float positionRight,
              float gyroHeading, float opticalDx, float opticalDy,
              int sampleSensors) {
  Handle* h = as(handle);
  h->gyro.stepHeading(gyroHeading - h->gyro.chipHeading());
  h->scripted.add(opticalDx, opticalDy);
  DiffDrive::DifferentialDrive::Output out;
  out.positionLeft = positionLeft;
  out.positionRight = positionRight;
  h->estimator.update(out, dt, sampleSensors != 0);
}

// As peReplay(), with the sensor's raw track (lever arm not applied) too.
void peReplayRaw(void* handle, float dt, float positionLeft, float positionRight,
                 float gyroHeading, float opticalDx, float opticalDy,
                 float rawDx, float rawDy, int sampleSensors) {
  Handle* h = as(handle);
  h->gyro.stepHeading(gyroHeading - h->gyro.chipHeading());
  h->scripted.add(opticalDx, opticalDy, rawDx, rawDy);
  DiffDrive::DifferentialDrive::Output out;
  out.positionLeft = positionLeft;
  out.positionRight = positionRight;
  h->estimator.update(out, dt, sampleSensors != 0);
}

void peSeed(void* handle, float x, float y, float heading) {
  as(handle)->estimator.seed(x, y, heading);
}
void peReset(void* handle) { as(handle)->estimator.reset(); }
void peReprime(void* handle) { as(handle)->estimator.reprime(); }

float peX(void* handle) { return as(handle)->estimator.x(); }
float peY(void* handle) { return as(handle)->estimator.y(); }
float peHeading(void* handle) { return as(handle)->estimator.heading(); }
float pePoseSourceX(void* handle) {
  const diffDrive::PoseSource& pose = as(handle)->estimator;
  return pose.x();
}
int peConfig(void* handle) {
  return static_cast<int>(as(handle)->estimator.config());
}
int peAtRest(void* handle) { return as(handle)->estimator.atRest() ? 1 : 0; }
float peBiasRate(void* handle) { return as(handle)->estimator.biasRate(); }
uint32_t peRejected(void* handle) { return as(handle)->estimator.rejectedCount(); }
uint32_t peSteps(void* handle) { return as(handle)->estimator.stepCount(); }
uint32_t peDisturbs(void* handle) { return as(handle)->estimator.disturbCount(); }
int peDisturbed(void* handle) { return as(handle)->estimator.disturbed() ? 1 : 0; }

float peTruthX(void* handle) { return as(handle)->truthX; }
float peTruthY(void* handle) { return as(handle)->truthY; }
float peTruthHeading(void* handle) { return as(handle)->truthHeading; }
float peTrueBias(void* handle) { return as(handle)->gyro.bias(); }

void peBeginKernel(void* handle, float maxDuty, float fullDutyVelocity) {
  Handle* h = as(handle);
  h->kernel.setMaxDuty(maxDuty);
  h->kernel.setFullDutyVelocity(fullDutyVelocity);
  h->kernel.begin();
}

void peSetLimits(void* handle, float accel, float decel, float vMax,
                 float omegaMax) {  // [mm/s^2] [mm/s^2] [mm/s] [deg/s]
  diffDrive::MotionLimits& lim = as(handle)->engine.limits();
  lim.setAccel(accel);
  lim.setDecel(decel);
  lim.setVMax(vMax);
  lim.setOmegaMax(omegaMax);
}

void peGoToW(void* handle, float x, float y, float speed, float arrive,
             uint32_t timeoutMs) {
  Handle* h = as(handle);
  h->engine.goToW(h->estimator, x, y, speed, arrive, timeoutMs);
}

// Plays the engine against the true robot until its move ends: wheel
// duty becomes wheel speed, which peDrive() integrates into truth, the
// encoders and the estimator. Returns the ticks run; equal to maxTicks
// means the move never ended.
uint32_t peRunMove(void* handle, float fullDutyVelocity, uint32_t periodMs,
                   uint32_t maxTicks) {
  Handle* h = as(handle);
  const float dt = static_cast<float>(periodMs) / 1000.0f;
  uint32_t ticks = 0;
  for (; ticks < maxTicks && h->engine.isMoveActive(); ++ticks) {
    const float cpm = h->engine.countsPerMm();
    const float speedLeft = h->left.appliedDuty() * fullDutyVelocity / cpm;
    const float speedRight = h->right.appliedDuty() * fullDutyVelocity / cpm;
    peDrive(handle, dt, speedLeft, speedRight,
            h->tick++ % static_cast<uint32_t>(h->sampleEvery) == 0 ? 1 : 0);
    h->left.nextPositionValue = h->posLeft;
    h->right.nextPositionValue = h->posRight;
    h->clock.nowUs += static_cast<uint64_t>(periodMs) * 1000ull;
    h->left.nextSampleTimeUs = h->right.nextSampleTimeUs = h->clock.nowUs;
    h->kernel.step();
    h->engine.service();
  }
  return ticks;
}

void peSetOmegaFloor(void* handle, float floor) {  // [deg/s]
  as(handle)->engine.limits().setOmegaFloor(floor);
}
void peSetVFloor(void* handle, float floor) {  // [mm/s]
  as(handle)->engine.limits().setVFloor(floor);
}
void peSetSampleEvery(void* handle, int every) { as(handle)->sampleEvery = every; }

void peSetPivotClosure(void* handle, int enabled, uint32_t dwellMs,
                       float deadbandDeg, float maxCorrectionDeg, float speed,
                       int maxCorrections, uint32_t timeoutMs) {
  diffDrive::PivotClosure& c = as(handle)->engine.pivotClosure();
  c.enabled = enabled != 0;
  c.dwell = dwellMs;
  c.deadband = deadbandDeg;
  c.maxCorrection = maxCorrectionDeg;
  c.speed = speed;
  c.maxCorrections = maxCorrections;
  c.timeout = timeoutMs;
}
int pePivotCorrections(void* handle) {
  return as(handle)->engine.lastPivotCorrections();
}
float pePivotResidual(void* handle) { return as(handle)->engine.lastPivotResidual(); }
int pePivotTimedOut(void* handle) {
  return as(handle)->engine.lastPivotClosureTimedOut() ? 1 : 0;
}
void peSetSteering(void* handle, int enabled, float lookahead, float gain,
                   float maxRateDeg, float maxShare) {
  diffDrive::StraightSteering& c = as(handle)->engine.straightSteering();
  c.enabled = enabled != 0;
  c.lookahead = lookahead;
  c.gain = gain;
  c.maxRate = maxRateDeg;
  c.maxShare = maxShare;
}
void peSetResidualTrim(void* handle, int enabled, float band, float deadband,
                       uint32_t dwellMs, int maxTrims, uint32_t timeoutMs) {
  diffDrive::ResidualTrim& c = as(handle)->engine.residualTrim();
  c.enabled = enabled != 0;
  c.band = band;
  c.deadband = deadband;
  c.dwell = dwellMs;
  c.maxTrims = maxTrims;
  c.timeout = timeoutMs;
}
int peTrimCount(void* handle) { return as(handle)->engine.lastTrimCount(); }
float peTrimResidual(void* handle) { return as(handle)->engine.lastTrimResidual(); }
int peTrimTimedOut(void* handle) {
  return as(handle)->engine.lastTrimTimedOut() ? 1 : 0;
}
int peMoveActive(void* handle) { return as(handle)->engine.isMoveActive() ? 1 : 0; }

int peEndedByWrongWay(void* handle) {
  return as(handle)->engine.lastSegmentEndedByWrongWay() ? 1 : 0;
}
uint32_t peWrongWayCount(void* handle) {
  return as(handle)->engine.wrongWayCount();
}

}  // extern "C"
