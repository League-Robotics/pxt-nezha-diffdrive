// shims.cpp -- the MakeCode-facing C++ surface. Composes the DiffDrive
// kernel (self-contained control law) with two NezhaMotorPorts and the
// CODAL platform ports, and adds the application-layer pieces the
// kernel deliberately does not contain:
//
//   - ODOMETRY: differential dead-reckoning from the kernel's Output
//     positions (the kernel is counts-native and has no chassis
//     geometry; track width and travel calibration live HERE).
//   - MOVE ENGINE: position-mode moves (distance+yaw, and goto via the
//     TS layer's arc math) as a start/update/end state machine over the
//     kernel's velocity interface. The TypeScript layer polls
//     updateMove() -- blocking and loop-style forms are both built on
//     that poll. Both updateMove() and the tick engine below share one
//     implementation, serviceMove().
//   - TICK ENGINE (sprint 002): tickDrive() runs one kernel.step() +
//     serviceMove() on the CALLER's own fiber, then self-paces to the
//     next 24 ms deadline. The kernel's own background fiber pacer
//     (start()/run()/fiberEntry()) is deliberately left unwired -- see
//     ensure()'s own comment -- so every control cycle now runs on
//     whichever fiber calls tickDrive() instead.
//   - STARVATION WATCHDOG (sprint 002): the one background fiber this
//     file still launches -- a safety net, not a control path; see its
//     own clearly delineated section below.
//
// Boundary convention: integers only. mm, mm/s, centidegrees,
// centidegrees/s; config values scaled x1000. The TS layer owns the
// cm/deg student units.
//
// Second caller (ticket 003): Protocol's binary motion-verb handlers
// (protocol.cpp) call a small subset of this file's functions directly
// -- startMove, stopAll, estopAll (unchanged), plus two new duration-
// bound primitives added by ticket 003 (setWheelsTimed, driveTwistTimed)
// -- via same-package C++ forward declarations, not through the TS/`//%`
// shim boundary main.ts uses. See protocol.cpp's own forward-declaration
// block for the up-to-date list this file must keep signature-compatible
// with.
#include "pxt.h"
#include "diffdrive.h"
#include "nezha_port.h"
#include "platform_ports.h"

#include <cmath>

using namespace pxt;

namespace diffDrive {

// Forward declaration: the starvation watchdog fiber entry point is
// defined in its own clearly delineated section further down (see
// "starvation watchdog"); ensure() launches it via the same
// CodalFiberLauncher mechanism the kernel used for its own now-unwired
// fiber.
static void watchdogEntry(void* context);

// ---- composition ----------------------------------------------------

struct Rig {
  // tovez-measured defaults; generic kits adjust via setGeometry().
  float travelCalib = 0.7837f;   // [mm/deg] wheel travel per shaft degree
  float trackWidth = 115.0f;     // [mm]
  float countsPerMm() const { return 10.0f / travelCalib; }

  // vevov wiring (stakeholder-measured 2026-08-19: forward was inverted
  // under the old tovez defaults left{2,-1}/right{1,+1} -- both signs
  // flipped so button-A "forward" drives the robot's actual nose-forward).
  NezhaMotorPort left{2, +1};    // left = M2
  NezhaMotorPort right{1, -1};   // right = M1, mirrored
  CodalClock clock;
  CodalSleeper sleeper;
  CodalFiberLauncher launcher;
  DiffDrive::DifferentialDrive kernel{left, right, clock, sleeper,
                                      launcher};

  // odometry [mm, rad], updated lazily from kernel Output
  float x = 0.0f, y = 0.0f, heading = 0.0f;
  float odomPosLeft = 0.0f, odomPosRight = 0.0f;  // [counts]
  bool odomPrimed = false;

  // move engine
  bool moveActive = false;
  float movePosLeft0 = 0.0f, movePosRight0 = 0.0f;  // [counts]
  float moveDistTarget = 0.0f;   // [counts] mean-axis target (signed)
  float moveYawTarget = 0.0f;    // [counts] half-differential target
  uint32_t moveDeadline = 0;     // [ms] lease-aligned backstop

