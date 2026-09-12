// motor_wiring_shim.cpp -- extern "C" ctypes surface for
// src/core/motor_wiring.h. That header is one pure function over two
// small structs (no class, no state), so this follows
// heading_wrap_shim.cpp's plain-function shape rather than the
// handle-plus-free-functions shims (kernel_shim.cpp, motion_engine_shim.cpp).
//
// The four resulting fields are returned through out-pointers rather than
// by value: returning a struct across ctypes means describing its layout
// twice, and the point of this shim is that the Python side asserts
// against the SAME decision shims.cpp applies, with nothing restated in
// between that could drift from it.
//
// Test scaffolding only: nothing under src/ knows this file exists.
#include "core/motor_wiring.h"

#include <cstdint>

extern "C" {

void motorWiringApply(int targetPort, int targetSign,
                      int otherPort, int otherSign,
                      int requestPort, int requestSign,
                      int* outTargetPort, int* outTargetSign,
                      int* outOtherPort, int* outOtherSign) {
  const diffDrive::MotorWiring target{static_cast<uint8_t>(targetPort),
                                      static_cast<int8_t>(targetSign)};
  const diffDrive::MotorWiring other{static_cast<uint8_t>(otherPort),
                                     static_cast<int8_t>(otherSign)};
  const diffDrive::WiringPair out =
      diffDrive::applyWiringRequest(target, other, requestPort, requestSign);
  *outTargetPort = out.target.port;
  *outTargetSign = out.target.sign;
  *outOtherPort = out.other.port;
  *outOtherSign = out.other.sign;
}

int motorWiringPortValid(int port) {
  return diffDrive::isValidMotorPort(port) ? 1 : 0;
}
int motorWiringSignValid(int sign) {
  return diffDrive::isValidMotorSign(sign) ? 1 : 0;
}

}  // extern "C"
