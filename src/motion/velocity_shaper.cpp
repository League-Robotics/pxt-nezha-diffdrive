// velocity_shaper.cpp -- diffDrive::VelocityShaper::advance(), design
// docs/design/motion-profile-unification.md S6.1 verbatim. See
// velocity_shaper.h's header comment for scope and portability.
#include "velocity_shaper.h"

#include <cmath>

namespace diffDrive {

void VelocityShaper::reset() {
  v_ = 0.0f;
  a_ = 0.0f;
}

VelocityShaper::Step VelocityShaper::advance(float target, float remain,
                                              float floor, float cap,
                                              float dt,
                                              const MotionLimits& lim) {
  const float vPrev = v_;  // [mm/s] this tick's starting speed
  const float aPrev = a_;  // [mm/s^2] this tick's starting acceleration

  // 1. Braking plan (design S6.1 step 1): the highest speed from which
  // decel can still stop inside what remains, less the coast the
  // hardware adds after the last command lands (stopDistance), less
  // one tick of pipeline (the command in flight this tick has not
  // landed yet, so it still covers vPrev*dt before decel can begin).
  float vGoal;
  if (remain >= 0.0f) {
    float usable = remain - lim.stopDistance - vPrev * dt;
    if (usable < 0.0f) usable = 0.0f;
    const float vBrake = std::sqrt(2.0f * lim.decel * usable);
    vGoal = target < vBrake ? target : vBrake;
    if (cap < vGoal) vGoal = cap;
  } else {
    vGoal = target < cap ? target : cap;
  }

  // 2. Rate limit toward vGoal (first-order shaper, design S6.1 step 2).
  float vNext = vGoal;
  const float vUp = vPrev + lim.accel * dt;
  const float vDown = vPrev - lim.decel * dt;
  if (vNext > vUp) vNext = vUp;
  if (vNext < vDown) vNext = vDown;

  // 3. Optional jerk rounding (second-order, design S6.1 step 3): bound
  // da/dt, with the a^2/(2j) anticipation so a jerk-limited ramp does
  // not overshoot vGoal.
  if (lim.jerk > 0.0f && dt > 0.0f) {
    float aWant = (vGoal - vPrev) / dt;
    if (aWant > lim.accel) aWant = lim.accel;
    if (aWant < -lim.decel) aWant = -lim.decel;
    const float anticipated = vPrev + (aPrev * aPrev) / (2.0f * lim.jerk);
    if (anticipated >= vGoal && aPrev > 0.0f) aWant = 0.0f;

    float a = aWant;
    if (a > aPrev + lim.jerk * dt) a = aPrev + lim.jerk * dt;
    if (a < aPrev - lim.jerk * dt) a = aPrev - lim.jerk * dt;

    vNext = vPrev + a * dt;
    if (vNext < 0.0f) vNext = 0.0f;
    if (vNext > vGoal) vNext = vGoal;
  }

  // 4. Floor (design S6.1 step 4): while not arrived the drivetrain
  // cannot move below it, so never command less. This is the ONLY
  // floor in the system.
  if (remain >= 0.0f && vNext < floor) vNext = floor;

  // 5. Arrival (design S6.1 step 5 / S6.3): "the tick I am about to
  // command will carry me to the target" -- predicted, not discovered
  // after the fact.
  const bool arriving =
      remain >= 0.0f && remain <= vNext * dt + lim.stopDistance;

  v_ = vNext;
  a_ = dt > 0.0f ? (vNext - vPrev) / dt : 0.0f;

  return Step{v_, arriving};
}

float VelocityShaper::velocity() const { return v_; }
float VelocityShaper::acceleration() const { return a_; }

}  // namespace diffDrive
