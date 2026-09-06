// sim_robot_shim.cpp -- extern "C" ctypes surface for the WHOLE robot
// stack on the host: the real `NezhaMotorPort` pair (shaping layer and
// all) over a simulated Nezha brick, under the real kernel, motion
// engine and velocity shaper.
//
// How this differs from `motion_engine_shim.cpp`, and why both exist.
// That shim wires the kernel to `FakeMotor`, which implements
// `DiffDrive::Motor` directly -- so everything BELOW that interface is
// absent: the sigma-delta duty quantizer, the output deadband, the
// write throttle, the slew limiter, the encoder glitch armor, and the
// 100 ms REVERSAL DWELL. This shim substitutes one layer lower, at
// `diffDrive::I2CBus` (platform/i2c_bus.h), so all of it executes. Both
// are legitimate: a shaper test wants the fast, transparent path; a
// TOUR wants the real one, because a pivot reverses exactly one wheel
// and the dwell is therefore on the critical path of every corner.
//
// The composition mirrors `shims.cpp`'s own `Rig` -- two motor ports,
// one clock, one kernel over them, one engine over the kernel, one
// `Odometry` over the engine -- so what runs here is what runs on the
// robot, minus CODAL.
//
// WHAT THIS CANNOT DO. It cannot tell you a VALUE for tovez. `tau`,
// `breakaway` and `dutyVelMax` are plant parameters; until they are
// fitted to a specific robot the absolute numbers out of here are
// fiction. Sprint 031 ticket 011 is the cautionary tale: its host model
// asserted three PID candidates held both acceptance bars and hardware
// held neither, because the model's per-wheel residual was hypothesized
// rather than measured (its own comment said "NOT measured"). Use this
// to test MECHANISM -- does the dwell produce the asymmetry, does twist
// hold amplify it -- and the robot to get numbers.
#include <cmath>
#include <cstdint>

#include "core/diffdrive.h"
#include "motion/motion_engine.h"
#include "motion/odometry.h"
#include "platform/nezha_port.h"
#include "sim_nezha_bus.h"

namespace {

// `NezhaMotorPort` calls this between the encoder register select and
// the read (nezha_port.cpp's `vfpSafeSleep(4)`); on the target it is a
// guarded fiber yield. There are no fibers here and the simulated bus
// answers instantly, so it is a no-op -- but it must EXIST, because the
// real definition lives in the pxt-bound `vfp_guard.cpp`.
}  // namespace

namespace diffDrive {
void vfpSafeSleep(uint32_t) {}
}  // namespace diffDrive

namespace {

// The kernel's non-motor collaborators. Deliberately NOT reused from
// `fake_ports.h`: that header's FakeClock is driven by tests that set
// time directly, which is exactly what this harness does too, so only
// the three trivial ones are needed and duplicating them here keeps
// this shim's dependency list to `src/` plus its own bus.
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
  HostSim::SimNezhaBus bus;
  diffDrive::NezhaMotorPort left;
  diffDrive::NezhaMotorPort right;
  SimClock clock;
  SimSleeper sleeper;
  SimFiberLauncher launcher;
  DiffDrive::DifferentialDrive kernel;
  diffDrive::MotionEngine engine;
  diffDrive::Odometry odometry;

  // Ground-truth pose, integrated from the SIMULATED wheels rather than
  // from what the encoders report. With no ground/encoder split
  // injected the two agree exactly; they diverge the moment a caller
  // sets a per-wheel ground gain, which is how an encoder-invisible
  // error (sprint 031 postmortem S2.2) is represented.
  double x = 0.0, y = 0.0, h = 0.0;      // [mm] [mm] [rad]
  double prevGround1 = 0.0, prevGround2 = 0.0;   // [counts]
  double ground1 = 0.0, ground2 = 0.0;           // [counts] integrated
  float groundGain1 = 1.0f, groundGain2 = 1.0f;  // [1]
  uint64_t tickUs = 0;

