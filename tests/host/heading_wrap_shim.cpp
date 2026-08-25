// heading_wrap_shim.cpp -- extern "C" ctypes surface for src/heading_wrap.h.
// heading_wrap.h is one pure, free function (no class, no state) --
// smaller in scope than the handle-plus-free-functions
// shims this directory otherwise uses (kernel_shim.cpp,
// motion_engine_shim.cpp), so this shim is just two free functions, no
// opaque handle needed.
//
// `headingWrapRoundTripLsb()` mirrors OtosPort::writePoseMm()'s heading
// channel (src/otos_port.cpp) field-for-field, using the same
// `kHdgRadPerLsb` scale (private to OtosPort, otos_port.h -- duplicated
// here deliberately, the same way wire_motion_verb_shim.cpp mirrors
// production math with counts-per-mm fixed at 1.0, per tests/host/DESIGN.md
// S2) -- because OtosPort itself cannot be host-compiled at all
// (otos_port.h includes pxt.h unconditionally), this is the only
// host-testable proxy for the exact LSB round-trip the real register
// write would produce.
//
// Test scaffolding only: nothing under src/ knows this file exists.
#include "heading_wrap.h"

#include <cmath>

extern "C" {

float headingWrapWrapRadians(float rad) {
  return diffDrive::wrapRadians(rad);
}

// Wraps `rad`, then quantizes it exactly the way
// OtosPort::writePoseMm() quantizes its heading channel (lroundf into
// LSB units, clamped to the int16 range), and converts the quantized
// LSB value back to radians -- i.e. what OtosPort::heading() would
// read back after a seedPose() round trip through real hardware.
float headingWrapRoundTripLsb(float rad) {
  // otos_port.h's kHdgRadPerLsb, duplicated (private, and OtosPort
  // cannot be host-compiled to read it from -- see this file's header
  // comment): 0.00549 deg/LSB, full scale +/-pi.
  const float kHdgRadPerLsb = 0.00549f * (3.14159265f / 180.0f);
  const float wrapped = diffDrive::wrapRadians(rad);
  long rh = lroundf(wrapped / kHdgRadPerLsb);
  if (rh > 32767) rh = 32767;
  if (rh < -32767) rh = -32767;
  return static_cast<float>(rh) * kHdgRadPerLsb;
}

}  // extern "C"
