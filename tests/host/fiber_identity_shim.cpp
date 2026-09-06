// fiber_identity_shim.cpp -- extern "C" ctypes surface for
// src/core/fiber_identity.h. One pure function, no state -- plain
// function, the same shape heading_wrap_shim.cpp uses for its own
// stateless header, no opaque handle needed.
//
// Fiber ids are opaque pointers in production (a real CODAL fiber's
// address); a host test has no fiber scheduler to take an address
// from, so this shim compares small integers cast to pointers instead
// -- shouldServiceHookRun() only ever compares its two arguments for
// pointer identity, so a fake id space works exactly like a real one.
//
// Test scaffolding only: nothing under src/ knows this file exists.
#include "core/fiber_identity.h"

extern "C" {

int fiberIdentityShouldServiceHookRun(long long protocolFiberId,
                                      long long currentFiberId) {
  const void* p = reinterpret_cast<const void*>(protocolFiberId);
  const void* c = reinterpret_cast<const void*>(currentFiberId);
  return diffDrive::shouldServiceHookRun(p, c) ? 1 : 0;
}

}  // extern "C"
