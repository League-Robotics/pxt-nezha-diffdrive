---
status: pending
sprint: 008
---

# Host tests compile at C++20 while both real targets compile at C++11, so target-only compile errors pass the suite

Priority: **High** — found the hard way on 2026-08-24 by sprint 004 ticket
005, which could not produce a flashable hex *at all* while the full host
suite was green at 253 passed.

## The gap

- `tests/host/` compiles the firmware's portable C++ with
  `/usr/bin/c++ -std=c++20` (`tests/host/test_kernel_harness.py:72`, and
  documented in `tests/host/DESIGN.md:88`).
- Both real embedded build targets compile with **`-std=c++11`**, baked
  into the pxt-microbit target's own yotta/CMake toolchain files and not
  overridable from this project's `pxt.json`. This applies to *both*
  variants the cloud compiler builds in parallel: the legacy
  mbed-classic/yotta `bbc-microbit-classic-gcc` target and the
  codal-microbit-v2 target.

So the project's only assertion-based test suite validates the firmware
against a language standard nine years newer than the one the robot is
built with. **Any C++14/17/20 construct in `src/` passes every host test
and fails the actual product build.** The host suite is structurally
incapable of catching this class of defect.

## The instance that exposed it

Sprint 004 ticket 004 gave `Wire::Column` (`src/wire_handler.h:157-161`)
default member initializers:

```cpp
struct Column {
  const char* name = "";
  int32_t value = 0;
  bool hex = false;
};
```

Under **C++11**, a class with default member initializers is not an
aggregate, so `columns_[i++] = {"seq", ..., false};`
(`src/wire_adapter.cpp:539-579`, ~20 sites) is neither valid
aggregate-initialization nor constructible via any declared constructor.
C++14 restored that aggregate rule, which is why it compiles at `-std=c++20`
and produced ~20 identical hard errors per build variant on both real
targets:

```
error: no match for 'operator=' (operand types are 'Wire::Column'
       and '<brace-enclosed initializer list>')
```

Ticket 004 shipped with six scale tests plus a golden-frame test, all
passing, against code that could not be compiled for a robot.

## Why this is worse than a one-off bug

The defect took a full sprint's worth of work to surface, and only because
one ticket happened to run a real build. Nothing else in the pipeline
compiles `src/` for the target: every prior ticket's "tests pass" signal
was true and meaningless for target viability. The next NSDMI, `auto`
return type, generic lambda, or `if constexpr` reintroduces it silently.

## Third instance, and it defeats the gate this issue's stopgap added (2026-08-24)

Sprint 006 merged three new headers — `src/heading_wrap.h`,
`src/encoder_glitch_armor.h`, `src/encoder_pose_source.h` — **without adding
them to `pxt.json`'s `files` manifest.** PXT copies only manifest-listed files
into the build, so after sprint 006 closed, `master` could not produce a hex at
all. All 324 host tests passed. Found on 2026-08-24 by sprint 007 ticket 001,
the first ticket after 006 that happened to run a real build.

**The `-std=c++11 -fsyntax-only` gate ticket 007 added cannot catch this
class.** The gate invokes the compiler directly on named translation units; it
never reads `pxt.json`. So a file can be gate-covered, host-tested, and
syntactically perfect at both standards while still being invisible to the
actual product build. The gate closes the *language-standard* hole and nothing
more — worth stating plainly, because its existence could otherwise be mistaken
for "target viability is covered now."

This is now three distinct target-only defects, none catchable by the host
suite, each found only because some ticket happened to run `make_deploy.py`:

| # | Defect | Found by | Would the C++11 gate catch it? |
|---|---|---|---|
| 1 | `Wire::Column` NSDMI → non-aggregate under C++11 | sprint 004 ticket 005 | Yes (that's why it exists) |
| 2 | `setRxBufferSize(uint8_t)` — 480 truncated to 224 | sprint 004 ticket 005 (`-Woverflow`) | No — needs the real toolchain's headers |
| 3 | Three headers absent from `pxt.json` `files` | sprint 007 ticket 001 | **No — the gate never reads `pxt.json`** |

The common factor is not the C++ standard. It is that **nothing in the
per-ticket or per-sprint flow requires a real build.** Sprint 006 closed
without any ticket invoking `make_deploy.py`, and `close_sprint` runs only
`uv run pytest`.

## What to do

Options, roughly in increasing cost:

1. **Match the standard**: compile the host suite with `-std=c++11`. Most
   faithful, and it makes the existing 253 tests meaningful for target
   viability. Risk: existing test-side code (shims, fakes, and the tests
   themselves) may use newer features deliberately, so this may not be a
   one-line change — measure before committing to it.
2. **Add a target-standard syntax gate**: keep the suite at C++20 but add a
   cheap `-std=c++11 -fsyntax-only` compile of every `src/` translation
   unit as a test. Catches the whole class without touching existing test
   code. Note the limit: it checks the *portable* subset only, since the
   CODAL-bound files need `pxt.h`.
3. **Build the hex at sprint close** — on the evidence above, this is the
   option that actually addresses the class, and the other two do not. "It
   builds for the robot" is currently verified once per *accident*, not once
   per sprint. A single `make_deploy.py` run wired into `close_sprint` (or a
   mandatory build-checkpoint ticket per sprint, the shape sprint 004's ticket
   005 already had) would have caught all three defects above. Note the two
   known-benign build outcomes it must tolerate without failing: the legacy V1
   `bbc-microbit-classic-gcc` variant's hex-merge failure, and the
   nondeterministic packaging abort (`TS9283`, and at least one `TS9043`
   variant) that succeeds on retry — triage on "did any `.cpp` fail to
   compile?", not on the error code.

Whichever is chosen, the acceptance test is the same: reintroduce a
C++14-only construct into `src/` and confirm something fails *before* a
build checkpoint does.

## Related

- `settle-tick-loop-is-not-host-testable.md` and
  `host-harness-double-drift.md` (both sprint 008) — same family: the host
  harness diverging from what production actually does. This issue is the
  most severe member of that family, because it invalidates the suite's
  signal for *any* defect of this class rather than for one behavior.
- Sprint 004 ticket 005's exception block records the full diagnosis.
