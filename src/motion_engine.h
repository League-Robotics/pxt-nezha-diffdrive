// motion_engine.h -- diffDrive::MotionEngine: the two-primitive reduction
// this project's motion surface is built on. Canonical spec (read-only,
// a different repo -- this project conforms to its grammar, it does not
// vendor its C++): radio-robot-lib/docs/design/motion-api.md S2
// ("Everything is constant-ratio wheel segments") and S2.1 ("b is the
// effective track width") are the whole design; read those two sections
// first.
//
// Host-portable by construction: this file and motion_engine.cpp include
// nothing but <cstdint>/<cmath> and diffdrive.h -- no pxt.h, no CODAL
// type, anywhere -- so the native host test harness (tests/host/) links
// and exercises this class with no micro:bit involved, and both call
// paths this sprint is building (main.ts's block API via shims.cpp, and
// the wire adapter, wire_adapter.cpp) are meant to eventually share this
// one implementation instead of duplicating the math (sprint.md Design
// Rationale: "motion_engine exposes one lazy-singleton instance ...
// reached by both shims.cpp and wire_adapter.cpp").
//
// TWO PRIMITIVES (motion-api.md S1/S2). Everything else in the six-
// operation Motion API reduces onto these; sprint 003 ticket 006
// implemented only these two plus the geometry they both depend on.
//
//   wheelsX(left, right, cruise, timeout) -- per-wheel commanded
//     DISTANCE [mm], ratio-locked so both wheels finish together
//     (motion-api.md S3.1); bounded by a dead-reckoned duration at the
//     dominant wheel's cruise ceiling, capped by `timeout`'s backstop.
//     No prior primitive in this codebase commands independent
//     per-wheel distances -- this is genuinely new.
//   wheelsV(left, right, duration) -- per-wheel commanded VELOCITY
//     [mm/s], held for `duration` [ms] -- `duration` IS the kernel's own
//     lease, the same field, same meaning (motion-api.md S3.2). This is
//     shims.cpp's existing setWheels()/driveTwist()/setWheelsTimed()/
//     driveTwistTimed() velocity-hold behavior, renamed and given one
//     home instead of four call sites computing the same math. Both
//     primitives now also clear the move-engine's own in-flight state
//     (see MOVE ENGINE below) -- motion-api.md S6: "wheels_* clears the
//     planner."
//
// MOVE ENGINE (motion-api.md S3.3-S3.5), sprint 003 ticket 007. The
// taper/ramp/wrong-way-abort/settle SHAPING that used to live in
// shims.cpp's Rig::serviceMove()/startMove() moves here verbatim
// (algorithm unchanged, only its home and calling convention), restated
// as the three reductions:
//
//   moveX(distance, rotation, cruise, timeout) -- body distance [mm] +
//     heading change [rad] CCW+, reduced onto wheelsX's ratio math
//     (distance -+ rotation*b/2). |rotation| >= 50 deg
//     (kTurnFirstAngleRad, motion-api.md S3.3's measured
//     `turn_first_angle`) with a nonzero distance is NOT one segment:
//     pivot to the new heading first, then travel the remainder
//     straight -- queued internally as one caller-visible moveX() call.
//     A live encoder-progress check (not just the dead-reckoned lease
//     wheelsX alone provides) is what stops each segment on arrival;
//     `timeout` is a REAL backstop tracked independently of that,
//     spanning the whole call (both phases, if two).
//   moveV(vx, omega, duration) -- the plain wheelsV reduction, no
//     shaping (a velocity hold has no "end" to taper toward).
//   goToR(x, y, speed, arrive, timeout) -- the spec's arc reduction
//     (turn angle theta = 2*atan2(y,x), arc length motion-api.md S3.5),
//     but goToR OWNS its own pivot-vs-blend split decision rather than
//     inheriting moveX()'s generic one (sprint 006, KERN-02): moveX()'s
//     |rotation| >= 50 deg split reissues theta/arc-length as pivot-
//     then-straight, which lands at a DIFFERENT endpoint than the
//     blended arc whenever it fires (arc length != chord length except
//     in the limit) -- goToR() instead pivots to the line-of-sight
//     bearing (atan2(y,x)) then drives the straight-line chord
//     (hypot(x,y)), which reaches (x, y) exactly, by construction.
//     `theta` is normalized to the short arc, (-pi, pi], before this
//     split decision (and before the plain-arc branch below threshold
//     uses it) -- doubling atan2's own principal value can otherwise
//     land up to just under +-2*pi, which is "the long way around" the
//     same constant-curvature circle as the short, wrapped angle (both
//     reach the same (x, y), but only the short one is a sane distance
//     to drive); this is what keeps a target nearly directly behind the
//     robot from being driven the long way around a huge circle
//     (sprint 006, KERN-03). `arrive` is now honored as a radial no-op
//     gate (sprint 006, KERN-04): `hypot(x, y) <= arrive` issues no
//     segment at all -- still a single-shot reduction, not the
//     supervisory re-solving loop motion-api.md S3.5 describes; a caller
//     that wants that re-issues goToR itself. This heuristic-free
//     reduction remains distinct from this project's own goToWorld() in
//     main.ts, a separate, TS-level turn-first/capped-curvature call
//     path (sprint.md Design Rationale: two paths sharing one primitive,
//     not one implementation).
//   goToW(pose, x, y, speed, arrive, timeout) -- sprint 003 ticket 010,
//     the WORLD-frame counterpart: motion-api.md S3.6, "go_to_w(x, y) ==
//     read pose -> world-to-body -> go_to_r". Reads `pose`'s current
//     (x, y, heading), rotates the world-frame delta into the body frame,
//     and delegates to goToR() above -- same single-shot, no-
//     supervisory-re-solve posture, same separateness from goToWorld()'s
//     own TS-level heuristic. `pose` is a PoseSource reference supplied
//     PER CALL (see the PoseSource class below) -- motion-api.md S9.3
//     item 3: "go_to_w's pose source is pluggable rather than assuming
//     an OTOS is fitted", because the fleet is not uniform (S3.6's own
//     `gopiv` example has no OTOS at all). MotionEngine holds no
//     PoseSource of its own; the caller (a wire adapter, a shim) chooses
//     which one to pass, which is what makes this class host-testable
//     with a fake pose with no OTOS anywhere in the link.
//
// serviceMove() is the per-tick advance: callers (shims.cpp's
// updateMove()/tickDrive(), formerly Rig::serviceMove()'s only callers)
// invoke it once per control cycle while isMoveActive() to re-scale the
// taper/ramp, check completion/deadline/stall/wrong-way, and reissue
// kernel_.drive() every tick while active -- the same "cheap, lease-safe
// reissue" scheme the code it is extracted from used, because gating
// reissues on a scale CHANGE would let the lease expire during any
// steady phase. Odometry (Rig's x/y/heading) stays OUT of this class --
// it is a shims.cpp/Rig concern this ticket does not move -- so callers
// must update it themselves around serviceMove(), exactly as the code
// this is extracted from did inside the old free-function serviceMove().
//
// GEOMETRY (motion-api.md S2.1): `effectiveTrackWidth()` is a METHOD,
// deliberately never a stored field, computed as `trackWidth /
// rotationalSlip` every time it is asked for -- so a config read-back
// can never report a derived number as though it had been measured.
// `trackWidth` itself is NEVER "corrected" to make a turn land -- it is
// the one independently-verifiable number in the robot's geometry (a
// caliper reaches it). All rotational scrub correction belongs in
// `rotationalSlip`, separately measurable against camera truth; keeping
// the two apart is what lets a bad turn be diagnosed instead of merely
// compensated (S2.1, and this project's own standing rule -- see this
// repo's CLAUDE.md/sprint.md Success Criteria).
//
// SIGN CONVENTION, unchanged from the code this class is extracted from
// and from motion-api.md S2.1: CCW-positive. A positive twist/rotation
// turns LEFT and increases camera yaw; the left wheel is the slower one
// in a left turn. This is NOT re-derived from cable order anywhere in
// this file -- see tests/host/test_motion_engine_primitives.py's own
// explicit sign-convention tests, written so a future cable-order "fix"
// fails a test instead of shipping (this project has shipped that exact
// bug and patched it four times downstream).
#pragma once

