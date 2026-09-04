---
status: pending
sprint: '032'
---

# Wire minors: telemetry terminator reserve and sink strip check, RX drain loop and counters, count handleRun refusals, seq wrap, GET rebase

Priority: **Low** · Source: [code review 2026-09-02](../../../docs/code-review/2026-09-02/review.md)

Findings: CM-06, CM-07, CM-08, CM-15, CM-16 ([comms](../../../docs/code-review/2026-09-02/raw/comms.md)). Triage #13.

## Description

- **CM-07.** `emitHeader()`/`emitFrame()` drop their `\n` at 239 bytes
  and both sinks then strip the last byte blind, turning `... -12345` into
  `... -1234`: a plausible wrong number. The pinned pathological FULL frame
  is exactly 239 bytes. `buildHelpLine()` already does this right.
- **CM-06.** One inbound line per transport per pass (= per 24 ms tick
  during a job); serial ring overflow and the radio single-slot drop are
  silent; `rxFrames_`/`rxAccepted_` never increment.
- **CM-08.** `handleRun()` drops overlong/non-printable/empty-name payloads
  uncounted; the 400 ms dedupe also eats a repeated `abort`.
- **CM-15.** `expectedNext_ = id + 1` wraps to 0 at `UINT32_MAX` (theoretical).
- **CM-16.** `GET rebase` answers `err 1` "unknown name" for an advertised field.

## Remedy

Bound the append at `sizeof - 2` and write `\n` last; sinks check the
terminator before stripping; extend the pathological-frame test to assert
it. Drain up to N lines per transport per pass; count the `rxReady_` drop;
wire or delete the two counters. One `runMalformed_` counter; exempt
bypass names from dedupe. Guard the wrap. `Result onGet(...)` or a
documented "write-only" code.
