// sim_cutebot_robot_shim.cpp -- extern "C" ctypes surface for the WHOLE
// robot stack on the host, Cutebot Pro board: the real
// `CutebotDevice`/`CutebotMotorPort` pair, `CutebotTapAdapter` and
// `CutebotActuationPolicy` (src/platform/cutebot_port.h/.cpp,
// cutebot_actuation_policy.h/.cpp) over a simulated 0x10 slave
// (sim_cutebot_bus.h), under the real kernel, `MotionEngine` and
// `Odometry` -- the Cutebot analogue of sim_robot_shim.cpp, foretold by
// that file's own sibling `cutebot_port_shim.cpp`'s header comment
// ("the way sim_tour.py sits beside sim_robot_shim.cpp today").
//
// WHY A SEPARATE SHIM FROM cutebot_port_shim.cpp/cutebot_hybrid_shim.cpp.
// Those two exercise CutebotDevice/CutebotMotorPort DIRECTLY, with no
// kernel in the link, because their job is the port's/policy's own
// correctness in isolation. This shim's job is a TOUR: the real
// `DifferentialDrive` kernel driving both ports through `MotionEngine`,
// exactly the composition `board_cutebot.cpp`'s own `CutebotBoard`
// singleton assembles for the target (device, two ports, one
// `CutebotTapAdapter` bound to the same pair, installed on the engine
// via `setWheelCommandTap()` the same way `shims.cpp`'s `ensure()`
// installs `boardWheelCommandTap()`) -- so what runs here is what would
// run on a real Cutebot build, minus CODAL. See sim_robot_shim.cpp's
// own header for why this goes below `DiffDrive::Motor` rather than
// substituting `FakeMotor` above it: only at this layer does a policy
// bug (an ineligible pair handed to the onboard loop, a stuck handoff)
// show up as a tour that fails to close, rather than as a unit test
// someone forgot to write.
//
// WHAT THIS CANNOT DO. Same caveat as sim_robot_shim.cpp, sharper here:
// `tau`, `breakaway` and `dutyVelMax` are UNVERIFIED placeholders (see
// sim_tour.py's own module docstring and SimCutebotRobot's) -- no
// Cutebot Pro has been fitted yet, so there is nothing to fit them to.
// This shim proves MECHANISM (does the hybrid policy hand off, does a
// tour still close under it), never a VALUE for any specific robot.
#include <cmath>
#include <cstdint>

#include "core/diffdrive.h"
#include "motion/motion_engine.h"
#include "motion/odometry.h"
#include "platform/cutebot_port.h"
#include "sim_cutebot_bus.h"

// See cutebot_port_shim.cpp's own comment on this symbol: the real
// definition lives in the pxt-bound vfp_guard.cpp; there are no fibers
// here and the simulated bus answers instantly, so this is a no-op.
namespace diffDrive {
void vfpSafeSleep(uint32_t) {}
}  // namespace diffDrive

namespace {

// The kernel's non-motor collaborators -- duplicated from
// sim_robot_shim.cpp rather than shared, for the same reason that file
// gives: this keeps the shim's dependency list to `src/` plus its own
// bus, matching `fake_ports.h`'s trivial three but driven by time this
// harness sets directly.
class SimClock final : public DiffDrive::Clock {
 public:
  uint64_t nowMicros() const override { return now_; }
  void setNow(uint64_t us) { now_ = us; }
 private:
  uint64_t now_ = 0;
};

class SimSleeper final : public DiffDrive::Sleeper {
 public:
  void sleepMillis(uint32_t) override {}
  void yield() override {}
};

class SimFiberLauncher final : public DiffDrive::FiberLauncher {
 public:
  void launch(void (*)(void*), void*) override {}
};

struct Handle {
  HostSim::SimCutebotBus bus;
  diffDrive::CutebotDevice device;
  diffDrive::CutebotMotorPort left;
  diffDrive::CutebotMotorPort right;
  diffDrive::CutebotTapAdapter tap;
  SimClock clock;
  SimSleeper sleeper;
  SimFiberLauncher launcher;
  DiffDrive::DifferentialDrive kernel;
  diffDrive::MotionEngine engine;
  diffDrive::Odometry odometry;

