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
