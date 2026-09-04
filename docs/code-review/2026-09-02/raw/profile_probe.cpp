// profile_probe.cpp -- characterise the motion profile the real engine +
// kernel command, on ideal and first-order-lag wheels. Host build:
//   c++ -std=c++20 -O1 -w -I src -I tests/host profile_probe.cpp \
//       src/core/diffdrive.cpp src/motion/motion_engine.cpp
#include <cstdio>
#include <cmath>
#include <vector>
#include <string>
#include "core/diffdrive.h"
#include "motion/motion_engine.h"
#include "fake_ports.h"

static const float kFullDuty = 10795.0f;   // counts/s (shims.cpp ensure())
static const uint32_t kPeriodMs = 24;
static const float kDt = kPeriodMs / 1000.0f;

struct Rig {
  FakeMotor left, right;
  FakeClock clock;
  FakeSleeper sleeper;
  FakeFiberLauncher launcher;
  DiffDrive::DifferentialDrive kernel;
  diffDrive::MotionEngine engine;
  float x = 0, y = 0, h = 0;
  float pl = 0, pr = 0;
  // wheel model: first-order lag toward duty*fullDuty*gain, time const tau
  float tauS = 0.0f;
  float gainL = 1.0f, gainR = 1.0f;
  float vL = 0, vR = 0;   // actual wheel speed [counts/s]
  float trueL = 0, trueR = 0; // true wheel position [counts]
  int dwellTicks = 0;      // emulate NezhaMotorPort reversal dwell: ticks a wheel is held at 0 after a sign flip
  int dwellL = 0, dwellR = 0; int signL = 0, signR = 0;
  int freezeTick = -1;    // if >=0, the right encoder holds its sample on this tick
  int tickNo = 0;
  std::vector<float> speedLog;  // dominant-wheel actual speed per tick [mm/s]
  std::vector<float> dutyLog;   // applied duty right [%]
  Rig() : kernel(left, right, clock, sleeper, launcher), engine(kernel, clock) {
    DiffDrive::DifferentialDrive::Config cfg;   // shims.cpp's ensure() bake
    cfg.maxDuty = 100.0f; cfg.fullDutyVelocity = kFullDuty;
    cfg.kp = 0.0f; cfg.ki = 6.0f; cfg.iMax = 765.6f; cfg.pidMax = 1276.0f;
    cfg.vMin = 893.2f; cfg.posErrMax = 127.6f; cfg.biasMax = 303.7f;
    cfg.tauAdapt = 30.0f; cfg.aSteady = 382.8f;
    cfg.stallSpeed = 191.4f; cfg.stallDemand = 510.4f; cfg.stallWindow = 500.0f;
    cfg.twistHoldGain = 2.0f; cfg.cyclePeriod = kPeriodMs;
    kernel.setConfig(cfg);
    kernel.begin();
    // prime one sample so velocity math works
    left.nextSampleTimeUs = right.nextSampleTimeUs = 1000;
    clock.nowUs = 1000;
    kernel.step();
  }
  void odom() {
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
  void tick() {
    const float tgtL = left.appliedDuty() * kFullDuty * gainL;
    const float tgtR = right.appliedDuty() * kFullDuty * gainR;
    float tL = tgtL, tR = tgtR;
    if (dwellTicks > 0) {
      auto dw = [&](float& t, int& sign, int& dwell) {
        const int s = t > 0 ? 1 : (t < 0 ? -1 : 0);
        if (s != 0 && sign != 0 && s != sign) { dwell = dwellTicks; }
        if (s != 0) sign = s;
        if (dwell > 0) { --dwell; t = 0; }
      };
      dw(tL, signL, dwellL); dw(tR, signR, dwellR);
    }
    if (tauS <= 0.0f) { vL = tL; vR = tR; }
    else { const float a = kDt / (tauS + kDt); vL += a * (tL - vL); vR += a * (tR - vR); }
    trueL += vL * kDt; trueR += vR * kDt;
    left.nextPositionValue = trueL;
    right.nextPositionValue = trueR;
    left.velocityValue = vL; right.velocityValue = vR;
    clock.nowUs += (uint64_t)kPeriodMs * 1000ull;
    left.nextSampleTimeUs = clock.nowUs;
    right.nextSampleTimeUs = clock.nowUs;
    right.collectSucceeds = (tickNo != freezeTick);
    kernel.step();
    right.collectSucceeds = true;
    odom();
    engine.serviceMove();
    const float cpm = engine.countsPerMm();
    speedLog.push_back(std::max(std::fabs(vL), std::fabs(vR)) / cpm);
    dutyLog.push_back(kernel.output().appliedDutyRight);
    ++tickNo;
  }
  int run(int maxTicks = 4000) {
    int n = 0;
    for (; n < maxTicks && engine.isMoveActive(); ++n) tick();
    // settle like tickDrive does
    engine.settleToRest(); odom();
    return n;
  }
};

static void profileStats(const char* label, Rig& r, int ticks, float targetMm, float targetDeg) {
  // finite-difference accel / jerk on the dominant wheel speed
  float peakA = 0, peakJ = 0, prevV = 0, prevA = 0, maxV = 0;
  int rampTicks = 0, cruiseTicks = 0;
  for (size_t i = 0; i < r.speedLog.size(); ++i) {
    const float v = r.speedLog[i];
    const float a = (v - prevV) / kDt;
    const float j = (a - prevA) / kDt;
    if (std::fabs(a) > peakA) peakA = std::fabs(a);
    if (i > 0 && std::fabs(j) > peakJ) peakJ = std::fabs(j);
    if (v > maxV) maxV = v;
    prevV = v; prevA = a;
  }
  for (size_t i = 0; i < r.speedLog.size(); ++i) {
    if (r.speedLog[i] < 0.98f * maxV) ++rampTicks; else break;
  }
  for (size_t i = 0; i < r.speedLog.size(); ++i) if (r.speedLog[i] >= 0.98f * maxV) ++cruiseTicks;
  float startA = 0, stopA = 0, midA = 0, midJ = 0;
  { const auto& L = r.speedLog; size_t n = L.size();
    if (n > 1) startA = (L[1] - L[0]) / kDt;
    for (size_t i = 1; i < n; ++i) if (L[i] < 1.0f && L[i-1] >= 1.0f) { stopA = (L[i] - L[i-1]) / kDt; break; }
    float pv = 0, pa = 0;
    for (size_t i = 0; i < n; ++i) { const float v = L[i]; const float a = (v - pv) / kDt; const float j = (a - pa) / kDt;
      if (i >= 3 && v >= 1.0f && (i + 4 < n) && L[i+1] >= 1.0f) { if (std::fabs(a) > midA) midA = std::fabs(a); if (std::fabs(j) > midJ) midJ = std::fabs(j); }
      pv = v; pa = a; }
  }
  const float travelled = hypotf(r.x, r.y);
  const float headingDeg = r.h * 180.0f / (float)M_PI;
  printf("%-36s t=%4d(%.2fs) Vpk=%5.1f ramp=%3d cru=%3d a:start=%6.0f mid=%5.0f stop=%6.0f j:mid=%7.0f ",
         label, ticks, ticks * kDt, maxV, rampTicks, cruiseTicks, startA, midA, stopA, midJ);
  if (targetMm != 0) printf("dist %.1f/%.0f mm (err %+.2f) ", travelled, targetMm, travelled - targetMm);
  if (targetDeg != 0) printf("yaw %.2f/%.0f deg (err %+.2f) ", headingDeg, targetDeg, headingDeg - targetDeg);
  printf("\n");
}

static void shaped(Rig& r, float a, float jerk = 0, float exitMmS = 0) {
  r.engine.setAAccelMmS2(a); r.engine.setADecelMmS2(a);
  if (jerk > 0) r.engine.setJerkMmS3(jerk);
  if (exitMmS > 0) r.engine.setProfileExitMmS(exitMmS);
}

int main() {
  const float kPi = 3.14159265f;
  printf("== E1/E2: straight 600 mm, ideal wheels ==\n");
  for (float cruise : {100.0f, 200.0f, 400.0f}) {
    { Rig r; r.engine.moveX(600, 0, cruise, 30000); int n = r.run();
      char b[64]; snprintf(b, sizeof b, "legacy   cruise %3.0f", cruise); profileStats(b, r, n, 600, 0); }
    { Rig r; shaped(r, 400); r.engine.moveX(600, 0, cruise, 30000); int n = r.run();
      char b[64]; snprintf(b, sizeof b, "shaped a=400 cruise %3.0f", cruise); profileStats(b, r, n, 600, 0); }
    { Rig r; shaped(r, 400, 4000); r.engine.moveX(600, 0, cruise, 30000); int n = r.run();
      char b[64]; snprintf(b, sizeof b, "shaped a=400 j=4000 cruise %3.0f", cruise); profileStats(b, r, n, 600, 0); }
    { Rig r; shaped(r, 400, 4000, 60); r.engine.moveX(600, 0, cruise, 30000); int n = r.run();
      char b[64]; snprintf(b, sizeof b, "shaped a=400 j=4000 exit=60 cr %3.0f", cruise); profileStats(b, r, n, 600, 0); }
  }
  printf("\n== E1b: straight 600 mm, lagged wheels tau=80ms ==\n");
  for (float cruise : {200.0f, 400.0f}) {
    { Rig r; r.tauS = 0.08f; r.engine.moveX(600, 0, cruise, 30000); int n = r.run();
      char b[64]; snprintf(b, sizeof b, "legacy   cruise %3.0f tau80", cruise); profileStats(b, r, n, 600, 0); }
    { Rig r; r.tauS = 0.08f; shaped(r, 400); r.engine.moveX(600, 0, cruise, 30000); int n = r.run();
      char b[64]; snprintf(b, sizeof b, "shaped a=400 cruise %3.0f tau80", cruise); profileStats(b, r, n, 600, 0); }
  }

  printf("\n== E3: pure pivot 90 deg (yawMargin 4 counts = 0.16 deg); floor 70 mm/s ==\n");
  for (float cruise : {60.0f, 100.0f, 200.0f}) {
    { Rig r; r.engine.moveX(0, kPi / 2, cruise, 30000); int n = r.run();
      char b[64]; snprintf(b, sizeof b, "legacy pivot cruise %3.0f", cruise); profileStats(b, r, n, 0, 90); }
    { Rig r; shaped(r, 400); r.engine.moveX(0, kPi / 2, cruise, 30000); int n = r.run();
      char b[64]; snprintf(b, sizeof b, "shaped pivot cruise %3.0f", cruise); profileStats(b, r, n, 0, 90); }
  }
  {
    // what does the floor do to a pivot's terminal crawl?
    Rig r; r.engine.moveX(0, kPi / 2, 100, 30000);
    float lastDeg = 0; int n = 0;
    printf("  legacy pivot @100: last ticks (deg per tick):");
    std::vector<float> hs;
    while (r.engine.isMoveActive() && n < 4000) { r.tick(); hs.push_back(r.h * 180 / kPi); ++n; }
    for (size_t i = hs.size() > 6 ? hs.size() - 6 : 0; i < hs.size(); ++i)
      printf(" %.2f(+%.2f)", hs[i], hs[i] - (i ? hs[i - 1] : 0));
    printf("\n");
  }
  printf("\n== E3b: pivot with speed floor off (vMin=0) ==\n");
  { Rig r; r.kernel.setSpeedFloor(0); r.engine.moveX(0, kPi / 2, 100, 30000); int n = r.run();
    profileStats("legacy pivot cruise 100 vMin=0", r, n, 0, 90); }

  printf("\n== E4: moveX split: 90 deg + 300 mm at cruise 150 ==\n");
  { Rig r; r.engine.moveX(300, kPi / 2, 150, 30000); int n = r.run();
    profileStats("legacy split", r, n, 300, 90);
    printf("  end pose x=%.1f y=%.1f (expect x~0 y~300)\n", r.x, r.y); }
  { Rig r; r.engine.moveX(300, kPi / 2, 150, 30000);
    printf("  per-tick heading around the handoff (deg, dutyL/dutyR %%):\n  ");
    float lastH = -1; int n = 0; bool printed = false;
    while (r.engine.isMoveActive() && n < 400) { r.tick(); ++n; auto o = r.kernel.output();
      const float hd = r.h * 180 / kPi;
      if (hd > 85 && n < 80) printf("t%d h=%.2f L=%.1f R=%.1f | ", n, hd, o.appliedDutyLeft, o.appliedDutyRight); }
    printf("\n"); }
  printf("\n== E8: split 90 deg + 300 mm, emulating the port's 100 ms per-wheel reversal dwell (4 ticks) ==\n");
  { Rig r; r.dwellTicks = 4; r.engine.moveX(300, kPi / 2, 150, 30000); int n = r.run();
    profileStats("legacy split, dwell emulated", r, n, 300, 90);
    printf("  end pose x=%.1f y=%.1f heading %.2f\n", r.x, r.y, r.h * 180 / kPi); }
  { Rig r; r.dwellTicks = 4; r.engine.moveX(0, kPi / 2, 150, 30000); int n = r.run();
    profileStats("pivot only, dwell emulated", r, n, 0, 90);
    printf("  end pose x=%.1f y=%.1f heading %.2f\n", r.x, r.y, r.h * 180 / kPi); }
  { Rig r; r.dwellTicks = 4; r.engine.moveX(300, 0, 150, 30000); r.run(); r.engine.moveX(0, kPi/2, 150, 30000); int n = r.run();
    profileStats("straight then pivot, dwell emulated", r, n, 0, 90);
    printf("  end pose x=%.1f y=%.1f heading %.2f (pivot should not translate)\n", r.x, r.y, r.h * 180 / kPi); }

  printf("\n== E5: frozen right-encoder tick mid-cruise (300 mm/s straight), kp=0 ==\n");
  { Rig r; r.freezeTick = 60; r.engine.moveX(1500, 0, 300, 30000);
    for (int i = 0; i < 75 && r.engine.isMoveActive(); ++i) r.tick();
    printf("  tick: dutyR%%  (freeze at tick 60)\n  ");
    for (int i = 56; i < 68; ++i) printf("%d:%.1f ", i, r.dutyLog[i]);
    printf("\n  velocity(out) right at 59..63:");
    // re-run capturing output velocity
  }
  { Rig r; r.freezeTick = 60; r.engine.moveX(1500, 0, 300, 30000);
    for (int i = 0; i < 64 && r.engine.isMoveActive(); ++i) { r.tick(); if (i >= 58) printf(" t%d vR=%.0f", i, r.kernel.output().velocityRight); }
    printf("\n"); }

  printf("\n== E6: wheel gain mismatch, right 5%% fast, 600 mm @200 (twist hold on) ==\n");
  { Rig r; r.gainR = 1.05f; r.engine.moveX(600, 0, 200, 30000); int n = r.run();
    profileStats("legacy right+5%", r, n, 600, 0);
    printf("  end heading %.2f deg, y=%.1f mm; last 8 dutyR:", r.h * 180 / kPi, r.y);
    for (size_t i = r.dutyLog.size() > 8 ? r.dutyLog.size() - 8 : 0; i < r.dutyLog.size(); ++i) printf(" %.1f", r.dutyLog[i]);
    printf("\n"); }

  printf("\n== E7: continuous wheelsV(200,200) from rest, ideal wheels ==\n");
  { Rig r; r.engine.wheelsV(200, 200, 5000);
    printf("  wheel speed per tick:");
    for (int i = 0; i < 6; ++i) { r.tick(); printf(" %.0f", r.speedLog.back()); }
    printf(" mm/s\n"); }
  return 0;
}

// ---- appended experiments ----
struct Extra {
  static void run() {
    const float kPi = 3.14159265f;
    printf("\n== E3c: pivot 90 @100 -- heading per tick THROUGH the end (ticks keep running after 'reached') ==\n  ");
    { Rig r; r.engine.moveX(0, kPi/2, 100, 30000); int n = 0; bool ended = false; int endTick = -1;
      while (n < 400) { r.tick(); ++n; const bool act = r.engine.isMoveActive(); if (!act && !ended) { ended = true; endTick = n; }
        if (ended && n > endTick + 3) break; if (n >= endTick - 3 && endTick > 0 || (r.h*180/kPi > 86)) printf("t%d h=%.2f act=%d dR=%.1f%% | ", n, r.h*180/kPi, act, r.kernel.output().appliedDutyRight); }
      printf("\n  -> overshoot after the neutral lands: %.2f deg\n", r.h*180/kPi - 90); }
    printf("\n== E9: profile exit 60 mm/s vs the kernel's own vMin floor (70 mm/s): speed on the last 5 driven ticks, straight 600 @200 ==\n");
    for (int useFloor = 1; useFloor >= 0; --useFloor) {
      Rig r; if (!useFloor) r.kernel.setSpeedFloor(0); shaped(r, 400, 0, 60); r.engine.moveX(600, 0, 200, 30000); int n = r.run();
      printf("  vMin=%s : ticks=%d last speeds:", useFloor ? "893(70mm/s)" : "0", n);
      for (size_t i = r.speedLog.size() > 6 ? r.speedLog.size()-6 : 0; i < r.speedLog.size(); ++i) printf(" %.0f", r.speedLog[i]);
      printf(" mm/s ; dist err %+.2f mm\n", hypotf(r.x, r.y) - 600); }
    printf("\n== E10: legacy 600 @200 -- speed on the last 6 driven ticks (what does the crawl actually run at?) ==\n  ");
    { Rig r; r.engine.moveX(600, 0, 200, 30000); r.run();
      for (size_t i = r.speedLog.size() > 6 ? r.speedLog.size()-6 : 0; i < r.speedLog.size(); ++i) printf(" %.0f", r.speedLog[i]);
      printf(" mm/s  (engine floor = 25%% of 200 = 50; kernel vMin = 70)\n"); }
    printf("\n== E11: ramp-end overshoot vs ki (ideal wheels, straight 600 @200) ==\n");
    for (float ki : {6.0f, 3.0f, 1.5f}) { Rig r; r.kernel.setKi(ki); r.engine.moveX(600, 0, 200, 30000); int n = r.run();
      float mx = 0; for (float v : r.speedLog) mx = std::max(mx, v);
      printf("  ki=%.1f peak %.1f mm/s (+%.0f%%) ticks=%d dist err %+.2f\n", ki, mx, (mx/200-1)*100, n, hypotf(r.x,r.y)-600); }
  }
};
struct Runner { Runner() { atexit([]{ Extra::run(); }); } } gRunner;
struct Extra2 {
  static void run() {
    const float kPi = 3.14159265f;
    printf("\n== E3d: does the twist-hold servo fight the speed floor in a pivot's crawl? (ideal wheels) ==\n");
    for (float cruise : {60.0f, 100.0f, 200.0f}) for (float gain : {2.0f, 0.0f}) {
      Rig r; r.kernel.setTwistHoldGain(gain); r.engine.moveX(0, kPi/2, cruise, 30000);
      int n = 0, endTick = -1; float minDuty = 0, maxV = 0;
      while (n < 600) { r.tick(); ++n; maxV = std::max(maxV, r.speedLog.back());
        if (endTick < 0 && !r.engine.isMoveActive()) endTick = n;
        if (endTick > 0 && n > endTick + 2) break;
        if (n > 5) minDuty = std::min(minDuty, r.kernel.output().appliedDutyRight); }
      printf("  cruise %3.0f gain %.0f : ticks %3d peakV %5.1f mm/s  most-negative dutyR %+6.1f%%  final yaw %.2f (err %+.2f)\n",
             cruise, gain, endTick, maxV, minDuty, r.h*180/kPi, r.h*180/kPi - 90);
    }
    printf("\n== E3e: same for an ARC (300 mm, 45 deg) at cruise 100 -- floor scales both axes ==\n");
    for (float gain : {2.0f, 0.0f}) {
      Rig r; r.kernel.setTwistHoldGain(gain); r.engine.moveX(300, kPi/4, 100, 30000); int n = r.run(); for (int i = 0; i < 2; ++i) r.tick();
      printf("  gain %.0f : ticks %3d end (%.1f, %.1f) heading %.2f (want 45)\n", gain, n, r.x, r.y, r.h*180/kPi);
    }
  }
};
struct Runner2 { Runner2() { atexit([]{ Extra2::run(); }); } } gRunner2;
