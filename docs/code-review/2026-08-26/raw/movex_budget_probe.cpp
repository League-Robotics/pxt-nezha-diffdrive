// Does the BLOCK path move(distance, yaw) abort mid-pivot on the split path?
// Replicates shims.cpp startMove()'s budget math EXACTLY, then runs moveX.
#include <cstdio>
#include <cmath>
#include "core/diffdrive.h"
#include "motion/motion_engine.h"
#include "fake_ports.h"

static const float kFullDuty = 10795.0f;
static const uint32_t kPeriodMs = 24;
static const float kPi = 3.14159265f;

struct Rig {
  FakeMotor left, right; FakeClock clock; FakeSleeper sleeper; FakeFiberLauncher launcher;
  DiffDrive::DifferentialDrive kernel; diffDrive::MotionEngine engine;
  float x=0, y=0, h=0, pl=0, pr=0;
  Rig() : kernel(left,right,clock,sleeper,launcher), engine(kernel,clock) {
    DiffDrive::DifferentialDrive::Config cfg;
    cfg.maxDuty=100.f; cfg.fullDutyVelocity=kFullDuty; cfg.kp=0.f; cfg.ki=6.f;
    cfg.iMax=765.6f; cfg.pidMax=1276.f; cfg.vMin=255.2f; cfg.posErrMax=127.6f;
    cfg.biasMax=303.7f; cfg.tauAdapt=30.f; cfg.aSteady=382.8f;
    cfg.stallSpeed=191.4f; cfg.stallDemand=510.4f; cfg.stallWindow=500.f;
    cfg.twistHoldGain=2.f; cfg.cyclePeriod=kPeriodMs;
    kernel.setConfig(cfg); kernel.begin();
    // openLoopProfile() -- what every tour and RUN: verb sets
    engine.setDistTaper(400); engine.setYawTaper(180);
    engine.setDistFloor(0.25f); engine.setTurnFloor(0.12f); engine.setRampMs(400);
  }
  void odom() {
    auto o = kernel.output();
    const float cpm = engine.countsPerMm();
    const float dL=(o.positionLeft-pl)/cpm, dR=(o.positionRight-pr)/cpm;
    pl=o.positionLeft; pr=o.positionRight;
    const float dC=0.5f*(dL+dR), dH=(dR-dL)/engine.effectiveTrackWidth();
    const float mid=h+0.5f*dH;
    x += dC*cosf(mid); y += dC*sinf(mid); h += dH;
  }
  void tick() {
    const float dt = kPeriodMs/1000.f;
    left.nextPositionValue  = left.position()  + left.appliedDuty()  * kFullDuty*dt;
    right.nextPositionValue = right.position() + right.appliedDuty() * kFullDuty*dt;
    clock.nowUs += (uint64_t)kPeriodMs*1000ull;
    left.nextSampleTimeUs = right.nextSampleTimeUs = clock.nowUs;
    kernel.step(); odom(); engine.serviceMove();
  }
};

// shims.cpp startMove(), transcribed verbatim. distance [mm], yaw [cdeg],
// speed [mm/s], yawRate [cdeg/s].
static void blockStartMove(Rig& r, int distance, int yaw, int speed, int yawRate,
                           uint32_t* timeoutOut, float* durOut) {
  const float distanceMm = (float)distance;
  const float rotationRad = (float)yaw * 0.01f * kPi / 180.0f;
  const float cpm = r.engine.countsPerMm();
  const float b = r.engine.effectiveTrackWidth();
  const float distTargetCounts = distanceMm * cpm;
  const float yawTargetCounts = rotationRad * 0.5f * b * cpm;
  const float speedCounts = (float)(speed > 0 ? speed : 1) * cpm;
  const float yawRadPerS = (float)(yawRate > 0 ? yawRate : 1) * 0.01f * kPi / 180.0f;
  const float twistCounts = yawRadPerS * 0.5f * b * cpm;
  float duration = 0.0f;
  if (distTargetCounts != 0.0f) duration = std::fabs(distTargetCounts) / speedCounts;
  if (yawTargetCounts != 0.0f) {
    const float yd = std::fabs(yawTargetCounts) / twistCounts;
    if (yd > duration) duration = yd;
  }
  if (duration <= 0.0f) { *timeoutOut = 0; *durOut = 0; return; }
  const float leftC = distTargetCounts - yawTargetCounts;
  const float rightC = distTargetCounts + yawTargetCounts;
  const float dom = std::fabs(leftC) > std::fabs(rightC) ? std::fabs(leftC) : std::fabs(rightC);
  const float cruiseMmS = (dom / duration) / cpm;
  const uint32_t timeoutMs = (uint32_t)(duration * 1000.0f) + 1500u;
  *timeoutOut = timeoutMs; *durOut = duration;
  r.engine.moveX(distanceMm, rotationRad, cruiseMmS, timeoutMs);
}

static void run(int distCm, int yawDeg, int speedCmS, int yawRateDegS) {
  Rig r;
  uint32_t timeoutMs = 0; float dur = 0;
  blockStartMove(r, distCm * 10, yawDeg * 100, speedCmS * 10, yawRateDegS * 100,
                 &timeoutMs, &dur);
  const uint64_t t0 = r.clock.nowUs;
  int ticks = 0;
  double phase2StartMs = -1;
  float lastH = 0;
  // detect phase-2 start: heading stops changing while position starts moving
  while (r.engine.isMoveActive() && ticks < 20000) {
    const float hBefore = r.h, xBefore = r.x;
    r.tick(); ++ticks;
    if (phase2StartMs < 0 && ticks > 3 &&
        std::fabs(r.h - hBefore) < 1e-4f && std::fabs(r.x - xBefore) > 1e-3f) {
      phase2StartMs = (r.clock.nowUs - t0) / 1000.0;
    }
    lastH = r.h;
  }
  const double elapsedMs = (r.clock.nowUs - t0) / 1000.0;
  const bool hitDeadline = elapsedMs >= (double)timeoutMs - kPeriodMs;
  printf("  move(%d cm, %d deg)  budget: blended dur %.0f ms -> timeout %u ms\n",
         distCm, yawDeg, dur * 1000.0, timeoutMs);
  printf("     ran %.0f ms (%d ticks)%s\n", elapsedMs, ticks,
         hitDeadline ? "   <-- ENDED ON DEADLINE" : "   (ended on completion)");
  printf("     phase 2 (straight leg) %s\n",
         phase2StartMs < 0 ? "NEVER STARTED" : "started");
  printf("     ends at x=%.1f mm  y=%.1f mm  heading=%.2f deg   (wanted x~%d mm, h~%d deg)\n\n",
         r.x, r.y, lastH * 180.0f / kPi, distCm * 10, yawDeg);
}

int main() {
  printf("Block path move(distance, yaw) -- block defaults speed 15 cm/s, yaw rate 90 deg/s\n");
  printf("(shims.cpp startMove() budget math transcribed verbatim; openLoopProfile shaping)\n\n");
  run(0, 180, 15, 90);   // peer: correct
  run(20, 0,  15, 90);   // peer: correct
  run(20, 90, 15, 90);   // peer: ends 77.3 deg, x ~ 0
  run(20, 180,15, 90);   // peer: ends 2.56 deg, x = 0
  printf("Same two failures with the tour profile (speed 20 cm/s, yaw 90 deg/s):\n\n");
  run(20, 90, 20, 90);
  run(20, 180,20, 90);
  return 0;
}