#include <cstdint>

#include "diffdrive.h"

namespace diffDrive {

// PoseSource -- a minimal world-pose read port for goToW() (motion-api.md
// S3.6, S9.3 item 3: "the pose source is pluggable... OTOS when fitted,
// encoder odometry otherwise"). Three reads, nothing else -- alongside
// DiffDrive::Motor/Clock/Sleeper in spirit (a small port a caller
// implements against its own platform), no CODAL/PXT dependency, so a
// future robot with no OTOS at all (motion-api.md S3.6's own `gopiv`
// example) can supply a trivial always-stale implementation without
// breaking the interface, and the host test harness can supply a fake
// with no OTOS anywhere in the link. `OtosPort` (src/otos_port.h)
// implements this for hardware; `FakePoseSource`
// (tests/host/fake_pose_source.h) implements it for tests.
class PoseSource {
 public:
  virtual ~PoseSource() = default;

  virtual float x() const = 0;        // [mm] world frame
  virtual float y() const = 0;        // [mm] world frame
  virtual float heading() const = 0;  // [rad] world frame, CCW+ (unwrapped)
};

class MotionEngine {
 public:
  // `kernel`/`clock` are constructed and owned by the CALLER (shims.cpp's
  // Rig for hardware; the host test harness's own fixture for tests) --
  // this class only ever holds references, exactly the way
  // DiffDrive::DifferentialDrive itself holds references to its own
  // Motor/Clock/Sleeper/FiberLauncher ports rather than owning them.
  // `clock` is new in ticket 007: the move engine's ramp (elapsed time
  // since a segment started) and its `timeout` backstop both need wall
  // time independent of whether/when the kernel has last step()'d, which
  // wheelsX/wheelsV never needed (kernel_.drive() reads ITS OWN clock_
  // reference internally to stamp a lease's `validUntil`; that reference
  // is private to DifferentialDrive, so the move engine needs its own).
  // Geometry defaults below are the tovez/vevov bake this class is
  // extracted from (shims.cpp's former Rig fields) -- see this class's
  // own field comments for the measurement behind each.
  MotionEngine(DiffDrive::DifferentialDrive& kernel,
               const DiffDrive::Clock& clock);

