// velocity_shaper_shim.cpp -- extern "C" ctypes surface for
// src/motion/velocity_shaper.h/.cpp (test_velocity_shaper.py).
//
// Opaque handle plus free functions, the same shape every other shim
// in this directory uses (ctypes cannot call C++ methods directly) --
// mirrors emit_queue_shim.cpp's minimal one-class-instance shape rather
// than motion_engine_shim.cpp's larger multi-object Handle, since
// VelocityShaper needs no fake ports or kernel to exercise: it is a
// pure host-portable object over a MotionLimits value (see
// velocity_shaper.h's own header comment).
//
// Test scaffolding only: nothing under src/ knows this file exists.
#include "motion/motion_limits.h"
#include "motion/velocity_shaper.h"

using diffDrive::MotionLimits;
using diffDrive::VelocityShaper;

extern "C" {

void* vsNew() { return new VelocityShaper(); }
void vsFree(void* h) { delete static_cast<VelocityShaper*>(h); }
void vsReset(void* h) { static_cast<VelocityShaper*>(h)->reset(); }

// advance() takes a MotionLimits by const reference -- ctypes cannot
// build that struct on the C++ side, so this shim takes every
// MotionLimits field as its own float argument and assembles the
// struct here, in DECLARATION order (motion_limits.h).
float vsAdvance(void* h, float target, float remain, float floor, float cap,
                float dt, float accel, float decel, float jerk, float vMax,
                float omegaMax, float vFloor, float omegaFloor,
                float stopDistance, float arriveDist, float arriveYaw,
                int* arriving) {
  MotionLimits lim;
  lim.accel = accel;
  lim.decel = decel;
  lim.jerk = jerk;
  lim.vMax = vMax;
  lim.omegaMax = omegaMax;
  lim.vFloor = vFloor;
  lim.omegaFloor = omegaFloor;
  lim.stopDistance = stopDistance;
  lim.arriveDist = arriveDist;
  lim.arriveYaw = arriveYaw;

  const VelocityShaper::Step step =
      static_cast<VelocityShaper*>(h)->advance(target, remain, floor, cap,
                                                dt, lim);
  *arriving = step.arriving ? 1 : 0;
  return step.vCmd;
}

float vsVelocity(void* h) {
  return static_cast<VelocityShaper*>(h)->velocity();
}
float vsAcceleration(void* h) {
  return static_cast<VelocityShaper*>(h)->acceleration();
}

// ---- MotionLimits, exercised directly (no VelocityShaper instance
// needed) -- the "positive, else keep" setters and the two axis-unit
// conversion helpers. ----

void* mlNew() { return new MotionLimits(); }
void mlFree(void* h) { delete static_cast<MotionLimits*>(h); }

void mlSetAccel(void* h, float v) { static_cast<MotionLimits*>(h)->setAccel(v); }
void mlSetDecel(void* h, float v) { static_cast<MotionLimits*>(h)->setDecel(v); }
void mlSetJerk(void* h, float v) { static_cast<MotionLimits*>(h)->setJerk(v); }
void mlSetVMax(void* h, float v) { static_cast<MotionLimits*>(h)->setVMax(v); }
void mlSetOmegaMax(void* h, float v) {
  static_cast<MotionLimits*>(h)->setOmegaMax(v);
}
void mlSetVFloor(void* h, float v) {
  static_cast<MotionLimits*>(h)->setVFloor(v);
}
void mlSetOmegaFloor(void* h, float v) {
  static_cast<MotionLimits*>(h)->setOmegaFloor(v);
}
void mlSetStopDistance(void* h, float v) {
  static_cast<MotionLimits*>(h)->setStopDistance(v);
}
void mlSetArriveDist(void* h, float v) {
  static_cast<MotionLimits*>(h)->setArriveDist(v);
}
void mlSetArriveYaw(void* h, float v) {
  static_cast<MotionLimits*>(h)->setArriveYaw(v);
}

float mlAccel(void* h) { return static_cast<MotionLimits*>(h)->accel; }
float mlDecel(void* h) { return static_cast<MotionLimits*>(h)->decel; }
float mlJerk(void* h) { return static_cast<MotionLimits*>(h)->jerk; }
float mlVMax(void* h) { return static_cast<MotionLimits*>(h)->vMax; }
float mlOmegaMax(void* h) { return static_cast<MotionLimits*>(h)->omegaMax; }
float mlVFloor(void* h) { return static_cast<MotionLimits*>(h)->vFloor; }
float mlOmegaFloor(void* h) {
  return static_cast<MotionLimits*>(h)->omegaFloor;
}
float mlStopDistance(void* h) {
  return static_cast<MotionLimits*>(h)->stopDistance;
}
float mlArriveDist(void* h) {
  return static_cast<MotionLimits*>(h)->arriveDist;
}
float mlArriveYaw(void* h) { return static_cast<MotionLimits*>(h)->arriveYaw; }

float mlOmegaFloorAsWheelSpeed(void* h, float trackWidth) {
  return static_cast<MotionLimits*>(h)->omegaFloorAsWheelSpeed(trackWidth);
}
float mlOmegaMaxAsWheelSpeed(void* h, float trackWidth) {
  return static_cast<MotionLimits*>(h)->omegaMaxAsWheelSpeed(trackWidth);
}

}  // extern "C"
