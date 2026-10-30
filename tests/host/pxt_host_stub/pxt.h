// pxt.h -- host stand-in for the PXT/CODAL header, just the names the
// pxt-bound sources in shims_cpp_shim.cpp's link list use. It is
// reachable only through the `-I` the shims.cpp recipe adds
// (shims_cpp_lib() in conftest.py); every other host build still has no
// pxt.h on its path.
//
// The state is controllable, not inert: a test owns the clock
// (system_timer_current_time_us()), fiber_sleep() advances it, create_fiber()
// records the entry instead of starting it, and uBit.i2c dispatches each
// transaction to the diffDrive::I2CBus registered for that address.
#pragma once
#include <cstddef>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <vector>

#include "../../../src/platform/i2c_bus.h"

#define MICROBIT_OK 0
#define MICROBIT_CODAL 1

struct ManagedString {
  ManagedString() {}
  ManagedString(const char*) {}
  ManagedString(const char*, int) {}
  ManagedString(int) {}
  const char* toCharArray() const { return ""; }
  int length() const { return 0; }
  ManagedString operator+(const ManagedString&) const { return *this; }
};

namespace pxt {
struct StringData {
  int getUTF8Size() const { return 0; }
  uint16_t length;
  char data[1];
  ManagedString toMString() const { return ManagedString(); }
};
typedef StringData* String;
typedef void* Action;
inline String mkString(const char*, int = -1) { return nullptr; }
inline void incr(void*) {}
inline void decr(void*) {}
inline void runInParallel(Action) {}
inline void runAction0(Action) {}
}  // namespace pxt
#define MSTR(s) ManagedString()

struct HostFiber {
  void (*entry)(void*);
  void* context;
};

struct HostPxtState {
  uint64_t nowUs = 0;                  // [us]
  uint64_t sleeps = 0;
  std::vector<HostFiber> fibers;
  struct Slave {
    uint8_t address8;                  // 8-bit form, as the callers pass it
    diffDrive::I2CBus* bus;
  };
  std::vector<Slave> slaves;
};

HostPxtState& hostPxt();

inline uint64_t system_timer_current_time_us() { return hostPxt().nowUs; }
// A fiber that waits on a flag nothing can clear (a guard acquired twice on
// the one host thread) would sleep forever; die loudly instead of hanging.
inline void fiber_sleep(unsigned long ms) {
  HostPxtState& state = hostPxt();
  state.nowUs += ms * 1000ull;
  if (++state.sleeps > 2000000) {
    std::fputs("pxt_host_stub: fiber_sleep runaway -- a deadlocked wait\n",
               stderr);
    std::abort();
  }
}
inline void schedule() {}
inline void* create_fiber(void (*entry)(void*), void* context) {
  hostPxt().fibers.push_back(HostFiber{entry, context});
  return nullptr;
}

struct HostI2C {
  static int route(uint8_t address8, bool isWrite, uint8_t* buf, int len) {
    for (const HostPxtState::Slave& s : hostPxt().slaves) {
      if (s.address8 != address8) continue;
      return isWrite ? s.bus->write(address8, buf, len)
                     : s.bus->read(address8, buf, len);
    }
    return 1;
  }
  int write(uint16_t address8, uint8_t* buf, int len) {
    return route(static_cast<uint8_t>(address8), true, buf, len);
  }
  int read(uint16_t address8, uint8_t* buf, int len) {
    return route(static_cast<uint8_t>(address8), false, buf, len);
  }
};

struct HostSerial {
  int send(const ManagedString&) { return 0; }
};

struct HostAccelerometer {
  int v[3] = {0, 0, -1000};  // [mg] flat on the floor
  int getX() { return v[0]; }
  int getY() { return v[1]; }
  int getZ() { return v[2]; }
};

struct HostUBit {
  HostI2C i2c;
  HostSerial serial;
  HostAccelerometer accelerometer;
};

HostUBit& hostUBit();
#define uBit (hostUBit())

// hostPxt() and hostUBit() are defined once, in shims_cpp_shim.cpp, as plain
// functions: a function-local static in an inline would be a unique symbol on
// Linux and shared by every copy of the library a test loads.
