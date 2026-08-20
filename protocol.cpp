// protocol.cpp -- see protocol.h.
#include "protocol.h"

#include <stdio.h>  // plain snprintf: mbed-classic gcc lacks std::snprintf
#include <cstring>

namespace diffDrive {

// ---- shims.cpp/Rig entry points (tickets 003-004) ----------------------
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
// ticket 004: setKernelValue already existed (the block API's `set
// config` shim); getConfigValue is new -- the read-back counterpart
// shims.cpp adds for GET_CONFIG (see that file's own comment).
void setKernelValue(int field, int value);
int getConfigValue(int field);
int diagValue(int what);
// ticket 005: poseX/poseY/poseHeading already existed -- the same `//%`
// shims.cpp entry points main.ts's Pose blocks call (mm, mm, centidegrees
// -- shims.cpp's own boundary convention). No shims.cpp change was needed
// for telemetry: these forward declarations are the only new plumbing.
int poseX();
int poseY();
int poseHeading();
// sprint 002: tickDrive()/moving() are the tick-engine shims this
// revision's motion-obligation tracking calls directly -- tickDrive() to
// actually step the kernel while an obligation is live, moving() to
// read Rig::moveActive as the position-mode obligation's own live
// signal (see protocol.h's "sprint 002: motion-obligation tracking"
// section). Both already exist in shims.cpp (sprint 002 ticket 001);
// same same-package forward-declaration convention as every entry point
// above.
bool tickDrive();
bool moving();

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
    {"DIAG", false},
    // RUN:<n> -- cleartext with a decimal test number as data. Raises a
    // MessageBus event (see handleRun) so a TS-side handler registered
    // via diffDrive.onRunCommand() dispatches the matching test
    // function. Lets the bench host trigger test.ts programs over the
    // wire instead of a physical button press.
    {"RUN", false},
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
//   - The DEVICE banner's <name>: the board's own five-letter
//     micro:bit name via CODAL's microbit_friendly_name() (derived in
//     silicon from FICR.DEVICEID[1]). The fleet tooling (mbdeploy)
//     keys its device registry off this field of the announcement, so
//     a fixed string here would make every robot announce the same
//     name and stomp the registry on each probe.
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
constexpr const char* kDrivetrain = "diffdrive";
constexpr const char* kProfile = "tovez";
constexpr const char* kVersion = "1.0.0";  // keep in sync with pxt.json

// Writes an snprintf() result as one wire line, clamping to what
// actually fits `bufCap` (snprintf returns the length it WOULD have
// written, which can exceed the buffer on truncation) and dropping
// silently on an encoding error (negative return) rather than sending
// garbage.
//
// sprint 002 ticket 006: `radio`, when non-null, mirrors the identical
// clamped bytes onto that RadioTransport after the serial write -- one
// formatted buffer, two sinks, the exact same bytes on both (sprint.md's
// "mirror the exact formatted line bytes" Design Rationale). Defaults to
// nullptr so this helper's four other call sites (PING/ID/VER/DIAG) are
// unchanged, serial-only, with no edit needed at those sites; only
// sendDeviceBanner() and sendTelemetry() below pass their radioTransport_.
void writeSnprintfResult(SerialTransport& transport, const char* buf, int n,
                         size_t bufCap, RadioTransport* radio = nullptr) {
  if (n < 0) return;
  size_t len = static_cast<size_t>(n);
  if (len > bufCap - 1) len = bufCap - 1;
  transport.writeLine(reinterpret_cast<const uint8_t*>(buf), len);
  if (radio != nullptr) {
    radio->sendLine(reinterpret_cast<const uint8_t*>(buf), len);
  }
}
}  // namespace

// ---- Cleartext identity/liveness verb handlers (ticket 002) ----------

