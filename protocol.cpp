// protocol.cpp -- see protocol.h.
#include "protocol.h"

#include <cstdio>
#include <cstring>

namespace diffDrive {

// ---- shims.cpp/Rig entry points (ticket 003) --------------------------
// shims.cpp has no header of its own (see its own file comment) and
// main.ts's `//% shim=diffDrive::...` mechanism is the TS-facing binding,
// not a C++ one -- these are plain same-namespace C++ forward
// declarations, exactly like any two .cpp files in one link unit sharing
// a symbol without a dedicated header. Must stay signature-compatible
// with shims.cpp's real definitions; shims.cpp's own top-of-file comment
// points back here.
void startMove(int distance, int yaw, int speed, int yawRate);
void stopAll();
void estopAll();
void setWheelsTimed(int left, int right, uint32_t durationMs);
void driveTwistTimed(int speed, int yawRate, uint32_t durationMs);

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

// ---- Binary motion verb payload shapes (ticket 003) --------------------
// Locally defined, not protobuf-derived (sprint.md Design Rationale) --
// fixed-size layouts sized to this project's own int-only boundary
// convention (shims.cpp: mm, mm/s, centidegrees, centidegrees/s), not
// protobuf's field-tag encoding. All multi-byte fields are little-endian.
// No `enum`/`enum class` here even though this is a .cpp, not a header --
// matching the plain-constant convention protocol.h's VerbEntry comment
// already establishes for this codebase's PXT-scanner workaround, for
// consistency within this same file.
namespace {

// MOVE: mirrors protocol-v5.md §4's Move message semantic fields
// (velocity variant + one stop condition + timeout + replace + id).
//
//   offset  size  field
//   0       1     velocityKind (0 = twist, 1 = wheels)
//   1       1     stopKind (0 = time, 1 = distance, 2 = angle)
//   2       4     fieldA int32 LE -- twist.speed [mm/s] or wheels.left [mm/s]
//   6       4     fieldB int32 LE -- twist.yawRate [cdeg/s] or wheels.right [mm/s]
//   10      4     stopValue int32 LE -- time [ms] or distance [mm] or angle [cdeg]
//   14      4     timeout uint32 LE [ms] -- parsed, not separately enforced
//                 (see handleMove's own comment for why)
//   18      1     replace (0/1) -- parsed, never read: every MOVE is
//                 immediate/preemptive regardless (sprint.md Open Question 3)
//   19      4     id uint32 LE -- parsed, unused (no ack plane, Open Question 1)
constexpr size_t kMovePayloadBytes = 23;
constexpr uint8_t kMoveVelTwist = 0;
constexpr uint8_t kMoveVelWheels = 1;
constexpr uint8_t kMoveStopTime = 0;
constexpr uint8_t kMoveStopDistance = 1;
constexpr uint8_t kMoveStopAngle = 2;

// WHEELS: v_left, v_right [mm/s] int32 LE, duration [ms] uint32 LE
// (REQUIRED -- protocol-v5.md §2.4's "held for a REQUIRED duration"),
// id uint32 LE (parsed, unused -- no ack plane).
constexpr size_t kWheelsPayloadBytes = 16;

// STOP/ESTOP: id uint32 LE only -- deliberately NOT the reference spec's
// zero-field `Estop{}` (protocol-v5.md §3). By decodeBinaryBody()'s own
// return contract (protocol.h), 0 is returned both on a genuine decode
// failure (bad COBS, short frame, CRC mismatch) AND on a legitimately-
// empty (0-byte) successful decode -- the two cases are numerically
// indistinguishable from the return value alone, a property of ticket
// 001's codec, not something this ticket invents. A truly empty STOP/
// ESTOP payload would therefore be indistinguishable from a malformed
// one, and this verb could never reliably fire. Carrying a 4-byte `id`
// (parsed, unused, same convention as MOVE/WHEELS' own `id`) gives a
// successful decode a nonzero length, resolving the ambiguity the same
// way MOVE/WHEELS' larger fixed payloads already do incidentally.
constexpr size_t kStopPayloadBytes = 4;
constexpr size_t kEstopPayloadBytes = 4;

int32_t readI32LE(const uint8_t* p) {
  return static_cast<int32_t>(
      static_cast<uint32_t>(p[0]) | (static_cast<uint32_t>(p[1]) << 8) |
      (static_cast<uint32_t>(p[2]) << 16) |
      (static_cast<uint32_t>(p[3]) << 24));
}

uint32_t readU32LE(const uint8_t* p) {
  return static_cast<uint32_t>(p[0]) | (static_cast<uint32_t>(p[1]) << 8) |
        (static_cast<uint32_t>(p[2]) << 16) |
        (static_cast<uint32_t>(p[3]) << 24);
}

}  // namespace

// ---- Binary motion verb handlers (ticket 003) --------------------------
// Each decodes its COBS+CRC binary body (ticket 001's codec) into a
// fixed-size local payload buffer, verifies the decoded length exactly
// matches this verb's payload shape (constants above), and dispatches
// onto the existing shims.cpp/Rig surface -- reusing startMove/stopAll/
// estopAll unchanged, and two new duration-bound primitives
// (setWheelsTimed/driveTwistTimed, shims.cpp) layered over kernel.drive()
// the same way the move engine already layers a lease/deadline over it
// (shims.cpp's startMove). Fire-and-forget: no reply is ever sent for
// these four verbs (sprint.md Open Question 1). A failed decode or a
// wrong-length payload is dropped silently -- no motion is ever commanded
// from it (this ticket's acceptance criteria).

void Protocol::handleMove(const uint8_t* data, size_t dataLen) {
  if (data == nullptr) return;
  uint8_t payload[kMovePayloadBytes];
  const size_t payloadLen =
      decodeBinaryBody("MOVE", data, dataLen, payload, sizeof(payload));
  if (payloadLen != kMovePayloadBytes) return;  // malformed/wrong shape

  const uint8_t velocityKind = payload[0];
  if (velocityKind != kMoveVelTwist && velocityKind != kMoveVelWheels) {
    return;  // unrecognized velocity-variant tag -- drop, no motion
  }
  const uint8_t stopKind = payload[1];
  const int32_t fieldA = readI32LE(payload + 2);
  const int32_t fieldB = readI32LE(payload + 6);
  const int32_t stopValue = readI32LE(payload + 10);
  // payload[14..17] (timeout), payload[18] (replace), and payload[19..22]
  // (id) are all present in the wire layout above (matching protocol-v5.md
  // §4's Move message shape) but deliberately never read here: a TIME-stop
  // MOVE's duration IS `stopValue` already (a separate timeout would be
  // redundant with it); a distance/angle-stop MOVE's own deadline is
  // already computed internally by startMove() (distance/speed + margin,
  // shims.cpp) with no parameter to override it; `replace` doesn't change
  // dispatch because every MOVE is immediate/preemptive regardless of its
  // value (Open Question 3); and `id` has nothing to be echoed against (no
  // ack plane, Open Question 1).

  switch (stopKind) {
    case kMoveStopTime: {
      const uint32_t durationMs =
          stopValue > 0 ? static_cast<uint32_t>(stopValue) : 0u;
      if (velocityKind == kMoveVelWheels) {
        setWheelsTimed(static_cast<int>(fieldA), static_cast<int>(fieldB),
                       durationMs);
      } else {
        driveTwistTimed(static_cast<int>(fieldA), static_cast<int>(fieldB),
                        durationMs);
      }
      break;
    }
    case kMoveStopDistance: {
      // Yaw target 0 -- the move engine's own guard makes yawRate's
      // value irrelevant whenever its target is 0 (shims.cpp's
      // startMove: the yaw axis is skipped from both the duration calc
      // and updateMove's completion check when moveYawTarget == 0). A
      // wheels-velocity MOVE approximates a single scalar speed as the
      // mean of the two wheel speeds -- this project's move engine has
      // no per-wheel distance-stop primitive, only a single-speed one.
      const int speed = (velocityKind == kMoveVelWheels)
                            ? static_cast<int>((fieldA + fieldB) / 2)
                            : static_cast<int>(fieldA);
      startMove(static_cast<int>(stopValue), 0, speed, 0);
      break;
    }
    case kMoveStopAngle: {
      // Distance target 0 -- symmetric to the distance-stop case above;
      // `speed` is irrelevant whenever the distance target is 0. A
      // wheels-velocity MOVE has no natural angular rate to hand
      // startMove without this project's trackWidth (Rig-private,
      // shims.cpp) -- approximated with a fixed nominal turn rate rather
      // than reaching across the module boundary for Rig state.
      constexpr int kNominalTurnRateCdegPerS = 9000;  // 90 deg/s
      const int yawRate = (velocityKind == kMoveVelWheels)
                              ? kNominalTurnRateCdegPerS
                              : static_cast<int>(fieldB);
      startMove(0, static_cast<int>(stopValue), 0, yawRate);
      break;
    }
    default:
      break;  // unrecognized stop kind -- drop, no motion commanded
  }
}

void Protocol::handleWheels(const uint8_t* data, size_t dataLen) {
  if (data == nullptr) return;
  uint8_t payload[kWheelsPayloadBytes];
  const size_t payloadLen =
      decodeBinaryBody("WHEELS", data, dataLen, payload, sizeof(payload));
  if (payloadLen != kWheelsPayloadBytes) return;  // malformed/wrong shape

  const int32_t left = readI32LE(payload + 0);
  const int32_t right = readI32LE(payload + 4);
  const uint32_t duration = readU32LE(payload + 8);
  // payload[12..15] (id) is present in the wire layout, deliberately
  // never read -- no ack plane to echo it against (Open Question 1).
  setWheelsTimed(static_cast<int>(left), static_cast<int>(right), duration);
}

void Protocol::handleStop(const uint8_t* data, size_t dataLen) {
  if (data == nullptr) return;
  uint8_t payload[kStopPayloadBytes];
  const size_t payloadLen =
      decodeBinaryBody("STOP", data, dataLen, payload, sizeof(payload));
  if (payloadLen != kStopPayloadBytes) return;  // malformed -- no stop applied
  // payload[0..3] (id) is present in the wire layout (see the constants
  // block above), deliberately never read -- no ack plane (Open Question 1).
  stopAll();
}

void Protocol::handleEstop(const uint8_t* data, size_t dataLen) {
  if (data == nullptr) return;
  uint8_t payload[kEstopPayloadBytes];
  const size_t payloadLen =
      decodeBinaryBody("ESTOP", data, dataLen, payload, sizeof(payload));
  if (payloadLen != kEstopPayloadBytes) return;  // malformed -- no e-stop applied
  // payload[0..3] (id) is present in the wire layout (see the constants
  // block above), deliberately never read -- no ack plane (Open Question 1).
  estopAll();
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
    // Ticket 002 dispatches the four cleartext identity/liveness verbs;
    // ticket 003 (this revision) adds the four binary motion verbs.
    // Every other registered verb -- CONFIG/GET_CONFIG/... (ticket 004's
    // binary verbs, not yet handled) or a stray reply verb sent
    // host->robot (e.g. DEVICE/PONG/CFG, which only ever originate from
    // this robot) -- is recognized by the registry but has no handler
    // here, so it is silently ignored: exactly this ticket's acceptance
    // criterion for an "unrecognized or out-of-place" verb, and
    // consistent with ticket 004 owning its own dispatch arms later.
    // Each handler MUST stay short and non-blocking (see this file's
    // header comment) -- the four motion handlers below all satisfy this
    // by construction: they decode a small fixed-size payload and hand
    // off to shims.cpp/Rig's own non-blocking `kernel.drive()`/
    // `neutral()`/`estop()` calls, never sleeping or looping themselves.
    if (std::strcmp(parsed.command, "HELLO") == 0) {
      handleHello();
    } else if (std::strcmp(parsed.command, "PING") == 0) {
      handlePing();
    } else if (std::strcmp(parsed.command, "ID") == 0) {
      handleId();
    } else if (std::strcmp(parsed.command, "VER") == 0) {
      handleVer();
    } else if (std::strcmp(parsed.command, "MOVE") == 0) {
      handleMove(parsed.data, parsed.dataLen);
    } else if (std::strcmp(parsed.command, "WHEELS") == 0) {
      handleWheels(parsed.data, parsed.dataLen);
    } else if (std::strcmp(parsed.command, "STOP") == 0) {
      handleStop(parsed.data, parsed.dataLen);
    } else if (std::strcmp(parsed.command, "ESTOP") == 0) {
      handleEstop(parsed.data, parsed.dataLen);
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
