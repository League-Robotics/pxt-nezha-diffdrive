// C++11 syntax-check translation unit for src/comms/reply_backpressure.h,
// which has no .cpp of its own (see test_cxx11_syntax_gate.py).
#include "comms/reply_backpressure.h"

namespace {
struct Link {
  int queuedSends() const { return 0; }
  bool ready() const { return true; }
};
void instantiate() {
  Link link;
  uint32_t clock = 0;
  (void)diffDrive::waitForTxRoom(
      link, 8, []() {}, []() {}, [&clock]() { return clock; }, 2000u);
}
}  // namespace