void Protocol::sendDeviceBanner() {
  char buf[64];
  const int n = snprintf(buf, sizeof(buf), "DEVICE:NEZHA2:robot:%s:%lu",
                              microbit_friendly_name(),
                              static_cast<unsigned long>(microbit_serial_number()));
  // sprint 002 ticket 006: mirror onto radio, uniformly at this one
  // function -- covers both call sites (the proactive boot-time send in
  // run(), and handleHello()'s re-send) with no special-casing between
  // them (sprint.md Design Rationale).
  writeSnprintfResult(transport_, buf, n, sizeof(buf), &radioTransport_);
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
  const int n = snprintf(buf, sizeof(buf), "PONG:t=%lu", nowMs);
  writeSnprintfResult(transport_, buf, n, sizeof(buf));
}

void Protocol::handleId() {
  char buf[64];
  const int n = snprintf(buf, sizeof(buf), "ID:%s:%s:%s", kDrivetrain,
                              kProfile, kVersion);
  writeSnprintfResult(transport_, buf, n, sizeof(buf));
}

void Protocol::handleVer() {
  char buf[32];
  const int n = snprintf(buf, sizeof(buf), "VER:%s", kVersion);
  writeSnprintfResult(transport_, buf, n, sizeof(buf));
}

int Protocol::formatDiag(char* buf, size_t cap) {
  // Kernel Output snapshot via shims.cpp's diagValue() -- debug surface
  // for bench diagnosis (stall/estop/connection/duty), cleartext like
  // the other identity verbs. Duty values are x100 (percent*100).
  // Shared by the DIAG verb reply (serial) and the 1 Hz radio DIAG
  // mirror in run() -- one formatter, two sinks.
  const int n = snprintf(
      buf, cap,
      "DIAG:rdy=%d,est=%d,stall=%d,lex=%d,conn=%d/%d,wsus=%d/%d,"
      "i2cf=%d,lexc=%d,pos=%d/%d,duty=%d/%d,vel=%d/%d,cyc=%d,sat=%d,"
      "def=%d,ovr=%d,err=%d,ln=%lu,vb=%lu,wh=%lu",
      diagValue(0), diagValue(1), diagValue(2), diagValue(3),
      diagValue(4), diagValue(5), diagValue(6), diagValue(7),
      diagValue(8), diagValue(9), diagValue(10), diagValue(11),
      diagValue(12), diagValue(13), diagValue(14), diagValue(15),
      diagValue(16), diagValue(17), diagValue(18), diagValue(19),
      diagValue(20),
      static_cast<unsigned long>(linesSeen_),
      static_cast<unsigned long>(verbsDispatched_),
      static_cast<unsigned long>(wheelsDecoded_));
  // Appended with a second snprintf: keeps each call's vararg count
  // modest (a 26-arg call bit this fiber's stack before).
  if (n > 0 && static_cast<size_t>(n) < cap) {
    const int m = snprintf(buf + n, cap - static_cast<size_t>(n),
                           ",wpk=%d/%d,egl=%d/%d", diagValue(21), diagValue(22),
                           diagValue(23), diagValue(24));
    if (m > 0) return n + m;
  }
  return n;
}

void Protocol::handleDiag() {
  const int n = formatDiag(diagBuf_, sizeof(diagBuf_));
  writeSnprintfResult(transport_, diagBuf_, n, sizeof(diagBuf_));
}

// ---- RUN: remote test trigger ----------------------------------------
// RUN:<n> (cleartext, decimal test number as data) raises a MessageBus
// event carrying <n> as the event value. main.ts's onRunCommand()
// registers a TS handler against the same source id, so test.ts can
// bind its test functions to wire commands as well as buttons. The
// event fires handlers on their own fiber (MessageBus default), so a
// long-running test (a full square tour ticking the kernel) does not
// block this protocol fiber.
namespace {
// Custom MessageBus source id -- must match RUN_EVENT_SOURCE in
// main.ts. Chosen well above the MICROBIT_ID_* range.
constexpr int kRunEventSource = 0x2001;
}  // namespace

