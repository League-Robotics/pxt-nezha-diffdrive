// profile_probe_kernel_check.cpp -- minimal probe-as-test harness for
// sprint 029 ticket 001's two probe-derived acceptance criteria, run
// through the REAL kernel + REAL MotionEngine (not the isolated,
// hand-scripted host tests in test_kernel_reference_handling.py):
//
//   E3d: a 90 deg pivot at cruise 100 with the twist-hold servo ON
//        must show no negative right duty on any tick (review MK-02 /
//        design §4.5 K1 -- the historical measurement was -11%).
//   E5:  a frozen right-encoder tick mid-cruise (300 mm/s-scale) must
//        show a duty step of (near) zero on the tick immediately after
//        the freeze (review MK-03 / design §4.5 K2 -- the historical
//        measurement was +6 duty points, 35.3 -> 41.3%).
//
// `Rig` below is the SAME construction as
// docs/code-review/2026-09-02/raw/profile_probe.cpp's own Rig (same
// fleet-bake Config, same ideal/lagged wheel model) -- duplicated here
// rather than #included because profile_probe.cpp defines its own
// main() and this file needs its own. Ticket 003 owns the full
// probe-as-test file (design §9.3 item 2, test_profile_probe.py) this
// stands in for; this is deliberately just the two scenarios this
// ticket's own acceptance criteria name.
//
// Build (mirrors profile_probe.cpp's own header comment):
//   c++ -std=c++20 -O1 -w -I src -I tests/host \
//       tests/host/profile_probe_kernel_check.cpp \
//       src/core/diffdrive.cpp src/motion/motion_engine.cpp -o <out>
//
// Exits 0 and prints "OK ..." lines on success; prints a "FAIL ..."
// line and exits 1 on the first failing scenario -- see
// test_profile_probe_kernel.py, which builds and runs this binary and
// asserts on both.
#include <cstdio>
#include <cmath>
#include <vector>
#include <algorithm>
#include "core/diffdrive.h"
#include "motion/motion_engine.h"
#include "fake_ports.h"

namespace {

const float kFullDuty = 10795.0f;   // counts/s (shims.cpp ensure())
const uint32_t kPeriodMs = 24;
const float kDt = kPeriodMs / 1000.0f;

// Verbatim copy of profile_probe.cpp's own Rig (see file header for why
// this is a copy, not an #include).
struct Rig {
  FakeMotor left, right;
  FakeClock clock;
  FakeSleeper sleeper;
  FakeFiberLauncher launcher;
  DiffDrive::DifferentialDrive kernel;
  diffDrive::MotionEngine engine;
  float x = 0, y = 0, h = 0;
  float pl = 0, pr = 0;
  float tauS = 0.0f;
  float gainL = 1.0f, gainR = 1.0f;
  float vL = 0, vR = 0;
  float trueL = 0, trueR = 0;
  int dwellTicks = 0;
  int dwellL = 0, dwellR = 0; int signL = 0, signR = 0;
  int freezeTick = -1;
  int tickNo = 0;
  std::vector<float> speedLog;
  std::vector<float> dutyLog;
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
};

bool checkE3d() {
  const float kPi = 3.14159265f;
  Rig r;
  r.engine.moveX(0, kPi / 2, 100, 30000);
  float minDutyRight = 0.0f;
  int n = 0;
  while (r.engine.isMoveActive() && n < 600) {
    r.tick();
    minDutyRight = std::min(minDutyRight, r.kernel.output().appliedDutyRight);
    ++n;
  }
  // A couple of points of slack for float noise; the historical
  // measurement was a clean -11 % to -13 %, so a real regression will
  // land far past this margin, not on its edge.
  const bool ok = minDutyRight >= -0.5f;
  printf("%s E3d: most-negative right duty %.2f%% over %d ticks (want >= 0)\n",
         ok ? "OK" : "FAIL", minDutyRight, n);
  return ok;
}

bool checkE5() {
  Rig r;
  r.freezeTick = 60;
  r.engine.moveX(1500, 0, 300, 30000);
  for (int i = 0; i < 63 && r.engine.isMoveActive(); ++i) r.tick();
  if (r.dutyLog.size() <= 61) {
    printf("FAIL E5: move ended before tick 61 (dutyLog.size()=%zu)\n",
           r.dutyLog.size());
    return false;
  }
  const float dutyFrozen = r.dutyLog[60];
  const float dutyAfter = r.dutyLog[61];
  const float step = dutyAfter - dutyFrozen;
  // Historical (pre-fix) jump was ~+6 duty points; require the step
  // stay under a sixth of that.
  const bool ok = std::fabs(step) < 1.0f;
  printf("%s E5: duty step %.2f%% (%.2f%% -> %.2f%%), want < 1%%\n",
         ok ? "OK" : "FAIL", step, dutyFrozen, dutyAfter);
  return ok;
}

}  // namespace

int main() {
  const bool okE3d = checkE3d();
  const bool okE5 = checkE5();
  return (okE3d && okE5) ? 0 : 1;
}
