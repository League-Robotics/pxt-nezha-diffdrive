# Code Review Guidelines

How code reviews are conducted in this repository. Each review produces a
dated entry under `docs/code-review/YYYY-MM-DD/` containing the review
report; findings are then converted into CLASI issues that feed the next
round of development. The review itself changes no source code — `src/` and
`tests/` are protected paths, and all remediation (including comment
cleanup) is ticketed work.

## Scope

- **Primary**: `src/` — the C++ firmware (kernel, motion engine, wire
  protocol, transports, hardware ports) and the TypeScript block/shim layer
  (`main.ts`, `shims.cpp`), plus `pxt.json` wiring.
- **Secondary**: `tests/host/` (Python host test harness and C++ shims),
  `test/` (PXT test files), `tools/` (Python bench tooling).
- **Excluded**: `node_modules/`, `built/`, `pxt_modules/`, `.tmp/`,
  generated files, and CLASI process artifacts.

Findings that duplicate an already-filed issue or work already planned in
an open sprint are cross-referenced, not re-reported.

## Phase 0 — Design documents first

The review is grounded in the CLASI per-subsystem design-doc model before
any code is judged:

- `docs/design/design.md` — system-level document: what the system is, the
  subsystem map (one line each), and global conventions.
- One `<root>/DESIGN.md` per declared source root — an overview of that
  tree.
- The doc set must pass `clasi design validate`.

**Repo-specific mapping.** This requires two config changes
(`design_docs: enabled` and a `sources:` list — proposed:
`[src, tools, tests, test]`). The source roots here are *flat* — `src/`
has no subdirectories — so the logical subsystems (kernel, motion engine,
wire protocol/grammar, transports, ports, shim + blocks; host harness;
bench tooling) are documented as sections of each root's `DESIGN.md`
rather than as per-directory docs. `test/`'s doc is deliberately thin.

The existing `overview.md`, `specification.md`, and `usecases.md` remain
authoritative for what they cover; the design docs must agree with them or
explicitly correct them. Where recent protocol work (v5 → v6 wire grammar,
radio transport, telemetry) has outrun these documents, updating them is
part of this phase.

**Then the assessment**: implementation and design are compared against
the docs. Every divergence is a finding that names which side is wrong —
the document or the code.

## Review dimensions

### 1. Correctness — gotcha bugs and landmines

Every correctness finding must state a concrete failure scenario (inputs
or state → wrong behavior) and be verified against the actual code, not
pattern-matched. Categories that matter in this codebase:

- Integer overflow/wraparound: encoder counts, millisecond clocks,
  fixed-point ×1000 scaling.
- Unit mismatches: cm vs mm, deg vs rad, per-wheel vs body frame, the
  left-motor mirroring convention.
- Concurrency and fiber-safety: kernel fiber vs. block-call interleaving,
  lazy-init races, init order.
- Wire protocol: framing, buffer bounds, the radio packet size limit,
  version negotiation, malformed-input handling.
- I2C failure paths: what happens when the brick is absent, latched, or
  mid-transaction.
- PXT traps: shim arity/adjacency, simulator/hardware behavior divergence,
  silent no-ops in fallback bodies.

### 2. Future landmines

Code that is correct today but positioned to break: hidden coupling
between files, duplicated constants (especially protocol values defined
independently in C++, TypeScript, and Python), implicit invariants nothing
asserts or documents, magic numbers, and behavior that only works because
of an undocumented calling order.

### 3. Modularity and information hiding

- Is every piece of code required? Dead code, speculative generality, and
  vestigial paths from superseded sprints are findings.
- Is anything implemented by copying code from one place to another
  instead of sharing it?
- Is the public surface minimal? Students see blocks; programmers see
  headers. Anything exposed that a user or caller should not engage with
  is a finding.
- Layering: the kernel must not know about MakeCode or I2C; ports must not
  know about blocks; the protocol layer must not reach into motion
  internals. Violations in either direction are findings.

### 4. API quality against use cases

Walk the use cases (`docs/design/usecases.md`, plus the bench-tooling
flows) and ask: *how would you actually write a program that drives this
robot?* Report awkward sequences, missing operations, surprising silent
failures (e.g. commands silently refused while e-stopped or
stall-latched), and places where the API makes the easy thing hard or the
wrong thing easy.

### 5. Readability for students

Students at our programming school will read this code. Prefer clarity
over cleverness. Findings include: names that don't say what a thing is,
functions doing several jobs, expressions requiring tribal knowledge to
parse, and abbreviations that save keystrokes at the reader's expense.

### 6. Comment hygiene

Comments are aids to future readers — **not historical documents**. The
review produces a concrete delete/rewrite list, reducing comments to the
minimal set that earns its place.

Delete:
- Narration of what the next line visibly does.
- Sprint/ticket archaeology ("changed in 003-002", "was previously X").
- Agent brain-dumps: reasoning transcripts, justifications addressed to a
  reviewer, restatements of the diff.

