// Throwaway probe: does the student block `goTo(x,y)` (TS startGoTo ->
// startMove -> MotionEngine::moveX) land where it says it will?
// Compares it against the sprint-006-fixed MotionEngine::goToR.
#include <cstdio>
#include <cmath>
#include "core/diffdrive.h"
#include "motion/motion_engine.h"
#include "fake_ports.h"

static const float kFullDuty = 10795.0f;   // counts/s (shims.cpp ensure())
static const uint32_t kPeriodMs = 24;

struct Rig {
  FakeMotor left, right;
  FakeClock clock;
  FakeSleeper sleeper;
  FakeFiberLauncher launcher;
  DiffDrive::DifferentialDrive kernel;
  diffDrive::MotionEngine engine;
  float x = 0, y = 0, h = 0;          // odometry [mm], [rad]
  float pl = 0, pr = 0;               // last consumed positions [counts]
  Rig() : kernel(left, right, clock, sleeper, launcher), engine(kernel, clock) {
    DiffDrive::DifferentialDrive::Config cfg;   // shims.cpp's ensure() bake
    cfg.maxDuty = 100.0f; cfg.fullDutyVelocity = kFullDuty;
    cfg.kp = 0.0f; cfg.ki = 6.0f; cfg.iMax = 765.6f; cfg.pidMax = 1276.0f;
    cfg.vMin = 255.2f; cfg.posErrMax = 127.6f; cfg.biasMax = 303.7f;
    cfg.tauAdapt = 30.0f; cfg.aSteady = 382.8f;
    cfg.stallSpeed = 191.4f; cfg.stallDemand = 510.4f; cfg.stallWindow = 500.0f;
    cfg.twistHoldGain = 2.0f; cfg.cyclePeriod = kPeriodMs;
    kernel.setConfig(cfg);
    kernel.begin();
  }
  void odom() {   // shims.cpp odomUpdate()
    auto out = kernel.output();
    const float cpm = engine.countsPerMm();
    const float dL = (out.positionLeft - pl) / cpm;
    const float dR = (out.positionRight - pr) / cpm;
    pl = out.positionLeft; pr = out.positionRight;
    const float dC = 0.5f * (dL + dR);
    const float dH = (dR - dL) / engine.effectiveTrackWidth();
    const float mid = h + 0.5f * dH;
    x += dC * cosf(mid); y += dC * sinf(mid); h += dH;
  }
  // One tick: ideal wheels -- position advances at exactly the applied duty.
  void tick() {
    const float dt = kPeriodMs / 1000.0f;
    left.nextPositionValue  = left.position()  + left.appliedDuty()  * kFullDuty * dt;
    right.nextPositionValue = right.position() + right.appliedDuty() * kFullDuty * dt;
    clock.nowUs += (uint64_t)kPeriodMs * 1000ull;
    left.nextSampleTimeUs = right.nextSampleTimeUs = clock.nowUs;
    kernel.step();
    odom();
    engine.serviceMove();
  }
  void run(int maxTicks = 4000) { for (int i = 0; i < maxTicks && engine.isMoveActive(); ++i) tick(); }
};

int main() {
  const float X = 100.0f, Y = 100.0f;      // mm -- the block call goTo(10, 10) cm
  const float cruiseMmS = 150.0f;

  // --- path A: exactly what blocks/motion.ts startGoTo() computes, in cm,
  //     then hands to startMove() -> shims.cpp -> engine.moveX().
  {
    const double x = X / 10.0, y = Y / 10.0;             // cm, as the block sees it
    const double theta = 2.0 * atan2(y, x);              // rad
    const double radius = (x * x + y * y) / (2.0 * y);   // cm
    const double s = radius * theta;                     // cm, arc length
    printf("blocks/motion.ts startGoTo(10,10) -> startMove(s=%.3f cm, theta=%.3f deg)\n",
           s, theta * 180.0 / M_PI);
    Rig r;
    r.engine.moveX((float)(s * 10.0), (float)theta, cruiseMmS, 20000u);
    r.run();
    printf("  block `go to`  : ends at (%.1f, %.1f) mm, heading %.1f deg"
           "   -> MISS %.1f mm on a %.1f mm hop\n",
           r.x, r.y, r.h * 180.0f / (float)M_PI,
           hypotf(r.x - X, r.y - Y), hypotf(X, Y));
  }

  // --- path B: the sprint-006-fixed C++ reduction, same target.
  {
    Rig r;
    r.engine.goToR(X, Y, cruiseMmS, 1.0f, 20000u);
    r.run();
    printf("  wire GO_TO_R   : ends at (%.1f, %.1f) mm, heading %.1f deg"
           "   -> miss %.1f mm\n",
           r.x, r.y, r.h * 180.0f / (float)M_PI, hypotf(r.x - X, r.y - Y));
  }

  // --- path C: a target 10 cm BEHIND and 1 cm left -- the long-way-around case.
  {
    const double x = -10.0, y = 1.0;
    const double theta = 2.0 * atan2(y, x);
    const double radius = (x * x + y * y) / (2.0 * y);
    const double s = radius * theta;
    printf("\nblocks/motion.ts startGoTo(-10,1) -> startMove(s=%.1f cm, theta=%.1f deg)"
           "  [target is %.1f cm away]\n", s, theta * 180.0 / M_PI, hypot(x, y));
    Rig r;
    r.engine.moveX((float)(s * 10.0), (float)theta, cruiseMmS, 600000u);
    r.run(200000);
    printf("  block `go to`  : ends at (%.1f, %.1f) mm  -> MISS %.1f mm; drove %.2f m of arc\n",
           r.x, r.y, hypotf(r.x - (-100.0f), r.y - 10.0f), fabs(s) / 100.0);
    Rig r2;
    r2.engine.goToR(-100.0f, 10.0f, cruiseMmS, 1.0f, 600000u);
    r2.run(200000);
    printf("  wire GO_TO_R   : ends at (%.1f, %.1f) mm  -> miss %.1f mm\n",
           r2.x, r2.y, hypotf(r2.x - (-100.0f), r2.y - 10.0f));
  }
  return 0;
}