void Protocol::handleRun(const uint8_t* data, size_t dataLen) {
  if (data == nullptr || dataLen == 0) return;
  // Parse an unsigned decimal test number; strip one trailing '\r'
  // (raw-terminal artifact, same tolerance parseLine() gives colon-less
  // lines). Any other non-digit byte -> malformed, drop silently (wire
  // spec S7.4 convention, same as the binary verbs).
  int value = 0;
  for (size_t i = 0; i < dataLen; ++i) {
    const uint8_t c = data[i];
    if (c == '\r' && i == dataLen - 1) break;
    if (c < '0' || c > '9') return;
    value = value * 10 + (c - '0');
    if (value > 65535) return;  // event-value ceiling (uint16); the
                                // zeguz rig vocabulary (testrig.ts)
                                // encodes arguments up to 42000
  }
  if (value == 0) return;  // 0 is MICROBIT_EVT_ANY -- never a test id
  MicroBitEvent(kRunEventSource, static_cast<uint16_t>(value));
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
      // sprint 002: a time-stop MOVE is duration-bound -- this fiber
      // must keep ticking until durationMs elapses, or the kernel would
      // never actually step (see protocol.h's obligation-tracking
      // section).
      beginTimedMotionObligation(durationMs);
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
      protocolMoveActive_ = true;  // this fiber must tick its own move
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
      protocolMoveActive_ = true;  // this fiber must tick its own move
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

  ++wheelsDecoded_;
  const int32_t left = readI32LE(payload + 0);
  const int32_t right = readI32LE(payload + 4);
  const uint32_t duration = readU32LE(payload + 8);
  // payload[12..15] (id) is present in the wire layout, deliberately
  // never read -- no ack plane to echo it against (Open Question 1).
  setWheelsTimed(static_cast<int>(left), static_cast<int>(right), duration);
  // sprint 002: WHEELS is duration-bound -- this fiber must keep
  // ticking until `duration` elapses, or the kernel would never
  // actually step (see protocol.h's obligation-tracking section).
  beginTimedMotionObligation(duration);
}

void Protocol::handleStop(const uint8_t* data, size_t dataLen) {
  protocolMoveActive_ = false;
  if (data == nullptr) return;
  uint8_t payload[kStopPayloadBytes];
  const size_t payloadLen =
      decodeBinaryBody("STOP", data, dataLen, payload, sizeof(payload));
  if (payloadLen != kStopPayloadBytes) return;  // malformed -- no stop applied
  // payload[0..3] (id) is present in the wire layout (see the constants
  // block above), deliberately never read -- no ack plane (Open Question 1).
  stopAll();
  // sprint 002: clear the local obligation tracking too, not just the
  // Rig-level stop above -- otherwise the loop would keep ticking (at
  // tickDrive()'s ~24 ms cadence) until a stale timed deadline elapsed
  // even though the robot is already stopped.
  clearTimedMotionObligation();
}

void Protocol::handleEstop(const uint8_t* data, size_t dataLen) {
  protocolMoveActive_ = false;
  if (data == nullptr) return;
  uint8_t payload[kEstopPayloadBytes];
  const size_t payloadLen =
      decodeBinaryBody("ESTOP", data, dataLen, payload, sizeof(payload));
  if (payloadLen != kEstopPayloadBytes) return;  // malformed -- no e-stop applied
  // payload[0..3] (id) is present in the wire layout (see the constants
  // block above), deliberately never read -- no ack plane (Open Question 1).
  estopAll();
  // sprint 002: clear the local obligation tracking too -- see
  // handleStop()'s identical comment above. ESTOP's own physical stop
  // effect (kernel.emergencyStopMotors()'s direct port write) is
  // unaffected by tick cadence either way; this only governs how soon
  // this loop reverts to its idle poll.
  clearTimedMotionObligation();
}

