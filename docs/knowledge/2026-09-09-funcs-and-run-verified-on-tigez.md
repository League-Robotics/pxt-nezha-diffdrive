# `FUNCS` and `RUN` verified on tigez, with a parser recipe for a UI

**MEASURED tigez 2026-09-09** over hodr's mbdeploy serial daemon
(`tigez._mbserial._tcp` at 192.168.1.148:33661), firmware
`1.20260907.5`, profile `calibration-0.20260909.1` (the
nezha-robot-template calibration program, whose `test/*.ts` bind the
names listed below). Every line quoted here is in
`captures/tigez-funcs-run-20260909/session-*.log`, timestamped by
`captures/tigez-funcs-run-20260909/session.py`; the one-shot
`mbdeploy connect tigez "FUNCS #1" --remote` form returned the same
listing.

The Nezha brick was unpowered for the whole session (`connL=0 connR=0`,
`cyc=2`), so only handlers that do not drive the motors were exercised
(`trace`, `counters`, `diag`). That `push`/`turn`/`square`/... actually
move is UNVERIFIED here; proving it needs a powered brick and the
overhead camera, never a receipt.

## Verdict

Both verbs work. `FUNCS` lists every name the program bound with
`onRun()`, and `RUN <name> [arg...] #<id>` dispatches to that handler
with its argument. Two things a UI author must know that the source
comments get wrong:

1. **The ack does NOT terminate the `FUNCS` listing. It precedes it.**
   `WireHandler::dispatch()` calls `replyAck()` and THEN the verb's
   executor (`src/comms/wire_handler.cpp:626-635`), so the wire order
   is `ack`, then N `funcs` lines, then nothing. There is no end
   marker. `execFuncs()`'s comment, `tools/robotlink.py:149-151` and
   `tools/wire_acceptance.py:586` all say the ack "tells the host it
   has them all"; the log says otherwise (session-1, 4.033 s: the ack
   and the first `funcs` line share a millisecond, the 17th arrives
   18 ms later).
2. **Signatures are always empty from a blocks program.** `onRun()`
   registers every name with `""` (`src/blocks/run.ts:128`), so the
   listing tells a UI *which* names exist, not their arity or types.
   The grammar reserves a second token for that (`funcs <name> <sig>`)
   but nothing fills it today.

## What the wire looks like

```
> HELLO
< device NEZHA2 robot tigez 3527777815
> FUNCS #1
< ack 1 0 none
< funcs trace
< funcs counters
< funcs square
< funcs circle
< funcs calx
< funcs cala
< funcs spin
< funcs line
< funcs abort
< funcs sense
< funcs push
< funcs turn
< funcs speed
< funcs m
< funcs t
< funcs clear
< funcs diag
< DBG:wifi state=1 ip=- peer=-:0 ...          <- unsolicited, interleaves
```

Listing order is registration order (the order the program's
`onRun()` calls ran at start-up), 17 entries here against a table of 32
slots (`src/comms/run_registry.h`); past 32 the newest are dropped and
counted, not listed.

```
> RUN trace 1 #1            handler(1)     -> emits its own line
< ack 1 0 none
< trace=1
> RUN counters #3           no arg         -> handler(0)
< ack 3 0 none
< C now i2cf=2 lease=0 sat=0 deficit=0 ...
> RUN trace abc #5          non-numeric    -> handler(0), no error
< ack 5 0 none
< trace=0
> RUN trace 1 2 3 4 5 6 7 8 9 10 #6         extra args accepted (cap 16)
< ack 6 0 none
< trace=1
> RUN nosuchname #2         unlisted name  -> acked, then refused
< ack 2 0 none
< err 1 #2
> RUN #3                    no name        -> decode failure, stream stalls
< nack 3 0 none
< err 2 #3
> STATUS                    every later line re-nacks until #3 is resent
< status ... next=3 ...
< nack 3 0 none
> funcs #1                  lowercase verb -> SILENTLY DROPPED, id unconsumed
> FUNCS #2
< nack 1 0 none             (the robot still expects #1)
```

The handler's output is free text from `emitLine()`, not a `ret` line.
`ret <text> #<id>` exists in `execRun()` for a native adapter that sets
`hasResult`, but a blocks `onRun()` handler is void, so a UI gets the
ack plus whatever the program prints and nothing structured.

## Parser recipe

Rules a UI needs, each one measured above:

- **Verbs are UPPERCASE and case-sensitive** (protocol S2.1: commands
  uppercase, replies lowercase). A lowercase-led line is treated as
  another robot's reply and dropped with no `nack`, no `err`, nothing,
  and the sequence id is not consumed. Names inside `RUN` are matched
  exactly as registered (lower case by convention).
- **Both verbs are sequenced.** Send `FUNCS #<id>` / `RUN ... #<id>`
  with `<id>` starting at 1 after `HELLO` and incrementing per line.
  An unsequenced line parses as `#0` and is dropped.
- **Terminate the listing with a trailer, not the ack.** Send
  `FUNCS #<id>\nPING\n` in one write (or follow with `STATUS`). The
  robot handles lines in order on one fiber, so `pong` (or `status`)
  arrives after the last `funcs` line: session-4, 17 lines between
  `ack 1` at 2.031 s and `pong` at 2.047 s, and the same with `status`.
  A 200 ms idle timeout after the last `funcs` line also works on this
  link (the whole listing spans ~15 ms) but a trailer is deterministic.