  // ---- geometry (motion-api.md S2.1) ----

  // [mm/deg] wheel travel per shaft degree; 1 count == 0.1 shaft degree,
  // so counts-per-mm is 10 / travelCalib.
  float travelCalib() const { return travelCalib_; }
  void setTravelCalib(float mmPerDeg) { travelCalib_ = mmPerDeg; }

  // [mm] the CALIPER-MEASURED track width. Never adjust this to correct
  // a turn -- see this file's header comment and motion-api.md S2.1.
  float trackWidth() const { return trackWidth_; }
  void setTrackWidth(float mm) { trackWidth_ = mm; }

  // [1] physical/odometric rotation ratio (wheel-contact scrub),
  // camera-measured against ground truth. This is where ALL rotational
  // correction lives -- never trackWidth. Read-only for now: no caller
  // in this codebase has ever needed to set it at runtime (mirrors the
  // Rig field this is extracted from, which had no setter either).
  float rotationalSlip() const { return rotationalSlip_; }

  // [counts/mm] 1 count == 0.1 shaft degree.
  float countsPerMm() const { return 10.0f / travelCalib_; }

  // [mm] b = trackWidth / rotationalSlip (motion-api.md S2.1) -- a
  // METHOD, computed fresh on every call, deliberately never cached into
  // a field so a config read-back can never report a derived number as
  // though it had been measured.
  float effectiveTrackWidth() const { return trackWidth_ / rotationalSlip_; }

  // ---- the two primitives (motion-api.md S3.1/S3.2) ----

  // wheels_v(left, right, duration): hold each wheel at a commanded
  // velocity [mm/s] for `duration` [ms] -- duration IS the kernel's
  // lease, no reinterpretation. Byte-for-byte the math shims.cpp's
  // setWheels()/driveTwist()/setWheelsTimed()/driveTwistTimed() already
  // perform: velocity = mean(left, right), twist = half-differential
  // (right - left) -- CCW-positive, per this file's header comment.
  // Clears any in-flight moveX()/goToR() move first (motion-api.md S6:
  // "wheels_* clears the planner" -- exactly one subsystem owns motion).
  void wheelsV(float left, float right, uint32_t durationMs);

  // wheels_x(left, right, cruise, timeout): move each wheel a commanded
  // DISTANCE [mm] at a ratio locked to `cruise` [mm/s] (the DOMINANT
  // wheel's ceiling, motion-api.md S3.1) so both wheels finish together.
  // This primitive's bound is dead-reckoned: the dominant wheel's own
  // commanded distance divided by cruise gives the lease, capped by the
  // required `timeout` [ms] backstop -- no live encoder-progress check;
  // that closed-loop stop condition is moveX()'s own shaping layer,
  // below, built on top of this primitive's kinematics, not inside it.
  // A zero-magnitude command (both wheels commanding no distance) or a
  // non-positive cruise is a no-op -- nothing is driven. Clears any
  // in-flight moveX()/goToR() move first, same as wheelsV() above.
  void wheelsX(float left, float right, float cruise, uint32_t timeoutMs);

  // ---- move engine (motion-api.md S3.3-S3.5), sprint 003 ticket 007 --
  // see this file's header comment for the shape of each reduction. ----

