// radio_rx_classify_syntax_check.cpp -- compile-only translation unit
// so the c++11 syntax gate has something to point -fsyntax-only at for
// src/comms/radio_transport.h's host-portable free functions.
//
// radio_transport.h as a whole belongs to a pxt.h-bound module and is
// NOT otherwise covered by that gate. Two things in it are the standard
// extracted-helper exception: radioRxLineFits() (the accept/reject
// predicate) and radioRxClassify()/RadioRxCounters (the RX
// disposition and its bookkeeping). Both are reached from onDatagram(),
// which cannot be host-compiled at all -- so this file is the only
// thing that would catch a construct legal at the host suite's C++20
// but not at the target's C++11.
//
// NOT part of the ctypes-bound behaviour surface -- see
// radio_transport_rx_capacity_shim.cpp for that.
#include "comms/radio_transport.h"

namespace {

// Force real instantiation: a header that parses is not a header that
// compiles.
diffDrive::RadioRxCounters g_counters;

diffDrive::RadioRxDisposition probeClassify(size_t declaredLen,
                                            size_t capacity, bool slotBusy) {
  return diffDrive::radioRxClassify(declaredLen, capacity, slotBusy,
                                    g_counters);
}

bool probeFits(size_t declaredLen, size_t capacity) {
  return diffDrive::radioRxLineFits(declaredLen, capacity);
}

// Reference both so neither is optimized out of the parse.
bool probeAll() {
  return probeFits(1, 2) &&
         probeClassify(1, 2, false) == diffDrive::RadioRxDisposition::kAccept;
}

const bool kProbe = probeAll();

}  // namespace
