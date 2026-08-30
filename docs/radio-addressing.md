# Radio addressing: a board's name IS its address

**Normative.** `docs/radio-address-vectors.json` is the machine-readable
companion; three repos assert against it.

> **Maintainer's note.** Three defects have been found in this spec —
> an ambiguous channel floor, an unpublished encode direction, and a digest
> that never exercised the production path. **None was in the arithmetic**,
> which has not moved since it was first written. Every failure was in what
> the contract *handed an implementer*. If something is wrong here, look at
> the contract before you look at the formula. If this document and that file
disagree, this document wins and the file is regenerated.

A micro:bit's five-letter name is not a label attached to a board — it is a
plain base-5 encoding of `NRF_FICR->DEVICEID[1]`, burned into silicon. So a
board can compute its own radio address at boot, and any tool that knows the
name computes the same pair, with no registry in the loop.

Published algorithm (codebook and a Python implementation):
<https://support.microbit.org/support/solutions/articles/19000067679-how-to-find-the-name-of-your-micro-bit>

**MEASURED 2026-08-29**, `radio-robot-lib/config/robots/devices.json`, 7/7
boards: `device_id mod 3125 == base5(name)` exactly — gopiv 2175407711→1461,
getez 1784514240→1740, zetuv 1468666101→476, tovez 2314287040→2665,
zeguz 4227700425→425, vevov 1198504156→1031, zavaz 4076631795→545.
Independently reproduced by radio-robot-lib (both sessions) and by
microbit-radio-relay from this prose rather than by porting the code.

## The map

```
positions 0, 2, 4   consonant   z v g p t   = 0 1 2 3 4
positions 1, 3      vowel       u o i e a   = 0 1 2 3 4

normalize:  trim ASCII whitespace; map A-Z to a-z
accept:     ^[zvgpt][uoiea][zvgpt][uoiea][zvgpt]$      (reject anything else)

n = 0
for p in 0..4:
    n = n * 5 + index_in_alphabet(name[p])        # n ∈ 0..3124, big-endian

channel = 25 + 2 * (n % 25)                       # 25, 27, 29 … 73
group   = 1 + (n / 25)                            # integer division
if group >= 10: group = group + 1                 # → 1..9, 11..126
```

`name[0]` is the **most significant** base-5 digit; `name[4]` the least.
This matters more than it looks — see *Endianness* below.

Encode (`n` → name), needed by anyone generating the canonical form:

```
for p = 4 down to 0:
    name[p] = alphabet(p)[n % 5]
    n = n / 5
```

Reverse (address → name):

```
reject unless channel is odd and 25 <= channel <= 73
reject unless group ∈ 1..9 or 11..126
g = group;  if g > 10: g = g - 1
n = 25 * (g - 1) + (channel - 25) / 2
for p = 4 down to 0:  digit = n % 5;  n = n / 5;  name[p] = alphabet(p)[digit]
```

Every intermediate is non-negative and at most 3124, so this is identical in
MakeCode static TypeScript (int32), C++ and Python. No shifts, no `%` on
negatives, no BigInt.

Because the split falls on a base-5 digit boundary it is also readable by
hand: **the last two letters give the channel, the first three give the
group.**

## Channel 25 is inclusive

**Channels run 25 to 73 inclusive. 25 is a valid channel and zeguz occupies
it** (n=425, 425 mod 25 = 0). This sentence exists because the constraint was
once stated as "channel > 25" and once as "start at channel 25"; the
stakeholder ruled inclusive on 2026-08-30. A reader who assumes channels begin
above 25 reintroduces an off-by-one at the boundary that costs a three-repo
migration.

## Endianness, and why the obvious test misses it

Base-5 conversion naturally emits the **least** significant digit first, but
the name is big-endian. Get it backwards and there is no error to see: you get
3125 well-formed, regex-passing, distinct names — in a different order.

```
n = 1     correct  zuzuv        reversed  vuzuz
n = 5     correct  zuzoz        reversed  zozuz
digest    correct  a1069d85…    reversed  52ea4a6e…
```

**If your digest equals `52ea4a6e6124cdebbb56639d21db15b48f95d54aeb38ce93f7df9e7f9fbeb8dc`,
your encoder is little-endian.** Reverse the digit order.

The trap is that digit-palindrome names are *identical* under both orderings,
and the vectors an implementer reaches for first are all palindromes:
`zuzuz` (n=0), `tatat` (n=3124), `zotoz`, `pipip` — and among the real boards,
`zavaz`. Checking the minimum and the maximum passes while the encoder is
still wrong.

Use **`zuzuv`** (n=1, reverses to `vuzuz`) or **`zotuz`** (n=225, reverses to
`zutoz`). Both are published for exactly this purpose, and
`$.properties.endianness_probe` in the vectors file names them.

## Properties

Machine-checked across all 3125 names.

