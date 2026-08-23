// protocol.h -- Protocol: the hardware transport-seam / fiber-loop
// composition module for protocol v6. Sprint 003 ticket 005 (the
// hardware transport-seam cutover) retires the ENTIRE v5 wire format
// this file used to own -- the COBS 0x0A-keyed codec, CRC-16/CCITT-
// FALSE, the locally-defined binary verb payload shapes (MOVE/WHEELS/
// CONFIG/GET_CONFIG/SET_FIELD/CALIBRATE/CFG), and the closed cleartext
// verb registry that used to dispatch HELLO/PING/ID/VER/DIAG -- all of
// it deleted, not merely unused. What remains under this filename is
// the CODAL fiber (start()/run()) and the byte plumbing between
// SerialTransport/RadioTransport and the new v6 wire stack
// (src/wire_handler.{h,cpp}, src/wire_adapter.{h,cpp}, tickets
// 002-004): this file feeds raw bytes in, writes reply bytes back out
// via a small Sink over the same serial transport, and otherwise knows
// nothing about the v6 grammar, the reliability layer, or any verb's
// own behavior -- all of that lives behind wire_handler_/wireAdapter_
// now, exactly as sprint.md's own module table draws the boundary.
//
// One exception, preserved deliberately: the OLD cleartext
// "RUN:<name>[:<arg>...]" MessageBus bridge (handleRun()/runText()/the
// runSlots_ ring below) is untouched, because main.ts's
// onRun()/onRunCommand() block API -- and every test/test.ts program
// built on it -- is unchanged this sprint (sprint.md Design Rationale:
// "the block API is UNCHANGED"). That old grammar has no general-verb
// registry to recognize it anymore (the v5 registry that used to do
// this is gone), so run() below detects it directly by its literal
// "RUN:" prefix before ever handing a line to the v6 wire stack -- see
// run()'s own comment. This is the ONE place the two grammars
// deliberately coexist on the same wire: a v6 host speaks the new
// space-and-`#id` RUN verb (wire_adapter.cpp's WireAdapter::onRun(),
// currently kUnknown -- this project's actual by-name test trigger is
// the bridge below, a CODAL-specific mechanism that class must never
// touch); test.ts's own bench tooling keeps speaking the old
// colon-separated form unchanged.
//
// The radio transport keeps its existing, narrower carve-out
// unchanged (sprint.md Open Question 4): its receive side accepts ONLY
// the old-style cleartext RUN, never the v6 grammar or any motion verb
// -- see run()'s own radio-polling block. Outbound, this ticket does
// NOT mirror v6 wire replies onto radio the way the old code mirrored
// its DEVICE banner and cleartext TLM: nothing can reach the v6 stack
// over radio to begin with (RX stays RUN-only), so mirroring its own
// replies there had no host to address. `emitLine()` below -- the free
// function shims.cpp's test-result reporting already uses -- still
// writes to both transports unchanged, so an untethered bench run's
// results still reach the radio exactly as before.
//
// Sprint 003 ticket 013 (final integration) note: this project's OWN
// automatic cleartext telemetry -- the old v5 loop's periodic
// "TLM:<ms>:<x>:<y>:<h>:<ox>:<oy>:<oh>:<vl>:<vr>" line -- is retired
// along with the rest of v5 and has NO v6 replacement yet:
// wire_handler.h's emitTelemetry() sends only ack/nack keepalives (see
// its own doc comment), not a data-bearing frame. `tools/tour_run.py`,
// `tools/tour_capture.py`, `tools/tour_watch.py`, and this repo's other
// bench scripts that parse a `TLM:` prefix will see that branch simply
// never fire on this firmware -- not a crash, but a silent loss of the
// wheel-speed/pose diagnostic those tools log and chart. A future
// ticket implementing real telemetry projection (thdr/t frames per
// `radio-robot-lib/docs/design/protocol.md` S5.2) is what restores
// this; until then, anyone running those tools against this build
// should be told, not left to discover an empty telemetry column on a
// live run.
#pragma once

#include <cstddef>
#include <cstdint>

#include "platform_ports.h"  // CodalFiberLauncher, CodalClock (reused, not reimplemented)
#include "radio_transport.h"  // the old-style RUN-only radio carve-out (unchanged)
#include "serial_transport.h"
#include "wire_adapter.h"
#include "wire_handler.h"

