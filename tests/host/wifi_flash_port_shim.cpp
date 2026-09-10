// wifi_flash_port_shim.cpp -- extern "C" surface for
// tests/host/test_wifi_credential_store.py: diffDrive::WifiCredentialStore
// driven against a fake WifiFlashPort backed by a plain in-memory byte
// array (default-filled 0xFF, simulating an erased/never-written flash
// page). Same handle-plus-free-functions shape as the other shims here
// (see DESIGN.md), following wifi_link_shim.cpp's own shape per this
// ticket's implementation plan.
#include <cstdint>
#include <cstring>

#include "comms/wifi_credential_store.h"
#include "platform/wifi_flash_port.h"

namespace {

class FakeWifiFlashPort : public diffDrive::WifiFlashPort {
 public:
  FakeWifiFlashPort() { eraseFill(); }

  void eraseFill() { std::memset(bytes_, 0xFF, sizeof(bytes_)); }

  void read(uint32_t offset, uint8_t* buffer, uint32_t length) const override {
    ++readCalls;  // mutable: read() is logically const to callers, but
                   // this fake counts calls for its own tests' benefit.
    if (!inRange(offset, length)) return;
    std::memcpy(buffer, bytes_ + offset, length);
  }

  bool write(uint32_t offset, const uint8_t* buffer, uint32_t length) override {
    ++writeCalls;
    if (refuseWrites) return false;
    if (!inRange(offset, length)) return false;
    std::memcpy(bytes_ + offset, buffer, length);
    return true;
  }

  bool erasePage() override {
    ++eraseCalls;
    if (refuseErase) return false;
    eraseFill();
    return true;
  }

  // Test-only introspection/poking, never used by the production class.
  uint8_t byteAt(uint32_t offset) const {
    return (offset < kPageBytes) ? bytes_[offset] : 0;
  }
  void pokeByte(uint32_t offset, uint8_t value) {
    if (offset < kPageBytes) bytes_[offset] = value;
  }

  bool refuseWrites = false;
  bool refuseErase = false;
  mutable int readCalls = 0;
  int writeCalls = 0;
  int eraseCalls = 0;

 private:
  static bool inRange(uint32_t offset, uint32_t length) {
    if (length == 0) return true;
    if (offset >= kPageBytes) return false;
    return length <= kPageBytes - offset;
  }

  uint8_t bytes_[kPageBytes];
};

struct Handle {
  FakeWifiFlashPort port;
  diffDrive::WifiCredentialStore store;
  Handle() : store(port) {}
};

}  // namespace

extern "C" {

void* wcsCreate() { return new Handle(); }
void wcsDestroy(void* p) { delete static_cast<Handle*>(p); }

void wcsBegin(void* p) { static_cast<Handle*>(p)->store.begin(); }

int wcsOccupied(void* p, int slot) {
  return static_cast<Handle*>(p)->store.occupied(slot) ? 1 : 0;
}

// Returns 1 and fills ssidOut/passwordOut (each must be at least
// kSsidBytes/kPasswordBytes) on success, 0 otherwise (buffers
// untouched).
int wcsGet(void* p, int slot, char* ssidOut, char* passwordOut) {
  return static_cast<Handle*>(p)->store.get(slot, ssidOut, passwordOut) ? 1 : 0;
}

int wcsHasPassword(void* p, int slot) {
  return static_cast<Handle*>(p)->store.hasPassword(slot) ? 1 : 0;
}

int wcsSet(void* p, int slot, const char* ssid, const char* password) {
  return static_cast<Handle*>(p)->store.set(slot, ssid, password) ? 1 : 0;
}

int wcsClear(void* p, int slot) {
  return static_cast<Handle*>(p)->store.clear(slot) ? 1 : 0;
}

int wcsSlots() { return diffDrive::WifiCredentialStore::kSlots; }
int wcsSsidBytes() { return static_cast<int>(diffDrive::WifiCredentialStore::kSsidBytes); }
int wcsPasswordBytes() {
  return static_cast<int>(diffDrive::WifiCredentialStore::kPasswordBytes);
}
int wcsRecordBytes() {
  return static_cast<int>(diffDrive::WifiCredentialStore::kRecordBytes);
}

// --- fake-port pokes, for the edge-case tests (erased page, raw byte
// content the store never itself writes) ---
void wcsPortEraseFill(void* p) { static_cast<Handle*>(p)->port.eraseFill(); }
int wcsPortByteAt(void* p, int offset) {
  return static_cast<Handle*>(p)->port.byteAt(static_cast<uint32_t>(offset));
}
void wcsPortPokeByte(void* p, int offset, int value) {
  static_cast<Handle*>(p)->port.pokeByte(static_cast<uint32_t>(offset),
                                          static_cast<uint8_t>(value));
}
void wcsPortSetRefuseWrites(void* p, int refuse) {
  static_cast<Handle*>(p)->port.refuseWrites = (refuse != 0);
}
int wcsPortWriteCalls(void* p) { return static_cast<Handle*>(p)->port.writeCalls; }
int wcsPortReadCalls(void* p) { return static_cast<Handle*>(p)->port.readCalls; }

}  // extern "C"