**Verify your implementation against the whole space, not the sampled rows.**
The vectors file publishes a digest at the JSON path
`$.properties.full_space_sha256` — nested under `properties`, not at the root.
Canonical form: for `n = 0..3124` in order, one line `<name>,<channel>,<group>\n`,
UTF-8, sha256 of the concatenation. Three lines of code, and it proves byte
identity with this spec across all 3125 names rather than the 13 that happen to
be tabulated:

```python
import json, hashlib
d = json.load(open("docs/radio-address-vectors.json"))
canon = "".join(f"{name(n)},{channel(n)},{group(n)}\n" for n in range(3125))
assert hashlib.sha256(canon.encode()).hexdigest() == d["properties"]["full_space_sha256"]
```

The digest lives only in the vectors file, never duplicated here — a second
copy is a second thing to drift.

### Two digests, and which one is the gate

`full_space_sha256` (**D1**) is generated by iterating `n = 0..3124` and
calling `encode()` and `addr()`. **It never calls `decode()` or `reverse()`.**
A build with both of those broken produces a byte-identical D1 — measured,
2026-08-30. That matters because of *which* functions they are:

| function | role | covered by D1 |
|---|---|---|
| `encode` (n → name) | test-only: generates the canonical form | yes |
| `addr` (n → pair) | production, everywhere | yes |
| **`decode` (name → n)** | **production — this is what `!N <name>` runs** | **no** |
| `reverse` (pair → n) | `!N?` readback, diagnostics | no |

So D1 covers a test-only function plus one production function, and misses
the one the relay executes on every command. A repo can ship a completely
broken `!N` and show a byte-perfect D1. A little-endian decoder is wrong on
**3000 of 3125 names (96%)** and D1 cannot see it.

**`conformance_sha256` (D2) is the conformance gate.** Same shape, same cost,
one line per `n`:

```
<name>,<channel>,<group>,<decode(name)>,<reverse(channel,group)>\n
```

The last two columns are always `n`. That is the point — every line forces
`decode()` and `reverse()` to run and hashes their output. Against the broken
decoder above, D2 comes out `2e4e9013…` and fails loudly.

Assert **both**. D1 is retained not for coverage — it is a strict subset —
but as a bisector: D2 failing while D1 passes localises the fault to
`decode`/`reverse` rather than the forward map.

Found by radio-robot-lib, who demonstrated it by deliberately breaking both
functions and regenerating D1 rather than by arguing from the code.

**A diagnostic constant must name its exact fault.** `conformance_sha256_broken_decode`
publishes `5acfd688…` for **exactly one** fault: `decode()` reads `name[0]` as
the least significant digit while everything else is correct. An earlier
revision published a constant for an *unspecified double* fault, which nobody
could regenerate — a diagnostic that cannot be reproduced is dead precisely
where it is meant to fire.

### Dump protocol

An implementation proves conformance by emitting the canonical form on stdout;
a checker hashes it. That is how C++ and static TypeScript conform without
sha256 in either.

| version | columns | digest |
|---|---|---|
| v1 | `name,channel,group` | D1 — does not exercise the inverse |
| **v2** | `name,channel,group,decode(name),reverse(channel,group)` | **D2 — preferred** |

Count columns to tell them apart. v1 remains valid; v2 is preferred because it
puts the inverse into the hashed artifact rather than trusting each dumper's
own internal self-check.

### A non-CVCVC name has no address

A string outside `^[zvgpt][uoiea][zvgpt][uoiea][zvgpt]$` after normalize
**must raise**. Never fall back to a hash, a default, or a truncation.
`base5` is undefined outside the codebook, and inventing an address for a
name that has none is precisely the silent-failure class this scheme exists
to remove. This binds `!N` and every host tool: `!N robot1` is an error, not
a link.

**But malformed is not the same as unknown, and conflating them fails
silently in the opposite direction.**

| input | verdict |
|---|---|
| `robot1`, `gauti`, `aeiou` — **malformed** | **raise.** No address exists. |
| `pipip` — **well-formed, no such board** | **accept.** 51/90 is a legal, quiet pair. |

A relay that rejects the second "to be safe" breaks the tune-to-whatever-I-name
model, which is the whole point of `!N`. One that accepts the first produces a
working-looking link on an arbitrary channel. Nothing in the address layer
knows which boards exist, and it must not pretend to — that is the silicon
gate's job, at deploy time, with `read_board_name()`.

*(Distinction contributed by radio-robot-lib.)*

- 3125 names → **3125 distinct (channel, group) pairs**. Never a collision on
  both axes.
- Exactly **125 names per channel**, **25 names per group**.
- Channels 25–73 = 2425–2473 MHz. Above Wi-Fi channel 1 (2401–2423 MHz);
  2 MHz spacing is what BLE uses at 1 Mbit. Inside `setFrequencyBand`'s 0–83.
- Groups 1–126, inside `setGroup`'s 0–255.
- **Never emits channel 3, 4 or 7, nor group 0 or 10.**

### Why those five values are reserved

| reserved | belongs to |
|---|---|
| channel 3, 4 + group 10 | the legacy hand-allocated fleet convention |
| channel 7 + group 0 | MakeCode's unconfigured default — where every board whose program forgot to set the radio up ends up |
| group 10 | microbit-radio-relay's `!C` button space, which spans channels 0–35 and *forces* group 10 |

