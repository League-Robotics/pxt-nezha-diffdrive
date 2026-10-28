# The Nezha brick's opcodes, and what the motor does with them

Written 2026-10-27 (sprint 042 ticket 001). In-tree reference for the
simulator and tests. The measurements were taken in the sibling repo
`nezha-esp32` and the four CSVs behind the tables are copied unchanged
into `docs/code-review/2026-10-27/data/` (`cmp` clean against the
originals). Hardware for every measured number: the micro:bit rig, one
smart motor on port M1, 83 mm wheel, unloaded, 2026-10-27, unless a row
says otherwise. Nothing in this document is a result from sprint 042
(host-only, no hardware).

Source readings, not measurements, are labelled "source reading". The
sources are `nezha-esp32/docs/motor-protocol.md` (sections 2, 3, 7, 8),
`nezha-esp32/docs/microbit-comparison.md` (sections 6, 7),
`nezha-esp32/docs/fifty-cm.md` and `pxt-nezha-diffdrive/test/test.ts`
(`brickCmd`, `RUN brick`, `RUN brickx`). The sniff of the brick's UART
frames behind the opcode map is `nezha-esp32/docs/data/sniff_walk1.log`
and `sniff_detail1.log` (micro:bit brick to an ESP32 acting as a fake
motor on M3, 2026-10-27); those logs are not copied here, so the opcode
map below is cited to them but is not reproducible from this tree.

Note (sprint 043): the `brickCmd`, `RUN brick`, `RUN brickx`, `brickraw`,
`brickread` and `brickstop` handlers cited here as the measurement method were
removed from `test/test.ts` in sprint 043. The text above is history. The
surviving raw-brick probe path is in the sibling repo `nezha-esp32/tools`
(`mb50.py`, `mb_probe.py`, `sniff.py`).

## 1. The units, stated once

**The `0x77` value is degrees per second.** The vendor's MakeCode block
takes a percent and multiplies it by 9 before writing `0x77`
(source reading, and what `RUN brick` in `test/test.ts` does: `speed =
pct * 9`), so "100 %" becomes 900. The brick copies the 16-bit value
verbatim into the speed field of the motor's `03 70` (and `03 67`)
frame, and that field is degrees per second: UART probe, M1 unloaded,
2026-10-27, `nezha-esp32/docs/data/uart_probe_probe1.csv` (speed 360 ran
at 361 deg/s; not copied into this tree). Through the brick the same
fact shows in `docs/code-review/2026-10-27/data/mb_probe_fine1.csv`:
`0x77` 300 ran 302.7 deg/s.

Both statements are true at once. The value is deg/s; the vendor's
"percent" is that value divided by 9. So "100 %" is 900 deg/s, below the
motor's free speed, and a `0x77` value need not be a multiple of 9
(905 ran 909.5 deg/s in `mb_probe_fine1.csv`). This tree stores and
documents deg/s; percent x 9 is only how the vendor block fills the
field.

Other units on the same bus:

- `0x60` run takes an **integer percent** (the motor's `03 6E` takes
  percent x 10, so 0x60 reaches only 1 % steps). One percent is about
  11.5 deg/s: `nezha-esp32/docs/motor-characterization.md` (ESP32 rig
  speed-step runs, 2026-10-27; the run file is not copied here).
- `0x70` mode 2 takes **integer degrees**; the brick sends them to the
  motor times 10 (tenths of a degree).
- Timed run (`0x70` mode 3) time field is `(10n - 3)` units of 100 ms.
- The `0x46` position read returns tenths of a degree, little-endian.

Fine-velocity saturation and the `0x60` slope come from different runs:
the roughly 980 deg/s ceiling is from
`docs/code-review/2026-10-27/data/mb_probe_fine1.csv` (micro:bit rig,
through the brick, 2026-10-27: 1000, 1100, 1200 gave 977.8, 981.4, 990.8
deg/s); the 11.5 deg/s per percent slope is from
`nezha-esp32/docs/motor-characterization.md` (ESP32 rig, UART
set-speed, 2026-10-27), not from that CSV. Do not mix them.

