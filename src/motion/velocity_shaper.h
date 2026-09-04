// velocity_shaper.h -- diffDrive::VelocityShaper: the ONE per-tick
// scalar (design docs/design/motion-profile-unification.md S4.2).
// Answers "given where I am and where I want to be, how fast should
// the dominant wheel be commanded this tick" -- braking plan, rate
// limit, optional jerk rounding, floor, and the predictive arrival
// decision, all in one place (design S6.1). Not yet wired into
// MotionEngine -- that is sprint 029 ticket 003. This ticket (002)
// builds the object in isolation (design S11).
//
// Host-portable by construction: <cstdint>/<cmath> only (std::sqrt for
// the braking plan) -- no pxt.h, no CODAL type, no counts, no wheels,
// no kernel knowledge anywhere in this file or velocity_shaper.cpp.
// Stateful only in the two values a rate limiter needs: the last
// commanded speed and the last commanded acceleration (design S4.2's
// exact class shape) -- nothing else survives between advance() calls.
#pragma once

#include <cstdint>

#include "motion_limits.h"

namespace diffDrive {

class VelocityShaper {
 public:
  struct Step {
    float vCmd;      // [mm/s] what to command the dominant wheel this tick
    bool arriving;   // true when this is the LAST nonzero tick (design S6.3)
  };

  // At every segment start: v = 0, a = 0 (design S4.2).
  void reset();

  // design S6.1's five-step algorithm verbatim: braking plan, first-order
  // rate limit, optional jerk rounding, floor, predictive arrival.
  //
  // `target`  [mm/s] the ceiling this segment may run at.
  // `remain`  [mm]   signed distance still to travel on the dominant
  //                  axis, or < 0 for "no displacement bound" (continuous
  //                  drive -- design S6.1's remain < 0 branch).
  // `floor`   [mm/s] already converted to dominant-wheel speed for THIS
  //                  axis (design S6.2's omegaFloorAsWheelSpeed()/vFloor).
  // `cap`     [mm/s] likewise, this axis's ceiling.
  // `dt`      [s]    this tick's elapsed time.
  // `lim`     the shaping limits (accel/decel/jerk/stopDistance) this
  //           tick's plan is built from.
  Step advance(float target, float remain, float floor, float cap, float dt,
               const MotionLimits& lim);

  float velocity() const;      // [mm/s] last commanded
  float acceleration() const;  // [mm/s^2] last commanded

 private:
  float v_ = 0.0f;  // [mm/s]
  float a_ = 0.0f;  // [mm/s^2]
};

}  // namespace diffDrive
