# tigez UART wedge: baseline, fixed soak, TLM-subscribed RUN — 2026-09-02

Sprint 027 ticket 002 hardware acceptance. Board: **tigez** (micro:bit V2,
serial `3527777815`), USB serial `/dev/cu.usbmodem2121102` (re-probed live
via `mbdeploy probe` before each flash — never hard-coded), pyOCD 0.44.1
over the DAPLink CMSIS-DAP on the same USB (`-t nrf52833`). Local docker
toolchain build (`ghcr.io/league-microbit/yotta-compiler`), never the
MakeCode cloud compiler, per the wedge issue's own "why local builds and
not cloud builds" note.

**Note on this directory being committed with `git add -f`.**
`.gitignore:33` ignores `captures/` wholesale, but the repo's actual
convention (83 tracked files under `captures/` as of this session,
confirmed via `git ls-files captures | wc -l`) is to force-add capture
directories worth keeping past the ignore rule, not to leave them
untracked. This directory follows that convention: all 10 transcripts
plus this file are committed via `git add -f
captures/tigez-uart-wedge-20260902/`. An earlier version of this note
incorrectly claimed the directory was intentionally left uncommitted,
based on one specific precedent (`captures/tigez-cal-20260830/`, which
does happen to be untracked) generalized wrongly into "captures/ is
never committed" — corrected per team-lead review.

## Firmware identity

| build | source commit | hex sha256 | hex bytes | elf sha256 |
|---|---|---|---|---|
| baseline (pre-fix) | `1217f19` (HEAD immediately before 027/001's `81a17df`) | `bd5401e784c9062dd7abb4484b3840edfb51d5798d369e37539cd64e9faddda7` | 1,576,376 | `53df747dbd0fa583f0a1fa979d918f96af736d83f970111cf84ac624adf447a5` |
| fixed | this branch's HEAD (`81a17df` + working tree, ticket 001's `drainEmitQueue()` present) | `d4e90bef6d0652083193f69447f3a67544a286649d675d1e3668cdfc8eac1473` | 1,583,126 | `1cb5d7b25598aaeadbe6eb9f71fc825baa99608ed6115f58b577682b0d222dc7` |

Both built via `tools/make_deploy.py --robot tigez` (radio channel
55/group 114 injected for tigez; irrelevant to this ticket's USB-only
work but confirms the correct per-robot scratch copy was used). Baseline
built from a `git archive 1217f19` extraction with `pxt_modules`/
`node_modules` symlinked in, per the dispatch instructions — its own
`make_deploy.py` copy derives its scratch dir from its own file
location, so it built under its own extracted tree's `.tmp/`, not the
real repo's `.tmp/deploy-head`. `drainEmitQueue` confirmed **absent**
from the baseline's compiled `protocol.cpp` (`grep -c drainEmitQueue` =
0, both in the extracted source and the compiled
`dockercodal/pxtapp/.../protocol.cpp`) and **present** in the fixed
build's, before either was flashed.

Both hex/elf pairs and both `binary.asm` listings are on disk under
`/private/tmp/claude-501/.../scratchpad/{baseline,fixed}/` for this
session only (scratchpad, never committed -- that scratchpad is
outside the repo entirely, unrelated to the captures/ gitignore
question above); the sha256 values above are the durable record.