## 2. Opcode map

Brick I2C frame, address 0x10, 8 bytes:
`FF F9 <port> <arg> <op> <hi> <mode> <lo>` (`brickCmd` in
`test/test.ts`). Port byte 1..4; 0 means all ports. UART frames are the
motor-side bytes after `F9 FF 01 <len>` (framing in `motor-protocol.md`
section 2). Source for the whole table: sniff logs named in the preface,
micro:bit brick, 2026-10-27.

| Opcode | UART frame(s) | Notes |
| --- | --- | --- |
| `0x60` run | `03 5A 02` if the mode changed, then `03 6E <int16 pct x 10>` | integer percent; direction byte 2 negates; not deduplicated |
| `0x77` speed store | none on the wire | per-port, 16-bit, deg/s; the next `03 67`/`03 70` uses it as its speed field; a `0x77` alone does not retarget a running move (`mb_probe_fine1.csv` supersede rows, 302.9 deg/s held) |
| `0x70` mode 0 or 1, n | `03 5A 01` if needed, then `03 67 11 00 <n x 3600 int32> <0x77 value int32>` | turns |
| `0x70` mode 2, n | `03 5A 01` if needed, then `03 67 11 00 <n x 10 int32> <0x77 value int32>` | integer degrees, times 10 counts; direction byte 2 negates |
| `0x70` mode 3, n | `03 5A 02` if needed, then `03 70 14 00 <int16 time> <int16 0x77 value>` | time `(10n - 3) x 100 ms` (1 s sends 7) |
| `0x5F` stop | `03 5A 01` if needed, then `03 67 11 00 00000000 84030000` | a zero relative move at 900 deg/s: hard stop, holds within 5 degrees |
| `0x5D` absolute | `02 46` read, then `03 67 11 00 <delta> 84030000` or nothing | partly decoded; the target maths is UNVERIFIED (a clean matrix with the fake motor at a known position would settle it); this design uses relative moves only |
| `0x46` / `0x47` read | `02 46` / `02 47` | the 4-byte I2C reply is the motor's raw value |
| `FE: 03 64 00` ... `03 64 02` | broadcast bracket around every mode change | `64 00` is a stop; what `64 02` does is UNVERIFIED |
| `45 46` ping | about every 400 ms, two frames back to back | the brick forwards commands whether or not it is answered |
| checksum | constant `CC` on every frame but `02 46` and `03 1D 01` | the motor accepts `CC` as a wildcard and rejects a wrong checksum (ack status 20): `uart_probe_probe1.csv` (not copied), M1, 2026-10-27 |

Motor-side details (same probe, same date, not copied): `03 70` flag byte
bit 0 is direction (`14` forward, `15` reverse); a second `03 70`
supersedes a running one at once.

## 3. Behaviour rules a simulator must reproduce

Micro:bit rig, M1, 2026-10-27, through the brick (`RUN brickx`);
source `nezha-esp32/docs/microbit-comparison.md` section 6. The raw
run log is not copied; the travel numbers below are from that section.

1. `0x60` with speed 0 during a move ramps down at v^2/2a (46 degrees
   more travel from 300 ms into a 360 degree move at 50 %) and drops the
   target.
2. A nonzero `0x60` takes the motor over: it runs at that percent until
   stopped, and the old target is gone (run 20 % at 300 ms).
3. A second `0x70` supersedes the first from the current position (a
   +90 degree move issued at 300 ms ended 95 degrees past the position at
   the command) and the old target is dropped.
4. `0x5F` stops within 5 degrees (5 degrees more travel, at rest 144 ms
   later) and drops the target. How far a hard stop adds from 150 deg/s
   is UNVERIFIED: the `supersede` rows of `mb_probe_fine1.csv` have an
   integer-0 column that was never filled, so it is not a measurement.
   The stop-table fit (section 5a) predicts about 1.5 degrees.