// ---- Binary config verb payload shapes (ticket 004) ---------------------
// Locally defined, not protobuf-derived, same rationale as ticket 003's
// motion payloads above (sprint.md Design Rationale). This project has one
// flat 15-member `ConfigField` enum (main.ts, ordinals 0-14, mirrored in
// specification.md S4.8), not the reference spec's seven `ConfigGroupTarget`
// groups -- so a field is addressed by that single ordinal alone, matching
// sprint.md's "GET_CONFIG/SET_FIELD address a single implicit config group
// by field number" design decision.
namespace {

// One (field, value) pair, shared by CONFIG's repeated arm and SET_FIELD's
// single-pair arm:
//
//   offset  size  field
//   0       1     field -- ConfigField ordinal, 0-14 (main.ts)
//   1       4     value int32 LE -- x1000-scaled, same convention
//                 setKernelValue()/getConfigValue() already use
//                 (shims.cpp's boundary convention, specification.md S9)
constexpr size_t kFieldValuePairBytes = 5;
constexpr uint8_t kMaxConfigField = 14;  // ConfigField's last ordinal

// CONFIG: one or more pairs back to back, no count prefix -- the payload
// length alone (a multiple of kFieldValuePairBytes) says how many.
// Bounded to one pair per field this project actually has (15), which is
// already far more than any single wire line needs in practice and stays
// well inside kMaxLineBytes.
constexpr size_t kConfigMaxPairs = kMaxConfigField + 1;
constexpr size_t kConfigMaxPayloadBytes = kConfigMaxPairs * kFieldValuePairBytes;

// GET_CONFIG request: field ordinal only -- no value, nothing else to ask
// for. Unlike STOP/ESTOP (ticket 003), a 0-byte successful decode is never
// a legitimate outcome here (a real request always names exactly one
// field), so decodeBinaryBody()'s failure-vs-empty ambiguity never arises
// for this verb.
constexpr size_t kGetConfigPayloadBytes = 1;

// CFG reply: echoes (field, value) back, the same pair shape CONFIG/
// SET_FIELD already use -- symmetric encode/decode of the same 5-byte
// layout.
constexpr size_t kCfgReplyPayloadBytes = kFieldValuePairBytes;

// CALIBRATE: id uint32 LE only, parsed but never read -- same "give a
// successful decode a nonzero length" rationale as STOP/ESTOP's own id
// field (ticket 003's comment on kStopPayloadBytes/kEstopPayloadBytes
// applies verbatim here). CALIBRATE never acts on its payload regardless
// of whether decoding succeeds: this hardware has no OTOS sensor, so it
// is a documented no-op (sprint.md Design Rationale) irrespective of what
// was sent.
constexpr size_t kCalibratePayloadBytes = 4;

void writeI32LE(uint8_t* p, int32_t v) {
  const uint32_t u = static_cast<uint32_t>(v);
  p[0] = static_cast<uint8_t>(u & 0xFF);
  p[1] = static_cast<uint8_t>((u >> 8) & 0xFF);
  p[2] = static_cast<uint8_t>((u >> 16) & 0xFF);
  p[3] = static_cast<uint8_t>((u >> 24) & 0xFF);
}

// Applies one decoded (field, value) pair via setKernelValue(), the same
// path the block API's `set config` block already uses. An out-of-range
// field ordinal is silently ignored -- this ticket's acceptance criteria
// leaves that choice to the implementer, and CONFIG/SET_FIELD have no
// ack plane to report it on regardless (sprint.md Open Question 1).
void applyFieldValuePair(const uint8_t* pair) {
  const uint8_t field = pair[0];
  if (field > kMaxConfigField) return;
  const int32_t value = readI32LE(pair + 1);
  setKernelValue(static_cast<int>(field), static_cast<int>(value));
}

}  // namespace

// ---- Binary config verb handlers (ticket 004) ---------------------------
// CONFIG/SET_FIELD/CALIBRATE mirror ticket 003's motion handlers: decode
// the COBS+CRC binary body into a fixed-capacity local buffer, and drop a
// failed decode or wrong-shape payload silently. GET_CONFIG is the
// exception -- it sends a synchronous binary CFG reply (sprint.md
// Architecture Step 3), the one binary reply this sprint keeps.