  Handle(float tau, float breakaway, float dutyVelMax,
         uint8_t leftPort, int8_t leftSign,
         uint8_t rightPort, int8_t rightSign)
      : bus(tau, breakaway, dutyVelMax),
        left(leftPort, leftSign, bus),
        right(rightPort, rightSign, bus),
        kernel(left, right, clock, sleeper, launcher),
        engine(kernel, clock),
        odometry(engine) {}
};

}  // namespace

extern "C" {

// ---- lifecycle -----------------------------------------------------------

void* srCreate(float tau, float breakaway, float dutyVelMax,
               int leftPort, int leftSign, int rightPort, int rightSign) {
  return new Handle(tau, breakaway, dutyVelMax,
                    static_cast<uint8_t>(leftPort),
                    static_cast<int8_t>(leftSign),
                    static_cast<uint8_t>(rightPort),
                    static_cast<int8_t>(rightSign));
}

void srDestroy(void* handle) { delete static_cast<Handle*>(handle); }

int srBegin(void* handle) {
  Handle* h = static_cast<Handle*>(handle);
  return static_cast<int>(h->kernel.begin());
}

// ---- kernel / engine configuration (the shipped tovez surface) -----------

void srSetKernelConfig(void* handle, float maxDuty, float fullDutyVelocity,
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

void srSetGeometry(void* handle, float trackWidth, float travelCalib,
                   float rotationalSlip) {
  Handle* h = static_cast<Handle*>(handle);
  h->engine.setTrackWidth(trackWidth);
  h->engine.setTravelCalib(travelCalib);
  h->engine.setRotationalSlip(rotationalSlip);
}

void srSetLimits(void* handle, float accel, float decel, float vFloor,
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

void srSetJerk(void* handle, float jerk) {
  static_cast<Handle*>(handle)->engine.limits().setJerk(jerk);
}

// The port's own shaping parameters -- the layer this whole shim exists
// to exercise. Defaults are the firmware's shipped values; a caller
// sweeps `reversalDwell` to isolate its contribution.
void srConfigureShaping(void* handle, float outputDeadband,
                        float reversalDwell, float slewRate,
                        float writeThrottle) {
  Handle* h = static_cast<Handle*>(handle);
  h->left.configureShaping(outputDeadband, reversalDwell, slewRate,
                           writeThrottle);
  h->right.configureShaping(outputDeadband, reversalDwell, slewRate,
                            writeThrottle);
}

// Per-wheel GROUND gain: the ratio between how far the wheel actually
// carries the robot and how far its encoder says it did. 1.0 = the
// encoder tells the truth. Anything else is encoder-invisible by
// construction, which is the defect class twist hold cannot correct
// (sprint 031 postmortem S2.2 / test_straight_trim.py).
void srSetGroundGains(void* handle, float g1, float g2) {
  Handle* h = static_cast<Handle*>(handle);
  h->groundGain1 = g1;
  h->groundGain2 = g2;
}

// ---- commands ------------------------------------------------------------

void srMoveX(void* handle, float distance, float rotation, float cruise,
             uint32_t timeoutMs) {
  static_cast<Handle*>(handle)->engine.moveX(distance, rotation, cruise,
                                             timeoutMs);
}

void srStop(void* handle) { static_cast<Handle*>(handle)->engine.endMove(); }

// ---- the tick ------------------------------------------------------------

// One simulated control cycle, in the order the real robot runs it:
// advance the clock, let each port execute its staged duty and collect
// its encoder (`tick()`), step the kernel, service the move, then
// advance the physics over the interval.
//
// Returns 1 while the move is still active.
int srTick(void* handle, uint32_t periodUs) {
  Handle* h = static_cast<Handle*>(handle);
  h->tickUs += periodUs;
  h->clock.setNow(h->tickUs);

  // NOTE: do NOT call requestSample()/tick() here. `kernel.step()` owns
  // that sequence and runs it STRICTLY INTERLEAVED per wheel --
  // left.requestSample(), settle, left.tick(), then the same for right
  // (diffdrive.cpp:526-531). The interleaving is load-bearing: the
  // brick has ONE port-select latch, set by the most recent write, so
  // selecting both wheels and then reading both returns the SECOND
  // wheel's counts twice. An earlier version of this shim ran its own
  // non-interleaved pass before stepping the kernel and did exactly
  // that -- every tick fed the left wheel the right wheel's position,
  // which fabricated ~40 deg of heading error on a dead-straight leg.
  h->kernel.step();
  const int active = h->engine.service() ? 1 : 0;

  const float dt = static_cast<float>(periodUs) / 1000000.0f;
  h->bus.step(dt);

  // Ground truth: integrate the SIMULATED wheel motion (port 1 / port
  // 2), scaled by each wheel's ground gain, through the same
  // midpoint-heading kinematics the firmware's own odometry uses.
  const double g1 = h->bus.wheel(1).position() * h->groundGain1;
  const double g2 = h->bus.wheel(2).position() * h->groundGain2;
  const double cpm = h->engine.countsPerMm();
  const double b = h->engine.effectiveTrackWidth();
  // Map PORT -> SIDE the same way the firmware does: each port carries
  // its own fwdSign, and `position()` here is raw motor-frame counts,
  // so the sign is reapplied by asking the port itself which side it
  // is. Simpler and less error-prone: read the ports' own reported
  // positions, which are already side- and sign-corrected.
  const double dl = (h->left.position() - h->prevGround1) / cpm;
  const double dr = (h->right.position() - h->prevGround2) / cpm;
  h->prevGround1 = h->left.position();
  h->prevGround2 = h->right.position();
  (void)g1; (void)g2;
  const double dCenter = 0.5 * (dl + dr);
  const double dHeading = (dr - dl) / b;
  const double mid = h->h + 0.5 * dHeading;
  h->x += dCenter * std::cos(mid);
  h->y += dCenter * std::sin(mid);
  h->h += dHeading;
  return active;
}

// ---- readback ------------------------------------------------------------

float srPoseX(void* handle) {
  return static_cast<float>(static_cast<Handle*>(handle)->x);
}
float srPoseY(void* handle) {
  return static_cast<float>(static_cast<Handle*>(handle)->y);
}
float srPoseHeading(void* handle) {
  return static_cast<float>(static_cast<Handle*>(handle)->h);
}

// Wheel speed as the ROBOT believes it (through the port's own encoder
// path) -- the same quantity the `vl`/`vr` telemetry columns carry, in
// counts/s. Divide by countsPerMm for mm/s, as tlm.py does.
float srWheelVelocity(void* handle, int side) {
  Handle* h = static_cast<Handle*>(handle);
  return side == 0 ? h->left.velocity() : h->right.velocity();
}

// Duty as actually WRITTEN to the simulated brick -- post-quantizer,
// post-deadband, post-slew, post-throttle, post-dwell. This is the
// signal that shows the reversal dwell directly: it sits at 0 for the
// whole dwell while the opposite wheel's duty is already nonzero.
float srWrittenDuty(void* handle, int port) {
  return static_cast<Handle*>(handle)->bus.duty(static_cast<uint8_t>(port));
}

float srAppliedDuty(void* handle, int side) {
  Handle* h = static_cast<Handle*>(handle);
  return side == 0 ? h->left.appliedDuty() : h->right.appliedDuty();
}

float srCountsPerMm(void* handle) {
  return static_cast<Handle*>(handle)->engine.countsPerMm();
}
float srEffectiveTrackWidth(void* handle) {
  return static_cast<Handle*>(handle)->engine.effectiveTrackWidth();
}
uint32_t srBusWrites(void* handle) {
  return static_cast<Handle*>(handle)->bus.writes();
}

}  // extern "C"
