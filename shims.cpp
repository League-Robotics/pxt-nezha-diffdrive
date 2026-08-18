// shims.cpp -- the MakeCode-facing C++ surface. Composes the DiffDrive
// kernel (its own fiber, 24 ms cadence) with two NezhaMotorPorts and the
// CODAL platform ports, and adds the two application-layer pieces the
// kernel deliberately does not contain:
//
//   - ODOMETRY: differential dead-reckoning from the kernel's Output
//     positions (the kernel is counts-native and has no chassis
//     geometry; track width and travel calibration live HERE).
//   - MOVE ENGINE: position-mode moves (distance+yaw, and goto via the
//     TS layer's arc math) as a start/update/end state machine over the
//     kernel's velocity interface. The TypeScript layer polls
//     updateMove() -- blocking and loop-style forms are both built on
//     that poll.
//
// Boundary convention: integers only. mm, mm/s, centidegrees,
// centidegrees/s; config values scaled x1000. The TS layer owns the
// cm/deg student units.
#include "pxt.h"
#include "diffdrive.h"
#include "nezha_port.h"
#include "platform_ports.h"

#include <cmath>

using namespace pxt;

namespace diffDrive {

// ---- composition ----------------------------------------------------

struct Rig {
  // tovez-measured defaults; generic kits adjust via setGeometry().
  float travelCalib = 0.7837f;   // [mm/deg] wheel travel per shaft degree
  float trackWidth = 115.0f;     // [mm]
  float countsPerMm() const { return 10.0f / travelCalib; }

  NezhaMotorPort left{2, -1};    // tovez wiring: left = M2, mirrored
  NezhaMotorPort right{1, +1};
  CodalClock clock;
  CodalSleeper sleeper;
  CodalFiberLauncher launcher;
  DiffDrive::DifferentialDrive kernel{left, right, clock, sleeper,
                                      launcher};

  // odometry [mm, rad], updated lazily from kernel Output
  float x = 0.0f, y = 0.0f, heading = 0.0f;
  float odomPosLeft = 0.0f, odomPosRight = 0.0f;  // [counts]
  bool odomPrimed = false;

