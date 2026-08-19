// protocol.cpp -- see protocol.h.
#include "protocol.h"

#include <cstdio>
#include <cstring>

namespace diffDrive {

// ---- CRC-16/CCITT-FALSE ----------------------------------------------

uint16_t crcInit() { return 0xFFFF; }

uint16_t crcUpdate(uint16_t crc, const uint8_t* data, size_t len) {
  for (size_t i = 0; i < len; ++i) {
    crc = static_cast<uint16_t>(crc ^ (static_cast<uint16_t>(data[i]) << 8));
    for (int bit = 0; bit < 8; ++bit) {
      if (crc & 0x8000u) {
        crc = static_cast<uint16_t>((crc << 1) ^ 0x1021u);
      } else {
        crc = static_cast<uint16_t>(crc << 1);
      }
    }
  }
  return crc;
}

uint16_t crcCompute(const uint8_t* data, size_t len) {
  return crcUpdate(crcInit(), data, len);
}

// ---- COBS, keyed on 0x0A ------------------------------------------------

namespace {
constexpr uint8_t kCobsDelimiter = 0x0A;
}  // namespace

size_t cobsEncode(const uint8_t* src, size_t srcLen, uint8_t* dst) {
  size_t read = 0;
  size_t write = 1;
  size_t codeIdx = 0;
  uint8_t code = 1;

  while (read < srcLen) {
    if (src[read] == 0x00) {
      dst[codeIdx] = static_cast<uint8_t>(code ^ kCobsDelimiter);
      codeIdx = write++;
      code = 1;
      ++read;
    } else {
      dst[write++] = static_cast<uint8_t>(src[read++] ^ kCobsDelimiter);
      ++code;
      if (code == 0xFF) {
        dst[codeIdx] = static_cast<uint8_t>(code ^ kCobsDelimiter);
        codeIdx = write++;
        code = 1;
      }
    }
  }
  dst[codeIdx] = static_cast<uint8_t>(code ^ kCobsDelimiter);
  return write;
}

size_t cobsDecode(const uint8_t* src, size_t srcLen, uint8_t* dst,
                  size_t dstCap) {
  size_t read = 0;
  size_t write = 0;

  while (read < srcLen) {
    const uint8_t code = static_cast<uint8_t>(src[read] ^ kCobsDelimiter);
    if (code == 0x00) return 0;  // a code byte of 0 is never legal
    ++read;
    for (uint8_t i = 1; i < code; ++i) {
      if (read >= srcLen || write >= dstCap) return 0;  // truncated/oversize
      dst[write++] = static_cast<uint8_t>(src[read++] ^ kCobsDelimiter);
    }
    if (code != 0xFF && read < srcLen) {
      if (write >= dstCap) return 0;
      dst[write++] = 0x00;
    }
  }
  return write;
}

// ---- Binary verb body framing -----------------------------------------

size_t encodeBinaryBody(const char* command, const uint8_t* payload,
                        size_t payloadLen, uint8_t* out, size_t outCap) {
  // Scoped CRC: command bytes, then ':', then payload -- folded via
  // crcUpdate() without concatenating the three ranges first.
  uint16_t crc = crcInit();
  crc = crcUpdate(crc, reinterpret_cast<const uint8_t*>(command),
                  std::strlen(command));
  const uint8_t colon = ':';
  crc = crcUpdate(crc, &colon, 1);
  crc = crcUpdate(crc, payload, payloadLen);

  // payload + little-endian CRC-16, then COBS-encode the combined bytes.
  uint8_t framed[kMaxLineBytes];
  if (payloadLen + 2 > sizeof(framed)) return 0;
  std::memcpy(framed, payload, payloadLen);
  framed[payloadLen] = static_cast<uint8_t>(crc & 0xFF);
  framed[payloadLen + 1] = static_cast<uint8_t>((crc >> 8) & 0xFF);

  const size_t framedLen = payloadLen + 2;
  if (cobsMaxEncodedLength(framedLen) > outCap) return 0;
  return cobsEncode(framed, framedLen, out);
}

size_t decodeBinaryBody(const char* command, const uint8_t* data,
                        size_t dataLen, uint8_t* payload,
                        size_t payloadCap) {
  uint8_t framed[kMaxLineBytes];
  const size_t framedLen = cobsDecode(data, dataLen, framed, sizeof(framed));
  if (framedLen < 2) return 0;  // too short to hold a trailing CRC

  const size_t payloadLen = framedLen - 2;
  if (payloadLen > payloadCap) return 0;

  const uint16_t wireCrc =
      static_cast<uint16_t>(framed[payloadLen]) |
      (static_cast<uint16_t>(framed[payloadLen + 1]) << 8);

  uint16_t crc = crcInit();
  crc = crcUpdate(crc, reinterpret_cast<const uint8_t*>(command),
                  std::strlen(command));
  const uint8_t colon = ':';
  crc = crcUpdate(crc, &colon, 1);
  crc = crcUpdate(crc, framed, payloadLen);
  if (crc != wireCrc) return 0;

  std::memcpy(payload, framed, payloadLen);
  return payloadLen;
}

// ---- Line grammar -------------------------------------------------------

bool parseLine(const uint8_t* line, size_t lineLen, ParsedLine* out) {
  *out = ParsedLine();

  size_t colonIdx = lineLen;  // sentinel: "not found"
  for (size_t i = 0; i < lineLen; ++i) {
    if (line[i] == ':') {
      colonIdx = i;
      break;
    }
  }

  size_t commandLen;
  if (colonIdx != lineLen) {
    // Binary/cleartext verb with data: first ':' ends the command name;
    // every later byte (including further ':' bytes) is data, verbatim.
    commandLen = colonIdx;
    out->hasData = true;
    out->data = line + colonIdx + 1;
    out->dataLen = lineLen - colonIdx - 1;
  } else {
    // Colon-less line: only ever a candidate for a no-data cleartext
    // verb. Strip a single trailing '\r' (raw terminal artifact) before
    // reading the command name.
    commandLen = lineLen;
    if (commandLen > 0 && line[commandLen - 1] == '\r') --commandLen;
    out->hasData = false;
  }

  if (commandLen >= sizeof(out->command)) return false;  // won't fit
  std::memcpy(out->command, line, commandLen);
  out->command[commandLen] = '\0';
  return true;
}

// ---- Verb registry --------------------------------------------------

const VerbEntry kVerbRegistry[] = {
    // Cleartext, host->robot (no data):
    {"HELLO", false},
    {"PING", false},
    {"ID", false},
    {"VER", false},
    // Cleartext, robot->host (with data):
    {"DEVICE", false},
    {"PONG", false},
    // TLM: cleartext here, unlike the reference spec's binary TLM --
    // this project's deliberate pose-only-telemetry deviation
    // (sprint.md Solution, SUC-004).
    {"TLM", false},
    // Binary, host->robot:
    {"MOVE", true},
    {"CONFIG", true},
    {"STOP", true},
    {"WHEELS", true},
    {"ESTOP", true},
    {"GET_CONFIG", true},
    {"SET_FIELD", true},
    {"CALIBRATE", true},
    // Binary, robot->host: GET_CONFIG's synchronous reply (sprint.md
    // Architecture Step 3 -- "the one binary reply verb this sprint
    // keeps binary").
    {"CFG", true},
};
const size_t kVerbRegistryCount = sizeof(kVerbRegistry) / sizeof(kVerbRegistry[0]);

const VerbEntry* findVerb(const char* name) {
  for (size_t i = 0; i < kVerbRegistryCount; ++i) {
    if (std::strcmp(kVerbRegistry[i].name, name) == 0) return &kVerbRegistry[i];
  }
  return nullptr;
}

// ---- Identity constants (ticket 002) ---------------------------------
// Sourced per this ticket's acceptance criteria ("the implementer picks
// a reasonable source ... and documents the choice"):
//
//   - kDeviceName: a fixed default. This project has no per-robot
//     naming config yet (no setter, no block) -- adding one is a
//     follow-up if a future sprint ever needs to tell two robots on
//     the same bench apart by name; the *serial* field below already
//     makes each robot's DEVICE banner unique without one.
//   - The DEVICE banner's <serial>: this micro:bit's own hardware
//     serial number, via CODAL's microbit_serial_number() -- the same
//     source pxt-microbit's own `control.deviceSerialNumber()` block
//     reads. Genuinely unique per device; nothing invented or cached.
//   - kDrivetrain/kProfile (ID's reply): "diffdrive" names this
//     extension's own kinematic type (matches the package name and
//     diffdrive.h/.cpp); "tovez" names the tuning bake shims.cpp's Rig
//     defaults are measured from (see shims.cpp's "tovez-measured
//     defaults" comment on Rig::travelCalib/trackWidth) -- a real,
//     already-existing identifier, not a new invention.
//   - kVersion (ID and VER's reply): this extension's own semver
//     identity, i.e. pxt.json's "version" field. There is no
//     build-time injection mechanism in this repo's C++ build (unlike
//     the reference firmware's generated version_generated.h), so this
//     constant is a manually-kept-in-sync mirror of pxt.json -- same
//     manual convention specification.md S13 already documents for
//     this project's versioning. Bump this alongside pxt.json's
//     "version" whenever that changes.
namespace {
constexpr const char* kDeviceName = "nezha";
constexpr const char* kDrivetrain = "diffdrive";
constexpr const char* kProfile = "tovez";
constexpr const char* kVersion = "1.0.0";  // keep in sync with pxt.json

// Writes an snprintf() result as one wire line, clamping to what
// actually fits `bufCap` (snprintf returns the length it WOULD have
// written, which can exceed the buffer on truncation) and dropping
// silently on an encoding error (negative return) rather than sending
// garbage.
void writeSnprintfResult(SerialTransport& transport, const char* buf, int n,
                         size_t bufCap) {
  if (n < 0) return;
  size_t len = static_cast<size_t>(n);
  if (len > bufCap - 1) len = bufCap - 1;
  transport.writeLine(reinterpret_cast<const uint8_t*>(buf), len);
}
}  // namespace

// ---- Cleartext identity/liveness verb handlers (ticket 002) ----------

void Protocol::sendDeviceBanner() {
  char buf[64];
  const int n = std::snprintf(buf, sizeof(buf), "DEVICE:NEZHA2:robot:%s:%lu",
                              kDeviceName,
                              static_cast<unsigned long>(microbit_serial_number()));
  writeSnprintfResult(transport_, buf, n, sizeof(buf));
}

void Protocol::handleHello() {
  sendDeviceBanner();  // "HELLO -> the same DEVICE: banner" (wire spec S2.4)
}

void Protocol::handlePing() {
  char buf[32];
  // t=<ms>: the robot's own clock at reply-formatting time, integer-
  // only -- matches the spec's newlib-nano rationale (no %f support;
  // `now` is already an integer, not a workaround).
  const unsigned long nowMs =
      static_cast<unsigned long>(clock_.nowMicros() / 1000ull);
  const int n = std::snprintf(buf, sizeof(buf), "PONG:t=%lu", nowMs);
  writeSnprintfResult(transport_, buf, n, sizeof(buf));
}

void Protocol::handleId() {
  char buf[64];
  const int n = std::snprintf(buf, sizeof(buf), "ID:%s:%s:%s", kDrivetrain,
                              kProfile, kVersion);
  writeSnprintfResult(transport_, buf, n, sizeof(buf));
}

void Protocol::handleVer() {
  char buf[32];
  const int n = std::snprintf(buf, sizeof(buf), "VER:%s", kVersion);
  writeSnprintfResult(transport_, buf, n, sizeof(buf));
}

// ---- Protocol loop -----------------------------------------------------

void Protocol::start() {
  if (running_) return;  // idempotent, mirrors DifferentialDrive::start()
  running_ = true;
  launcher_.launch(&Protocol::fiberEntry, this);
}

void Protocol::fiberEntry(void* self) {
  static_cast<Protocol*>(self)->run();
}

void Protocol::run() {
  // Boot banner: sent here, before the loop below ever blocks on a
  // read, so it goes out unsolicited the moment this fiber starts --
  // SUC-001's "without any host request." This is the only place the
  // banner is sent proactively; `HELLO` re-sends the identical banner
  // on request (handleHello() above).
  sendDeviceBanner();

  uint8_t lineBuf[kMaxLineBytes];
  while (true) {
    const size_t len = transport_.readLine(lineBuf, sizeof(lineBuf));
    ParsedLine parsed;
    if (!parseLine(lineBuf, len, &parsed)) continue;  // name too long, drop
    const VerbEntry* verb = findVerb(parsed.command);
    if (verb == nullptr) continue;  // unrecognized verb -- wire spec's
                                     // malformedCount_ case; no counter
                                     // exists this sprint (see protocol.h).
    // Ticket 002 dispatches the four cleartext identity/liveness
    // verbs. Every other registered verb -- MOVE/CONFIG/... (tickets
    // 003-005's binary verbs, not yet handled) or a stray reply verb
    // sent host->robot (e.g. DEVICE/PONG, which only ever originate
    // from this robot) -- is recognized by the registry but has no
    // handler here, so it is silently ignored: exactly this ticket's
    // acceptance criterion for an "unrecognized or out-of-place
    // cleartext verb," and consistent with tickets 003-005 owning
    // their own dispatch arms later. Each handler MUST stay short and
    // non-blocking (see this file's header comment).
    if (std::strcmp(parsed.command, "HELLO") == 0) {
      handleHello();
    } else if (std::strcmp(parsed.command, "PING") == 0) {
      handlePing();
    } else if (std::strcmp(parsed.command, "ID") == 0) {
      handleId();
    } else if (std::strcmp(parsed.command, "VER") == 0) {
      handleVer();
    }
  }
}

namespace {
Protocol* gProtocol = nullptr;
}  // namespace

Protocol& protocol() {
  if (gProtocol == nullptr) {
    gProtocol = new Protocol();
    gProtocol->start();
  }
  return *gProtocol;
}

// Boot-time auto-start wiring (ticket 002): called once from a
// top-level statement in main.ts's `diffDrive` namespace (see
// protocol()'s doc comment in protocol.h), so the protocol loop -- and
// its boot banner -- start as soon as this extension's compiled code
// loads, independent of whether any block is ever placed in a user's
// program. `protocol()`'s own lazy-singleton guard makes this call
// (and any other) idempotent.
//%
void startProtocol() { protocol(); }

}  // namespace diffDrive
