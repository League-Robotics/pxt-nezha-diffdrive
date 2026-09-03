// wifi_link_shim.cpp -- extern "C" surface for tests/host/test_wifi_link.py:
// diffDrive::WifiLink over a FakeWifiUart the test scripts like a module
// (inject the bytes the module "sends", read back what the link wrote),
// plus a settable fake clock. Same handle-plus-free-functions shape as
// the other shims here (see DESIGN.md).
#include <cstdint>
#include <cstring>
#include <deque>
#include <string>

#include "comms/wifi_link.h"

namespace {

uint32_t gNowMs = 0;
uint32_t fakeNow() { return gNowMs; }

class FakeWifiUart : public diffDrive::WifiUart {
 public:
  uint32_t baud = 0;
  bool refuseWrites = false;
  std::deque<uint8_t> rx;   // what the module has "sent" to the link
  std::string tx;           // everything the link wrote, in order
  int clearRxCalls = 0;

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
    if (refuseWrites) return false;
    tx.append(reinterpret_cast<const char*>(data), len);
    return true;
  }
  void clearRx() override {
    ++clearRxCalls;
    rx.clear();
  }
};

struct Handle {
  FakeWifiUart uart;
  diffDrive::WifiLink link;
  std::string ssid, password, hostname;
  Handle() : link(uart, &fakeNow) {}
};

}  // namespace

extern "C" {

void* wlCreate(const char* ssid, const char* password, const char* hostname) {
  Handle* h = new Handle();
  h->ssid = ssid;
  h->password = password;
  h->hostname = hostname;
  diffDrive::WifiLink::Config config;
  config.ssid = h->ssid.c_str();
  config.password = h->password.c_str();
  config.hostname = h->hostname.c_str();
  h->link.begin(config);
  return h;
}

void wlDestroy(void* p) { delete static_cast<Handle*>(p); }

void wlSetNow(uint32_t ms) { gNowMs = ms; }
void wlAdvance(uint32_t ms) { gNowMs += ms; }

void wlInject(void* p, const uint8_t* data, int len) {
  Handle* h = static_cast<Handle*>(p);
  for (int i = 0; i < len; ++i) h->uart.rx.push_back(data[i]);
}

// Drains what the link wrote since the last call. Returns the length.
int wlTakeTx(void* p, uint8_t* out, int cap) {
  Handle* h = static_cast<Handle*>(p);
  const int n = static_cast<int>(h->uart.tx.size()) < cap
                    ? static_cast<int>(h->uart.tx.size()) : cap;
  memcpy(out, h->uart.tx.data(), static_cast<size_t>(n));
  h->uart.tx.erase(0, static_cast<size_t>(n));
  return n;
}

void wlSetRefuseWrites(void* p, int refuse) {
  static_cast<Handle*>(p)->uart.refuseWrites = (refuse != 0);
}

void wlService(void* p) { static_cast<Handle*>(p)->link.service(); }

int wlState(void* p) { return static_cast<int>(static_cast<Handle*>(p)->link.state()); }
int wlSendLine(void* p, const char* line) {
  return static_cast<Handle*>(p)->link.sendLine(
             reinterpret_cast<const uint8_t*>(line), strlen(line)) ? 1 : 0;
}
int wlTryReceive(void* p, uint8_t* out, int cap) {
  size_t len = 0;
  if (!static_cast<Handle*>(p)->link.tryReceiveLine(out, static_cast<size_t>(cap), &len)) {
    return -1;
  }
  return static_cast<int>(len);
}
int wlPeerKnown(void* p) { return static_cast<Handle*>(p)->link.peerKnown() ? 1 : 0; }
const char* wlPeerIp(void* p) { return static_cast<Handle*>(p)->link.peerIp(); }
int wlPeerPort(void* p) { return static_cast<Handle*>(p)->link.peerPort(); }
const char* wlOwnIp(void* p) { return static_cast<Handle*>(p)->link.ownIp(); }
int wlRestarts(void* p) { return static_cast<int>(static_cast<Handle*>(p)->link.restartCount()); }
int wlDrops(void* p) { return static_cast<int>(static_cast<Handle*>(p)->link.dropCount()); }
int wlSent(void* p) { return static_cast<int>(static_cast<Handle*>(p)->link.sentCount()); }
int wlReceived(void* p) { return static_cast<int>(static_cast<Handle*>(p)->link.receivedCount()); }
int wlNewPeerEdge(void* p) { return static_cast<Handle*>(p)->link.pollNewPeerEdge() ? 1 : 0; }
int wlStateChanged(void* p) { return static_cast<Handle*>(p)->link.pollStateChanged() ? 1 : 0; }
int wlTelemetryAllowed(void* p) { return static_cast<Handle*>(p)->link.telemetryAllowed() ? 1 : 0; }
int wlMdnsOpen(void* p) { return static_cast<Handle*>(p)->link.mdnsSocketOpen() ? 1 : 0; }
int wlMdnsCount(void* p) { return static_cast<int>(static_cast<Handle*>(p)->link.mdnsAnnounceCount()); }
const char* wlLastCommand(void* p) { return static_cast<Handle*>(p)->link.lastCommand(); }
const char* wlLastReply(void* p) { return static_cast<Handle*>(p)->link.lastReply(); }
int wlClearRxCalls(void* p) { return static_cast<Handle*>(p)->uart.clearRxCalls; }
int wlBaud(void* p) { return static_cast<int>(static_cast<Handle*>(p)->uart.baud); }

int wlBuildMdns(uint8_t* out, int cap, const char* hostname, const char* ip, int port,
                const char* proto) {
  return static_cast<int>(diffDrive::WifiLink::buildMdnsAnnouncement(
      out, static_cast<size_t>(cap), hostname, ip, static_cast<uint16_t>(port), 120,
      proto));
}
int wlNewClientEdge(void* p) { return static_cast<Handle*>(p)->link.pollNewClientEdge() ? 1 : 0; }
int wlReplyLink(void* p) { return static_cast<Handle*>(p)->link.replyLink(); }
int wlTcpMask(void* p) { return static_cast<Handle*>(p)->link.tcpOpenMask(); }
int wlTcpServerOpen(void* p) { return static_cast<Handle*>(p)->link.tcpServerOpen() ? 1 : 0; }

}  // extern "C"
