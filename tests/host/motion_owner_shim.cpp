// motion_owner_shim.cpp -- extern "C" ctypes surface for
// src/core/motion_owner.h. Pure functions, no persistent state of their
// own (the `MotionOwner*` they mutate is caller-owned) -- plain
// functions, the same shape heading_wrap_shim.cpp uses for its own
// stateless header, no opaque handle needed.
//
// Test scaffolding only: nothing under src/ knows this file exists.
#include "core/motion_owner.h"

extern "C" {

// int in, int out -- MotionOwner's own declaration-order ordinal
// (kNone=0, kWire=1, kJob=2, kBlock=3), the same int-not-enum-class
// ctypes convention this project's other shims already use.

int motionOwnerTryTakeBlockOwnership(int owner) {
  diffDrive::MotionOwner o = static_cast<diffDrive::MotionOwner>(owner);
  const bool took = diffDrive::tryTakeBlockOwnership(&o);
  return took ? static_cast<int>(o) : -1;
}

int motionOwnerReleaseBlockOwnership(int owner) {
  diffDrive::MotionOwner o = static_cast<diffDrive::MotionOwner>(owner);
  diffDrive::releaseBlockOwnership(&o);
  return static_cast<int>(o);
}

}  // extern "C"