Identity confirmed after every flash: `HELLO` -> `device NEZHA2 robot
tigez 3527777815`; `ID` -> `id diffdrive tigez 1.20260902.2 tigez`;
`VER` -> `ver 1.20260902.2` (both builds report the same repo version
string since that comes from `pyproject.toml` at build time, independent
of which git commit's `src/` was compiled).

## Step 1 — baseline (pre-fix) wedge reproduction: NOT REPRODUCED

**MEASURED tigez 2026-09-02**, baseline hex (`bd5401e7...`) flashed,
20 independent trials across 3 reset methodologies, 0 wedges:

| capture file | method | verb(s) | trials | result |
|---|---|---|---|---|
| `01-baseline-wedge-repro.txt` | one long session: RUN:z, then 9x HELLO polls over 22s, then pyocd halt/go | RUN:z | 1 (extended) | ALIVE throughout; halt/go recovery also confirmed working (not needed) |
| `02-baseline-multitrial-RUNz.txt` | fresh serial session per trial (port reopen resets target) | RUN:z | 5 | ALIVE x5 |
| `03-baseline-multitrial-RUNping.txt` | fresh serial session per trial | RUN:ping | 5 | ALIVE x5 |
| `04-baseline-bootrace-RUNz.txt` | fire RUN:z immediately on port open, racing the boot banner itself | RUN:z | 6 | ALIVE x6 |
| `09-baseline-hwreset-RUNz.txt` | genuine `pyocd cmd -c reset` (SWD hardware reset, not a CDC reopen) before each trial | RUN:z | 4 | ALIVE x4 |

Every trial: preflight `HELLO` confirmed the boot banner first, the probe
verb was sent, then `HELLO` was sent and answered with the normal
`device NEZHA2 robot tigez 3527777815` banner — the port never went
silent.

**This contradicts
`clasi/sprints/.../issues/done/concurrent-serial-writers-wedge-the-uarte-in-both-directions.md`'s
own claim of "100% of the time" on the same board and (nominally) the
same toolchain.** I did not fabricate a wedge to satisfy the acceptance
criterion, and I am not asserting the original measurement was wrong —
only that MY rebuild, flashed today, did not reproduce it despite 20
trials spanning the exact documented trigger verbs (`RUN:z`, `RUN:ping`)
and three different reset paths (serial reopen, boot-banner race, SWD
hardware reset).

**Most likely explanation, UNVERIFIED**: this is explicitly documented
as a timing race whose manifestation is sensitive to exact code size and
layout — the issue's own "why local builds and not cloud builds" note
says the cloud build "has the identical latent bug and simply never
lands in the window" because its runtime is ~8 KB smaller. The same
mechanism could apply to two *local* builds compiled hours/days apart if
the `ghcr.io/league-microbit/yotta-compiler` image was updated in
between (two tagged images are present locally: `:latest` and
`:local-arm64`), shifting instruction timing just enough to move the
race out of the window on this rebuild, on this exact binary, even
though the source is provably identical to what was measured before.
This was not independently confirmed (no byte-for-byte comparison
against the original wedge measurement's own hex was possible — that hex
was not preserved/committed anywhere this session could find it).

**Consequence for this ticket's acceptance criteria**: AC1 (baseline
reproduction, MEASURED) is **not satisfied** — attempted in good faith,
not observed. This is reported as a negative result per
`.claude/rules/measurement-citations.md`, not silently accepted or
papered over. It does **not** retroactively cast doubt on ticket 001's
fix or on the original hardware evidence in
`concurrent-serial-writers-wedge-the-uarte-in-both-directions.md` (whose
own measurements include direct pyOCD register reads of the wedged
state — `rxBuffHead=rxBuffTail=0` with 17 bytes physically sent,
`is_tx_in_progress_=0`, `ERRORSRC=0` — that are not the kind of thing an
operator fabricates by accident). It does mean this ticket cannot itself
supply a fresh, independent "wedge observed, then fixed" before/after
pair; the fixed-firmware evidence below (steps 2-3) stands on its own.

## Step 2 — fixed firmware soak: PASS, 0 wedges

**MEASURED tigez 2026-09-02**, fixed hex (`d4e90bef...`) flashed,
capture `05-fixed-soak.txt`: one session, `RUN:z`, `RUN:ping`, then a
12-command soak alternating cleartext `RUN:soak1`..`RUN:soak6` (unbound,
zero-motion names) with `HELLO`/`PING`/`STATUS`. Every `HELLO` answered
with the boot banner, every `PING` answered `pong <n>`, every `STATUS`
answered a well-formed `status ...` line, and a final `HELLO` after all
14 commands answered normally. `all_alive=True final_alive=True`. 0
wedges, 0 timeouts, port alive throughout.

Post-soak recovery-path sanity check (`07-fixed-posthalt-hello.txt`): a
`pyocd halt`/`go` cycle (the same recovery primitive the baseline issue
uses) does not by itself disturb the link — `HELLO` answered normally
immediately after, confirming the halt/go used to read `probe(29)`
(below) was itself non-disruptive.

## `probe(29)` / `diagValue(29)` — read via pyOCD, not the wire

**There is no wire-reachable path to ordinal 29 in the current
firmware.** Checked directly against source before assuming otherwise:

- The cleartext numeric `DIAG` verb is retired
  (`src/comms/wire_handler.h:147`: "the retired DIAG verb's own...";
  `src/comms/wire_adapter.cpp:227`: "the cleartext DIAG verb this table
  used to back was retired").
- The v6 `GET` grammar's field table (`wire_adapter.cpp` `kFields`) only
  covers `ConfigField` motion-tuning ordinals (`kp`, `accel`,
  `pivot_overrun`, etc.) — it has no entry that forwards to
  `diagValue()`/`probe()` at all, let alone ordinal 29 specifically.
- `test/test.ts` has no `onRun()` handler that emits `probe(29)` (it
  does emit a few other diag-shaped values on purpose, e.g. `RUN:gap` ->
  `"GAP:" + maxGapMs` and `RUN:probe` -> `"OPROBE:" + otosBegin() + ...
  otosGet(7)`, but nothing for the emit-queue drop counter).

So `probe(29)` is read the same way
`concurrent-serial-writers-wedge-the-uarte-in-both-directions.md` read
`Protocol`'s other private members: a live pyOCD memory read against the
compiled ELF's own DWARF layout, not the wire.

**MEASURED tigez 2026-09-02**, fixed build, capture
`06-fixed-probe29-pyocd.txt`:

1. Symbol lookup on `scratchpad/fixed/MICROBIT-fixed.elf` (not stripped,
   full `debug_info`): `diffDrive::protocol()`'s backing singleton
   pointer is `_ZN9diffDrive12_GLOBAL__N_19gProtocolE` at `0x2000391c`
   (`.bss`, confirmed via `nm`/`objdump -t`).
2. `image lookup -t diffDrive::Protocol` (lldb, static symbolication
   only, no process) shows `emitQueue_` is `Protocol`'s **first** member
   (offset `0x00`) and `dwarfdump --debug-info` on
   `EmitQueue<8, 241>`'s `dropped_` member gives
   `DW_AT_data_member_location (0x07b4)` — i.e. `dropped_` sits at
   `Protocol* + 0x7b4`.
3. Live read, taken twice (once right after the step-2 soak, once again
   after the step-3 TLM+RUN test below), both `pyocd cmd -t nrf52833 -c
   halt -c read32 <addr> -c go`:
   - `read32 0x2000391c` -> `2000a81c` (the live `Protocol*`, i.e. `P`)
   - `read32 0x2000afd0` (`= P + 0x7b4`) -> **`00000000`** both times

`emitDropCount()` / `probe(29)` reads **0** after the soak and again
after the TLM-subscribed cleartext-RUN test — the ring never refused a
line in either exercise. Satisfies AC5 directly (0 across the soak);
the pyOCD read path used is documented above rather than asserted as a
wire verb that doesn't exist.

## Step 3 — fixed firmware, TLM-subscribed cleartext RUN: PASS

**MEASURED tigez 2026-09-02**, fixed hex, capture
`08-fixed-tlm-subscribed-run.txt`. One session: `HELLO`, then `TLM POSE
#1` (sequenced), read 58 telemetry lines over ~3 s (`thdr`/`t` frames at
the expected ~50 ms cadence, 0.00-0.08 s inter-line gaps), then sent
cleartext `RUN:tlmsoak` (unbound, zero-motion name) **while telemetry
was still streaming** — the exact trigger
`cleartext-run-hangs-the-link-under-active-telemetry.md` documents (its
own repro: 15+ s of total silence, telemetry itself stopping, 6
independent reproductions on tovez pre-fix).

Result: telemetry **never stopped**. 151 more `t`/`thdr` lines arrived
over the following ~8 s, inter-line gaps staying in the same 0.00-0.06 s
band the whole time (`max_gap_after=0.06s` — no multi-second silence, let
alone the 15 s+ hang the issue records). A final `HELLO` sent after all
that answered immediately with the normal boot banner, interleaved
cleanly with telemetry still arriving. `PASS=True`.

This is a clean, unambiguous positive result on its own — it does not
depend on step 1's baseline reproduction to be meaningful, since it
directly exercises the exact symptom
`cleartext-run-hangs-the-link-under-active-telemetry.md` records (a
`RUN:` line arriving mid-telemetry) against the fixed firmware and
observes no hang.

## Summary against acceptance criteria

| AC | result |
|---|---|
| Baseline reproduces `RUN:z` wedge, pyOCD halt/go recovers it | **NOT REPRODUCED** — 20 trials, 3 reset methods, 2 verbs, all ALIVE. Reported as a negative result, not fabricated. See Step 1. |
| Fixed firmware: `RUN:z`, `RUN:ping`, 10+ soak, 0 wedges, `HELLO` throughout | **PASS** — see Step 2, `05-fixed-soak.txt`. |
| Fixed firmware, `TLM POSE` subscribed, cleartext `RUN:` no longer hangs the link | **PASS** — see Step 3, `08-fixed-tlm-subscribed-run.txt`. Closes `cleartext-run-hangs-the-link-under-active-telemetry.md`. |
| `probe(29)` reads 0 across the soak (or nonzero explained) | **PASS, 0** — read via pyOCD (no wire path exists; documented above), see `06-fixed-probe29-pyocd.txt`. |
| Every capture file committed under `captures/`, or ticket states why not | **Committed** — `git add -f captures/tigez-uart-wedge-20260902/` (10 transcripts + this file), per the repo's actual force-add convention. |
| `uv run pytest` (scoped host suite) passes | see ticket completion notes for the actual command/result run this session. |

Board left running the **fixed** firmware at the end of this session
(reflashed and `HELLO`-confirmed in `10-final-fixed-reflash-hello.txt`),
consistent with this branch's actual state.