  // move_x(distance, rotation, cruise, timeout): see header comment.
  // Supersedes any in-flight move (this call's own prior phase, or a
  // previous moveX()/goToR() never finished) -- exactly one moveX()-
  // family move is ever active at a time.
  void moveX(float distance, float rotation, float cruise,
             uint32_t timeoutMs);

  // move_v(vx, omega, duration): the plain wheelsV reduction --
  // vx +- omega*b/2 -- held for `duration`, no shaping. CCW-positive,
  // per this file's header comment.
  void moveV(float vx, float omega, uint32_t durationMs);

  // go_to_r(x, y, speed, arrive, timeout): see header comment. `x`
  // forward, `y` left, both [mm]; `speed` is the resulting segment's
  // cruise. A target within `arrive` [mm] of the current position
  // (radially: `hypot(x, y) <= arrive`; (0, 0) with any `arrive >= 0`
  // is included) is a no-op -- nothing is driven (sprint 006, KERN-04).
  // Otherwise this method makes its OWN pivot-vs-blend split decision
  // (sprint 006, KERN-02/03) instead of inheriting moveX()'s generic
  // one -- see header comment for why, and for the short-arc
  // normalization applied to the arc angle before that decision.
  void goToR(float x, float y, float speed, float arrive,
             uint32_t timeoutMs);

  // go_to_w(x, y, speed, arrive, timeout): see header comment. `x`, `y`
  // are WORLD-frame [mm]; `pose` supplies the current world pose this
  // call reads ONCE, at call time -- not stored. Rotates the world-frame
  // delta (x - pose.x(), y - pose.y()) into the body frame by
  // -pose.heading() (this file's CCW-positive convention) and delegates
  // to goToR() above. A target equal to the current pose reduces to a
  // (0, 0) body-frame delta, which goToR() already treats as a no-op.
  void goToW(const PoseSource& pose, float x, float y, float speed,
             float arrive, uint32_t timeoutMs);

  // Advance the current move by one control cycle. See header comment
  // for the full contract (taper/ramp/deadline/wrong-way, one reissue
  // per call while active, neutral-on-end). No-op (returns false) if no
  // move is active. Callers own odometry around this call -- see header
  // comment.
  bool serviceMove();

  bool isMoveActive() const { return move_.active; }

  // Force-end the current move now (no-op if none): neutrals the kernel
  // if a move was active, then clears the move-engine's own state.
  void endMove();

  // Fraction of the current move's dominant axis completed, [0..1000];
  // 1000 if no move is active (matches "isMoving()? -> false" reading as
  // "already there").
  int progress() const;

  uint32_t wrongWayCount() const { return wrongWayCount_; }

  // ---- end-of-move shaping knobs (settable per tour) -- shims.cpp's
  // setTaperWindows()/setTaperFloors()/setRampMs() forward to these. See
  // this class's own field comments (below) for what each trades off. --
  void setDistTaper(float counts) { distTaper_ = counts; }
  void setYawTaper(float counts) { yawTaper_ = counts; }
  void setDistFloor(float fraction) { distFloor_ = fraction; }
  void setTurnFloor(float fraction) { turnFloor_ = fraction; }
  void setRampMs(float ms) { rampMs_ = ms; }

 private:
  // |rotation| at/above this is NOT one blended segment -- pivot to the
  // new heading first, then travel straight (motion-api.md S3.3,
  // `navigator.cpp:237-240`'s measured `turn_first_angle`). 50 deg.
  static constexpr float kTurnFirstAngleRad = 0.8726646f;

  // One move-engine segment's targets/commands, shared by moveX()'s
  // single-segment and pivot-then-straight forms. `deadline` is fixed
  // for the whole moveX() call (set once, in moveX()/goToR()) and is
  // NOT reset across a pivot-to-straight phase transition -- one
  // `timeout` bounds the whole call, matching the wire's one field.
  struct MoveState {
    bool active = false;
    bool hasPending = false;     // a queued second (straight) phase
    float pendingDistance = 0.0f;  // [mm] phase 2's distance, if pending
    float pendingCruise = 0.0f;    // [mm/s] phase 2's cruise, if pending
    float posLeft0 = 0.0f, posRight0 = 0.0f;  // [counts]
    float distTarget = 0.0f;  // [counts] mean-axis target (signed)
    float yawTarget = 0.0f;   // [counts] half-differential target (signed)
    float velCmd = 0.0f;      // [counts/s] full-rate velocity command
    float twistCmd = 0.0f;    // [counts/s] full-rate twist command
    uint32_t startMs = 0;     // [ms] for the acceleration ramp
    float cmdScale = 1.0f;    // last commanded rate scale (ramp/taper)
    uint32_t deadline = 0;    // [ms] the caller's timeout backstop
  };