namespace diffDrive {

// ---- Protocol loop -----------------------------------------------------
class Protocol {
 public:
  // Starts the protocol loop on its own CODAL fiber via
  // CodalFiberLauncher. Idempotent, mirroring
  // DifferentialDrive::start()'s own idempotent guard.
  void start();

  // Emit one caller-supplied text line on BOTH transports, the same way
  // the old sendTelemetry()/sendDeviceBanner() used to mirror their own
  // lines. Exists because the test programs' result lines (tour fixes,
  // calibration data, timings) were written with TypeScript's
  // `serial.writeLine`, which reaches the USB cable only -- and the USB
  // cable only reaches the bench stand, where the wheels are off the
  // ground. Every test that needs the robot to actually move therefore
  // runs untethered, and its results have to come back over the radio.
  //
  // Called from the TS layer (shims.cpp's emitLine), NOT from this
  // object's own fiber; SerialTransport::writeLine blocks the caller
  // until the bytes are out, and RadioTransport::sendLine is a single
  // datagram, so a caller between moves pays a bounded cost.
  void emitLine(const char* text);

  // Text of the RUN command that raised MessageBus event value `slot`
  // (1..kRunSlots) -- the whole payload after `RUN:`, e.g.
  // "pivot:180". Returns "" for an out-of-range or never-written slot.
  // Called from the TS layer (shims.cpp's runCommandText), on the event
  // handler's fiber rather than this object's own.
  const char* runText(int slot) const;

 private:
  static void fiberEntry(void* self);
  void run();

  // ---- the old-style cleartext RUN MessageBus bridge, preserved
  // unchanged from before this cutover (see this file's own top-of-file
  // comment for why it survives the v5 retirement) -----------------------
  // RUN:<name>[:<arg>...] (cleartext, e.g. "RUN:pivot:180") parks the
  // payload text in a slot and raises a MessageBus event carrying that
  // slot as the event value. main.ts's run dispatcher registers a TS
  // handler against the same source id, reads the text back through the
  // runCommandText shim, and calls whichever handler test.ts bound to
  // that NAME -- so a wire command reads as the test it runs, not as a
  // magic number, and its arguments ride along as text instead of being
  // encoded into numeric offsets. The event fires handlers on their own
  // fiber (MessageBus default), so a long-running test (a full square
  // tour ticking the kernel) does not block this protocol fiber.
  void handleRun(const uint8_t* data, size_t dataLen);

  // RUN payload storage. The event value is a uint16 and cannot carry
  // text, so the payload is parked here and the event carries only the
  // slot it landed in (1-based; 0 is MICROBIT_EVT_ANY). A RING of slots,
  // not one buffer: MessageBus events queue and a test handler can run
  // for a minute, so a second RUN arriving mid-test would otherwise
  // overwrite the text the queued handler has not read yet. Four slots
  // covers any burst a host can plausibly send inside one handler.
  static constexpr size_t kRunTextBytes = 48;  // name + args + NUL
  static constexpr int kRunSlots = 4;
  char runSlots_[kRunSlots][kRunTextBytes] = {};
  int nextRunSlot_ = 0;      // round-robin write cursor, 0-based

  // RUN repeat suppression -- see handleRun's own comment. Hosts repeat
  // commands to survive the single-slot inbound buffer, and without
  // this a repeated RUN runs the test once per copy. Compared on the
  // whole payload, so RUN:pivot:180 does not suppress RUN:pivot:-180.
  static constexpr int32_t kRunDedupeMs = 3000;
  char lastRunText_[kRunTextBytes] = {};
  uint32_t lastRunMs_ = 0;   // [ms] arrival time of the last accepted RUN

