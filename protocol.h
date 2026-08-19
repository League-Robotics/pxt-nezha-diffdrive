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
// registry only, with no handler dispatched. Ticket 002 added the first
// four handlers -- HELLO/PING/ID/VER -- the boot banner, and the
// run()-loop dispatch that calls them; those handlers still had no
// dependency on Rig/shims.cpp (they format identity/liveness strings
// only). Ticket 003 is the first to add that dependency: its four binary
// motion-verb handlers -- MOVE/WHEELS/STOP/ESTOP -- dispatch onto the
// existing shims.cpp/Rig surface (startMove/stopAll/estopAll, plus two
// new duration-bound primitives, setWheelsTimed/driveTwistTimed) via
// same-package C++ forward declarations (protocol.cpp; shims.cpp has no
// header of its own). Ticket 004 (this revision) attaches the remaining
// four binary config-verb handlers -- CONFIG/SET_FIELD/GET_CONFIG/
// CALIBRATE -- dispatching CONFIG/SET_FIELD onto the existing
// setKernelValue() (same surface the block API's `set config` block
// already uses) and GET_CONFIG onto a new read-back counterpart,
// getConfigValue() (shims.cpp). GET_CONFIG is the one binary verb this
// sprint keeps a synchronous reply for (`CFG`) -- see sprint.md
// Architecture Step 3. Ticket 005 (this revision) adds the cleartext
// pose-only `TLM` line (SUC-004): run()'s loop no longer blocks
// indefinitely on a single readLine() call -- it polls
// SerialTransport::tryReadLine() (non-blocking) alongside a fixed-cadence
// telemetry emission, so TLM goes out on schedule without starving
// command dispatch, both on this same fiber (see run()'s own comment).
//
// Sprint 002 (this revision) adds motion-obligation tracking: with the
// kernel's own background fiber removed (shims.cpp, sprint 002 ticket
// 001), a wire-issued MOVE/WHEELS has no student loop left to keep
// ticking it, so THIS fiber becomes its own bounded tickDrive() caller
// while one of its own dispatched commands is still outstanding -- see
// run()'s own comment and the "sprint 002: motion-obligation tracking"
// section below. Labeled "(sprint 002)", not by ticket number, because
// this file already has an unrelated, earlier-sprint "ticket 003" label
// a few sections up (the binary motion-verb handlers) that happens to
// share the same number as this ticket in ITS OWN (current) sprint.
//
// Sprint 002 ticket 006 (this revision) mirrors sendDeviceBanner()'s and
// sendTelemetry()'s already-formatted line bytes onto a second, radio
// transport (radio_transport.h/.cpp, ticket 005) -- see this file's
// "sprint 002 ticket 006: radio mirror" comment further down for the
// member and its rationale.
#pragma once

#include <cstddef>
#include <cstdint>

