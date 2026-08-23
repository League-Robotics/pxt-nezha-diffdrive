// motion_engine.cpp -- see motion_engine.h for the class contract, the
// two-primitive design (motion-api.md S2), and the geometry rationale
// (S2.1). Host-portable: this file includes nothing but <cmath> and its
// own header -- no pxt.h, no CODAL type.
#include "motion_engine.h"

#include <cmath>

namespace diffDrive {

MotionEngine::MotionEngine(DiffDrive::DifferentialDrive& kernel)
    : kernel_(kernel) {}

void MotionEngine::wheelsV(float left, float right, uint32_t durationMs) {
  const float cpm = countsPerMm();
  const float velocity = 0.5f * (left + right) * cpm;  // [counts/s]
  const float twist = 0.5f * (right - left) * cpm;     // [counts/s] CCW+
  kernel_.drive(velocity, twist, durationMs);
}

void MotionEngine::wheelsX(float left, float right, float cruise,
                           uint32_t timeoutMs) {
  const float absLeft = std::fabs(left);
  const float absRight = std::fabs(right);
  const float dominant = absLeft > absRight ? absLeft : absRight;
  if (dominant <= 0.0f || cruise <= 0.0f) return;  // nothing to command

  // Normalize so the dominant wheel's own ratio is exactly +-1
  // (motion-api.md S4's control block: "uLeft, uRight normalized so
  // max(|uLeft|, |uRight|) == 1"), then scale by cruise -- the DOMINANT
  // wheel's own ceiling (S3.1) -- to get each wheel's commanded speed.
  const float uLeft = left / dominant;
  const float uRight = right / dominant;
  const float leftSpeed = uLeft * cruise;    // [mm/s]
  const float rightSpeed = uRight * cruise;  // [mm/s]

  const float cpm = countsPerMm();
  const float velocity = 0.5f * (leftSpeed + rightSpeed) * cpm;  // [counts/s]
  const float twist = 0.5f * (rightSpeed - leftSpeed) * cpm;     // [counts/s]

  // Dead-reckoned lease: how long the dominant wheel takes to cover its
  // own commanded distance at the ratio-locked cruise ceiling, capped by
  // the required timeout backstop (motion-api.md S3.1: "timeout is a
  // required backstop, not the stop condition" -- the live
  // encoder-progress check that makes this genuinely closed-loop is
  // ticket 007's shaping layer, not this primitive).
  const float computedMs = (dominant / cruise) * 1000.0f;
  uint32_t lease = static_cast<uint32_t>(std::lround(computedMs));
  if (timeoutMs > 0 && timeoutMs < lease) lease = timeoutMs;

  kernel_.drive(velocity, twist, lease);
}

}  // namespace diffDrive
