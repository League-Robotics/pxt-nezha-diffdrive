// wifi_credential_store_host_singleton.cpp -- a host-only definition of
// diffDrive::wifiCredentialStore() (declared in
// src/comms/wifi_credential_store.h), for shims that link
// src/comms/wire_adapter.cpp but do not otherwise care about exercising
// WIFICRED behavior (test_config_descriptor_table.py,
// test_config_surface_single_source.py, test_wire_motion_verbs.py and
// everything that reuses its motion_verb_lib fixture).
//
// WireAdapter::wifiCredCount()/wifiCredSlot()/wifiCredSet()/
// wifiCredClear() (sprint 038 ticket 003) call this free function
// unconditionally -- the symbol is referenced by wire_adapter.cpp's
// object code regardless of whether any test ever sends WIFICRED, so
// ANY shim that links wire_adapter.cpp needs a definition or the link
// fails on undefined diffDrive::wifiCredentialStore() (and the
// WifiCredentialStore methods it calls). The real definition
// (src/platform/wifi_flash_port.cpp) reaches pxt.h via MicroBitFlash.h
// and cannot be linked into a host shim; this file is the host
// substitute, mirroring that file's own function-local-static shape
// exactly, just with a FakeWifiFlashPort (in-memory, erase-filled
// 0xFF) in place of WifiFlashPortCodal -- the same fake shape
// wifi_flash_port_shim.cpp already uses for
// test_wifi_credential_store.py, kept local here rather than shared
// since the only thing this file needs from it is "holds bytes,
// never fails."
//
// No test in the shims that pull this file in asserts anything about
// WIFICRED's own behavior -- that is test_wire_grammar.py's job, via
// WireMockAdapter, which needs none of this. This file exists purely
// to make those OTHER shims link.
#include <cstdint>
#include <cstring>

#include "comms/wifi_credential_store.h"
#include "platform/wifi_flash_port.h"

namespace diffDrive {

namespace {

class FakeWifiFlashPort : public WifiFlashPort {
 public:
  FakeWifiFlashPort() { std::memset(bytes_, 0xFF, sizeof(bytes_)); }

  void read(uint32_t offset, uint8_t* buffer, uint32_t length) const override {
    if (!inRange(offset, length)) return;
    std::memcpy(buffer, bytes_ + offset, length);
  }
  bool write(uint32_t offset, const uint8_t* buffer, uint32_t length) override {
    if (!inRange(offset, length)) return false;
    std::memcpy(bytes_ + offset, buffer, length);
    return true;
  }
  bool erasePage() override {
    std::memset(bytes_, 0xFF, sizeof(bytes_));
    return true;
  }

 private:
  static bool inRange(uint32_t offset, uint32_t length) {
    if (length == 0) return true;
    if (offset >= kPageBytes) return false;
    return length <= kPageBytes - offset;
  }

  uint8_t bytes_[kPageBytes];
};

}  // namespace

WifiCredentialStore& wifiCredentialStore() {
  static FakeWifiFlashPort port;
  static WifiCredentialStore store(port);
  static bool began = (store.begin(), true);
  (void)began;
  return store;
}

}  // namespace diffDrive
