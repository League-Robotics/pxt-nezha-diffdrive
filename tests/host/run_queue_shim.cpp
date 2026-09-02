// run_queue_shim.cpp -- ctypes surface for src/comms/run_queue.h.
//
// Opaque handle plus free functions, the same shape every other shim
// here uses, because ctypes cannot call C++ methods.
#include "comms/run_queue.h"

#include <cstring>

using Q = diffDrive::RunQueue<8, 48>;

extern "C" {

void* rqNew() { return new Q(); }
void rqFree(void* h) { delete static_cast<Q*>(h); }

int rqEnqueue(void* h, const char* text) {
  return static_cast<Q*>(h)->enqueue(text, static_cast<int>(std::strlen(text)));
}
int rqEnqueueLen(void* h, const char* text, int len) {
  return static_cast<Q*>(h)->enqueue(text, len);
}
const char* rqAt(void* h, int slot) { return static_cast<Q*>(h)->at(slot); }
void rqRelease(void* h, int slot) { static_cast<Q*>(h)->release(slot); }
int rqPeek(void* h) { return static_cast<Q*>(h)->peek(); }
int rqDequeue(void* h) { return static_cast<Q*>(h)->dequeue(); }
int rqCount(void* h) { return static_cast<Q*>(h)->count(); }
unsigned int rqDropped(void* h) { return static_cast<Q*>(h)->dropped(); }
int rqSlots(void*) { return Q::kSlots; }

}  // extern "C"
