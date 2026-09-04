// bus_guard_shim.cpp -- extern "C" ctypes surface for
// src/core/bus_guard.h. BusGuard is small but stateful (the acquired/
// released flag persists across calls), so this shim follows the
// handle-plus-free-functions shape (tests/host/DESIGN.md S2) rather than
// heading_wrap_shim.cpp's plain-function shape -- the same convention
// encoder_glitch_armor_shim.cpp uses ("bgXxx", mirroring its "egaXxx"
// prefix).
//
// Pairs a BusGuard with tests/host/fake_ports.h's own FakeSleeper so a
// test can script FakeSleeper::onSleep to release the guard from
// *inside* a scripted sleepMillis() call -- simulating "another fiber
// released the bus while this caller was mid-spin" without needing real
// concurrency, the same technique kernel_shim.cpp's
// kdArmCrossFiberStopOnSleepCall() already uses for the kernel's own
// settle-window race.
//
// Test scaffolding only: nothing under src/ knows this file exists.
#include "core/bus_guard.h"
#include "fake_ports.h"

extern "C" {

struct BusGuardHandle {
  diffDrive::BusGuard guard;
  FakeSleeper sleeper;
};

// ---- lifecycle ---------------------------------------------------------

void* bgCreate() { return new BusGuardHandle(); }
void bgDestroy(void* handle) { delete static_cast<BusGuardHandle*>(handle); }

// ---- the guard under test -----------------------------------------------

void bgAcquire(void* handle) {
  BusGuardHandle* h = static_cast<BusGuardHandle*>(handle);
  h->guard.acquire(h->sleeper);
}

void bgRelease(void* handle) {
  static_cast<BusGuardHandle*>(handle)->guard.release();
}

// ---- FakeSleeper readback -------------------------------------------

int bgSleepCalls(void* handle) {
  return static_cast<BusGuardHandle*>(handle)->sleeper.sleepCalls;
}

// ---- the mid-spin release hook -----------------------------------------

// Arms FakeSleeper::onSleep so that the Nth sleepMillis() call (1-based,
// counting from process start) releases THIS SAME guard, from inside
// the scripted callback -- lets a test land "another fiber called
// release()" at an exact point inside acquire()'s own spin loop without
// real threads.
void bgArmReleaseOnSleepCall(void* handle, int sleepCallNumber) {
  BusGuardHandle* h = static_cast<BusGuardHandle*>(handle);
  h->sleeper.onSleep = [h, sleepCallNumber](int callNumber) {
    if (callNumber == sleepCallNumber) {
      h->guard.release();
    }
  };
}

void bgDisarm(void* handle) {
  static_cast<BusGuardHandle*>(handle)->sleeper.onSleep = nullptr;
}

}  // extern "C"