  // ---- ticket 005: identity, assembled once the fiber actually runs --
  // WireAdapter must stay CODAL-free to keep it host-testable (its own
  // header comment), so it cannot call microbit_friendly_name()/
  // microbit_serial_number() itself -- this, the CODAL-facing side of
  // the seam, calls them and hands the result to wireAdapter_ via
  // setIdentity(). Deliberately NOT done at Protocol construction time
  // (wireAdapter_'s own NSDMI below constructs it with a harmless
  // placeholder Wire::Identity() instead): this object is constructed
  // the instant main.ts's top-level `_startProtocol()` statement runs
  // protocol()'s lazy-singleton new, which is earlier than this class's
  // own existing safety margin was ever proven for a CODAL identity
  // read -- the fiber body (run(), launched separately by start()) is
  // the exact call site the OLD sendDeviceBanner() safely used for the
  // same two functions, so buildIdentity() is called from there
  // instead, preserving that proven timing exactly.
  //
  // name/drivetrain/profile/version are all program-lifetime-stable
  // pointers (CODAL's own static name buffer; string literals below);
  // serial is the one field with no ready-made string form
  // (microbit_serial_number() returns a uint32_t) -- formatted once
  // into serialBuf_, a Protocol member so its storage outlives the
  // WireAdapter that borrows a pointer into it.
  static constexpr size_t kSerialBufBytes = 16;  // 10 decimal digits + NUL, with margin
  char serialBuf_[kSerialBufBytes] = {};
  Wire::Identity buildIdentity();

  // Real clock for WireAdapter::now()/its motion-obligation tracking
  // (see wire_adapter.h's own comment on both) -- a plain static member
  // function so it matches WireAdapter::NowMsFn's C-function-pointer
  // type exactly (no captured state possible, so it reaches this
  // Protocol instance through the existing protocol() singleton
  // accessor instead, safe here because it is only ever CALLED from the
  // running fiber, well after that singleton is assigned).
  static uint32_t wireNowMs();

  // ---- ticket 005: the v6 wire transport seam --------------------------
  // The one Sink WireHandler writes every reply line through (Sink's own
  // contract, wire_handler.h). `data`/`length` always include a
  // trailing '\n' -- WireHandler::writeLine() supplies it on every
  // call -- so this strips that one byte before handing off to
  // SerialTransport::writeLine(), which appends its OWN trailing
  // delimiter; passing both through would double the newline.
  class SerialSink : public Wire::Sink {
   public:
    explicit SerialSink(SerialTransport& transport) : transport_(transport) {}
    void write(const char* data, size_t length) override {
      const size_t contentLen = length > 0 ? length - 1 : 0;
      transport_.writeLine(reinterpret_cast<const uint8_t*>(data),
                           contentLen);
    }

   private:
    SerialTransport& transport_;
  };

  RadioTransport radioTransport_;
  SerialTransport transport_;
  CodalFiberLauncher launcher_;
  CodalClock clock_;  // PING's t=<ms> equivalent is now wireNowMs(); this
                      // instance now backs only handleRun()'s own dedupe
                      // timing and wireNowMs() itself (via protocol()).
  bool running_ = false;

  // NSDMI, not a hand-written constructor: each of these depends only on
  // members declared textually above it (transport_ for serialSink_;
  // wireNowMs() -- callable before its own later textual declaration,
  // same as any other member function -- for wireAdapter_; wireAdapter_
  // and serialSink_ for wireHandler_), so plain in-class initializers,
  // evaluated in declaration order, are enough -- no constructor body
  // needed to sequence them by hand. wireAdapter_ starts with a
  // placeholder Wire::Identity() (every field ""); run() replaces it
  // with the real one via setIdentity() once it is safe to read (see
  // buildIdentity()'s own comment above for why that is deferred).
  SerialSink serialSink_{transport_};
  WireAdapter wireAdapter_{Wire::Identity(), &Protocol::wireNowMs};
  Wire::WireHandler wireHandler_{wireAdapter_, serialSink_};

  // Radio RX scratch (the old-style RUN-only carve-out only -- see this
  // file's top-of-file comment); reused every poll, serial branch is
  // done with its own buffer by the time this runs each iteration.
  uint8_t rxLineBuf_[64];
};

// Lazy singleton, mirroring shims.cpp's Rig/ensure() pattern: the
// Protocol object -- and its fiber -- is constructed and started on
// first access, never from a global constructor (which would run
// before uBit.init() has brought up the CODAL fiber scheduler, and
// before microbit_friendly_name()/microbit_serial_number() are safe to
// call -- see buildIdentity()). Ticket 002 wires the actual call site:
// main.ts's `diffDrive` namespace calls this (through the
// `startProtocol()` shim defined alongside this function in
// protocol.cpp) as a top-level statement, which runs once when this
// extension's compiled code loads -- independent of whether any block
// below is ever placed in a user's program. That is what makes the
// boot banner (emitted from the top of `Protocol::run()`, before the
// loop ever blocks on a read) go out "without any host request" per
// SUC-001.
Protocol& protocol();

}  // namespace diffDrive