  // Ground-truth pose, integrated from the ports' own reported
  // positions (already side/sign-corrected) -- same approach
  // sim_robot_shim.cpp settled on after trying a bus-side read first:
  // reading the ports directly needs no PORT -> SIDE remapping.
  double x = 0.0, y = 0.0, h = 0.0;    // [mm] [mm] [rad]
  double prevGround1 = 0.0, prevGround2 = 0.0;  // [counts]
  uint64_t tickUs = 0;

  // Hybrid-actuation bookkeeping for sim_tour.py's own reporting: the
  // bus's onboardActive() flips exactly when a shipped frame's TYPE
  // changes (cutebot_port.cpp's serviceCycle()/shipFrame()/
  // writeOnboardFrame() -- a 0x10 write always clears it, a 0x80 write
  // always sets it), so watching it once per control cycle counts
  // engage/release transitions with no separate hook into the policy.
  bool prevOnboardActive = false;
  uint32_t engageCount = 0;
  uint32_t releaseCount = 0;

  Handle(float tau, float breakaway, float dutyVelMax,
         int8_t leftSign, int8_t rightSign)
      : bus(tau, breakaway, dutyVelMax),
        device(bus),
        left(device, 0, leftSign),
        right(device, 1, rightSign),
        tap(device, left, right),
        kernel(left, right, clock, sleeper, launcher),
        engine(kernel, clock),
        odometry(engine) {
    engine.setWheelCommandTap(&tap);
  }
};

}  // namespace

