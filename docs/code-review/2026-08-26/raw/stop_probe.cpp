// Throwaway probe 2: do the stop paths actually stop the wheels?
#include <cstdio>
#include <cmath>
#include "core/diffdrive.h"
#include "motion/motion_engine.h"
#include "fake_ports.h"
static const float kFullDuty = 10795.0f;
static const uint32_t kPeriodMs = 24;
struct Rig {
  FakeMotor left, right; FakeClock clock; FakeSleeper sleeper; FakeFiberLauncher launcher;
  DiffDrive::DifferentialDrive kernel; diffDrive::MotionEngine engine;
  Rig() : kernel(left,right,clock,sleeper,launcher), engine(kernel,clock) {
    DiffDrive::DifferentialDrive::Config cfg;
    cfg.maxDuty=100.f; cfg.fullDutyVelocity=kFullDuty; cfg.kp=0.f; cfg.ki=6.f;
    cfg.iMax=765.6f; cfg.pidMax=1276.f; cfg.vMin=255.2f; cfg.posErrMax=127.6f;
    cfg.biasMax=303.7f; cfg.tauAdapt=30.f; cfg.aSteady=382.8f;
    cfg.stallSpeed=191.4f; cfg.stallDemand=510.4f; cfg.stallWindow=500.f;
    cfg.twistHoldGain=2.f; cfg.cyclePeriod=kPeriodMs;
    kernel.setConfig(cfg); kernel.begin();
  }
  void tick() {
    const float dt = kPeriodMs/1000.f;
    left.nextPositionValue  = left.position()  + left.appliedDuty()  * kFullDuty*dt;
    right.nextPositionValue = right.position() + right.appliedDuty() * kFullDuty*dt;
    clock.nowUs += (uint64_t)kPeriodMs*1000ull;
    left.nextSampleTimeUs = right.nextSampleTimeUs = clock.nowUs;
    kernel.step(); engine.serviceMove();
  }
  // shims.cpp's deliverStopNow(): PORT-level zero write, no kernel.neutral()
  void deliverStopNow() { left.emergencyStop(); right.emergencyStop(); }
  void report(const char* what) {
    auto o = kernel.output();
    printf("  %-42s dutyL=%6.1f%% dutyR=%6.1f%%  moveActive=%d\n",
           what, o.appliedDutyLeft, o.appliedDutyRight, (int)engine.isMoveActive());
  }
};

int main() {
  printf("A. `stop move` block (shims endMove(): engine.endMove() + deliverStopNow())\n");
  printf("   after a CONTINUOUS command (setWheelSpeeds), no move-engine move active:\n");
  { Rig r;
    r.engine.wheelsV(200.f, 200.f, DiffDrive::DifferentialDrive::kLeaseMax);
    for (int i=0;i<10;++i) r.tick();
    r.report("driving, before stop move");
    r.engine.endMove();     // no-op: no move_ active, so NO kernel.neutral()
    r.deliverStopNow();     // port-level zero
    r.report("immediately after stop move");
    r.tick();
    r.report("one tick later");
    for (int i=0;i<10;++i) r.tick();
    r.report("ten ticks later");
  }
  printf("\n   ...and the same sequence via `stop` (shims stopAll(), which DOES\n"
         "   call kernel.neutral() as well):\n");
  { Rig r;
    r.engine.wheelsV(200.f, 200.f, DiffDrive::DifferentialDrive::kLeaseMax);
    for (int i=0;i<10;++i) r.tick();
    r.report("driving, before stop");
    r.engine.endMove(); r.kernel.neutral(); r.deliverStopNow();
    r.tick();
    r.report("one tick later");
    for (int i=0;i<10;++i) r.tick();
    r.report("ten ticks later");
  }

  printf("\nB. e-stop latched WITHOUT going through shims' estopAll()\n"
         "   (serviceMove() checks stallHalted but never Output.estopped):\n");
  { Rig r;
    r.engine.moveX(1000.f, 0.f, 150.f, 30000u);
    for (int i=0;i<10;++i) r.tick();
    r.report("mid-move");
    r.kernel.estop();               // latch only -- as emergencyStopMotors() also does
    for (int i=0;i<10;++i) r.tick();
    r.report("10 ticks after estop latch");
    int n=0; while (r.engine.isMoveActive() && n < 5000) { r.tick(); ++n; }
    printf("  move stayed 'active' for %d further ticks (%.1f s) after the e-stop\n",
           n, n*kPeriodMs/1000.0);
  }
  return 0;
}
