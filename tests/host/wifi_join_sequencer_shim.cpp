// wifi_join_sequencer_shim.cpp -- extern "C" surface for
// tests/host/test_wifi_join_sequencer.py: diffDrive::WifiJoinSequencer
// driving a real diffDrive::WifiLink (over a scripted fake Ai-WB2-12F
// module, same FakeWifiUart shape wifi_link_shim.cpp uses) and a real
// diffDrive::WifiCredentialStore (over a fake in-memory WifiFlashPort,
// same shape wifi_flash_port_shim.cpp uses) -- the first host harness
// to exercise all three host-portable sprint-038 pieces together, per
// this ticket's own Testing Plan. Same handle-plus-free-functions shape
// as the other shims here (see DESIGN.md).
#include <cstdint>
#include <cstring>
#include <deque>
#include <string>

#include "comms/wifi_credential_store.h"
#include "comms/wifi_join_sequencer.h"
#include "comms/wifi_link.h"
#include "platform/wifi_flash_port.h"

namespace {

uint32_t gNowMs = 0;
uint32_t fakeNow() { return gNowMs; }

// -- same fake UART wifi_link_shim.cpp uses (duplicated, not shared --
// each shim in this directory is self-contained) -----------------------
class FakeWifiUart : public diffDrive::WifiUart {
 public:
  uint32_t baud = 0;
  std::deque<uint8_t> rx;  // what the module has "sent" to the link
  std::string tx;          // everything the link wrote, in order

  void begin(uint32_t b) override { baud = b; }
  uint16_t read(uint8_t* buf, uint16_t cap) override {
    uint16_t n = 0;
    while (n < cap && !rx.empty()) {
      buf[n++] = rx.front();
      rx.pop_front();
    }
    return n;
  }
  bool write(const uint8_t* data, uint16_t len) override {
    tx.append(reinterpret_cast<const char*>(data), len);
    return true;
  }
  void clearRx() override { rx.clear(); }
};

// -- same fake flash port wifi_flash_port_shim.cpp uses (duplicated for
// the same self-contained-shim reason) ----------------------------------
class FakeWifiFlashPort : public diffDrive::WifiFlashPort {
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

struct Handle {
  FakeWifiUart uart;
  FakeWifiFlashPort port;
  diffDrive::WifiLink link;
  diffDrive::WifiCredentialStore store;
  diffDrive::WifiJoinSequencer seq;
  Handle() : link(uart, &fakeNow), store(port), seq(link, store) {}
};

}  // namespace

extern "C" {

void* wjsCreate() { return new Handle(); }
void wjsDestroy(void* p) { delete static_cast<Handle*>(p); }

void wjsSetNow(uint32_t ms) { gNowMs = ms; }
void wjsAdvance(uint32_t ms) { gNowMs += ms; }

void wjsInject(void* p, const uint8_t* data, int len) {
  Handle* h = static_cast<Handle*>(p);
  for (int i = 0; i < len; ++i) h->uart.rx.push_back(data[i]);
}

int wjsTakeTx(void* p, uint8_t* out, int cap) {
  Handle* h = static_cast<Handle*>(p);
  const int n = static_cast<int>(h->uart.tx.size()) < cap
                    ? static_cast<int>(h->uart.tx.size()) : cap;
  memcpy(out, h->uart.tx.data(), static_cast<size_t>(n));
  h->uart.tx.erase(0, static_cast<size_t>(n));
  return n;
}

// Populates the store DIRECTLY (bypassing any wire path -- this ticket's
// own Testing Plan calls a WIFICRED SET "simulated at the store level")
// before/while the sequencer walks it.
int wjsStoreSet(void* p, int slot, const char* ssid, const char* password) {
  return static_cast<Handle*>(p)->store.set(slot, ssid, password) ? 1 : 0;
}
int wjsStoreClear(void* p, int slot) {
  return static_cast<Handle*>(p)->store.clear(slot) ? 1 : 0;
}

// Arms the walk: builds a WifiLink::Config template from the given
// hostname/port/hostPort/tcpServer (ssid/password are irrelevant here --
// the sequencer overwrites them per slot) and calls WifiJoinSequencer::
// begin(). Mirrors Protocol::serviceWifi()'s own lazy-begin construction.
void wjsBegin(void* p, const char* hostname, int port, int hostPort, int tcpServer) {
  diffDrive::WifiLink::Config config;
  config.hostname = hostname;
  config.port = static_cast<uint16_t>(port);
  config.hostPort = static_cast<uint16_t>(hostPort);
  config.tcpServer = (tcpServer != 0);
  static_cast<Handle*>(p)->seq.begin(config);
}

void wjsService(void* p) { static_cast<Handle*>(p)->seq.service(); }

int wjsLinkState(void* p) { return static_cast<int>(static_cast<Handle*>(p)->link.state()); }
int wjsLastJoinError(void* p) { return static_cast<Handle*>(p)->link.lastJoinError(); }
const char* wjsLastCommand(void* p) { return static_cast<Handle*>(p)->link.lastCommand(); }

int wjsCurrentSlot(void* p) { return static_cast<Handle*>(p)->seq.currentSlot(); }
int wjsAttemptsOnSlot(void* p) { return static_cast<Handle*>(p)->seq.attemptsOnSlot(); }
int wjsWalking(void* p) { return static_cast<Handle*>(p)->seq.walking() ? 1 : 0; }
int wjsMaxAttemptsPerSlot() { return diffDrive::WifiJoinSequencer::kMaxAttemptsPerSlot; }

// The empty-store regression-guard test's own primitive: begins
// WifiLink DIRECTLY, bypassing WifiJoinSequencer entirely -- mirroring
// how Protocol::serviceWifi() begins the link itself for the
// setupWifi()/baked precedence branches, never arming this class for
// an empty store. wjsService() above is then driven WITHOUT ever
// calling wjsBegin(), proving it is a pure pass-through.
void wjsLinkBeginDirect(void* p, const char* ssid, const char* password,
                        const char* hostname, int port, int hostPort) {
  diffDrive::WifiLink::Config config;
  config.ssid = ssid;
  config.password = password;
  config.hostname = hostname;
  config.port = static_cast<uint16_t>(port);
  config.hostPort = static_cast<uint16_t>(hostPort);
  static_cast<Handle*>(p)->link.begin(config);
}

}  // extern "C"
