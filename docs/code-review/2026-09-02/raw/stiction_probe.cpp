// stiction_probe.cpp -- NEW engine, non-ideal wheels: breakaway stiction,
// first-order lag, and random stale encoder ticks. Does a 90 deg pivot
// overshoot the way tovez did on 2026-09-04?
#include <cstdio>
#include <cmath>
#include <cstdlib>
#include <vector>
#include "core/diffdrive.h"
#include "motion/motion_engine.h"
#include "fake_ports.h"
static const float kFullDuty = 10795.0f, kDt = 0.024f; static const uint32_t kPeriodMs = 24;
struct Rig {
  FakeMotor left, right; FakeClock clock; FakeSleeper sleeper; FakeFiberLauncher launcher;
  DiffDrive::DifferentialDrive kernel; diffDrive::MotionEngine engine;
  float x=0,y=0,h=0,pl=0,pr=0; float tauS=0, breakaway=0, staleP=0; unsigned seed=1;
  float vL=0,vR=0,trueL=0,trueR=0; bool movL=false,movR=false; int stale=0;
  std::vector<float> dutyR, velR; std::vector<int> staleAt;
  Rig(float trackWidth=128.0f, float slip=0.9617f, float calib=0.7878f)
    : kernel(left,right,clock,sleeper,launcher), engine(kernel,clock) {
    DiffDrive::DifferentialDrive::Config cfg; cfg.maxDuty=100; cfg.fullDutyVelocity=kFullDuty;
    cfg.kp=0; cfg.ki=6; cfg.iMax=765.6f; cfg.pidMax=1276; cfg.vMin=0; cfg.posErrMax=127.6f;
    cfg.biasMax=303.7f; cfg.tauAdapt=30; cfg.aSteady=382.8f; cfg.stallSpeed=191.4f; cfg.stallDemand=510.4f;
    cfg.stallWindow=500; cfg.twistHoldGain=2.0f; cfg.cyclePeriod=kPeriodMs;
    kernel.setConfig(cfg); kernel.begin(); engine.setTrackWidth(trackWidth); engine.setRotationalSlip(slip); engine.setTravelCalib(calib);
    left.nextSampleTimeUs=right.nextSampleTimeUs=1000; clock.nowUs=1000; kernel.step();
  }
  void odom(){ auto o=kernel.output(); float cpm=engine.countsPerMm(); float dL=(o.positionLeft-pl)/cpm, dR=(o.positionRight-pr)/cpm; pl=o.positionLeft; pr=o.positionRight; float dC=0.5f*(dL+dR), dH=(dR-dL)/engine.effectiveTrackWidth(); float mid=h+0.5f*dH; x+=dC*cosf(mid); y+=dC*sinf(mid); h+=dH; }
  float wheel(float cmdCounts, float& v, bool& moving){ // stiction: needs |cmd| >= breakaway (mm/s) to start; keeps moving above 0.5*breakaway
    float cpm=engine.countsPerMm(); float cmdMm=cmdCounts/cpm;
    if(!moving && std::fabs(cmdMm)>=breakaway) moving=true;
    if(moving && std::fabs(cmdMm)<0.5f*breakaway) moving=false;
    float tgt = moving? cmdCounts : 0.0f;
    if(tauS<=0) v=tgt; else { float a=kDt/(tauS+kDt); v+=a*(tgt-v);} return v; }
  void tick(){
    wheel(left.appliedDuty()*kFullDuty, vL, movL); wheel(right.appliedDuty()*kFullDuty, vR, movR);
    trueL+=vL*kDt; trueR+=vR*kDt; left.nextPositionValue=trueL; right.nextPositionValue=trueR; left.velocityValue=vL; right.velocityValue=vR;
    clock.nowUs+=(uint64_t)kPeriodMs*1000ull; left.nextSampleTimeUs=right.nextSampleTimeUs=clock.nowUs;
    bool st = (staleP>0) && ((float)rand_r(&seed)/RAND_MAX < staleP); left.collectSucceeds=!st; right.collectSucceeds=!st; if(st){++stale; staleAt.push_back((int)dutyR.size());}
    kernel.step(); left.collectSucceeds=right.collectSucceeds=true; odom(); engine.service();
    dutyR.push_back(kernel.output().appliedDutyRight); velR.push_back(vR/engine.countsPerMm());
  }
  int run(){ int n=0; while(n<3000 && engine.isMoveActive()){ tick(); ++n; } for(int i=0;i<12;++i) tick(); return n; }
};
static void pivot(const char* label, float cruise, float tau, float brk, float staleP, float accel, float decel, float omegaFloor){
  Rig r; r.tauS=tau; r.breakaway=brk; r.staleP=staleP; r.engine.limits().accel=accel; r.engine.limits().decel=decel; r.engine.limits().omegaFloor=omegaFloor;
  r.engine.moveX(0, 3.14159265f/2, cruise, 5000); int n=r.run();
  float maxD=0; for(float d: r.dutyR) maxD=std::max(maxD,std::fabs(d));
  printf("%-44s cruise %3.0f: ticks %4d yaw %.1f deg (err %+.1f)  stale %d  peak duty %.0f%%\n", label, cruise, n, r.h*180/3.14159265f, r.h*180/3.14159265f-90, r.stale, maxD);
}
int main(){
  printf("== NEW engine, 90 deg pivot, tovez geometry (b=128/0.9617), limits accel/decel 400, omegaFloor 20 ==\n");
  for(float c: {40.f,100.f,200.f}){
    pivot("ideal wheels",                     c, 0,    0,   0,   400,400,20);
    pivot("lag 80 ms",                        c, 0.08f,0,   0,   400,400,20);
    pivot("lag 80 ms + breakaway 70 mm/s",    c, 0.08f,70,  0,   400,400,20);
    pivot("lag 80 + breakaway 70 + 10% stale",c, 0.08f,70,  0.10f,400,400,20);
    pivot("lag 150 + breakaway 70",           c, 0.15f,70,  0,   400,400,20);
    pivot("lag 80 + brk 70, omegaFloor 67",   c, 0.08f,70,  0,   400,400,67);
  }
  return 0;
}
