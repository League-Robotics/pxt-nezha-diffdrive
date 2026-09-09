// run_registry_shim.cpp -- extern "C" ctypes surface for the RUN
// registry's own host tests. Test scaffolding only: nothing under src/
// knows this file exists.
//
// Exercises the TEMPLATE directly (its own instance per handle) rather
// than the firmware's shared runRegistry() singleton -- a process-wide
// table would carry state between tests, and the rules under test
// (truncation, dedupe-by-name, saturation) are the template's.
#include <cstddef>

#include "comms/run_registry.h"

namespace {
// Small on purpose: 4 slots and 8-byte cells make the overflow and
// truncation edges reachable in a test without 32 setup calls.
// 4 slots, 8-byte names, 12-byte signatures: every truncation edge
// reachable in a few calls, and the two cell sizes distinct so a test
// can tell which limit clipped what.
using TestRegistry = diffDrive::RunRegistry<4, 8, 12>;
}  // namespace

extern "C" {

void* rrNew() { return new TestRegistry(); }
void rrFree(void* handle) { delete static_cast<TestRegistry*>(handle); }

int rrAdd(void* handle, const char* name, const char* signature) {
  return static_cast<TestRegistry*>(handle)->add(name, signature) ? 1 : 0;
}

int rrCount(void* handle) {
  return static_cast<TestRegistry*>(handle)->count();
}

const char* rrName(void* handle, int index) {
  return static_cast<TestRegistry*>(handle)->name(index);
}

const char* rrSignature(void* handle, int index) {
  return static_cast<TestRegistry*>(handle)->signature(index);
}

unsigned int rrOverflowCount(void* handle) {
  return static_cast<TestRegistry*>(handle)->overflowCount();
}

int rrFind(void* handle, const char* name) {
  return static_cast<TestRegistry*>(handle)->find(name);
}

}  // extern "C"
