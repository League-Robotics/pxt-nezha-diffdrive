// odometry_shim.cpp -- extern "C" ctypes surface for
// src/motion/odometry.h. Odometry is stateful (a frame, a wheel
// baseline, a rebase-epoch memory carried across calls), so this shim
// follows the handle-plus-free-functions shape (tests/host/DESIGN.md
// S2) rather than heading_wrap_shim.cpp's plain-function shape -- the
// same convention kernel_shim.cpp/motion_engine_shim.cpp use ("odoXxx",
// mirroring their "kdXxx"/"meXxx" prefixes).
//
// Odometry reads its geometry (countsPerMm/effectiveTrackWidth) from a
// MotionEngine, and a MotionEngine needs a kernel, so the handle bundles
// the same FakeMotor x2/FakeClock/FakeSleeper/FakeFiberLauncher + real
// kernel + real engine stack motion_engine_shim.cpp already uses. The
// kernel is never step()'d here: odoUpdate() below synthesizes the
// DiffDrive::DifferentialDrive::Output directly, which is the whole
// point of Odometry::update() taking an Output rather than holding a
// kernel -- a test can script an exact wheel-count path with no encoder,
// no clock and no control loop in the link.
//
// Test scaffolding only: nothing under src/ knows this file exists.
#include <cstdint>

#include "core/diffdrive.h"
#include "fake_ports.h"
#include "motion/motion_engine.h"
#include "motion/odometry.h"

namespace {

struct Handle {
  FakeMotor left;
  FakeMotor right;
  FakeClock clock;
  FakeSleeper sleeper;
  FakeFiberLauncher launcher;
  DiffDrive::DifferentialDrive kernel;
  diffDrive::MotionEngine engine;
  // Declared AFTER `engine`: Odometry binds its geometry reference at
  // construction and members initialize in DECLARATION order -- the same
  // rule shims.cpp's Rig states for its own `odometry` member.
  diffDrive::Odometry odometry;

  Handle()
      : kernel(left, right, clock, sleeper, launcher),
        engine(kernel, clock),
        odometry(engine) {}
};

}  // namespace

extern "C" {

// ---- lifecycle -------------------------------------------------------

void* odoCreate() { return new Handle(); }
void odoDestroy(void* handle) { delete static_cast<Handle*>(handle); }

// ---- geometry (the two numbers Odometry integrates with, set through
// the engine that owns them -- countsPerMm() == 10 / travelCalib,
// effectiveTrackWidth() == trackWidth / rotationalSlip) ----------------

void odoSetGeometry(void* handle, float travelCalib, float trackWidth,
                    float rotationalSlip) {  // [mm/deg] [mm] [1]
  Handle* h = static_cast<Handle*>(handle);
  h->engine.setTravelCalib(travelCalib);
  h->engine.setTrackWidth(trackWidth);
  h->engine.setRotationalSlip(rotationalSlip);
}

float odoCountsPerMm(void* handle) {  // [counts/mm]
  return static_cast<Handle*>(handle)->engine.countsPerMm();
}
float odoEffectiveTrackWidth(void* handle) {  // [mm]
  return static_cast<Handle*>(handle)->engine.effectiveTrackWidth();
}

// ---- the integration under test ---------------------------------------

// One synthesized kernel Output folded into the frame. `positionLeft`/
// `positionRight` are [counts]; the two epochs are the kernel's own
// rebase counters (diffdrive.h) -- bump either to script a SET rebase.
void odoUpdate(void* handle, float positionLeft, float positionRight,
               uint32_t positionEpochLeft, uint32_t positionEpochRight) {
  DiffDrive::DifferentialDrive::Output out;
  out.positionLeft = positionLeft;
  out.positionRight = positionRight;
  out.positionEpochLeft = positionEpochLeft;
  out.positionEpochRight = positionEpochRight;
  static_cast<Handle*>(handle)->odometry.update(out);
}

void odoReset(void* handle) { static_cast<Handle*>(handle)->odometry.reset(); }

void odoSeed(void* handle, float x, float y, float heading) {
  // [mm] [mm] [rad]
  static_cast<Handle*>(handle)->odometry.seed(x, y, heading);
}

// ---- PoseSource reads --------------------------------------------------

float odoX(void* handle) { return static_cast<Handle*>(handle)->odometry.x(); }
float odoY(void* handle) { return static_cast<Handle*>(handle)->odometry.y(); }
float odoHeading(void* handle) {
  return static_cast<Handle*>(handle)->odometry.heading();
}

// Reads through the PoseSource base-class reference specifically -- proof
// Odometry IS the port (a virtual dispatch), not merely shaped like it.
float odoPoseSourceX(void* handle) {
  const diffDrive::PoseSource& pose = static_cast<Handle*>(handle)->odometry;
  return pose.x();
}

}  // extern "C"