Keep (and write well):
- Invariants and constraints the code cannot express.
- Units and coordinate/sign conventions at declaration sites.
- Hardware gotchas (measured brick failure modes, timing requirements).
- Wire-format layouts.

What "keep" looks like in practice, concretely:
- `nezha_port.cpp`'s wedge/glitch-armor comments — the 12/12 measured
  wedge-window and the phantom-teleport capture are stated as measured
  facts, not asserted.
- `diffdrive.cpp`'s `kMaxCycleGapUs` block — states the failure it
  detects (a missed tick) and the recovery (re-anchor, don't integrate)
  at the point that does it.
- `wire_adapter.cpp`'s `mradToRad` — names itself as *the* wire's one
  milliradian→radian conversion seam, so every caller can point at it
  by name instead of re-explaining the conversion.
- `main.ts`'s no-initialiser trap on the `runParts`/`runNames`/... block
  — documents a PXT init-order hazard that is invisible from the code
  alone and was measured on hardware, not theorized.
- `shims.cpp`'s vevov-wiring forensics and starvation-watchdog section —
  hardware-specific facts (which motor is mirror-swapped, the
  ~100-150 ms watchdog fire window) that no amount of reading the code
  would recover.

#### Recurring anti-patterns (delete or rewrite on sight)

A 2026-08-23 audit of ~854 comment blocks across this repo (`docs/code-
review/2026-08-23/raw/comment-audit.md`) found the noise clustered into
five repeatable shapes. Watch for these when writing or reviewing:

1. **Sprint/ticket archaeology as file headers.** A header that narrates
   which ticket added what, in order, instead of stating the current
   contract. Extreme case: `wire_adapter.h`'s pre-cleanup 108-line
   ticket chronicle (collapsed to a ~17-line contract summary in sprint
   009 ticket 004). Git history already stores this; the header should
   state only what's true now.
2. **Justification-to-reviewer essays around decisions.** A
   multi-paragraph "DECISION (this ticket's own acceptance criteria
   require one)…" block defending a choice against an imagined
   reviewer. Examples: `wire_adapter.h`'s old `lastDone()` essay and
   `shims.cpp`'s settle-loop essay. Rule: keep the decision plus one
   line of reason; the defense belongs in the ticket or PR, not the
   source.
3. **Stale cross-layer claims after a refactor.** A comment asserts
   what *another* file or an earlier protocol version does, and rots
   silently when that changes. Examples: "the other five [verbs] answer
   `kUnknown`" (false the moment a sixth verb ships), "for the Protocol
   v5 wire link / COBS keyed on `0x0A`" (v6's grammar is text/token
   based — there is no COBS layer to cite), and dangling `readLine()`
   references to a method that no longer exists. Rule: describe the
   contract at *this* seam; point elsewhere by name, never by restating
   another layer's behavior.
4. **Diff restatement / caller-history comments.** A comment describes
   the edit, not the code. Examples: "fields formerly here moved to X
   (ticket N)", "now thin forwards into `wheelsV()` — the math is
   unchanged", `shims.cpp`'s old "Second/Third/Fourth caller (ticket
   N)…" narration. Rule: the code immediately below already says this;
   the comment adds nothing a diff wouldn't.
5. **Orphaned/misplaced comments surviving code motion.** A comment
   stays behind, or lands over the wrong declaration, when its code
   moves. Examples: `shims.cpp`'s dangling "first one or two pivots
   over-rotate" fragment (its describing code had already moved),
   `probe()`'s doc comment sitting 48 lines away fused onto
   `setTaperWindows()`'s, `main.ts`'s `_startProtocol()` doc parked over
   unrelated run-state variables. Rule: a comment moves with its code,
   or dies with it, and sits immediately above what it describes.

#### Applying a comment audit or cleanup work order safely

A batch cleanup pass like the one above has a shelf life pinned to the
code state it ran against. Every sprint that lands between the audit
and the ticket applying it can invalidate some of its verdicts — sprint
009's ten cleanup tickets found this happened often enough to be the
rule, not the exception, applying a ~135-item work order against code
that had moved under it for months:

- **Re-anchor by content match, not by the audit's line numbers.** A
  file that grew between the audit and the ticket (new sections, new
  fields) makes recorded line numbers point at the wrong text. Locate
  every item by matching its quoted content against the current file.
- **Treat every item as a possible no-op.** Some flagged comments are
  already fixed by intervening work. Verify the *live* text before
  touching it — don't paste a stale replacement over an already-correct
  comment. (`radio_transport.h`'s `kMaxPayloadBytes` comment and
  `main.ts`'s `goToWorld` JSDoc were both already fixed by earlier
  sprints by the time their cleanup tickets ran.)