void Protocol::handleConfig(const uint8_t* data, size_t dataLen) {
  if (data == nullptr) return;
  uint8_t payload[kConfigMaxPayloadBytes];
  const size_t payloadLen =
      decodeBinaryBody("CONFIG", data, dataLen, payload, sizeof(payload));
  // Malformed, empty, or not a whole number of (field, value) pairs --
  // nothing applied. (payloadLen == 0 also covers a genuine decode
  // failure; CONFIG always carries at least one pair, so there is no
  // legitimate 0-byte success to distinguish it from, same as
  // GET_CONFIG above.)
  if (payloadLen == 0 || payloadLen % kFieldValuePairBytes != 0) return;
  for (size_t offset = 0; offset < payloadLen; offset += kFieldValuePairBytes) {
    applyFieldValuePair(payload + offset);
  }
}

void Protocol::handleSetField(const uint8_t* data, size_t dataLen) {
  if (data == nullptr) return;
  uint8_t payload[kFieldValuePairBytes];
  const size_t payloadLen =
      decodeBinaryBody("SET_FIELD", data, dataLen, payload, sizeof(payload));
  if (payloadLen != kFieldValuePairBytes) return;  // malformed -- no write applied
  applyFieldValuePair(payload);
}

void Protocol::handleGetConfig(const uint8_t* data, size_t dataLen) {
  if (data == nullptr) return;
  uint8_t payload[kGetConfigPayloadBytes];
  const size_t payloadLen = decodeBinaryBody("GET_CONFIG", data, dataLen,
                                             payload, sizeof(payload));
  if (payloadLen != kGetConfigPayloadBytes) return;  // malformed -- no reply

  const uint8_t field = payload[0];
  if (field > kMaxConfigField) return;  // out-of-range -- no reply (see
                                         // protocol.h's handler comment)
  const int32_t value = static_cast<int32_t>(getConfigValue(field));

  uint8_t reply[kCfgReplyPayloadBytes];
  reply[0] = field;
  writeI32LE(reply + 1, value);

  // The wire line must carry the v5 grammar's "CFG:" command prefix ahead
  // of the COBS body -- encodeBinaryBody() folds "CFG" into the CRC but
  // returns only the encoded body, so build the full line here. (Bench
  // bug: the body used to be written bare, unparseable by the host.)
  uint8_t line[4 + cobsMaxEncodedLength(kCfgReplyPayloadBytes + 2)];
  std::memcpy(line, "CFG:", 4);
  const size_t encodedLen =
      encodeBinaryBody("CFG", reply, sizeof(reply), line + 4,
                       sizeof(line) - 4);
  if (encodedLen == 0) return;  // shouldn't happen at this fixed size
  transport_.writeLine(line, 4 + encodedLen);
}

void Protocol::handleCalibrate(const uint8_t* data, size_t dataLen) {
  if (data == nullptr) return;
  uint8_t payload[kCalibratePayloadBytes];
  // Decoded so CALIBRATE is genuinely "parsed" (this ticket's acceptance
  // criteria), but the result is never used: no OTOS sensor on this
  // hardware, so CALIBRATE is a documented no-op (sprint.md Design
  // Rationale) regardless of whether decoding succeeds. No reply sent,
  // no motor output touched.
  decodeBinaryBody("CALIBRATE", data, dataLen, payload, sizeof(payload));
}

