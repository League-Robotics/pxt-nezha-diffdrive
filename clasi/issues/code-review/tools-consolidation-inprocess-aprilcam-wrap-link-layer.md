---
status: pending
sprint: '033'
---

# Tools consolidation: in-process aprilcam, one wrap(), one link layer, one repositioner, delete dead tools, DESIGN.md truth pass

Priority: **Medium** · Source: [code review 2026-09-02](../../../docs/code-review/2026-09-02/review.md)

Findings: TL-07, TL-09, TL-12, TL-13, TL-14, TL-15, TL-16, TL-17, TL-18
([tools-and-tests](../../../docs/code-review/2026-09-02/raw/tools-and-tests.md)). Triage #22.

## Description

08-26 Q-06/Q-09 are still open and their premise is gone: `aprilcam[daemon]`
is a dependency of this venv and imports under `uv run`, so `camproc.py`'s
subprocess-into-a-second-venv and the second `Cam` class have no remaining
reason. Four `wrap()` implementations (two with different boundary
semantics), the link layer written four times with three relay addresses
and two sequence-id implementations, two repositioning loops (one
documenting an ordering bug the other still has), `truth_check.py` dead on
arrival (v1 JSON keys, hard-coded port), five tools kept "for reference"
but executable on the stale relay address, `tools/DESIGN.md` omitting 11
of 30 tools, `tour_chart --meta` reading a field nothing writes, and test
names asserting "vevov is channel 4" beside a table saying 37/43.

## Remedy

Import aprilcam in-process and delete `camlink`/`camproc`'s subprocess
shape; one `wrap()` in `field.py`; one `Link`; one repositioner; delete
`truth_check.py` and the five reference-only tools (git keeps them);
rewrite `tools/DESIGN.md` as an inventory.