- **Load-bearing check before every REWRITE — sampled or not, "already
  verified" or not.** Before landing any replacement text, ask: does it
  preserve every invariant, unit, measured value, and derivation the
  *current* comment carries? A prior verification pass checked the
  replacement against the code as of *its* run, not as of today. The
  near-miss that motivates this rule: `motion_engine.h`'s
  `rotationalSlip_` comment carries a full measurement-to-constant
  derivation (a 0.915 measured pivot ratio → 120.0 mm effective track
  width → 0.952 slip) plus an explicit warning against "correcting"
  the constant back to 0.915. Two independently-drafted proposed
  replacements — the original audit's and a later corrected pass's —
  both would have shortened this comment below that derivation. Applying
  either would have been the exact regression the audit exists to
  prevent. It was left untouched.
- **An audit's own replacement text can be wrong, not just stale.** One
  proposed rewrite for `radio_transport.h`'s header asserted the module
  is TX-only with no RX listener ever registered — contradicted by the
  audit's *own* keep-list for the same file (`tryReceiveLine()`,
  `onDatagram()`). Cross-check a proposed replacement against what the
  same pass says to keep in the same file before trusting either.

None of this is optional ceremony: across sprint 009's ten tickets,
blind application of the work order's literal replacement text would
have introduced a wrong or stale claim into the codebase at least six
separate times — each one caught only by reading the current code
before writing the current comment.

#### Standards that came from getting this wrong once

- **A derivation must be reproducible from the comment alone.** A
  number with a citation ("measured 2026-08-20") is not enough —
  restate the arithmetic. `motion_engine.h`'s `rotationalSlip_` and
  `encoder_glitch_armor.h`'s `kMaxDeltaCounts` both do this: the latter
  derives its threshold from the kernel's own cycle period and measured
  full-duty wheel rate, and explicitly names `rotationalSlip` as the
  cautionary tale it is declining to repeat.
- **Record why a constant is what it is, especially at a platform
  ceiling.** `serial_transport.h`'s `kRingBytes{255}` isn't a round
  number — `setRxBufferSize()` takes a `uint8_t`, so a naive resize to
  480 would silently truncate to 224, below the 240-byte line cap,
  defeating the resize entirely. The comment states the ceiling and the
  silent failure it prevents, not just the chosen value.
- **A comment stating a deliberate asymmetry is load-bearing.**
  `radio_transport.h`'s `sendLine()` drops silently and leaves retry to
  the caller; `serial_transport.h`'s `writeLine()` retries internally.
  Each doc comment says so and points at the other — delete either
  comment and a future reader "unifies" the two transports incorrectly.
- **Document what a test does NOT prove.** `tests/host/` compiles the
  portable core at `-std=c++20`; both real embedded targets compile at
  `-std=c++11`. A green host suite alone never proved the firmware
  builds — `test_cxx11_syntax_gate.py` exists specifically to close that
  gap, and its own header comment states what it does and does not
  cover.
- **Don't hardcode counts, line numbers, or file lists in prose.** They
  rot the moment the next ticket lands. `wire_adapter.cpp`'s `kFields`
  comment once stated a field count as a number; a later sprint added
  fields and the count went silently wrong until a cleanup pass caught
  it. Point at the definition (`kFields`, `kFieldCount`) instead of
  restating a count that can drift out from under the sentence.
- **Provenance belongs in one authoritative place.** Before sprint 009,
  the vendored kernel's upstream repository name was independently
  restated across nine-plus files, and one of those independent copies
  had drifted to an unresolvable name. It's now stated once, in
  `src/DESIGN.md` §2; files that need to say where the kernel comes
  from point at that section by name instead of repeating a path that
  can go stale in eight other places without anyone noticing.

## Coding standards

Consistency with surrounding code beats any external standard. Standards
violations are reported at **Minor** unless they create a real hazard.

- **C++**: Google C++ Style Guide as baseline, adapted to CODAL/PXT
  reality: no exceptions, no RTTI, restrained heap use, MakeCode shim
  conventions (`//%` annotations, PXT calling conventions) win over the
  guide where they conflict.
- **TypeScript**: Google TypeScript Style Guide as baseline, adapted to
  PXT static TypeScript: namespace-based organization, block annotations,
  no ES modules, simulator-body conventions.
- **Python** (`tools/`, `tests/host/`): CLASI's `python` language
  instruction plus PEP 8.

## Severity rubric

| Severity | Definition |
|----------|------------|
| **Critical** | Can damage hardware, bypass e-stop/safety, lose or corrupt state, or wedge the program. |
| **Major** | User-visible misbehavior, a landmine likely to bite in normal development, or a correctness bug with a demonstrated failure scenario. |
| **Minor** | Quality issue: readability, style, comment noise, weak naming. |
| **Suggestion** | Improvement idea; not a defect. |

## Process

1. **Phase 0** (design docs) completes and validates before code review
   starts.
2. Review work fans out across reviewers by dimension and subsystem;
   every candidate finding is **verified against the code before it enters
   the report** — no speculation, no unconfirmed pattern-matches.
3. Each finding records: file:line, dimension, severity, failure scenario
   or rationale, and a suggested remedy.
4. The report lands in `docs/code-review/YYYY-MM-DD/review.md` (with
   per-area annexes if volume warrants).
5. Findings are triaged with the stakeholder and converted into CLASI
   issues for the next round of development.