// ---- Cleartext pose telemetry (ticket 005) ------------------------------
// SUC-004's one deliberate deviation from the reference spec: a cleartext,
// pose-only `TLM:<x>:<y>:<heading>` line -- no binary ReplyEnvelope, no
// COBS+CRC, no ack data (sprint.md Solution). Units match shims.cpp's own
// boundary convention (its file comment, and poseX/poseY/poseHeading's own
// per-function comments): x/y in [mm], heading in [centidegrees] -- the
// same integers a MakeCode `pose x`/`pose y`/`heading` block would read,
// not re-derived or re-scaled here.
namespace {
// Emission cadence: coarser than the kernel's own 24 ms real-time cycle
// (shims.cpp's `cfg.cyclePeriod`) -- sprint.md's implementer-choice cadence
// explicitly allows this ("matching the kernel's ~24 ms period, or a
// coarser rate") -- while still on the same order of magnitude as the
// reference spec's own ~40 ms primary telemetry period (protocol-v5.md
// S8), plenty responsive for a host tracking pose in real time (SUC-004).
constexpr uint32_t kTlmPeriodMs = 50;
// Poll granularity between tryReadLine() checks -- small relative to
// kTlmPeriodMs so a command that just missed one poll is still picked up
// well within a single telemetry period (acceptance criterion: TLM must
// not starve command dispatch), but not so small it spins this fiber
// against an idle UART between bytes.
constexpr uint32_t kPollIntervalMs = 5;
}  // namespace

void Protocol::sendTelemetry() {
  // On-device millisecond timestamp leads the record (stakeholder,
  // 2026-08-20): host arrival times carry serial-buffering jitter
  // (measured: bursty 0/120 ms gaps around the 50 ms cadence), so
  // trajectory analysis needs the emission time, not the arrival time.
  char buf[64];  // "TLM:" + u32 ms + three int32 fields + separators
  const uint32_t nowMs = static_cast<uint32_t>(clock_.nowMicros() / 1000ull);
  const int n = snprintf(buf, sizeof(buf), "TLM:%lu:%d:%d:%d",
                         static_cast<unsigned long>(nowMs), poseX(),
                         poseY(), poseHeading());
  // sprint 002 ticket 006: mirror the identical formatted bytes onto
  // radio (SUC-004) -- same buf/n/bufCap, one source of truth for line
  // content, two sinks (sprint.md Solution).
  writeSnprintfResult(transport_, buf, n, sizeof(buf), &radioTransport_);
}

// ---- sprint 002: motion-obligation tracking -----------------------------
// See protocol.h's own comment on this section (and on why it's labeled
// "(sprint 002)" rather than by ticket number) for the full rationale.
// Kept deliberately small and localized (APPROVE-WITH-CHANGES guidance,
// sprint architecture review): two fields (protocol.h) plus these three
// one-purpose methods are the entire obligation-tracking surface --
// every call site below (handleMove/handleWheels/handleStop/handleEstop/
// run()) goes through one of them rather than touching the fields
// directly.

bool Protocol::hasLiveMotionObligation() {
  if (timedObligationActive_) {
    const uint32_t nowMs = static_cast<uint32_t>(clock_.nowMicros() / 1000ull);
    // Wraparound-safe elapsed check, same signed-difference idiom as
    // run()'s own TLM cadence check and shims.cpp's moveDeadline check.
    if (static_cast<int32_t>(nowMs - timedObligationDeadlineMs_) >= 0) {
      timedObligationActive_ = false;  // deadline elapsed -- idle from here
    }
  }
  // Position-mode MOVE: only one THIS fiber started (wire MOVE verb).
  // TS/button-driven moves tick themselves in their own loop; ticking
  // them from here as well made every move double-ticked (two fibers
  // alternating kernel.step() against one shared pacing anchor).
  if (protocolMoveActive_ && !moving()) {
    protocolMoveActive_ = false;  // our move finished
  }
  return (protocolMoveActive_ && moving()) || timedObligationActive_;
}

void Protocol::beginTimedMotionObligation(uint32_t durationMs) {
  timedObligationActive_ = true;
  const uint32_t nowMs = static_cast<uint32_t>(clock_.nowMicros() / 1000ull);
  timedObligationDeadlineMs_ = nowMs + durationMs;
}

void Protocol::clearTimedMotionObligation() {
  timedObligationActive_ = false;
}

// ---- Protocol loop -----------------------------------------------------

