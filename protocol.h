// protocol.h -- Protocol: the Protocol v5 wire codec + line grammar +
// verb registry, layered on SerialTransport. Owns the COBS 0x0A-keyed
// codec, CRC-16/CCITT-FALSE, the v5 line grammar (wire spec S2.1), and a
// small closed verb registry -- and runs its own read/parse loop in its
// own CODAL fiber (CodalFiberLauncher, the same mechanism
// diffdrive.cpp's DifferentialDrive::start() uses for the kernel's own
// fiber), independent of the kernel's 24 ms real-time fiber. See
// sprint.md's Design Rationale ("the protocol loop runs in its own
// fiber, not the kernel's") for why: serial I/O, codec work, and
// dispatch have no real-time deadline and must never steal cycles from
// the wheel-speed control loop.
//
// Handlers registered against this loop (future tickets) MUST stay
// short and non-blocking: CODAL fibers are cooperative, never
// preemptive, so a long-running handler here delays this loop's own
// next line by exactly as much as it runs, and if it never yields, it
// can starve every other fiber on the same run queue, including the
// kernel's.
//
// Ticket 001 scope was transport + codec + line grammar + a verb-name
// registry only, with no handler dispatched. Ticket 002 (this
// revision) adds the first four handlers -- HELLO/PING/ID/VER -- the
// boot banner, and the run()-loop dispatch that calls them; tickets
// 003-005 attach the remaining (binary) verb handlers. Protocol still
// has no dependency on Rig/shims.cpp: none of ticket 002's handlers
// touch the kernel or Nezha port either -- they format identity/
// liveness strings only, reading nothing but this project's own
// identity constants and the CODAL clock.
#pragma once

#include <cstddef>
#include <cstdint>

#include "platform_ports.h"  // CodalFiberLauncher (reused, not reimplemented)
#include "serial_transport.h"

namespace diffDrive {

// ---- CRC-16/CCITT-FALSE ----------------------------------------------
// poly 0x1021, init 0xFFFF, no input/output reflection, no final XOR --
// wire spec S2.2. Known-answer vector: crcCompute("123456789", 9) ==
// 0x29B1. crcInit()/crcUpdate() are split so a caller can fold two
// byte ranges that are not adjacent in memory (a parsed command name,
// then a payload buffer) into one CRC without concatenating them
// first -- see encodeBinaryBody()/decodeBinaryBody() below, which are
// exactly that caller.
uint16_t crcInit();
uint16_t crcUpdate(uint16_t crc, const uint8_t* data, size_t len);
uint16_t crcCompute(const uint8_t* data, size_t len);

// ---- COBS, keyed on 0x0A, not 0x00 -----------------------------------
// Wire spec S2.2: standard 0x00-keyed COBS is guaranteed to never emit
// a literal 0x00 byte, so XOR-ing every encoded byte with the 0x0A
// delimiter afterward can never produce a literal 0x0A byte either
// (b ^ 0x0A == 0x0A iff b == 0, which never occurs in 0x00-keyed COBS
// output) -- sound by construction, not by scanning the result. A
// COBS-encoded body under this delimiter is therefore 0x0A-free but MAY
// legitimately contain an embedded 0x00 byte, the inverse of
// 0x00-keyed COBS's own guarantee.
//
// Desk-verified round trip (ticket 001 acceptance criterion), source
// bytes {0x11, 0x00, 0x22, 0x33} (an embedded 0x00 mid-payload):
//   encode -> {0x02, 0x11, 0x03, 0x22, 0x33} (pre-XOR view; the actual
//     wire bytes are each of these XORed with 0x0A)
//   decode -> {0x11, 0x00, 0x22, 0x33}  -- exact match.
constexpr size_t cobsMaxEncodedLength(size_t srcLen) {
  return srcLen + srcLen / 254 + 1;
}
// `dst` must have room for cobsMaxEncodedLength(srcLen) bytes. Returns
// the number of bytes written.
size_t cobsEncode(const uint8_t* src, size_t srcLen, uint8_t* dst);
// Returns the decoded length, or 0 if `src` is malformed or truncated,
// or if the decoded content would not fit `dstCap`.
size_t cobsDecode(const uint8_t* src, size_t srcLen, uint8_t* dst,
                  size_t dstCap);

// ---- Binary verb body framing (COBS + scoped CRC together) -----------
// Wire spec S2.2: "CRC scope now covers COMMAND ':' payload, not
// payload alone" -- the CRC-16 is computed over the parsed ASCII
// command-name bytes, then the ':' separator, then the payload.
//
// Encodes a binary verb's wire data: appends the little-endian CRC-16
// (computed over `command`, then ':', then `payload`) to `payload`,
// then COBS-encodes the combined bytes into `out`. Returns the encoded
// length, or 0 if `out` is too small (needs
// cobsMaxEncodedLength(payloadLen + 2) bytes).
size_t encodeBinaryBody(const char* command, const uint8_t* payload,
                        size_t payloadLen, uint8_t* out, size_t outCap);
// Decodes a binary verb's wire data (`data`, the bytes after the
// command name's ':' on an already-line-delimited wire line) into
// `payload`, verifying the CRC over `command ':' payload`. Returns the
// decoded payload length (excluding the trailing 2-byte CRC), or 0 if
// COBS decoding fails, the frame is too short to hold a CRC, the
// decoded payload would not fit `payloadCap`, or the CRC does not
// match. A malformed/undecodable frame gets no reply at all (wire spec
// S7.4) -- callers should simply drop a 0 return, never synthesize one.
size_t decodeBinaryBody(const char* command, const uint8_t* data,
                        size_t dataLen, uint8_t* payload, size_t payloadCap);

// ---- Line grammar (wire spec S2.1) ------------------------------------
// The longest verb this project's registry names ("GET_CONFIG", 10
// bytes) plus a NUL terminator; every registered verb name fits with
// margin.
constexpr size_t kMaxCommandBytes = 16;

struct ParsedLine {
  char command[kMaxCommandBytes] = {0};  // NUL-terminated
  bool hasData = false;
  const uint8_t* data = nullptr;  // points into the caller's line buffer
  size_t dataLen = 0;
};

// Parses `line` (the raw bytes SerialTransport::readLine() returned --
// i.e. one already-0x0A-delimited line with the delimiter itself
// already stripped) into `out`. The FIRST ':' ends the command name;
// every later byte, including further ':' bytes, is data. A colon-less
// line is only ever a candidate for a no-data cleartext verb; a single
// trailing '\r' on such a line (a raw terminal artifact) is stripped
// before the command name is read. Returns false only if the parsed
// command name would not fit `ParsedLine::command` (never true for any
// name in kVerbRegistry).
bool parseLine(const uint8_t* line, size_t lineLen, ParsedLine* out);

// ---- Verb registry --------------------------------------------------
// Wire spec S2.4's registry is the SOLE text/binary discriminator: a
// verb's own data is never inspected to decide how it's read. This
// project's closed verb set (sprint.md Scope/Architecture) --
// intentionally smaller than the reference firmware's: no radio-relay
// control-plane verbs, no ack-ring/OK verb (this sprint's fire-and-
// forget command plane -- sprint.md Open Question 1), no ERR verb
// (deferred to whichever of tickets 002-005 first needs one). Extending
// this array is how a later ticket adds a verb name. The array itself
// hasn't grown since ticket 001 -- ticket 002 attaches handlers (see
// Protocol::run()) for four names already listed here, HELLO/PING/
// ID/VER, without adding new entries.
//
// Binary verbs stay binary here exactly as in the reference spec.
// TLM is the one entry that reads differently from the reference spec:
// this project's telemetry is cleartext pose-only (sprint.md's
// deliberate deviation, SUC-004), not the reference's binary
// ReplyEnvelope, so TLM is registered cleartext (binary = false) here.
//
// A plain bool, not an enum: PXT's build scans every C++ file listed in
// pxt.json for a top-level `enum` to auto-generate a block-facing
// TypeScript mirror (see the `enums.d.ts` this project's `main.ts`
// already gets for `ConfigField`) -- appropriate for a genuinely
// student-facing enum, but VerbKind would be an internal-only
// implementation type wrongly exposed the same way (and, worse, PXT's
// scanner expects the classic multi-line `enum Name {\n  A,\n  B\n};`
// shape; a same-line `enum class X { A, B };` desyncs its line-based
// parser and corrupts the generated file). A bool sidesteps both
// problems and is exactly as expressive for a two-state flag.
struct VerbEntry {
  const char* name;
  bool binary;  // false: cleartext, true: binary (wire spec S2.4)
};

extern const VerbEntry kVerbRegistry[];
extern const size_t kVerbRegistryCount;

// Linear scan -- the registry is small (16 entries); returns nullptr if
// `name` is not registered.
const VerbEntry* findVerb(const char* name);

// ---- Protocol loop -----------------------------------------------------
class Protocol {
 public:
  // Starts the protocol loop on its own CODAL fiber via
  // CodalFiberLauncher. Idempotent, mirroring
  // DifferentialDrive::start()'s own idempotent guard.
  void start();