Excluding the first two lets un-migrated and migrated boards coexist: there is
no flag day. Excluding group 10 keeps a hand-dialed `!C` from landing on a
derived address — without the skip, six names (`zotuz`, `zotuv`, `zotug`,
`zotup`, `zotut`, `zotoz`) collide with it exactly.

**Consequence: `!C` cannot address a migrated board at all.** Derived channels
are 25–73 with group ≠ 10, so only `!CG <ch> <grp>` or the relay's `!N <name>`
can reach one. That is intended. `!C` remains the hand-dial space for
un-migrated and ad-hoc boards, which is what makes `?` on the relay display
mean unambiguously "named/custom".

## A relay has no address of its own

**It adopts the robot's.** getez derives 55/71, but when it serves tovez it
tunes to 55/108 and its own pair never goes on air. Relay rows in the table
below are informational.

Corollary: `channel` is the CODAL frequency band and `group` is only an
address filter, so two *robots* sharing a channel contend for air even though
neither parses the other's traffic. Across the configured fleet there is
exactly one such pair — **togov and vevov both derive channel 37** (2437 MHz).
Tolerable at this duty cycle, but real, and it grows as 1 − (24/25)^(n−1).

## The fleet

| name | role | device_id | n | channel | group | evidence |
|---|---|---|---|---|---|---|
| zeguz | robot | 4227700425 | 425 | 25 | 19 | silicon |
| zetuv | robot | 1468666101 | 476 | 27 | 21 | silicon |
| vevov | robot | 1198504156 | 1031 | 37 | 43 | silicon |
| gopiv | bench rig | 2175407711 | 1461 | 47 | 60 | silicon |
| getez | relay | 1784514240 | 1740 | 55 | 71 | silicon |
| zavaz | relay | 4076631795 | 545 | 65 | 23 | silicon |
| tovez | robot | 2314287040 | 2665 | 55 | 108 | silicon |
| togov | robot | — | 2681 | 37 | 109 | **label only** |

**togov has never been probed.** It appears in no device registry in either
repo, yet "togov" is a well-formed name that derives cleanly. Nothing
establishes that the board labelled togov is togov. Confirm on first
connection; it is also the one half of the only channel share.

## Deriving from a name is not the same as deriving from silicon

A board reading `microbit_friendly_name()` cannot be stale. **A host tool
reading a name out of a config file can be**, and substituting one for the
other would move the staleness rather than remove it — which is the whole
point of the change.

So any host tool that resolves a board by name must verify against silicon:

```python
from mbdeploy.devices import read_board_name   # src/mbdeploy/devices.py:275
silicon = read_board_name(uid)                 # FICR.DEVICEID[1] via pyOCD,
                                               # connect_mode="attach": no halt,
                                               # no reset, no serial port; works
                                               # on an unflashed or bricked board
```

Mismatch is a hard failure naming both. `read_board_name()` returns `None`
when pyOCD is unavailable or the probe is busy — with a board attached that is
a failure; with no board attached there is nothing to read, so warn.

**Never use `connection.serial_last_6` as an identity source.** Verified
2026-08-30, it means three different things across six files:

| robot | value | what it actually is |
|---|---|---|
| tovez, vevov, zetuv | f137c0, 6fb8dc, 8a10f5 | last 6 **hex** of `device_id` |
| gopiv | 407711 | last 6 **decimal** (hex would be `aa165f`) |
| zeguz | 0cfd6c | substring of the **DAPLink USB UID** — a different chip |
| togov | ade9b4 | unknown; never probed |

zeguz is the trap: the interface chip's USB serial carries no information
about the nRF target's identity, while looking exactly like the fields that
do.

## Why derivation beats allocation

Hand-allocation has already failed. In `radio-robot-lib/config/robots/`,
**gopiv and zeguz both sit on `radio_channel: 5`**, and zetuv sits on 7 —
MakeCode's unconfigured default. `zetuv.json`'s own provenance note records
the author reasoning "3/4/5/6 were already taken and a collision makes both
robots unusable", and the collision happened anyway two robots later, because
nothing enforced it. Injectivity here is a property of the map, not of
whoever edited the file last.

## Ownership

| repo | owns |
|---|---|
| pxt-nezha-diffdrive | this document, the vectors file, robot firmware self-addressing, `make_deploy.py`, `robotlink.py`, `wire_acceptance.py` |
| microbit-radio-relay | `!N <name>` and `!N?` in `RadioRelay.cpp`, `mbrelay.naming`, the server-side `!C`/`!CG`/`!RC`/`!N` watcher |
| radio-robot-lib | deleting `connection.radio_channel`, its schema entry, and the rogo fixture |

The other two repos mirror `docs/radio-address-vectors.json` into their tests
and assert against the file, never against prose or chat.

`!N` is a convenience, not a prerequisite: a self-addressing board is
reachable today via plain `!CG`, so the three repos can land in any order.
