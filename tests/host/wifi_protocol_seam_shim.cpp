// wifi_protocol_seam_shim.cpp -- extern "C" surface for
// tests/host/test_wifi_protocol_seam.py: sprint 038 ticket 006's own
// acceptance criterion "WireAdapter's wifiCred* seam reads/writes the
// SAME store instance WifiJoinSequencer walks."
//
// Compiled into the SAME shared library as wire_motion_verb_shim.cpp
// (which supplies waCreate()/waFeed()/waSinkRead(), a REAL
// WireHandler + REAL diffDrive::WireAdapter over a real kernel double)
// and wifi_credential_store_host_singleton.cpp (which supplies the ONE
// diffDrive::wifiCredentialStore() definition both TUs link against).
// A function-local static singleton is one instance PER LOADED SHARED
// LIBRARY, not per translation unit -- so a `WIFICRED SET` sent
// through waFeed() (which calls WireAdapter::wifiCredSet(), which
// calls wifiCredentialStore().set()) and a WifiJoinSequencer
// constructed HERE, in a different .cpp file, against
// wifiCredentialStore() are provably driving the identical store. This
// is what closes the gap ticket 005's own test left open (that one
// simulated a wire SET "at the store level," store.set() directly,
// against a store LOCAL to its own shim -- explicitly not exercising
// WireAdapter/wire_handler.cpp at all; see wifi_join_sequencer_shim.cpp's
// own header comment).
//
// This file mirrors wifi_join_sequencer_shim.cpp's own FakeWifiUart and
// WifiJoinSequencer wiring (duplicated, not shared -- each shim in this
// directory is self-contained), MINUS the store/port: those come from
// the singleton, not a locally-owned instance.
#include <cstdint>
#include <cstring>
#include <deque>
#include <string>

#include "comms/wifi_credential_store.h"
#include "comms/wifi_join_sequencer.h"
#include "comms/wifi_link.h"

namespace {

uint32_t gWpsNowMs = 0;
uint32_t wpsFakeNow() { return gWpsNowMs; }

// -- same fake UART wifi_join_sequencer_shim.cpp/wifi_link_shim.cpp use
// (duplicated, not shared -- see this file's own header comment) -------
class FakeWifiUart : public diffDrive::WifiUart {
 public:
  uint32_t baud = 0;
  std::deque<uint8_t> rx;
  std::string tx;

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

struct WpsHandle {
  FakeWifiUart uart;
  diffDrive::WifiLink link;
  diffDrive::WifiJoinSequencer seq;
  // Bound to the SAME wifiCredentialStore() singleton
  // wire_motion_verb_shim.cpp's WaHandle -> WireAdapter::wifiCredSet()
  // reaches -- this is the whole point of this file.
  WpsHandle()
      : link(uart, &wpsFakeNow), seq(link, diffDrive::wifiCredentialStore()) {}
};

}  // namespace

extern "C" {

void* wpsCreate() { return new WpsHandle(); }
void wpsDestroy(void* p) { delete static_cast<WpsHandle*>(p); }

void wpsSetNow(uint32_t ms) { gWpsNowMs = ms; }
void wpsAdvance(uint32_t ms) { gWpsNowMs += ms; }

void wpsInject(void* p, const uint8_t* data, int len) {
  WpsHandle* h = static_cast<WpsHandle*>(p);
  for (int i = 0; i < len; ++i) h->uart.rx.push_back(data[i]);
}

int wpsTakeTx(void* p, uint8_t* out, int cap) {
  WpsHandle* h = static_cast<WpsHandle*>(p);
  const int n = static_cast<int>(h->uart.tx.size()) < cap
                    ? static_cast<int>(h->uart.tx.size()) : cap;
  memcpy(out, h->uart.tx.data(), static_cast<size_t>(n));
  h->uart.tx.erase(0, static_cast<size_t>(n));
  return n;
}

// Arms the walk -- mirrors Protocol::serviceWifi()'s own lazy-begin
// construction of the non-credential Config template.
void wpsBegin(void* p, const char* hostname, int port, int hostPort, int tcpServer) {
  diffDrive::WifiLink::Config config;
  config.hostname = hostname;
  config.port = static_cast<uint16_t>(port);
  config.hostPort = static_cast<uint16_t>(hostPort);
  config.tcpServer = (tcpServer != 0);
  static_cast<WpsHandle*>(p)->seq.begin(config);
}

void wpsService(void* p) { static_cast<WpsHandle*>(p)->seq.service(); }

int wpsLinkState(void* p) { return static_cast<int>(static_cast<WpsHandle*>(p)->link.state()); }
int wpsCurrentSlot(void* p) { return static_cast<WpsHandle*>(p)->seq.currentSlot(); }
const char* wpsCurrentSsid(void* p) { return static_cast<WpsHandle*>(p)->seq.currentSsid(); }
int wpsCurrentHasPassword(void* p) {
  return static_cast<WpsHandle*>(p)->seq.currentHasPassword() ? 1 : 0;
}
int wpsWalking(void* p) { return static_cast<WpsHandle*>(p)->seq.walking() ? 1 : 0; }

}  // extern "C"
