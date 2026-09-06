---
source_file: rogo-DESIGN.md
source_hash: ee3a5e38e498841249bc691a104d3c3202d0699c073fec28990e80d1fcbcaaea
---
# Diff: rogo-DESIGN.md

Comparison of the sprint overlay copy of `rogo-DESIGN.md` against its pristine (seed-commit) canonical version.

```diff
--- rogo-DESIGN.md (pristine)
+++ rogo-DESIGN.md (current)
@@ -1,9 +1,11 @@
 # tools/rogo — `nc` for a robot over its WiFi TCP server
 
-**Owner:** Eric Busboom · **Last reviewed:** 2026-09-04 · **Status:**
-stable (merged to master 2026-09-03 with the WiFi transport; this
-document added at sprint 029's close, which found the subsystem
-without one)
+**Owner:** Eric Busboom · **Last reviewed:** 2026-09-06 · **Status:**
+stable. Re-checked against `tools/link.py`, which now owns the
+sequenced-wire protocol for the rest of `tools/`: rogo still does not
+use it and still must not — see "The duplication is deliberate" below,
+the one section of this document a consolidation pass needs to read
+before re-filing `rogo.py` as an accidental copy.
 
 A single-file, standard-library-only CLI (`rogo.py`, packaged by
 `pyproject.toml` so `pipx install` works from this checkout or straight
@@ -39,6 +41,33 @@
 - Not dependent on this repo at run time: `pipx install` copies only
   `rogo.py`, so it must never import from `tools/`.
 
+## The duplication is deliberate
+
+`tools/link.py` (sprint 034 ticket 006) is the one owner of the
+sequenced-wire protocol for everything else in `tools/` — `Sequencer`,
+`LineBuffer`, `relay_setup_lines()`. **rogo does not use it and must
+not.** Its socket reading and line splitting stay its own.
+
+That is a decision, not an oversight (sprint 034 Design Rationale 3).
+The alternatives were considered and rejected:
+
+- *rogo imports `tools/link.py`* — breaks the whole premise outright.
+  `pipx install tools/rogo` (or straight from git) copies `rogo.py` and
+  nothing else; an import of a sibling directory that is not in the
+  package makes the installed command fail on first run.
+- *package `tools/link.py` so rogo can depend on it* — a published
+  package to version, release and keep compatible, for one consumer,
+  to save a few dozen lines.
+
+So the copy stands, and this note stands with it: a future
+consolidation pass that re-files rogo's line handling as an
+unintentional duplicate should stop here. What keeps the two honest is
+that rogo shares almost none of the surface — it deliberately does not
+sequence at all (`rogo` sends lines verbatim; a sequenced verb must be
+typed with its `#<id>`), so there is no id-allocation rule to drift.
+`tests/tools/test_link.py::test_rogo_imports_nothing_from_tools` pins
+the constraint from the other side.
+
 ## Versioning
 
 `pyproject.toml`'s `version` follows the firmware's `0.YYYYMMDD.n`
@@ -48,8 +77,14 @@
 
 ## Tests
 
-None on the host: the module is stdlib networking against a live
-firmware announcer. Its acceptance is `tools/wire_acceptance.py
---wifi-tcp <name>` (the carrier proof) and a manual `rogo <name> PING`.
-A loopback test of the discovery parser would be the first thing to add
-if `rogo.py` grows.
+`tests/tools/test_rogo.py` pins the parts that can be pinned without a
+robot: the `dns-sd` parsers, against output captured verbatim on
+2026-09-02 (macOS, tovez announcing from 192.168.1.213); the discovery
+ORDER, with `_dns_sd`/`resolve_host` monkeypatched — including the
+announced SRV port beating the 7654 default, which is the whole reason
+discovery reads the port and not just the address; and the pipe itself
+over a `socket.socketpair()`. No network, no subprocess.
+
+What no host test can reach is the live announcer. That acceptance is
+`tools/wire_acceptance.py --wifi-tcp <name>` (the carrier proof) plus a
+manual `rogo <name> PING`.
```
