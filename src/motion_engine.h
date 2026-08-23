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
// operation Motion API reduces onto these; sprint 003 ticket 006 (this
// file's origin) implements only these two plus the geometry they both
// depend on. The taper/ramp/wrong-way-abort/settle SHAPING that today
// lives in shims.cpp's Rig::serviceMove() is a different, separable
// responsibility -- it changes when the shaping algorithm changes, not
// when the wheel-count reduction changes -- and stays in shims.cpp until
// ticket 007 moves it here as moveX/moveV/goToR:
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
//     home instead of four call sites computing the same math.
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

class MotionEngine {
 public:
  // `kernel` is constructed and owned by the CALLER (shims.cpp's Rig for
  // hardware; the host test harness's own fixture for tests) -- this
  // class only ever holds a reference, exactly the way
  // DiffDrive::DifferentialDrive itself holds references to its own
  // Motor/Clock/Sleeper/FiberLauncher ports rather than owning them.
  // Geometry defaults below are the tovez/vevov bake this class is
  // extracted from (shims.cpp's former Rig fields) -- see this class's
  // own field comments for the measurement behind each.
  explicit MotionEngine(DiffDrive::DifferentialDrive& kernel);

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
  void wheelsV(float left, float right, uint32_t durationMs);

  // wheels_x(left, right, cruise, timeout): move each wheel a commanded
  // DISTANCE [mm] at a ratio locked to `cruise` [mm/s] (the DOMINANT
  // wheel's ceiling, motion-api.md S3.1) so both wheels finish together.
  // This primitive's bound is dead-reckoned: the dominant wheel's own
  // commanded distance divided by cruise gives the lease, capped by the
  // required `timeout` [ms] backstop. The live encoder-progress check
  // that makes this genuinely closed-loop (stopping early exactly when
  // the encoders confirm arrival, independent of the dead-reckoned
  // estimate) is ticket 007's shaping layer (Rig::serviceMove's eventual
  // new home) -- this primitive is the kinematics moveX reduces onto,
  // not yet the full closed-loop stop condition.
  // A zero-magnitude command (both wheels commanding no distance) or a
  // non-positive cruise is a no-op -- nothing is driven.
  void wheelsX(float left, float right, float cruise, uint32_t timeoutMs);

 private:
  DiffDrive::DifferentialDrive& kernel_;

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
};

}  // namespace diffDrive