  // tick engine (sprint 002): caller-driven stepping replaces the
  // kernel's own now-unwired fiber pacer -- see ensure(), tickDrive(),
  // and the starvation watchdog section below.
  uint64_t lastTickUs = 0;       // [us] clock.nowMicros() at the start
                                  // of the most recent tickDrive() call
                                  // -- the watchdog's only freshness
                                  // signal. 0 = no tick has run yet.
  uint64_t tickDeadlineUs = 0;   // [us] tickDrive()'s own absolute-
                                  // deadline pacing anchor. 0 = no tick
                                  // has run yet -- re-anchor to now.
  bool stepBusy = false;         // concurrency guard around
                                  // kernel.step() inside tickDrive();
                                  // see that function's own comment.
  uint32_t tickOverrunCount = 0; // Rig-level: tickDrive() calls that ran
                                  // past their own paced deadline.
                                  // Distinct from the kernel's own
                                  // cycleOverrunCount_, which only its
                                  // unused run() ever increments.
};

static Rig* rig = nullptr;

static Rig& ensure() {
  if (rig == nullptr) {
    rig = new Rig();
    // Kernel defaults: the tovez bake (boot_calibration.cpp) with
    // NEUTRAL wheel gains -- a generic kit starts uncorrected.
    DiffDrive::DifferentialDrive::Config cfg;
    cfg.maxDuty = 100.0f;            // [%]
    cfg.fullDutyVelocity = 10795.0f; // [counts/s]
    cfg.kp = 0.0f;
    cfg.ki = 6.0f;                   // [1/s]
    cfg.iMax = 765.6f;               // [counts/s]
    cfg.pidMax = 1276.0f;            // [counts/s]
    cfg.vMin = 255.2f;               // [counts/s]
    cfg.posErrMax = 127.6f;          // [counts]
    cfg.biasMax = 303.7f;            // [counts/s]
    cfg.tauAdapt = 30.0f;            // [s]
    cfg.aSteady = 382.8f;            // [counts/s^2]
    cfg.stallSpeed = 191.4f;         // [counts/s]
    cfg.stallDemand = 510.4f;        // [counts/s]
    cfg.stallWindow = 500.0f;        // [ms]
    cfg.cyclePeriod = 24;            // [ms]
    rig->kernel.setConfig(cfg);
    rig->kernel.begin();   // primes encoders, arms boot zero-write

    // TICK MODEL (sprint 002): the kernel's own background fiber pacer
    // is intentionally left unwired here -- every control cycle now
    // runs on whichever fiber calls tickDrive() (below), not a fiber
    // this file starts. kernel.start()/run()/fiberEntry() stay compiled
    // and available (diffdrive.h/.cpp are byte-unmodified); restoring
    // the single call below re-enables the old free-running fiber-paced
    // mode. See sprint.md's Design Rationale ("pure tick model, fiber
    // pacer entirely unwired -- no dual mode").
    // rig->kernel.start();

    // The starvation watchdog is the only background fiber this sprint
    // leaves running -- launched the same way the kernel used to launch
    // its own (CodalFiberLauncher), so an abandoned tick caller can
    // still be stopped even though no control fiber of this file's own
    // is running. See the "starvation watchdog" section below.
    rig->launcher.launch(&watchdogEntry, rig);
  }
  return *rig;
}

// ---- odometry -------------------------------------------------------

static void odomUpdate(Rig& r) {
  const DiffDrive::DifferentialDrive::Output out = r.kernel.output();
  if (!r.odomPrimed) {
    r.odomPosLeft = out.positionLeft;
    r.odomPosRight = out.positionRight;
    r.odomPrimed = true;
    return;
  }
  const float cpm = r.countsPerMm();
  const float dLeft = (out.positionLeft - r.odomPosLeft) / cpm;    // [mm]
  const float dRight = (out.positionRight - r.odomPosRight) / cpm; // [mm]
  r.odomPosLeft = out.positionLeft;
  r.odomPosRight = out.positionRight;
  const float dCenter = 0.5f * (dLeft + dRight);          // [mm]
  const float dHeading = (dRight - dLeft) / r.trackWidth; // [rad]
  const float midHeading = r.heading + 0.5f * dHeading;
  r.x += dCenter * std::cos(midHeading);
  r.y += dCenter * std::sin(midHeading);
  r.heading += dHeading;
}

// ---- velocity commands ----------------------------------------------

//%
void setWheels(int left, int right) {  // [mm/s] [mm/s]
  Rig& r = ensure();
  const float cpm = r.countsPerMm();
  const float velocity = 0.5f * static_cast<float>(left + right) * cpm;
  const float twist = 0.5f * static_cast<float>(right - left) * cpm;
  r.kernel.drive(velocity, twist,
                 DiffDrive::DifferentialDrive::kLeaseMax);
}

//%
void driveTwist(int speed, int yawRate) {  // [mm/s] [cdeg/s]
  Rig& r = ensure();
  const float cpm = r.countsPerMm();
  const float yawRad =
      static_cast<float>(yawRate) * 0.01f * 3.14159265f / 180.0f;
  const float twist = yawRad * 0.5f * r.trackWidth * cpm;  // [counts/s]
  r.kernel.drive(static_cast<float>(speed) * cpm, twist,
                 DiffDrive::DifferentialDrive::kLeaseMax);
}

// ---- duration-bound direct drive (ticket 003: Protocol's WHEELS and
// MOVE-with-TIME-stop verb handlers) ------------------------------------
// Two small additive primitives, each identical to setWheels()/
// driveTwist() above except the lease is the caller's own duration
// instead of kLeaseMax (kernel.drive()'s own validUntil bookkeeping,
// diffdrive.cpp, already treats an expired lease as neutral every
// subsequent step() -- see that file's `if (leaseExpired) effective =
// kModeNeutral;` -- so no separate timer/callback is needed here: the
// kernel's own real-time fiber auto-neutralizes at the deadline, the
// same backstop mechanism the move engine's own `moveDeadline` already
// leans on). Deliberately NOT `//%`-annotated: the block API never
// needed a duration-bound direct-drive primitive (every block-facing use
// case is already served by setWheels/driveTwist or the move engine), so
// these stay C++-internal to avoid exposing a new, un-asked-for block
// (sprint.md Architecture, Impact). Protocol (protocol.cpp) is their only
// caller, via its own same-package forward declarations.
void setWheelsTimed(int left, int right,
                    uint32_t durationMs) {  // [mm/s] [mm/s] [ms]
  Rig& r = ensure();
  r.moveActive = false;  // WHEELS supersedes any in-flight move-engine move
  const float cpm = r.countsPerMm();
  const float velocity = 0.5f * static_cast<float>(left + right) * cpm;
  const float twist = 0.5f * static_cast<float>(right - left) * cpm;
  r.kernel.drive(velocity, twist, durationMs);
}

void driveTwistTimed(int speed, int yawRate,
                     uint32_t durationMs) {  // [mm/s] [cdeg/s] [ms]
  Rig& r = ensure();
  r.moveActive = false;  // supersedes any in-flight move-engine move
  const float cpm = r.countsPerMm();
  const float yawRad =
      static_cast<float>(yawRate) * 0.01f * 3.14159265f / 180.0f;
  const float twist = yawRad * 0.5f * r.trackWidth * cpm;  // [counts/s]
  r.kernel.drive(static_cast<float>(speed) * cpm, twist, durationMs);
}

// ---- move engine ----------------------------------------------------

//%
void startMove(int distance, int yaw, int speed, int yawRate) {
  // [mm] [cdeg] [mm/s] [cdeg/s]
  Rig& r = ensure();
  odomUpdate(r);
  const float cpm = r.countsPerMm();
  const DiffDrive::DifferentialDrive::Output out = r.kernel.output();
  r.movePosLeft0 = out.positionLeft;
  r.movePosRight0 = out.positionRight;
  r.moveDistTarget = static_cast<float>(distance) * cpm;  // [counts]
  const float yawRad =
      static_cast<float>(yaw) * 0.01f * 3.14159265f / 180.0f;
  r.moveYawTarget = yawRad * 0.5f * r.trackWidth * cpm;   // [counts]

  const float speedCounts =
      static_cast<float>(speed > 0 ? speed : 1) * cpm;    // [counts/s]
  const float yawRadPerS =
      static_cast<float>(yawRate > 0 ? yawRate : 1) * 0.01f *
      3.14159265f / 180.0f;
  const float twistCounts = yawRadPerS * 0.5f * r.trackWidth * cpm;

  // One duration covers both axes -> simultaneous arc completion.
  float duration = 0.0f;  // [s]
  if (r.moveDistTarget != 0.0f)
    duration = std::fabs(r.moveDistTarget) / speedCounts;
  if (r.moveYawTarget != 0.0f) {
    const float yawDuration = std::fabs(r.moveYawTarget) / twistCounts;
    if (yawDuration > duration) duration = yawDuration;
  }
  if (duration <= 0.0f) return;  // nothing to do

  const float velocity = r.moveDistTarget / duration;  // [counts/s]
  const float twist = r.moveYawTarget / duration;      // [counts/s]
  const uint32_t lease =
      static_cast<uint32_t>(duration * 1000.0f) + 500u;  // [ms] backstop
  r.kernel.drive(velocity, twist, lease);
  r.moveActive = true;
  r.moveDeadline = static_cast<uint32_t>(
      r.clock.nowMicros() / 1000ull) + lease;
}

// serviceMove(): odometry update + progress/deadline/stall check +
// kernel.neutral() on done -- the body previously inline in
// updateMove(), pulled out so both the old poll path (updateMove(),
// below) and the new tick path (tickDrive(), in the tick engine section
// below) share one implementation. INVARIANT: no fiber_sleep/yield
// anywhere in this function or anything it calls -- that is what keeps
// one Rig read-modify-write atomic across whichever fiber happens to be
// calling in (a student's TS loop, the wire protocol, tickDrive()
// itself). Returns the post-check moveActive state.
static bool serviceMove(Rig& r) {
  if (!r.moveActive) return false;
  odomUpdate(r);
  const DiffDrive::DifferentialDrive::Output out = r.kernel.output();
  const float dLeft = out.positionLeft - r.movePosLeft0;    // [counts]
  const float dRight = out.positionRight - r.movePosRight0; // [counts]
  const float meanProgress = 0.5f * (dLeft + dRight);
  const float diffProgress = 0.5f * (dRight - dLeft);

  const float margin = 25.0f;  // [counts] ~2 mm decel allowance
  bool distDone = true;
  if (r.moveDistTarget != 0.0f) {
    distDone = std::fabs(meanProgress) >=
               std::fabs(r.moveDistTarget) - margin;
  }
  bool yawDone = true;
  if (r.moveYawTarget != 0.0f) {
    yawDone = std::fabs(diffProgress) >=
              std::fabs(r.moveYawTarget) - margin;
  }
  const uint32_t nowMs =
      static_cast<uint32_t>(r.clock.nowMicros() / 1000ull);
  const bool expired = static_cast<int32_t>(nowMs - r.moveDeadline) >= 0;

  if ((distDone && yawDone) || expired || out.stallHalted) {
    r.kernel.neutral();
    r.moveActive = false;
    return false;
  }
  return true;
}

//%
bool updateMove() {
  if (rig == nullptr) return false;
  return serviceMove(*rig);
}

// ---- tick engine (sprint 002) -----------------------------------------
// tickDrive(): the caller-driven replacement for the kernel's own
// now-unwired fiber. Runs exactly one kernel.step() + serviceMove() on
// the CALLER's fiber every time it is called, then self-paces to the
// next absolute 24 ms deadline before returning -- the same
// absolute-deadline pacing DifferentialDrive::run() uses
// (diffdrive.cpp:290-306), lifted here since run() itself is no longer
// wired to anything. The deadline is anchored to the previous tick's
// own deadline while calls stay consecutive (no drift accumulates from
// per-call scheduling jitter); a gap since the last recorded deadline
// re-anchors to now instead of trying to "catch up" a burst of overdue
// ticks.
//
// Always executes the step, even with no move active and no continuous
// command in force -- see sprint.md's Design Rationale: a
// while (_tickDrive()) loop driving setWheelSpeeds()/driveTwist() must
// step the kernel on every call, or continuous-mode driving would never
// progress. The returned bool reports moveActive AFTER this call's
// serviceMove() ran, so a position-mode move's final tick still returns
// false, ending a while (_tickDrive()) loop on the same call that
// finishes the move (no extra idle tick).
//%
bool tickDrive() {
  Rig& r = ensure();
  const uint64_t cycleStartUs = r.clock.nowMicros();
  r.lastTickUs = cycleStartUs;  // the watchdog's only freshness signal

  // Concurrency guard: check-and-set with no intervening yield is
  // atomic on CODAL's cooperative fibers, so this is safe against a
  // second fiber also calling tickDrive() -- it just waits (a short
  // timed poll, since the busy fiber may itself be parked in step()'s
  // settle sleeps) until the flag clears rather than racing
  // kernel.step().
  while (r.stepBusy) {
    r.sleeper.sleepMillis(1);
  }
  r.stepBusy = true;
  r.kernel.step();
  r.stepBusy = false;

  const bool moveActive = serviceMove(r);

  // Absolute-deadline self-pacing, lifted from DifferentialDrive::run()
  // (diffdrive.cpp:290-306): read the cadence from the kernel's own
  // config (still 24 ms per sprint.md's Design Rationale) rather than
  // duplicating the constant here.
  const uint64_t periodUs =
      static_cast<uint64_t>(r.kernel.config().cyclePeriod) * 1000ull;
  const bool consecutive =
      r.tickDeadlineUs != 0 && cycleStartUs < r.tickDeadlineUs + periodUs;
  const uint64_t deadlineUs =
      consecutive ? r.tickDeadlineUs + periodUs : cycleStartUs + periodUs;
  r.tickDeadlineUs = deadlineUs;

  const uint64_t nowUs = r.clock.nowMicros();
  if (nowUs < deadlineUs) {
    const uint32_t shortfallMs =
        static_cast<uint32_t>((deadlineUs - nowUs + 999) / 1000);
    r.sleeper.sleepMillis(shortfallMs);
  } else {
    ++r.tickOverrunCount;
    r.sleeper.yield();
  }

  return moveActive;
}

// cycleStat(): read-only tick/cycle diagnostics for desk verification
// (and future wire-protocol reporting). 0 = measured cycle period [us],
// 1 = measured busy time [us] (both straight off the kernel's own
// Output, unaffected by who calls step()); 2 = the Rig-level
// tick-overrun counter above (NOT the kernel's own cycleOverrunCount_,
// which only its unused run() increments); 3 = cycleCount (existing
// kernel Output field, likewise unaffected by who calls step()).
// Deliberately NOT exposing more than these four fields -- diagValue()
// above already covers the rest of Output for the wire protocol's DIAG
// verb.
//%
int cycleStat(int which) {
  Rig& r = ensure();
  const DiffDrive::DifferentialDrive::Output out = r.kernel.output();
  switch (which) {
    case 0: return static_cast<int>(out.cyclePeriodMeasured);
    case 1: return static_cast<int>(out.cycleBusy);
    case 2: return static_cast<int>(r.tickOverrunCount);
    case 3: return static_cast<int>(out.cycleCount);
    default: return 0;
  }
}

// ---- starvation watchdog (sprint 002) ----------------------------------
// The ONLY background fiber this sprint leaves running (every other
// control cycle now runs on whichever caller's fiber invokes
// tickDrive() above). Purely a safety net -- it never drives, only
// stops -- guaranteeing "the robot only moves while something ticks" is
// actually true even when a tick caller (a student's loop, a wire
// session) disappears mid-move. Launched from ensure() via the same
// CodalFiberLauncher the kernel used for its own now-unwired fiber.
//
// Every ~50 ms: if something looks like it is actively commanding the
// wheels AND it has been more than ~100 ms (about 4 tick periods) since
// the last tickDrive() call, force a stop DIRECTLY at the motor-port
// level -- NOT through kernel.neutral() alone, which only takes effect
// on the next step() and may never run again if the caller has truly
// abandoned its loop. This reuses NezhaMotorPort::emergencyStop()
// (nezha_port.cpp:80-85), already proven tick-independent by its
// exact-zero short-circuit in writeShapedDuty(). kernel.neutral() is
// still called too, so whichever fiber resumes ticking finds the
// kernel's own commanded mode already neutral instead of stale.
//
// This is a resumable SOFT stop, a third flavor distinct from both the
// block API's stop() (kernel.neutral(), takes effect on the next step()
// only) and emergencyStop() (kernel.estop() latch + port zero): it
// never touches kernel.estop()/estopLatch_, so a fresh tickDrive() call
// (a new move, or a resumed driveTick() loop) resumes motion
// immediately, with no clearEmergencyStop() needed. See sprint.md's
// Design Rationale ("the starvation watchdog stops at the port level,
// not via the kernel's e-stop latch").
//
// Note: while abandonment persists, this fires on every ~50 ms poll,
// not just once -- kernel.neutral()/moveActive=false/the port zero
// write are all idempotent, and re-asserting zero is the conservative
// choice given commandLooksActive() below can only see stale state
// (nothing refreshes Output without a step()) until ticking resumes.

static constexpr uint32_t kWatchdogPeriodMs = 50;          // [ms]
static constexpr uint64_t kWatchdogTimeoutUs = 100000ull;  // [us] ~4 periods

// The kernel exposes no direct "is the commanded mode non-neutral"
// accessor (Command::mode is private, read only inside step()).
// appliedDutyLeft/Right -- the last duty actually WRITTEN to a motor
// port -- is the most honest available proxy for "is something
// currently driving the wheels": writeShapedDuty()'s exact-zero
// short-circuit (nezha_port.cpp) means a genuinely neutral commanded
// mode reads back as exactly zero here, with no separate Rig-level
// "driving" flag needed. Combined with moveActive, this covers both
// continuous-drive (setWheels/driveTwist and their timed variants) and
// move-engine abandonment.
static bool commandLooksActive(const Rig& r) {
  if (r.moveActive) return true;
  const DiffDrive::DifferentialDrive::Output out = r.kernel.output();
  return out.appliedDutyLeft != 0.0f || out.appliedDutyRight != 0.0f;
}

static void watchdogEntry(void* context) {
  Rig& r = *static_cast<Rig*>(context);
  while (true) {
    r.sleeper.sleepMillis(kWatchdogPeriodMs);
    const uint64_t nowUs = r.clock.nowMicros();
    const uint64_t sinceLastTickUs = nowUs - r.lastTickUs;
    if (sinceLastTickUs <= kWatchdogTimeoutUs) continue;
    if (!commandLooksActive(r)) continue;
    r.kernel.neutral();      // commands neutral for whenever step() next runs
    r.moveActive = false;
    r.left.emergencyStop();  // port-level zero write, NOW, tick-independent
    r.right.emergencyStop();
  }
}

//%
bool moving() { return rig != nullptr && rig->moveActive; }

//%
int progress() {  // [0..1000]
  if (rig == nullptr || !rig->moveActive) return 1000;
  Rig& r = *rig;
  const DiffDrive::DifferentialDrive::Output out = r.kernel.output();
  const float dLeft = out.positionLeft - r.movePosLeft0;
  const float dRight = out.positionRight - r.movePosRight0;
  float fraction = 1.0f;
  if (r.moveDistTarget != 0.0f) {
    const float f = std::fabs(0.5f * (dLeft + dRight)) /
                    std::fabs(r.moveDistTarget);
    if (f < fraction) fraction = f;
  }
  if (r.moveYawTarget != 0.0f) {
    const float f = std::fabs(0.5f * (dRight - dLeft)) /
                    std::fabs(r.moveYawTarget);
    if (f < fraction) fraction = f;
  }
  if (fraction < 0.0f) fraction = 0.0f;
  if (fraction > 1.0f) fraction = 1.0f;
  return static_cast<int>(fraction * 1000.0f);
}

//%
void endMove() {
  if (rig == nullptr) return;
  if (rig->moveActive) {
    rig->kernel.neutral();
    rig->moveActive = false;
  }
}

// ---- stopping -------------------------------------------------------

//%
void stopAll() {
  Rig& r = ensure();
  r.moveActive = false;
  r.kernel.neutral();
}

//%
void estopAll() {
  Rig& r = ensure();
  r.moveActive = false;
  r.kernel.estop();
  r.kernel.emergencyStopMotors();
}

//%
void estopClear() { ensure().kernel.estopClear(); }

// Kernel Output diagnostics accessor for the wire protocol's DIAG verb
// (protocol.cpp is the only caller, via forward declaration -- same
// convention as setWheelsTimed/getConfigValue above). Returns one field
// per call as an int; floats are scaled x100. Not //%-annotated: not a
// block, C++-internal only.
int diagValue(int what) {
  const DiffDrive::DifferentialDrive::Output out = ensure().kernel.output();
  switch (what) {
    case 0: return out.ready ? 1 : 0;
    case 1: return out.estopped ? 1 : 0;
    case 2: return out.stallHalted ? 1 : 0;
    case 3: return out.leaseExpired ? 1 : 0;
    case 4: return out.connectedLeft ? 1 : 0;
    case 5: return out.connectedRight ? 1 : 0;
    case 6: return out.wedgeSuspectLeft ? 1 : 0;
    case 7: return out.wedgeSuspectRight ? 1 : 0;
    case 8: return static_cast<int>(out.i2cFaultCount);
    case 9: return static_cast<int>(out.leaseExpiryCount);
    case 10: return static_cast<int>(out.positionLeft);
    case 11: return static_cast<int>(out.positionRight);
    case 12: return static_cast<int>(out.appliedDutyLeft * 100.0f);
    case 13: return static_cast<int>(out.appliedDutyRight * 100.0f);
    case 14: return static_cast<int>(out.velocityLeft);
    case 15: return static_cast<int>(out.velocityRight);
    case 16: return static_cast<int>(out.cycleCount);
    case 17: return (out.satLeft ? 1 : 0) | (out.satRight ? 2 : 0);
    case 18: return (out.deficitLeft ? 1 : 0) | (out.deficitRight ? 2 : 0);
    case 19: return static_cast<int>(out.cycleOverrunCount);
    // 20: latched first refusal (Status enum: 0 ok, 1 unconfigured,
    // 2 not-begun, 3 estopped, 4 non-finite, 5 cadence-preserved).
    case 20:
      return static_cast<int>(ensure().kernel.lastError());
    default: return 0;
  }
}

// ---- pose -----------------------------------------------------------

//%
int poseX() {  // [mm]
  Rig& r = ensure();
  odomUpdate(r);
  return static_cast<int>(std::lround(r.x));
}

//%
int poseY() {  // [mm]
  Rig& r = ensure();
  odomUpdate(r);
  return static_cast<int>(std::lround(r.y));
}

//%
int poseHeading() {  // [cdeg]
  Rig& r = ensure();
  odomUpdate(r);
  return static_cast<int>(
      std::lround(r.heading * 180.0f / 3.14159265f * 100.0f));
}

//%
void resetPose() {
  Rig& r = ensure();
  odomUpdate(r);  // consume any pending deltas first
  r.x = 0.0f;
  r.y = 0.0f;
  r.heading = 0.0f;
}

// ---- configuration --------------------------------------------------

//%
void setGeometry(int trackWidth, int calib) {  // [0.1 mm] [1e-4 mm/deg]
  Rig& r = ensure();
  if (trackWidth > 0) r.trackWidth = static_cast<float>(trackWidth) * 0.1f;
  if (calib > 0) r.travelCalib = static_cast<float>(calib) * 1e-4f;
}

//%
void setKernelValue(int field, int value) {  // [x1000 scaled]
  Rig& r = ensure();
  const float v = static_cast<float>(value) * 0.001f;
  DiffDrive::DifferentialDrive& k = r.kernel;
  switch (field) {
    case 0: k.setMaxDuty(v); break;
    case 1: k.setFullDutyVelocity(v); break;
    case 2: k.setKp(v); break;
    case 3: k.setKi(v); break;
    case 4: k.setIMax(v); break;
    case 5: k.setKaff(v); break;
    case 6: k.setPidMax(v); break;
    case 7: k.setTwistHoldGain(v); break;
    case 8: k.setSpeedFloor(v); break;
    case 9: k.setPositionErrorMax(v); break;
    case 10: k.setStall(v, k.config().stallDemand,
                        k.config().stallWindow); break;
    case 11: k.setStall(k.config().stallSpeed, v,
                        k.config().stallWindow); break;
    case 12: k.setStall(k.config().stallSpeed, k.config().stallDemand,
                        v); break;
    case 13: k.setLambdaEnabled(v != 0.0f); break;
    case 14: k.setCrawlPulse(v); break;
    default: break;
  }
}

// ---- config read-back (ticket 004: Protocol's GET_CONFIG verb handler) --
// The read-back counterpart to setKernelValue() above: same field-ordinal
// switch, same x1000 scaling convention, reading from
// DiffDrive::DifferentialDrive::config() -- the kernel's own existing
// accessor (unchanged, vendored; setKernelValue's cases 10-12 already read
// through it for their untouched two stall fields, above). `config()`
// returns the kernel's `staged_` Config, which every `setXxx()` writes
// synchronously and unconditionally -- there is no separate "applied"
// copy to lag behind it -- so this always reflects the true current
// value, whether it was last set over the wire (setKernelValue, via
// CONFIG/SET_FIELD) or via a MakeCode `set config` block in the same
// running program: both paths call this exact same setKernelValue(), into
// this exact same kernel Config. No kernel change: config() already
// existed; only this shim-layer getter is new (sprint.md Architecture
// Impact). Deliberately NOT `//%`-annotated -- like setWheelsTimed/
// driveTwistTimed (ticket 003), the block API never needed a read-back
// primitive (its `set config` block is write-only), so this stays
// C++-internal; Protocol (protocol.cpp) is its only caller, via its own
// same-package forward declaration. An out-of-range field returns 0 --
// protocol.cpp's handleGetConfig() validates the field range itself
// before ever calling this, so `default` here is an unreachable-in-
// practice guard, not a relied-upon behavior.
int getConfigValue(int field) {  // -> [x1000 scaled]
  Rig& r = ensure();
  const DiffDrive::DifferentialDrive::Config c = r.kernel.config();
  float v = 0.0f;
  switch (field) {
    case 0: v = c.maxDuty; break;
    case 1: v = c.fullDutyVelocity; break;
    case 2: v = c.kp; break;
    case 3: v = c.ki; break;
    case 4: v = c.iMax; break;
    case 5: v = c.kaff; break;
    case 6: v = c.pidMax; break;
    case 7: v = c.twistHoldGain; break;
    case 8: v = c.vMin; break;
    case 9: v = c.posErrMax; break;
    case 10: v = c.stallSpeed; break;
    case 11: v = c.stallDemand; break;
    case 12: v = c.stallWindow; break;
    case 13: v = c.lambdaEnabled ? 1.0f : 0.0f; break;
    case 14: v = c.crawlPulse; break;
    default: return 0;
  }
  return static_cast<int>(std::lround(v * 1000.0));
}

}  // namespace diffDrive