5. `0x77` is per-port and persists across moves; the most recent write to
   that port governs, whichever port byte set it.
6. Negative degrees (direction byte 2) mirror all of the above.

Simulator constants. The simulator's accel/decel of 4200 deg/s^2, the
2200 deg/s^2 decel for a `0x60 0` during a move, the 20.6 ms hard-stop
ramp and the 980 deg/s ceiling are fits to the rows cited above
(`mb_probe_stops1.csv`, `mb_probe_fine1.csv`) and are UNVERIFIED beyond
them.

Steady hold. With `speed_path 1` the port re-issues a bare `0x70` mode 3
every 400 ms during a steady hold, so the 0.7 s timed run never lapses.

## 4. The three frames sprint 042 emits

Exact I2C bytes. Layout from `test/test.ts` `brickCmd` and `RUN brickx`;
the two quoted issue texts give `FF F9 <port> <dir> 70 <hi> 02 <lo>` and
`FF F9 <port> 00 77 <hi> 00 <lo>`, which match. `hi`/`lo` are the
big-endian halves of the unsigned 16-bit value.

| Frame | Bytes | Value |
| --- | --- | --- |
| `0x77` per-port speed | `FF F9 <port> 00 77 <hi> 00 <lo>` | deg/s, port 1..4 (0 = all) |
| `0x70` dir mode 2 | `FF F9 <port> <dir> 70 <hi> 02 <lo>` | integer degrees (magnitude); dir 1 forward, 2 reverse |
| `0x5F` stop | `FF F9 <port> 00 5F 00 F5 00` | none; the `F5` mode byte is what `RUN brickx` sends |

A move is `0x77`, then `0x70`; a speed change on a running move costs the
`0x77` and a fresh `0x70`. The `0x5F` mode byte `F5` and the `0x77` mode
byte `00` are as sent by `test/test.ts`; whether the brick ignores both
is a source reading, not a separate measurement.

## 5. Measured tables

### 5a. Stop travel, ramp (`0x60 0`) against hard (`0x5F`)

Micro:bit rig, M1, 83 mm wheel, unloaded, 2026-10-27,
`docs/code-review/2026-10-27/data/mb_probe_stops1.csv`. Run at the
percent for 800 ms, then stop. Travel after the stop command, mean of
two trials, one each way (columns `after_stop_mm`, `rest_ms`).

| Speed | `0x60 0` ramp | `0x5F` hold | rest ms, ramp / hold |
| --- | --- | --- | --- |
| 8 % | 0.6 mm | 0.6 mm | 48 / 24 |
| 15 % | 2.8 mm | 1.4 mm | 48 / 60 |
| 30 % | 11.1 mm | 2.2 mm | 108 / 96 |
| 60 % | 41.7 mm | 4.9 mm | 204 / 132 |
| 100 % | 101.9 mm | 8.6 mm | 314 / 168 |