- **Ignore everything you did not ask for.** `DBG:` lines, telemetry
  `t`/`thdr` frames and handler output interleave freely; only lines
  starting with `funcs ` belong to the listing.
- **Reply grammar**:
  - `ack <id> <done> <reason>`: line accepted, executor about to run.
    `<done>`/`<reason>` describe the last finished MOTION job, not
    this `RUN`.
  - `err <code> #<id>` after an ack: accepted but refused on merits.
    Code 1 = unknown/unlisted name.
  - `nack <expected> <done> <reason>` plus `err 2 #<id>`: decode
    failure (e.g. `RUN` with no name). Resend that exact id
    well-formed, or send `HELLO` to start over; until then every
    inbound line re-nacks.
  - `funcs <name>` or `funcs <name> <signature>`: one entry. One or
    two space-separated tokens, never a `#<id>`.
- **Calling a listed name**: `RUN <name> [<arg> ...] #<id>`. The first
  argument reaches the handler as a number, `0` when absent or
  non-numeric; up to 16 arguments in total (`kMaxRunArgs`,
  `src/comms/wire_handler.h:576`), the rest readable by the handler via
  `runArg(i)`/`runArgText(i)`.

Reference parser (Python, a transcript of the rules above):

```python
import re, socket

_ACK  = re.compile(r'^ack (\d+) (\d+) (\S+)$')
_NACK = re.compile(r'^nack (\d+) (\d+) (\S+)$')
_ERR  = re.compile(r'^err (\d+) #(\d+)$')

def read_lines(sock, until, timeout=2.0):
    """Yield stripped lines until one satisfies `until` (inclusive)."""
    sock.settimeout(timeout); buf = b''
    while True:
        d = sock.recv(4096)
        if not d: return
        buf += d
        while b'\n' in buf:
            raw, buf = buf.split(b'\n', 1)
            line = raw.decode('utf-8', 'replace').strip('\r ')
            if not line: continue
            yield line
            if until(line): return

def funcs(sock, seq):
    """-> {name: signature_or_None}; raises on nack/err."""
    sock.sendall(f'FUNCS #{seq}\nPING\n'.encode())   # PING is the terminator
    names, acked = {}, False
    for line in read_lines(sock, until=lambda l: l.startswith('pong ')):
        if _ACK.match(line):   acked = True
        elif _NACK.match(line): raise RuntimeError(f'stream stalled: {line}')
        elif _ERR.match(line):  raise RuntimeError(line)
        elif line.startswith('funcs '):
            toks = line.split()                      # ['funcs', name, (sig)]
            names[toks[1]] = toks[2] if len(toks) > 2 else None
        # anything else (DBG:, telemetry, handler output) is ignored
    if not acked: raise RuntimeError('FUNCS not acked')
    return names

def run(sock, seq, name, *args):
    """-> (ok, lines the handler emitted before the trailer pong)."""
    argtxt = ''.join(f' {a}' for a in args)
    sock.sendall(f'RUN {name}{argtxt} #{seq}\nPING\n'.encode())
    ok, out = False, []
    for line in read_lines(sock, until=lambda l: l.startswith('pong ')):
        if _ACK.match(line):    ok = True
        elif _ERR.match(line):  ok = False; out.append(line)
        elif _NACK.match(line): raise RuntimeError(f'stream stalled: {line}')
        elif not line.startswith(('pong ', 'DBG:', 't ', 'thdr ')):
            out.append(line)    # the handler's own emitLine() text
    return ok, out

# sock = socket.create_connection((host, port)); sock.sendall(b'HELLO\n')
# ... consume the `device ...` banner, then seq = 1:
# table = funcs(sock, 1)            # {'trace': None, 'counters': None, ...}
# ok, out = run(sock, 2, 'trace', 1) # (True, ['trace=1'])
```

Whether the `pong` trailer after a `RUN` also marks the handler's
*completion* is UNVERIFIED: the three handlers exercised return in
under 20 ms, so the log cannot distinguish "handler finished before
pong" from "pong answered while a long handler still runs". A tour-length
handler on a powered brick would settle it (`run.ts`'s own doc says
handlers run nested on the protocol fiber, which would make the trailer
wait).

## Stale source claims found on the way

Filed as `clasi/issues/funcs-ack-precedes-the-listing-and-stale-run-colon-comments.md`:

- `src/comms/wire_handler.cpp` `execFuncs()` header, `tools/robotlink.py:149-151`,
  `tools/wire_acceptance.py:586-599`: "the ack terminates the
  variable-length reply". It precedes it (see verdict 1). The
  acceptance check passes only because it waits a fixed 1.5 s.
- `src/comms/wire_adapter.h:263-273`: says a listed name "is
  addressable as `RUN:<name>`, NOT as `RUN <name> #id`, which still
  errs kUnknown". Reversed since d4d8e4e (2026-09-07): `RUN <name> #id`
  is the only form that dispatches and the colon form is dropped
  (`clasi/issues/high/colon-run-form-is-silently-not-dispatched.md`).
- The signature slot is never populated by blocks, so the UI-facing
  promise of `funcs <name> <signature>` is currently empty.