void Protocol::start() {
  if (running_) return;  // idempotent, mirrors DifferentialDrive::start()
  running_ = true;
  transport_.begin();  // size serial rings before any traffic
  // No analogous radioTransport_.begin() call here: RadioTransport has no
  // such method (ticket 005) -- it lazily enables uBit.radio on its own
  // first sendLine() call instead. That first call happens unconditionally
  // via sendDeviceBanner() at the top of run() below (fiberEntry(), just
  // launched), so the radio is still effectively started unconditionally
  // from this boot path, without a redundant explicit call here. See
  // protocol.h's "sprint 002 ticket 006: radio mirror" comment for the
  // full rationale and its accepted tradeoff.
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

  // Ticket 005: this loop no longer blocks indefinitely inside
  // transport_.readLine() -- doing so would starve TLM's own regular
  // cadence (SUC-004's acceptance criteria) for as long as no host sends
  // anything. Instead it polls transport_.tryReadLine() (non-blocking:
  // drains whatever bytes are already buffered, returns immediately
  // either way) once per short fiber_sleep(kPollIntervalMs) tick,
  // dispatching a command whenever a full line completed, and checking a
  // separate kTlmPeriodMs cadence every tick to emit TLM on schedule --
  // both on this same single fiber, so writes to transport_ (a CFG reply,
  // a cleartext reply, a TLM line) never interleave with each other.
  uint8_t lineBuf[kMaxLineBytes];
  uint32_t lastTlmMs = static_cast<uint32_t>(clock_.nowMicros() / 1000ull);
  sendTelemetry();  // first tick emitted promptly, not after a full
                     // kTlmPeriodMs wait -- SUC-004 doesn't require
                     // withholding the very first line.
  while (true) {
    size_t len = 0;
    if (transport_.tryReadLine(lineBuf, sizeof(lineBuf), &len)) {
      ++linesSeen_;
      ParsedLine parsed;
      if (parseLine(lineBuf, len, &parsed)) {  // else: name too long, drop
        const VerbEntry* verb = findVerb(parsed.command);
        if (verb != nullptr) {  // else: unrecognized verb -- wire spec's
                                 // malformedCount_ case; no counter exists
                                 // this sprint (see protocol.h).
          // Ticket 002 dispatches the four cleartext identity/liveness
          // verbs; ticket 003 adds the four binary motion verbs; ticket
          // 004 adds the four binary config verbs. Every other registered
          // verb -- a stray reply verb sent host->robot (e.g.
          // DEVICE/PONG/CFG/TLM, which only ever originate from this
          // robot) -- is recognized by the registry but has no handler
          // here, so it is silently ignored: this ticket's own acceptance
          // criterion (SUC-002) for an "unrecognized or out-of-place"
          // verb. Each handler MUST stay short and non-blocking (see this
          // file's header comment) -- every handler below satisfies this
          // by construction: they decode a small fixed-size (or small
          // bounded-repeat, for CONFIG) payload and hand off to
          // shims.cpp/Rig's own non-blocking calls
          // (`kernel.drive()`/`neutral()`/`estop()`/`setXxx()`), or --
          // GET_CONFIG only -- one blocking-but-bounded
          // `transport_.writeLine()` for its synchronous CFG reply, the
          // same guaranteed-bounded write ticket 002's cleartext replies
          // already rely on. Never sleeping or looping themselves.
          ++verbsDispatched_;
          if (std::strcmp(parsed.command, "HELLO") == 0) {
            handleHello();
          } else if (std::strcmp(parsed.command, "PING") == 0) {
            handlePing();
          } else if (std::strcmp(parsed.command, "ID") == 0) {
            handleId();
          } else if (std::strcmp(parsed.command, "VER") == 0) {
            handleVer();
          } else if (std::strcmp(parsed.command, "DIAG") == 0) {
            handleDiag();
          } else if (std::strcmp(parsed.command, "RUN") == 0) {
            handleRun(parsed.data, parsed.dataLen);
          } else if (std::strcmp(parsed.command, "MOVE") == 0) {
            handleMove(parsed.data, parsed.dataLen);
          } else if (std::strcmp(parsed.command, "WHEELS") == 0) {
            handleWheels(parsed.data, parsed.dataLen);
          } else if (std::strcmp(parsed.command, "STOP") == 0) {
            handleStop(parsed.data, parsed.dataLen);
          } else if (std::strcmp(parsed.command, "ESTOP") == 0) {
            handleEstop(parsed.data, parsed.dataLen);
          } else if (std::strcmp(parsed.command, "CONFIG") == 0) {
            handleConfig(parsed.data, parsed.dataLen);
          } else if (std::strcmp(parsed.command, "GET_CONFIG") == 0) {
            handleGetConfig(parsed.data, parsed.dataLen);
          } else if (std::strcmp(parsed.command, "SET_FIELD") == 0) {
            handleSetField(parsed.data, parsed.dataLen);
          } else if (std::strcmp(parsed.command, "CALIBRATE") == 0) {
            handleCalibrate(parsed.data, parsed.dataLen);
          }
        }
      }
    }

    // Radio command plane (single-fragment RX), gated to RUN only:
    // motion/config verbs stay wired-only until the fire-and-forget-
    // over-lossy-link safety question is settled (see
    // clasi/issues/radio-rx-command-plane-run-over-bridge.md). Reuses
    // lineBuf -- the serial branch above is done with it this
    // iteration.
    size_t radioLen = 0;
    if (radioTransport_.tryReceiveLine(rxLineBuf_, sizeof(rxLineBuf_),
                                       &radioLen)) {
      ParsedLine radioParsed;
      if (parseLine(rxLineBuf_, radioLen, &radioParsed) &&
          std::strcmp(radioParsed.command, "RUN") == 0) {
        handleRun(radioParsed.data, radioParsed.dataLen);
      }
    }

    const uint32_t nowMs = static_cast<uint32_t>(clock_.nowMicros() / 1000ull);
    // Wraparound-safe elapsed check (signed-difference idiom): correct
    // across nowMs's uint32_t rollover the same way moveDeadline's own
    // expiry check (shims.cpp updateMove()) already relies on.
    if (static_cast<int32_t>(nowMs - lastTlmMs) >=
        static_cast<int32_t>(kTlmPeriodMs)) {
      sendTelemetry();
      lastTlmMs = nowMs;
      // 1 Hz DIAG mirror over radio (every 20th 50 ms TLM tick): the
      // untethered bench instrument -- stall/wedge/duty/velocity flags
      // arrive at the relay alongside pose, so an intermittent wheel
      // failure can be caught in the act without a cable. Single
      // fragment at the fleet's 250-byte packet size.
      if (++tlmTicks_ >= 20) {
        tlmTicks_ = 0;
        const int dn = formatDiag(diagBuf_, sizeof(diagBuf_));
        if (dn > 0) {
          size_t dlen = static_cast<size_t>(dn);
          if (dlen > sizeof(diagBuf_) - 1) dlen = sizeof(diagBuf_) - 1;
          radioTransport_.sendLine(
              reinterpret_cast<const uint8_t*>(diagBuf_), dlen);
        }
      }
    }

    // Sprint 002: with the kernel's own background fiber removed
    // (shims.cpp), a wire-issued MOVE/WHEELS has no student loop left to
    // keep ticking it -- while this fiber's own motion obligation is
    // live, tickDrive() replaces this iteration's idle poll entirely.
    // tickDrive()'s own absolute-deadline pacing sleep (~24 ms) IS this
    // iteration's sleep; it is never followed by fiber_sleep() too (that
    // would double-sleep). When idle, behavior is unchanged from ticket
    // 001: a plain 5 ms poll, no tick. See protocol.h's "sprint 002:
    // motion-obligation tracking" section.
    if (hasLiveMotionObligation()) {
      tickDrive();
    } else {
      fiber_sleep(kPollIntervalMs);  // cooperative yield -- lets the
                                     // kernel's own fiber (and any other)
                                     // run between polls; never spins.
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