  // [ms] this engine's own notion of "now" -- see the constructor
  // comment on why a separate Clock reference is needed at all.
  uint32_t nowMs() const;

  // Post one constant-ratio segment (motion-api.md S2's wheels_x
  // reduction: left = distance - rotation*b/2, right = distance +
  // rotation*b/2), ratio-normalized to `cruise` exactly as wheelsX()
  // does, but tracked in `move_` so serviceMove() can shape/advance it
  // tick by tick instead of firing once. A zero-magnitude command or a
  // non-positive cruise leaves `move_.active` false (no-op), same
  // contract as wheelsX(). The initial kernel_.drive() lease is however
  // much time remains until `move_.deadline` (already set by the
  // caller), so an abandoned move still self-neutrals at the real
  // timeout even if nothing ever calls serviceMove() again.
  void startSegment(float distance, float rotation, float cruise);

  // Queue a pivot to `pivotRotation` now, then `straightDistance` [mm]
  // straight once that pivot completes cleanly -- the shared tail of
  // moveX()'s own pivot-first split (motion-api.md S3.3) and goToR()'s
  // above-threshold bearing-pivot-then-chord split (sprint 006,
  // KERN-02): both are "pivot then straight," differing only in which
  // (rotation, distance) pair is queued. The caller must set
  // `move_.deadline` (and clear `move_.hasPending`) first -- this
  // leaves the deadline untouched, which is what keeps one `timeout`
  // spanning both phases.
  void queuePivotThenStraight(float pivotRotation, float straightDistance,
                               float cruise);

  // Clears the move-engine's own state without touching the kernel --
  // the shared tail of endMove() and of wheelsX()/wheelsV()'s "clear the
  // planner" contract.
  void cancelMove();

  DiffDrive::DifferentialDrive& kernel_;
  const DiffDrive::Clock& clock_;

  // vevov-measured travel calibration (2026-08-19 bench: commanded
  // 80 cm, odometry believed 798 mm, tape measured 825 mm ->
  // 0.7837 * 825/798 = 0.8102). Generic kits calibrate via
  // setTravelCalib()/setTrackWidth() (shims.cpp's setGeometry() block).
  float travelCalib_ = 0.8102f;  // [mm/deg] wheel travel per shaft degree

  // [mm] MEASURED track (stakeholder tape, 2026-08-19). This is the
  // robot's geometry; it is never "corrected" -- turning slip is
  // modeled separately by rotationalSlip_ below.
  float trackWidth_ = 114.2f;

  // [1] physical/odometric rotation ratio (wheel-contact scrub).
  // CAMERA-MEASURED 2026-08-20 on the playfield, overhead AprilCam vs
  // commanded: six steady-state 180 deg pivots turned 164-166 deg
  // physical, ratio 0.915. effectiveTrackWidth must therefore be
  // 109.8/0.915 = 120.0 mm, so slip = 114.2/120.0 = 0.952.
  //
  // REPLACES 1.040, which came from a single camera pivot on 2026-08-19
  // and had the sign of the effect BACKWARDS (it said the robot
  // over-rotated; it under-rotates). The OTOS agreed with the camera to
  // 1.005 across ten pivots, so the sensor was never the problem -- this
  // constant was.
  float rotationalSlip_ = 0.952f;

  // ---- move engine state (extracted from shims.cpp's former Rig
  // fields, sprint 003 ticket 007) ----

  MoveState move_;

  // Moves aborted because the robot was rotating AWAY from the
  // commanded direction (serviceMove). Cumulative since construction.
  uint32_t wrongWayCount_ = 0;

  // End-of-move shaping. The defaults are the accuracy-tuned values --
  // they took turn overshoot from several degrees to under one, which
  // an OPEN-LOOP tour needs because its errors accumulate forever. They
  // are also the dominant cost in a tour's wall clock (see
  // setDistTaper()'s call site in shims.cpp for the measured trade). A
  // CLOSED-LOOP caller can afford far less -- hence settable per tour.
  float distTaper_ = 400.0f;  // [counts] ~32 mm window
  float yawTaper_ = 180.0f;   // [counts] ~15 deg window
  float distFloor_ = 0.25f;   // [1] slowest fraction of commanded
  float turnFloor_ = 0.12f;   // [1] pure turns crawl slower
  float rampMs_ = 400.0f;     // [ms] acceleration ramp
};

}  // namespace diffDrive
