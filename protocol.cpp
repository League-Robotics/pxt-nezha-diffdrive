// protocol.cpp -- see protocol.h.
#include "protocol.h"

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
  uint8_t lineBuf[kMaxLineBytes];
  while (true) {
    const size_t len = transport_.readLine(lineBuf, sizeof(lineBuf));
    ParsedLine parsed;
    if (!parseLine(lineBuf, len, &parsed)) continue;  // name too long, drop
    const VerbEntry* verb = findVerb(parsed.command);
    // Ticket 001: registry lookup only. Tickets 002-005 dispatch
    // `verb`'s handler here -- each handler MUST stay short and
    // non-blocking (see this file's header comment). An unrecognized
    // verb (verb == nullptr) is exactly the wire spec's
    // malformedCount_ case; tickets 002-005 own the counter.
    (void)verb;
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

}  // namespace diffDrive
