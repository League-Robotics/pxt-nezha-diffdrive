// reply_backpressure_shim.cpp -- ctypes surface for
// src/comms/reply_backpressure.h's waitForTxRoom(), driven with a fake
// link, a fake pump and a fake millisecond clock.
#include <cstdint>

#include "comms/reply_backpressure.h"

namespace {

struct FakeLink {
  int queued;
  bool isReady;
  int queuedSends() const { return queued; }
  bool ready() const { return isReady; }
};

}  // namespace

extern "C" {

// Runs one waitForTxRoom() call.
//   queued               lines already in the ring
//   slots                ring capacity
//   pumpsPerDrain        every Nth pump completes one send (0 = never drains)
//   unreadyAfterPumps    the link stops being ready after this many pumps (0 = never)
//   msPerYield           fake clock advance per yield [ms]
//   budget               the wait budget [ms]
// Returns 1 if room was found; writes pumps, yields and the final queue depth.
int rbWaitForTxRoom(int queued, int slots, int pumpsPerDrain,
                    int unreadyAfterPumps, uint32_t msPerYield,
                    uint32_t budget, int* outPumps, int* outYields,
                    int* outQueued) {
  FakeLink link = {queued, true};
  uint32_t clock = 1000;  // [ms]
  int pumps = 0;
  int yields = 0;
  const bool room = diffDrive::waitForTxRoom(
      link, slots,
      [&]() {
        ++pumps;
        if (pumpsPerDrain > 0 && pumps % pumpsPerDrain == 0 && link.queued > 0)
          --link.queued;
        if (unreadyAfterPumps > 0 && pumps >= unreadyAfterPumps)
          link.isReady = false;
      },
      [&]() {
        ++yields;
        clock += msPerYield;
      },
      [&]() { return clock; }, budget);
  *outPumps = pumps;
  *outYields = yields;
  *outQueued = link.queued;
  return room ? 1 : 0;
}

}  // extern "C"