extern "C" {

// ---- lifecycle -----------------------------------------------------------

void* scCreate(float tau, float breakaway, float dutyVelMax,
               int leftSign, int rightSign) {
  return new Handle(tau, breakaway, dutyVelMax,
                    static_cast<int8_t>(leftSign),
                    static_cast<int8_t>(rightSign));
}

void scDestroy(void* handle) { delete static_cast<Handle*>(handle); }

int scBegin(void* handle) {
  Handle* h = static_cast<Handle*>(handle);
  return static_cast<int>(h->kernel.begin());
}

// ---- kernel / engine configuration (same shape as sim_robot_shim.cpp) ----

void scSetKernelConfig(void* handle, float maxDuty, float fullDutyVelocity,
                       float kp, float ki, float iMax, float kaff,
                       float pidMax, float twistHoldGain) {
  Handle* h = static_cast<Handle*>(handle);
  h->kernel.setMaxDuty(maxDuty)
      .setFullDutyVelocity(fullDutyVelocity)
      .setKp(kp)
      .setKi(ki)
      .setIMax(iMax)
      .setKaff(kaff)
      .setPidMax(pidMax)
      .setTwistHoldGain(twistHoldGain);
}

void scSetGeometry(void* handle, float trackWidth, float travelCalib,
                   float rotationalSlip) {
  Handle* h = static_cast<Handle*>(handle);
  h->engine.setTrackWidth(trackWidth);
  h->engine.setTravelCalib(travelCalib);
  h->engine.setRotationalSlip(rotationalSlip);
}

void scSetLimits(void* handle, float accel, float decel, float vFloor,
                 float omegaFloor, float lag, float stopDistance) {
  Handle* h = static_cast<Handle*>(handle);
  diffDrive::MotionLimits& l = h->engine.limits();
  l.setAccel(accel);
  l.setDecel(decel);
  l.setVFloor(vFloor);
  l.setOmegaFloor(omegaFloor);
  l.setLag(lag);
  l.setStopDistance(stopDistance);
}

void scSetJerk(void* handle, float jerk) {
  static_cast<Handle*>(handle)->engine.limits().setJerk(jerk);
}

// ---- hybrid actuation config (onboard_pid / onboard_floor) --------------

int scSetOnboardMode(void* handle, int mode) {
  return static_cast<Handle*>(handle)->device.setOnboardMode(mode) ? 1 : 0;
}
int scOnboardMode(void* handle) {
  return static_cast<Handle*>(handle)->device.onboardMode();
}
int scSetOnboardFloor(void* handle, float floorMmS) {
  return static_cast<Handle*>(handle)->device.setOnboardFloor(floorMmS) ? 1 : 0;
}
float scOnboardFloor(void* handle) {
  return static_cast<Handle*>(handle)->device.onboardFloor();
}

// ---- commands --------------------------------------------------------

void scMoveX(void* handle, float distance, float rotation, float cruise,
             uint32_t timeoutMs) {
  static_cast<Handle*>(handle)->engine.moveX(distance, rotation, cruise,
                                             timeoutMs);
}

void scStop(void* handle) { static_cast<Handle*>(handle)->engine.endMove(); }

// ---- the tick ----------------------------------------------------------

// One simulated control cycle -- same order as sim_robot_shim.cpp's
// srTick(): advance the clock, let kernel.step() run each port's
// requestSample()/tick() strictly interleaved (kernel.step() owns that
// ordering; see srTick()'s own comment for why an independent
// non-interleaved pass fabricates heading error), service the move
// (this is where the tap fires, staging the NEXT cycle's onboard
// setpoint), then advance the simulated physics.
//
// Returns 1 while the move is still active.
int scTick(void* handle, uint32_t periodUs) {
  Handle* h = static_cast<Handle*>(handle);
  h->tickUs += periodUs;
  h->clock.setNow(h->tickUs);

  h->kernel.step();
  const int active = h->engine.service() ? 1 : 0;

  const float dt = static_cast<float>(periodUs) / 1000000.0f;
  h->bus.step(dt);

  // Handoff bookkeeping: onboardActive() reflects whichever frame TYPE
  // kernel.step()'s own port tick()s just shipped via
  // CutebotDevice::serviceCycle() -- see this file's Handle comment.
  const bool onboardNow = h->bus.onboardActive();
  if (onboardNow != h->prevOnboardActive) {
    if (onboardNow) ++h->engageCount; else ++h->releaseCount;
    h->prevOnboardActive = onboardNow;
  }

  // Ground truth: integrate the ports' own reported positions (already
  // side/sign-corrected) through the same midpoint-heading kinematics
  // the firmware's own odometry uses.
  const double cpm = h->engine.countsPerMm();
  const double b = h->engine.effectiveTrackWidth();
  const double dl = (h->left.position() - h->prevGround1) / cpm;
  const double dr = (h->right.position() - h->prevGround2) / cpm;
  h->prevGround1 = h->left.position();
  h->prevGround2 = h->right.position();
  const double dCenter = 0.5 * (dl + dr);
  const double dHeading = (dr - dl) / b;
  const double mid = h->h + 0.5 * dHeading;
  h->x += dCenter * std::cos(mid);
  h->y += dCenter * std::sin(mid);
  h->h += dHeading;
  return active;
}

// ---- readback ----------------------------------------------------------

float scPoseX(void* handle) {
  return static_cast<float>(static_cast<Handle*>(handle)->x);
}
float scPoseY(void* handle) {
  return static_cast<float>(static_cast<Handle*>(handle)->y);
}
float scPoseHeading(void* handle) {
  return static_cast<float>(static_cast<Handle*>(handle)->h);
}

float scWheelVelocity(void* handle, int side) {
  Handle* h = static_cast<Handle*>(handle);
  return side == 0 ? h->left.velocity() : h->right.velocity();
}

float scAppliedDuty(void* handle, int side) {
  Handle* h = static_cast<Handle*>(handle);
  return side == 0 ? h->left.appliedDuty() : h->right.appliedDuty();
}

float scCountsPerMm(void* handle) {
  return static_cast<Handle*>(handle)->engine.countsPerMm();
}
float scEffectiveTrackWidth(void* handle) {
  return static_cast<Handle*>(handle)->engine.effectiveTrackWidth();
}

// ---- hybrid actuation readback, for sim_tour.py's own report ---------

uint32_t scFrameCount(void* handle) {
  return static_cast<Handle*>(handle)->bus.frameCount();       // 0x10 shipped
}
uint32_t scOnboardFrameCount(void* handle) {
  return static_cast<Handle*>(handle)->bus.onboardFrameCount(); // 0x80 shipped
}
int scOnboardActive(void* handle) {
  // Whether the LAST frame shipped was 0x80 -- see this file's Handle
  // comment for why onboardActive() alone tells us that. A tour ends
  // with a neutral tick, and CutebotActuationPolicy::decide() forces
  // PWM on every neutral tick, so a caller checking this after the
  // final tick is checking "did the tour actually come to rest on
  // PWM", not merely reading a leftover flag.
  return static_cast<Handle*>(handle)->bus.onboardActive() ? 1 : 0;
}
uint32_t scEngageCount(void* handle) {
  return static_cast<Handle*>(handle)->engageCount;
}
uint32_t scReleaseCount(void* handle) {
  return static_cast<Handle*>(handle)->releaseCount;
}

}  // extern "C"
