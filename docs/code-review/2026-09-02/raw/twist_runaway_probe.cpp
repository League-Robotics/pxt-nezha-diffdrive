// twist_runaway_probe.cpp -- NEW engine + K1 kernel: does a straight
// WHEELS_V / MOVE_X run away when the wheels are slightly asymmetric?
#include <cstdio>
#include <cmath>
#include <vector>
#include "core/diffdrive.h"
#include "motion/motion_engine.h"
#include "fake_ports.h"
static const float kFullDuty=10795.0f, kDt=0.024f; static const uint32_t kPeriodMs=24;
struct Rig {
  FakeMotor left,right; FakeClock clock; FakeSleeper sleeper; FakeFiberLauncher launcher;
  DiffDrive::DifferentialDrive kernel; diffDrive::MotionEngine engine;
  float tauS=0.08f, gainL=1.0f, gainR=1.05f, vL=0,vR=0,trueL=0,trueR=0, x=0,y=0,h=0,pl=0,pr=0;
  Rig(float twistGain): kernel(left,right,clock,sleeper,launcher), engine(kernel,clock){
    DiffDrive::DifferentialDrive::Config c; c.maxDuty=100; c.fullDutyVelocity=kFullDuty; c.kp=0; c.ki=6; c.iMax=765.6f; c.pidMax=1276;
    c.vMin=0; c.posErrMax=127.6f; c.biasMax=303.7f; c.tauAdapt=30; c.aSteady=382.8f; c.stallSpeed=191.4f; c.stallDemand=510.4f; c.stallWindow=500;
    c.twistHoldGain=twistGain; c.cyclePeriod=kPeriodMs; kernel.setConfig(c); kernel.begin();
    left.nextSampleTimeUs=right.nextSampleTimeUs=1000; clock.nowUs=1000; kernel.step(); }
  void odom(){ auto o=kernel.output(); float cpm=engine.countsPerMm(); float dL=(o.positionLeft-pl)/cpm, dR=(o.positionRight-pr)/cpm; pl=o.positionLeft; pr=o.positionRight; float dC=0.5f*(dL+dR), dH=(dR-dL)/engine.effectiveTrackWidth(); float mid=h+0.5f*dH; x+=dC*cosf(mid); y+=dC*sinf(mid); h+=dH; }
  void tick(){ float tL=left.appliedDuty()*kFullDuty*gainL, tR=right.appliedDuty()*kFullDuty*gainR; float a=kDt/(tauS+kDt); vL+=a*(tL-vL); vR+=a*(tR-vR);
    trueL+=vL*kDt; trueR+=vR*kDt; left.nextPositionValue=trueL; right.nextPositionValue=trueR; left.velocityValue=vL; right.velocityValue=vR;
    clock.nowUs+=(uint64_t)kPeriodMs*1000ull; left.nextSampleTimeUs=right.nextSampleTimeUs=clock.nowUs; kernel.step(); odom(); engine.service(); }
};
int main(){
  for(float g: {0.0f, 2.0f}){
    Rig r(g); r.engine.wheelsV(200,200,2000);
    float maxR=0,minL=1e9; for(int i=0;i<80;++i){ r.tick(); float cpm=r.engine.countsPerMm(); maxR=std::max(maxR,r.vR/cpm); minL=std::min(minL,r.vL/cpm); }
    float cpm=r.engine.countsPerMm();
    printf("WHEELS_V 200 200, right wheel +5%%, lag 80ms, twistHoldGain %.0f: after 1.9 s vL=%.0f vR=%.0f mm/s (min vL %.0f, max vR %.0f) heading %.1f deg y=%.0f mm\n", g, r.vL/cpm, r.vR/cpm, minL, maxR, r.h*180/3.14159f, r.y);
  }
  for(float g: {0.0f, 2.0f}){
    Rig r(g); r.engine.moveX(600,0,200,8000); int n=0; while(n<600 && r.engine.isMoveActive()){ r.tick(); ++n; }
    printf("MOVE_X 600 0 200, right wheel +5%%, lag 80ms, twistHoldGain %.0f: ticks %d end (%.0f, %.0f) heading %.1f deg\n", g, n, r.x, r.y, r.h*180/3.14159f);
  }
  return 0; }