#include "platform_ports.h"  // CodalFiberLauncher (reused, not reimplemented)
#include "radio_transport.h"  // sprint 002 ticket 006: TLM/DEVICE radio mirror
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
  //
  // sprint 002 ticket 006: sendDeviceBanner() is the ONE handler below
  // that also mirrors its formatted line onto radioTransport_ (see this
  // file's own radio-mirror section further down) -- covering both its
  // call sites (the proactive boot-time send in run(), and handleHello()'s
  // re-send) uniformly, per sprint.md's Design Rationale. PING/ID/VER/DIAG
  // stay serial-only; no other reply verb goes over radio this sprint.
  void sendDeviceBanner();  // DEVICE:NEZHA2:robot:<name>:<serial>
  void handleHello();       // HELLO -> the same DEVICE banner
  void handlePing();        // PING -> PONG:t=<ms>
  void handleId();          // ID -> ID:<drivetrain>:<profile>:<version>
  void handleVer();         // VER -> VER:<version>
  void handleDiag();        // DIAG -> kernel Output flags/counters (debug)
  void handleRun(const uint8_t* data, size_t dataLen);  // RUN:<n> ->
                            // raises a MessageBus event so TS-side test
                            // functions registered via
                            // diffDrive.onRunCommand() run remotely

  // ---- ticket 003: binary motion verb handlers -----------------------
  // Each decodes its COBS+CRC binary body (ticket 001's codec, `data`/
  // `dataLen` being `ParsedLine::data`/`dataLen`, the bytes after the
  // verb's ':') and dispatches onto the existing shims.cpp/Rig surface.
  // Fire-and-forget: none of these four ever sends a reply (sprint.md
  // Open Question 1). A failed decode or a wrong-shape payload is
  // dropped silently -- no motion is ever commanded from it.
  void handleMove(const uint8_t* data, size_t dataLen);
  void handleWheels(const uint8_t* data, size_t dataLen);
  void handleStop(const uint8_t* data, size_t dataLen);
  void handleEstop(const uint8_t* data, size_t dataLen);

  // ---- sprint 002: motion-obligation tracking -------------------------
  // With the kernel's background fiber removed (shims.cpp, sprint 002
  // ticket 001), a wire-issued MOVE/WHEELS has no student loop left to
  // keep ticking it -- this fiber becomes its own bounded tick caller
  // instead, but only while one of ITS OWN dispatched commands is still
  // outstanding (sprint.md's "protocol.cpp ticks conditionally"
  // decision), not on every loop iteration (that would spin the I2C bus
  // even when nothing is commanded). Deliberately labeled "(sprint 002)"
  // rather than by ticket number -- see this header's top-of-file
  // comment for why "(ticket 003)" alone would be ambiguous in this
  // particular file.
  //
  // Two obligation kinds, one boolean check (hasLiveMotionObligation()):
  // a position-mode MOVE already tracks itself (Rig::moveActive, read
  // via the existing moving() shim -- no duplicate state needed here);
  // WHEELS and a time-stop MOVE are duration-bound, tracked locally via
  // timedObligationDeadlineMs_ below, mirroring shims.cpp's own
  // moveActive/moveDeadline pattern at this fiber's own granularity.
  // handleMove()/handleWheels() call beginTimedMotionObligation() when
  // they dispatch a duration-bound command; handleStop()/handleEstop()
  // call clearTimedMotionObligation() so the loop reverts to idle
  // cadence immediately on a wire-issued stop, rather than continuing to
  // tick until the tracked deadline naturally elapses. run() calls
  // hasLiveMotionObligation() once per iteration to decide between
  // tickDrive() and the loop's normal idle poll -- never both in the
  // same iteration (that would double-sleep).
  bool hasLiveMotionObligation();
  void beginTimedMotionObligation(uint32_t durationMs);
  void clearTimedMotionObligation();

  // ---- ticket 004: binary config verb handlers -----------------------
  // CONFIG/SET_FIELD/CALIBRATE decode their COBS+CRC binary body (ticket
  // 001's codec) exactly like ticket 003's motion handlers above --
  // fire-and-forget, no reply, a failed decode or wrong-shape payload
  // silently dropped (no ack plane, sprint.md Open Question 1). CONFIG
  // and SET_FIELD dispatch each decoded (field, value) pair onto the
  // existing shims.cpp `setKernelValue()`. CALIBRATE is decoded (so it is
  // genuinely "parsed", not merely recognized) but never acts on its
  // payload: this hardware has no OTOS sensor, so it is a documented
  // no-op (sprint.md Design Rationale) that never touches motor output.
  //
  // GET_CONFIG is the ONE exception this sprint keeps a synchronous
  // binary reply for (wire spec S6.1/S6.2, sprint.md Architecture Step
  // 3): it decodes a single field-number, reads that field's current
  // value back through shims.cpp's new getConfigValue() (the read-back
  // counterpart to the existing setKernelValue() -- both read/write the
  // same kernel `Config` state, via `DifferentialDrive::config()`, so the
  // reply reflects the true current value regardless of whether it was
  // last set over the wire or via a MakeCode `set config` block), then
  // sends a COBS+CRC-framed `CFG` reply carrying (field, value) via
  // encodeBinaryBody()/transport_.writeLine() -- the same outbound path
  // sendDeviceBanner()/PONG/etc. use for their cleartext replies, just
  // binary-framed here. An out-of-range field-number on any of these four
  // verbs is silently ignored (implementer's choice per this ticket's
  // acceptance criteria) -- GET_CONFIG simply sends no reply in that case,
  // since no ERR verb exists in this sprint's registry to report one.
  void handleConfig(const uint8_t* data, size_t dataLen);
  void handleGetConfig(const uint8_t* data, size_t dataLen);
  void handleSetField(const uint8_t* data, size_t dataLen);
  void handleCalibrate(const uint8_t* data, size_t dataLen);

  // ---- ticket 005: simplified cleartext pose telemetry (TLM) ---------
  // Formats and sends the cleartext, pose-only `TLM:<x>:<y>:<heading>`
  // line -- this sprint's deliberate deviation from the reference spec's
  // binary `Telemetry` (sprint.md Solution, SUC-004). Reads pose via the
  // same poseX()/poseY()/poseHeading() shims.cpp accessors main.ts's Pose
  // blocks already call (same Rig singleton, same odomUpdate() -- so a
  // concurrent MakeCode `pose x`/`pose y`/`heading` block read is
  // guaranteed pose-consistent with what this sends). Called from run()'s
  // own polling loop on a fixed cadence (kTlmPeriodMs, protocol.cpp),
  // interleaved with -- never blocking -- incoming command dispatch; see
  // run()'s own comment for how the loop avoids readLine()'s indefinite
  // block to make that interleaving possible.
  //
  // sprint 002 ticket 006: also mirrors the identical formatted bytes
  // onto radioTransport_ -- see this file's radio-mirror section below.
  void sendTelemetry();

  // ---- sprint 002 ticket 006: radio mirror (TLM + DEVICE banner) -----
  // `radioTransport_` is a second thin transport, sibling to `transport_`
  // under this same Protocol object (sprint.md's module diagram has no
  // edge between the two transports themselves) -- mirrors, never
  // replaces, serial. Only sendDeviceBanner() and sendTelemetry() write
  // to it (via writeSnprintfResult()'s optional `radio` argument,
  // protocol.cpp); no other reply verb does, and no wire verb is ever
  // read from it (ticket 005's module has no RX path). There is no
  // explicit "begin"/"start" call for it anywhere in this file:
  // RadioTransport::sendLine() lazily enables and configures uBit.radio
  // on its own first call (radio_transport.h/.cpp, ticket 005) precisely
  // so a bench-only serial user who never triggers it never pays the
  // radio-enable cost. Because sendDeviceBanner() is called unconditionally
  // at the top of run() (before the loop ever blocks on a read), the radio
  // IS started unconditionally from this class's boot path the moment the
  // fiber starts -- satisfying this ticket's "radio transport started
  // unconditionally from Protocol::start() (or equivalent boot path)"
  // acceptance criterion without inventing a redundant explicit begin()
  // surface RadioTransport doesn't have. Tradeoff, stated honestly: this
  // also means every boot now pays the one-time uBit.radio.enable() cost
  // (RAM/softdevice), even for a serial-only bench session that never
  // cares about radio -- accepted per this ticket's own guidance, since
  // gating the mirror behind a new condition would itself be a new
  // pxt.json-visible configuration surface, which this ticket's
  // acceptance criteria explicitly rule out.
  RadioTransport radioTransport_;

  SerialTransport transport_;
  CodalFiberLauncher launcher_;
  CodalClock clock_;  // reused for PONG's t=<ms>, not a second Clock impl
  bool running_ = false;
  // Bench instrumentation surfaced by DIAG: lines completed by
  // tryReadLine, parsed lines whose verb matched the registry, and
  // WHEELS payloads that decoded to the right shape.
  uint32_t linesSeen_ = 0;
  uint32_t verbsDispatched_ = 0;
  uint32_t wheelsDecoded_ = 0;
  // sprint 002: motion-obligation tracking state -- see the methods'
  // own comment above for what these mean and who touches them.
  bool timedObligationActive_ = false;
  uint32_t timedObligationDeadlineMs_ = 0;  // [ms], clock_ ms scale
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
