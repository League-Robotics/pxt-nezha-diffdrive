// wheel_command_tap_syntax_check.cpp -- dedicated compile-only
// translation unit giving tests/host/test_cxx11_syntax_gate.py
// something to point a -fsyntax-only -std=c++11 compile at directly.
//
// src/motion/wheel_command_tap.h is a pure abstract-interface header
// with no natural .cpp of its own (every member is a pure virtual) --
// this file exists solely to be that translation unit for the gate,
// the same reason motion_limits_syntax_check.cpp exists for
// motion_limits.h. It is NOT part of the ctypes-bound behavior-test
// surface; see motion_engine_shim.cpp's FakeWheelCommandTap for that
// (WheelCommandTap has no state of its own to bind directly).
#include "motion/wheel_command_tap.h"

namespace {

// Instantiates the interface (a no-op override of each pure virtual)
// so this translation unit exercises more than a bare #include -- a
// pure interface with no implementation anywhere would otherwise
// compile even with a typo in a signature nothing calls.
class NoOpTap : public diffDrive::WheelCommandTap {
 public:
  void onDrive(float leftMmS, float rightMmS,
               diffDrive::VelocityShaper::Phase phase) override {
    (void)leftMmS;
    (void)rightMmS;
    (void)phase;
  }
  void onNeutral() override {}
};

}  // namespace