 private:
  static void fiberEntry(void* self);
  void run();

  // ---- ticket 002: cleartext identity/liveness verb handlers --------
  // Each formats its reply into a small stack buffer, then writes it
  // via `transport_.writeLine()`. `SerialTransport::writeLine()`
  // blocks this fiber (SYNC_SLEEP) until the bytes are sent -- on this
  // single-fiber-per-loop platform that blocking write is this
  // ticket's accepted approximation of the wire spec's
  // `sendReliable()` bounded-wait/must-not-drop semantics (ticket 002
  // acceptance criteria): there is no separate retry/ack layer, but
  // every reply below is guaranteed to have left the UART before its
  // handler returns.
  void sendDeviceBanner();  // DEVICE:NEZHA2:robot:<name>:<serial>
  void handleHello();       // HELLO -> the same DEVICE banner
  void handlePing();        // PING -> PONG:t=<ms>
  void handleId();          // ID -> ID:<drivetrain>:<profile>:<version>
  void handleVer();         // VER -> VER:<version>

  SerialTransport transport_;
  CodalFiberLauncher launcher_;
  CodalClock clock_;  // reused for PONG's t=<ms>, not a second Clock impl
  bool running_ = false;
};

// Lazy singleton, mirroring shims.cpp's Rig/ensure() pattern: the
// Protocol object -- and its fiber -- is constructed and started on
// first access, never from a global constructor (which would run
// before uBit.init() has brought up the CODAL fiber scheduler). Ticket
// 002 wires the actual call site: main.ts's `diffDrive` namespace
// calls this (through the `startProtocol()` shim defined alongside
// this function in protocol.cpp) as a top-level statement, which runs
// once when this extension's compiled code loads -- independent of
// whether any block below is ever placed in a user's program. That is
// what makes the boot banner (emitted from the top of `Protocol::run()`,
// before the loop ever blocks on a read) go out "without any host
// request" per SUC-001.
Protocol& protocol();

}  // namespace diffDrive
