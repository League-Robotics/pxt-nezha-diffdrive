---
id: '001'
title: execHelp() cannot lose its terminator
status: done
use-cases: []
depends-on: []
github-issue: ''
issue: wire-and-shim-minor-defects.md
completes_issue: true
---
<!-- CLASI: Before changing code or making plans, review the SE process in CLAUDE.md -->

# execHelp() cannot lose its terminator

## Description

`src/comms/wire_handler.cpp:771-792` (`WireHandler::execHelp`) builds the HELP
reply into `char buf[kMaxLineBytes]` with a hand-rolled `append` lambda bounded
at `pos < sizeof(buf) - 1`, then appends `"\n"` **last**:

```cpp
char buf[kMaxLineBytes];
size_t pos = 0;
auto append = [&](const char* text) {
  while (*text != '\0' && pos < sizeof(buf) - 1) buf[pos++] = *text++;
};
append("help");
for (const auto& entry : kCommandTable) { append(" "); append(entry.name); }
append("\n");
buf[pos] = '\0';
writeLine(buf);
```

Today's 18 verbs (`kCommandTable`, pinned by the `static_assert` in
`WireHandler`'s constructor, `wire_handler.cpp:340`) produce ~110 bytes against
the 240-byte buffer, so this fits with plenty of room to spare. The landmine is
structural, not a today-problem: because `"\n"` is appended after every verb
name, it is the FIRST thing `append`'s bound silently drops once the content
reaches `sizeof(buf) - 1`. A HELP reply with no trailing `\n` is a line the
host's line-based reassembler never completes -- it glues whatever the device
sends next onto the same logical line.

`WireHandler::execRun` (well below `execHelp` in the same file, ~line
1119-1154) gets the equivalent problem right: it sizes its buffer
`kMaxLineBytes + 1` and carries a comment (`wire_handler.cpp:1145-1150`)
explaining exactly why a content string that legitimately reaches the full
240 bytes needs the extra byte -- `snprintf`'s own trailing NUL would
otherwise silently eat the last content byte (here, the `\n`) to make room for
itself. `execHelp` has neither that guard nor a test pinning the terminator.

**The fix must be structural** -- a bigger buffer alone only raises the verb
count at which the same defect reappears. Acceptable approaches (pick one,
implementer's choice):

1. A `static_assert` at compile time (alongside the existing verb-count
   `static_assert` in the constructor, `wire_handler.cpp:330-341`) on the
   summed width of `"help"` + one space-plus-name per `kCommandTable` entry +
   the trailing `"\n"`, against `kMaxLineBytes` -- so a future verb whose name
   would push the reply past the buffer fails the BUILD, not the wire.
2. Reserve the final content byte structurally for `'\n'` -- bound the
   `append` loop one byte tighter (`pos < sizeof(buf) - 2`, leaving room for
   both the reserved `'\n'` byte and the closing NUL) and write `buf[pos++] =
   '\n'` unconditionally after the loop, outside `append`, so truncation (if
   it ever happens) always drops table content and never the terminator.
3. Emit HELP as multiple `writeLine()` calls if the table would overflow a
   single line -- more invasive, only worth it if the implementer judges (1)
   or (2) insufficient.

Whichever is chosen, the resulting code must make it structurally impossible
for the reply to end in anything but `'\n'`, regardless of how many verbs
`kCommandTable` grows to hold.

`src/core/diffdrive.{h,cpp}` is vendored and byte-stable -- not touched by
this ticket (it has no HELP surface).

## What to change

1. `src/comms/wire_handler.cpp` -- restructure `execHelp()` per one of the
   three options above.
2. Optionally, `src/comms/wire_handler.h` -- if a compile-time
   `static_assert` needs a named helper (e.g. a `constexpr` sum-of-lengths
   function) to compute the table's total width from `kCommandTable`, it may
   need declaring alongside the existing `kMaxLineBytes`/`kCommandTable`
   declarations. Not required if the assert can be written entirely within
   the `.cpp` file.
3. `tests/host/test_wire_grammar.py` (or a new file under `tests/host/` if a
   cleaner home fits the existing test organization better) -- add the
   regression/demonstration test described below.

## Acceptance Criteria

- [x] `execHelp()`'s reply is guaranteed by construction to end in `'\n'` --
      never merely true because today's 18 verbs happen to fit.
- [x] The fix is structural (static_assert on summed table width, a reserved
      final byte for `'\n'`, or multi-line emission) -- not simply a larger
      fixed buffer, which would only move the same failure to a higher verb
      count.
- [x] A host test demonstrates the terminator survives even when content
      would overflow a single line (see Testing below) -- this test must FAIL
      against the current (unfixed) `execHelp()` and PASS after the fix,
      since today's real 18-verb table is too small to trigger the defect on
      its own.
- [x] The real, current `kCommandTable` still produces a correct HELP line
      (content unchanged, `\n`-terminated) -- no behavior regression for the
      existing 18 verbs.
- [x] No change to `src/core/diffdrive.{h,cpp}` (vendored, byte-stable).

## Testing

- **Existing tests to run**: `uv run pytest tests/host/test_wire_grammar.py
  tests/host/test_wire_reliability.py` (HELP-adjacent wire behavior), plus
  the full host suite (`uv run pytest tests/host/`) since `wire_handler.cpp`
  is centrally shared.
- **New tests to write**: the existing 18-verb table cannot itself trigger
  the overflow (that is the whole point of the finding), so demonstrating the
  defect needs one of:
  (a) a test-only build of `WireHandler` (or a refactor that exposes the
  buffer-filling logic as a separately callable/testable unit) fed a
  synthetic, artificially long command table or verb-name list sized to
  exceed `kMaxLineBytes`, asserting the emitted line still ends in `\n`; or
  (b) a direct unit test of whatever named helper implements the chosen fix
  (e.g. the `static_assert`'s summed-width computation, tested against both a
  table that fits and a hypothetical one that would not, using the C++ host
  harness pattern in `tests/host/`). Choose whichever the implementer's fix
  shape (option 1, 2, or 3 above) naturally supports; the requirement is that
  the new test fails on the current code and passes after the fix, not that
  it exercises the real 18-verb table. Also add a plain regression assertion
  that today's real HELP reply is unchanged and `\n`-terminated.
- **Verification command**: `uv run pytest tests/host/`
