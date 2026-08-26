// fake_pose_source.h -- FakePoseSource: a test double for
// diffDrive::PoseSource (src/motion/motion_engine.h), settable by a test to an
// arbitrary (x, y, heading). Same shape as fake_ports.h's
// FakeMotor/FakeClock/FakeSleeper/FakeFiberLauncher: a plain test double
// with public "canned response" state a test arms before calling
// MotionEngine::goToW(), nothing more -- "no timer, no clock,
// deterministic, caller-driven" (fake_ports.h's own phrase).
//
// Test scaffolding only: nothing under src/ knows this file exists, and
// it is compiled only into this test tree's own throwaway shared
// libraries (see motion_engine_shim.cpp).
#pragma once

#include "motion/motion_engine.h"

class FakePoseSource : public diffDrive::PoseSource {
 public:
  float x() const override { return x_; }
  float y() const override { return y_; }
  float heading() const override { return heading_; }

  // Sets the pose a subsequent goToW() call will read. [mm] [mm] [rad]
  void setPose(float x, float y, float heading) {
    x_ = x;
    y_ = y;
    heading_ = heading;
  }

 private:
  float x_ = 0.0f;
  float y_ = 0.0f;
  float heading_ = 0.0f;
};