(The 8 % row's second trial reads 0.0 for both; the means are 0.6.)

### 5b. Fine velocity through the brick

Micro:bit rig, M1, unloaded, 2026-10-27,
`docs/code-review/2026-10-27/data/mb_probe_fine1.csv` (`finevel` rows;
two `0x46` reads 1.2 s apart, `0x77` then `0x70` mode 3).

| `0x77` value (deg/s) | measured deg/s |
| --- | --- |
| 60 | 60.5 |
| 100 / 105 | 100.5 / 105.7 |
| 300 | 302.7 |
| 450 | 454.6 |
| 900 / 905 | 907.4 / 909.5 |
| 1000 / 1100 / 1200 | 977.8 / 981.4 / 990.8 (saturated near 980) |

The `supersede` rows of the same file: 300 then re-issued at 150 gave
302.9 then 151.4 deg/s; a reversed direction byte gave -152.3 deg/s.
Command resolution is 1 deg/s (0.72 mm/s on this wheel), against
11.5 deg/s per `0x60` percent (section 1 names that file).

### 5c. Kernel with `pid_ki 0` (feed-forward only)

Micro:bit rig, M1, 83 mm wheel, 50 cm straights, four trials per speed,
alternating direction, 2026-10-27, with the ESP32 silent on the shared
M3 cable. Files:
`docs/code-review/2026-10-27/data/mb50_ffcmp2_stock.csv` (stock gains
`pid_kp 0`, `pid_ki 6`) and
`docs/code-review/2026-10-27/data/mb50_ffcmp2_ffonly.csv` (`pid_ki 0`,
`accel_kaff 0`). Error is settled minus commanded, mm, column `err_mm`;
mean / sd / worst, recomputed from the CSVs for this document.

| cruise | stock | feed-forward only |
| --- | --- | --- |
| 248 mm/s | +2.94 / 0.53 / 3.40 | +1.96 / 0.33 / 2.45 |
| 504 mm/s | +2.20 / 0.60 / 2.74 | +3.96 / 0.91 / 4.99 |
| 792 mm/s | +2.07 / 0.76 / 3.03 | +9.75 / 9.77 / 23.53 |

At 792 mm/s the feed-forward saturates (10 900 counts/s demanded against
a `full_duty_velocity` of 10 795, source reading of
`microbit-comparison.md` section 7c) and one trial in four ran about
24 mm long (`err_mm` 23.53 in `mb50_ffcmp2_ffonly.csv`).

### 5d. 50 cm table

Both rigs, 83 mm wheel (260.75 mm per turn, 50 cm = 690.3 degrees of
shaft), 2026-10-27, source `nezha-esp32/docs/fifty-cm.md` (tables copied
as written; the per-trial files for the ESP32 rig and for the brick
move are not in this tree, so those rows are cited to the document only).
Only the stock micro:bit row of section 2 is backed by a copied CSV,
`mb50_ffcmp2_stock.csv` (its means differ from the stock row of `fifty-cm.md`
section 2, +2.64/+2.51/+2.31 mm; the copied file gives the section 5c
means, and which run the document's row came from is UNVERIFIED).

Mean / sd / worst error, mm:

| Config | 30 % | 60 % | 100 % | Source |
| --- | --- | --- | --- | --- |
| ESP32 trapezoid + PID settle | 0.00 / 0.13 / 0.14 | 0.00 / 0.17 / 0.14 | 0.00 / 0.21 / 0.22 | `fifty-cm.md` section 1, ESP32 rig |
| ESP32 motor's built-in move | 0.00 / 0.25 / 0.22 | -0.20 / 0.04 / 0.22 | -0.09 / 0.16 / 0.22 | `fifty-cm.md` section 1, ESP32 rig |
| micro:bit kernel, stock | +2.64 / 0.35 / 2.96 | +2.51 / 0.59 / 3.40 | +2.31 / 0.61 / 3.03 | `fifty-cm.md` section 2, run file not copied |
| micro:bit brick `0x70` move | -0.22 / 0.00 / 0.22 | -0.22 / 0.18 / 0.44 | +0.10 / 0.08 / 0.14 | `fifty-cm.md` section 3, run file not copied |

The brick move is sent as integer degrees (690, not 690.3), so a 0.22 mm
short bias is expected from the rounding.

## 6. Never send

**`0x1D` (UART `03 1D 01`, the motor reset) is never sent**, by
firmware, tests or the simulator's emitted-command table. On the motor
tested in the ESP32 repo (firmware string `R003_GJYB,Oct  8 2025`,
2026-10-27, `nezha-esp32/docs/motor-protocol.md` section 3) it did not
reset: the position jumped from 2408.9 to 67.5 degrees, and every motion
command (`03 6E`, `03 67`) was then refused with ack status 40 until the
cable was unplugged. Power-cycling the drive rail and rewriting modes did
not clear it. The brick forwards `0x1D` as `03 1D 01` with a correct
checksum and no mode select; this tree must not reproduce that. The
simulator may recognise the byte only to fail a test that emits it.
