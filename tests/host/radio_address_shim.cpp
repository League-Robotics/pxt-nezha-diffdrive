// radio_address_shim.cpp -- extern "C" ctypes surface for
// src/comms/radio_transport.h's deriveRadioAddress() and
// selectRadioGroup() (sprint 025 ticket 002,
// derive-each-micro-bit-s-radio-channel-group-from-its-five-letter-name.md).
// Both are pure, free functions (no class, no state) -- same shape
// radio_transport_rx_capacity_shim.cpp already uses for
// radioRxLineFits() in this same header.
//
// #includes radio_transport.h directly -- NOT radio_transport.cpp,
// which requires pxt.h (uBit.radio, PacketBuffer) and cannot be
// host-compiled at all (src/DESIGN.md §1's layering table). The header
// itself has no CODAL dependency (only <cstddef>/<cstdint>), which is
// exactly what makes these functions reachable from a desktop host
// build with zero link against the CODAL-bound translation unit.
//
// Test scaffolding only: nothing under src/ knows this file exists.
#include "comms/radio_transport.h"

extern "C" {

// Wraps deriveRadioAddress(): returns 1 (name is a valid CVCVC board
// name, *outChannel/*outGroup hold the derived pair) or 0 (name was
// rejected, *outChannel/*outGroup hold the legacy fallback pair 4/10)
// -- ctypes has no native C++ bool ABI guarantee across platforms, so
// this shim surfaces the bool result as a plain int, the same
// convention radio_transport_rx_capacity_shim.cpp uses for
// radioRxLineFits().
int radioAddressDerive(const char* name, uint8_t* outChannel,
                       uint8_t* outGroup) {
  return diffDrive::deriveRadioAddress(name, outChannel, outGroup) ? 1 : 0;
}

// Wraps selectRadioGroup(): the override-vs-derived selection contract
// ensureRadioReady() applies. groupOverridden is a plain int (1/0),
// same ctypes-bool convention as above.
uint8_t radioAddressSelectGroup(int groupOverridden, uint8_t storedGroup,
                                uint8_t derivedGroup) {
  return diffDrive::selectRadioGroup(groupOverridden != 0, storedGroup,
                                     derivedGroup);
}

}  // extern "C"