  // move engine
  bool moveActive = false;
  float movePosLeft0 = 0.0f, movePosRight0 = 0.0f;  // [counts]
  float moveDistTarget = 0.0f;   // [counts] mean-axis target (signed)
  float moveYawTarget = 0.0f;    // [counts] half-differential target
  uint32_t moveDeadline = 0;     // [ms] lease-aligned backstop
};

static Rig* rig = nullptr;

static Rig& ensure() {
  if (rig == nullptr) {
    rig = new Rig();
    // Kernel defaults: the tovez bake (boot_calibration.cpp) with
    // NEUTRAL wheel gains -- a generic kit starts uncorrected.
    DiffDrive::DifferentialDrive::Config cfg;
    cfg.maxDuty = 100.0f;            // [%]
    cfg.fullDutyVelocity = 10795.0f; // [counts/s]
    cfg.kp = 0.0f;
    cfg.ki = 6.0f;                   // [1/s]
    cfg.iMax = 765.6f;               // [counts/s]
    cfg.pidMax = 1276.0f;            // [counts/s]
    cfg.vMin = 255.2f;               // [counts/s]
    cfg.posErrMax = 127.6f;          // [counts]
    cfg.biasMax = 303.7f;            // [counts/s]
    cfg.tauAdapt = 30.0f;            // [s]
    cfg.aSteady = 382.8f;            // [counts/s^2]
    cfg.stallSpeed = 191.4f;         // [counts/s]
    cfg.stallDemand = 510.4f;        // [counts/s]
    cfg.stallWindow = 500.0f;        // [ms]
    cfg.cyclePeriod = 24;            // [ms]
    rig->kernel.setConfig(cfg);
    rig->kernel.begin();   // primes encoders, arms boot zero-write
    rig->kernel.start();   // kernel fiber free-runs from here
  }
  return *rig;
}

// ---- odometry -------------------------------------------------------

static void odomUpdate(Rig& r) {
  const DiffDrive::DifferentialDrive::Output out = r.kernel.output();
  if (!r.odomPrimed) {
    r.odomPosLeft = out.positionLeft;
    r.odomPosRight = out.positionRight;
    r.odomPrimed = true;
    return;
  }
  const float cpm = r.countsPerMm();
  const float dLeft = (out.positionLeft - r.odomPosLeft) / cpm;    // [mm]
  const float dRight = (out.positionRight - r.odomPosRight) / cpm; // [mm]
  r.odomPosLeft = out.positionLeft;
  r.odomPosRight = out.positionRight;
  const float dCenter = 0.5f * (dLeft + dRight);          // [mm]
  const float dHeading = (dRight - dLeft) / r.trackWidth; // [rad]
  const float midHeading = r.heading + 0.5f * dHeading;
  r.x += dCenter * std::cos(midHeading);
  r.y += dCenter * std::sin(midHeading);
  r.heading += dHeading;
}

// ---- velocity commands ----------------------------------------------

//%
void setWheels(int left, int right) {  // [mm/s] [mm/s]
  Rig& r = ensure();
  const float cpm = r.countsPerMm();
  const float velocity = 0.5f * static_cast<float>(left + right) * cpm;
  const float twist = 0.5f * static_cast<float>(right - left) * cpm;
  r.kernel.drive(velocity, twist,
                 DiffDrive::DifferentialDrive::kLeaseMax);
}

//%
void driveTwist(int speed, int yawRate) {  // [mm/s] [cdeg/s]
  Rig& r = ensure();
  const float cpm = r.countsPerMm();
  const float yawRad =
      static_cast<float>(yawRate) * 0.01f * 3.14159265f / 180.0f;
  const float twist = yawRad * 0.5f * r.trackWidth * cpm;  // [counts/s]
  r.kernel.drive(static_cast<float>(speed) * cpm, twist,
                 DiffDrive::DifferentialDrive::kLeaseMax);
}

// ---- move engine ----------------------------------------------------

//%
void startMove(int distance, int yaw, int speed, int yawRate) {
  // [mm] [cdeg] [mm/s] [cdeg/s]
  Rig& r = ensure();
  odomUpdate(r);
  const float cpm = r.countsPerMm();
  const DiffDrive::DifferentialDrive::Output out = r.kernel.output();
  r.movePosLeft0 = out.positionLeft;
  r.movePosRight0 = out.positionRight;
  r.moveDistTarget = static_cast<float>(distance) * cpm;  // [counts]
  const float yawRad =
      static_cast<float>(yaw) * 0.01f * 3.14159265f / 180.0f;
  r.moveYawTarget = yawRad * 0.5f * r.trackWidth * cpm;   // [counts]

  const float speedCounts =
      static_cast<float>(speed > 0 ? speed : 1) * cpm;    // [counts/s]
  const float yawRadPerS =
      static_cast<float>(yawRate > 0 ? yawRate : 1) * 0.01f *
      3.14159265f / 180.0f;
  const float twistCounts = yawRadPerS * 0.5f * r.trackWidth * cpm;

  // One duration covers both axes -> simultaneous arc completion.
  float duration = 0.0f;  // [s]
  if (r.moveDistTarget != 0.0f)
    duration = std::fabs(r.moveDistTarget) / speedCounts;
  if (r.moveYawTarget != 0.0f) {
    const float yawDuration = std::fabs(r.moveYawTarget) / twistCounts;
    if (yawDuration > duration) duration = yawDuration;
  }
  if (duration <= 0.0f) return;  // nothing to do

  const float velocity = r.moveDistTarget / duration;  // [counts/s]
  const float twist = r.moveYawTarget / duration;      // [counts/s]
  const uint32_t lease =
      static_cast<uint32_t>(duration * 1000.0f) + 500u;  // [ms] backstop
  r.kernel.drive(velocity, twist, lease);
  r.moveActive = true;
  r.moveDeadline = static_cast<uint32_t>(
      r.clock.nowMicros() / 1000ull) + lease;
}

//%
bool updateMove() {
  if (rig == nullptr) return false;
  Rig& r = *rig;
  if (!r.moveActive) return false;
  odomUpdate(r);
  const DiffDrive::DifferentialDrive::Output out = r.kernel.output();
  const float dLeft = out.positionLeft - r.movePosLeft0;    // [counts]
  const float dRight = out.positionRight - r.movePosRight0; // [counts]
  const float meanProgress = 0.5f * (dLeft + dRight);
  const float diffProgress = 0.5f * (dRight - dLeft);

  const float margin = 25.0f;  // [counts] ~2 mm decel allowance
  bool distDone = true;
  if (r.moveDistTarget != 0.0f) {
    distDone = std::fabs(meanProgress) >=
               std::fabs(r.moveDistTarget) - margin;
  }
  bool yawDone = true;
  if (r.moveYawTarget != 0.0f) {
    yawDone = std::fabs(diffProgress) >=
              std::fabs(r.moveYawTarget) - margin;
  }
  const uint32_t nowMs =
      static_cast<uint32_t>(r.clock.nowMicros() / 1000ull);
  const bool expired = static_cast<int32_t>(nowMs - r.moveDeadline) >= 0;

  if ((distDone && yawDone) || expired || out.stallHalted) {
    r.kernel.neutral();
    r.moveActive = false;
    return false;
  }
  return true;
}

//%
bool moving() { return rig != nullptr && rig->moveActive; }

//%
int progress() {  // [0..1000]
  if (rig == nullptr || !rig->moveActive) return 1000;
  Rig& r = *rig;
  const DiffDrive::DifferentialDrive::Output out = r.kernel.output();
  const float dLeft = out.positionLeft - r.movePosLeft0;
  const float dRight = out.positionRight - r.movePosRight0;
  float fraction = 1.0f;
  if (r.moveDistTarget != 0.0f) {
    const float f = std::fabs(0.5f * (dLeft + dRight)) /
                    std::fabs(r.moveDistTarget);
    if (f < fraction) fraction = f;
  }
  if (r.moveYawTarget != 0.0f) {
    const float f = std::fabs(0.5f * (dRight - dLeft)) /
                    std::fabs(r.moveYawTarget);
    if (f < fraction) fraction = f;
  }
  if (fraction < 0.0f) fraction = 0.0f;
  if (fraction > 1.0f) fraction = 1.0f;
  return static_cast<int>(fraction * 1000.0f);
}

//%
void endMove() {
  if (rig == nullptr) return;
  if (rig->moveActive) {
    rig->kernel.neutral();
    rig->moveActive = false;
  }
}

// ---- stopping -------------------------------------------------------

//%
void stopAll() {
  Rig& r = ensure();
  r.moveActive = false;
  r.kernel.neutral();
}

//%
void estopAll() {
  Rig& r = ensure();
  r.moveActive = false;
  r.kernel.estop();
  r.kernel.emergencyStopMotors();
}

//%
void estopClear() { ensure().kernel.estopClear(); }

// ---- pose -----------------------------------------------------------

//%
int poseX() {  // [mm]
  Rig& r = ensure();
  odomUpdate(r);
  return static_cast<int>(std::lround(r.x));
}

//%
int poseY() {  // [mm]
  Rig& r = ensure();
  odomUpdate(r);
  return static_cast<int>(std::lround(r.y));
}

//%
int poseHeading() {  // [cdeg]
  Rig& r = ensure();
  odomUpdate(r);
  return static_cast<int>(
      std::lround(r.heading * 180.0f / 3.14159265f * 100.0f));
}

//%
void resetPose() {
  Rig& r = ensure();
  odomUpdate(r);  // consume any pending deltas first
  r.x = 0.0f;
  r.y = 0.0f;
  r.heading = 0.0f;
}

// ---- configuration --------------------------------------------------

//%
void setGeometry(int trackWidth, int calib) {  // [0.1 mm] [1e-4 mm/deg]
  Rig& r = ensure();
  if (trackWidth > 0) r.trackWidth = static_cast<float>(trackWidth) * 0.1f;
  if (calib > 0) r.travelCalib = static_cast<float>(calib) * 1e-4f;
}

//%
void setKernelValue(int field, int value) {  // [x1000 scaled]
  Rig& r = ensure();
  const float v = static_cast<float>(value) * 0.001f;
  DiffDrive::DifferentialDrive& k = r.kernel;
  switch (field) {
    case 0: k.setMaxDuty(v); break;
    case 1: k.setFullDutyVelocity(v); break;
    case 2: k.setKp(v); break;
    case 3: k.setKi(v); break;
    case 4: k.setIMax(v); break;
    case 5: k.setKaff(v); break;
    case 6: k.setPidMax(v); break;
    case 7: k.setTwistHoldGain(v); break;
    case 8: k.setSpeedFloor(v); break;
    case 9: k.setPositionErrorMax(v); break;
    case 10: k.setStall(v, k.config().stallDemand,
                        k.config().stallWindow); break;
    case 11: k.setStall(k.config().stallSpeed, v,
                        k.config().stallWindow); break;
    case 12: k.setStall(k.config().stallSpeed, k.config().stallDemand,
                        v); break;
    case 13: k.setLambdaEnabled(v != 0.0f); break;
    case 14: k.setCrawlPulse(v); break;
    default: break;
  }
}

}  // namespace diffDrive
