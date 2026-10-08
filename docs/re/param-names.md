# Param names (P00–P9D)

Static analysis. Values are from `backups/df_20261007_221649.bin`
(active block 0xF1800, 158 params).

## How the param area is laid out

- The 158 params are one packed 632-byte RAM struct at 0xFF510–0xFF787. P_n = bytes 0xFF510+4n..+3.
  Firmware fields are bytes and u16s at arbitrary offsets, so one param often holds two unrelated
  u16 fields, and a few fields straddle a param boundary (strings, logs). `lo` = bytes +0..+1 and
  `hi` = bytes +2..+3 (LE u16). Floats are IEEE-754 LE u32 aligned to a param.
- Persist calls: `callt [0xb0]` marks one u16 dirty (arg = RAM address); `callt [0xa2]` marks a range
  (ax = address, bc = length). Those arguments were the main xref source.
- **The SBS command table is at 0x2008**: 6-byte entries `[cmd][flags][read fn][write fn]`, terminated at
  0x22B4 (flags: b7 block, b6 W, b5 R, b4..0 len-1; [../protocol.md](../protocol.md)). It gives the direct SBS↔param map.
- **Vendor block source table** at 0x1F3A + 4·cmd: `[src u16][len u16]`, read by 0x75B8. The special
  cases are E0 (0x232A const), E1 (built by 0x7C2A) and EB (code 0xD518):

| SBS | RAM src | len | params |
|---|---|---|---|
| E2 | FF60C | 32 | P3F–P46 (lifetime signature + 24 code counters) |
| E3 | FF62C | 32 | P47–P4E (reserved, zero) |
| E4 | FF64C | 10 | P4F–P51 lo (event counters) |
| E5 | FF656 | 20 | P51 hi–P56 lo (lifetime min/max) |
| E6 | FF66A | 18 | P56 hi–P5A (timestamps of min/max) |
| E7 | FF67C | 10 | P5B–P5D lo (hour/throughput counters) |
| E8+E9 | FF686 | 30+24 | P5D hi–P6A (5×5 V×T histogram + hi/lo-cell hours) |
| EA | FF6BC | 32 | P6B–P72 (6 counters, zero) |
| EB | **code 0xD518** | 20 | histogram bin edges. Constants, not params, and not protection thresholds. The live read matches 0xD518 byte for byte (verified on board, `_board_log.md`) |
| EC | FF6DC | 4 | P73 (sub-hour tick bytes) |
| ED | FF6E0 | 28 | P74–P7A (histogram sub-counters, hi/lo-cell sub-counters) |
| EE | FF6FC | 16 | P7B–P7E (sub-counters for EA, zero) |
| EF | FF70C | 2 | P7F lo (snapshot / fault-log ring indices) |
| F0/F1/F2 | FF70E/FF726/FF73E | 24 each | P7F hi–P91 lo (3 fault snapshots) |
| F3 | FF756 | 32 | P91 hi–P99 lo (fault log, 8×4 B) |
| F4 | FF776 | 2 | P99 hi (event-log ring index) |
| F5 | FF778 | 16 | P9A–P9D (event log, 4×4 B) |
| FB | FF5F8 | 16 | P3A–P3D (usage-time counters, via 0x4C7B) |
| AA | FF818 (RAM) | 30 | working copy of P1B–P29 (packed) |
| AB | FF854 (RAM) | 16 | working copy of P2A–P31 (packed) |

- Factory-default images in code flash: **0xDA3A** (194 B → FF54A–FF60B = P0E hi..P3E, used by
  SBS 0x87 mode 2) and **0xDA5C** (160 B → P17–P3E, mode 3). The defaults are all zero except the
  model string (P32 hi–P35) and P10 lo = 0x4C50 ("PL"). Gauge defaults come from 0xD904 / 0xD940 /
  0xD960 / 0xD96E instead (0x7E01).

## Findings by region

**Calibration block P00–P0E lo (0xFF510–0xFF549), verified-static.** Written by the SBS 0x58 write
handler 0x446D (unlock-gated) with sub-modes 0..6. Mode 6 recomputes the checksum and persists the
58-byte block. FF510 = low byte of the byte sum of FF512..FF549 (0xAD91, checked at boot 0xADA3 →
code 0xA4). FF511 = 0xA5 signature.
- Cell-voltage 2-point cal (0x4F9A = raw ADC FA92+2i, 0x504A = FFB36−FFB28 for cell 6): point 1 at
  2200 mV (const 0xD446) → FF512..FF51B cells 1–5 ≈ 8885 counts, FF51C cell 6 = 11739. Point 2 at
  4200 mV (0xD448) → FF526..FF52F ≈ 16967, FF530 cell 6 = 22438. The ratios match 4200/2200.
- Pack-terminal (P+/charger-side) voltage (SBS 0x47 = FFE6E; on board: 22253 mV with FETs on)
  2-point cal: FF53A = 11051 @ 13200 mV (0xD44A), FF53C = 21319 @
  25200 mV (0xD44C). Used at 0x9F0F.
- Current: FF53E = ADC zero offset (32776 ≈ 0x8000 + 8). FF540 = ADC at the cal current (34212). Raw
  = FFB24 (0x5265); offset is subtracted at 0x4FB6.
- Temperature: FF546 = reference temp at cal (2993 = 299.3 K = 26.2 °C), FF548 = thermistor ADC at
  that point (7152). Used at 0x505A.
- FF520–23 (P04), FF524 (P05 lo), FF534–37 (P09), FF538 (P0A lo), FF542–45 = 0, inside the
  checksum range but never written. Spare.

**Identity, verified-static + register_dump.**
- P0E hi (FF54A) = SBS 0x94 R/W = 0x5227. It decodes as an SBS date, 2021-01-07, 18 days before the
  mfg date, so probably the cell/lot date (inferred). P0F lo (FF54C) = SBS 0x95 R/W = 15143 (lot
  number? inferred). P0F hi (FF54E) = 0. All three also go into SBS E1 (0x7C2A).
- P10 hi (FF552) = **ManufactureDate** (SBS 0x1B R/W) = 0x5239 = 2021-01-25. While it is non-zero,
  SBS 0x80 mode 5 is blocked (0x47E3) and, when a PF bit is set, 0x877C sets FFE34.0, which drives
  the fuse pin P1.1 ([afe-map.md](afe-map.md) §3). So it doubles as the fuse arm. Set to 0 on
  2026-10-08 for cell assembly (P10 = 0x00004C50); restore 0x52394C50 once PF reads clear (README). P10 lo = 0x4C50 "PL", default image only, no code xref.
- P11 lo (FF554) = **SerialNumber** (SBS 0x1C R/W) = 415.
- P32 hi–P35 (FF5DA–FF5E7) = **DeviceName / model string** for SBS 0x2F: length byte 12 at FF5DA, then
  "SEC_VS9000NL". R/W via 0xAF9B/0xAFB3.

**Faults.** P17 lo = PF mask bits 48–63 (known). P17 hi (FF56E) = persisted **protection-disable
mask** FFB50 (SBS 0xB2). It is persisted at 0x8417 when a PF is set or FFB50 bit 6 is set, ORed back
into FFB50 at boot (0x83CA → 0xB216), and cleared with P17 lo by 0xAA55. Currently 0. Bits
([protection.md](protection.md), verified-static):
- 0x0002: voltage checks off (0x0A/0x14/0xC8/0xCA/0xCC). Latched by 0xB23F/0xB28B on an implausible
  reading, code 0xB4/bit 40.
- 0x0004: current checks off (0x28/0x29/0x32/0x50/0xDC, charge timer).
- 0x0008: temperature checks off (0x3C/0x3D/0x46/0x47).
- 0x0040: persist trigger.
- 0x0080: alternate path for 0x16.
- **Rebuild note:** P17 hi must stay 0. A non-zero value here silently disables protection classes
  and survives reboots.

**Gauge, P18–P39 (0x7E01 init, 0x7FD1 update; details in [gauge-scaling.md](gauge-scaling.md)).**
Addresses verified-static; table meanings partly inferred.
- P32 lo (FF5D8) = 0xBEEF "gauge state valid" marker. If it is missing, 0x7E01 re-seeds P18–P31 and
  the cycle count from ROM defaults (0x7E03). 0x7F16 zeroes it.
- P18 float = 2924 (RAM FF8AE) = **Qmax**, learned chemical capacity, mAh. Seeded at 3195.0 (0xD98C ×
  parallel count 0xD982 = 1). SBS 0xA3 = int(P18) (0x824F); SOC denominator at 0x8200. Verified-static.
- P19 float = 2390.8 = **FullChargeCapacity, mAh** (FF8EE; SBS 0x10 = 2390). Seeded from 2850.0
  @0xD960, learned by 0x3610 only over a ≥ 40 % SOC span, clamped to ≤ 2850.
- P1A float = 98.67 (FF8D8) = SOC % at the 4160 mV charge-termination OCV (0xD96E), interpolated
  through the 32-point OCV table @0xD6B0/0xD630 by 0xA32F. Seed ≈ 99.2 %. Mechanism verified-static,
  name inferred.
- P1B–P29 = 15 floats (FF818 working copy, SBS 0xAA) = learned cell resistance vs SOC, Ω, on the
  15-point SOC grid @0xD7B0. Defaults @0xD904 run 0.399 → 0.018. Only P24, P25, P27, P28 have moved
  (+2–4 %). Inferred.
- P2A–P31 = 8 floats (FF854, SBS 0xAB) = second resistance table, Ω, on the 8-point SOC grid @0xD7EC.
  Defaults @0xD940 are 0.044..0.046; learned values are far above them at high SOC (P30 0.117, P31
  0.179), which fits aged cells. Inferred.
- P38 hi (FF5F2) = **CycleCount** (SBS 0x17 R/W) = 387. Incremented at 0x815F when the FF8E6 float
  accumulator passes 100 %. Reset to 0 by a gauge reseed (0xDAE2).
- P39 lo (FF5F4) = cycle accumulator, % of FCC discharged toward the next cycle (= 50).
- P36, P37, P38 lo, P39 hi, P3E = 0, no xref (spare).

**Usage counters, verified-static.**
- P3A/P3B/P3C (FF5F8/FC/600, u32) = time spent discharging in three power bins. P = V·|I| scaled
  (0x7A2C), with edges from 0xD4F8 = 10/80/180/560. P3A: 10 < P ≤ 130 (low mode), P3B: 130 < P ≤ 370
  (mid), P3C: P > 370 (max/turbo). The unit is the 0x7A2C tick (seconds if the tick is 1 s; same tick
  as P5B). Values 10609 / 133535 / 61039 = 2.9 h / 37.1 h / 17.0 h, which is consistent with P5B hi
  = 54 discharge hours. SBS 0xFB returns P3A–P3D.
- P3D (FF604, u32) = 43620 = **charge accepted after dropping out of "full" while still on the
  charger** (dock top-up), in 10 mAh: 436 Ah. Incremented every 0x23280 (144000) FFE30 units while
  FFB71 is set and I > 0 (0x77E7–0x7840; [gauge-scaling.md](gauge-scaling.md)).
- 0x87 modes 2/3/4 reset P3A–P3D to defaults @0xDAE8 (zero), and every mode also clears P3F–P9D
  (0xAA55 → 0x7547; [events-boot.md](events-boot.md)).

**Lifetime block P3F–P5D (reset by 0x7547 → P3F = 0x00239FD5 signature).**
- P3F = reset signature 0x00239FD5. P40–P45 = 24 saturating per-code fault counters, byte i ↔ code
  table @0x2312 (0A 0B 14 15 16 1E 28 29 32 33 34 3C 3D 3E 3F 46 47 50 51 5A 5B 5C 5D 5E). Current
  values: 0x14 = 38, 0x16 = 1, 0x3C = 58, 0x46 = 4, 0x5C = 122. Codes 0B/15/1E/3E/3F/5A/5D/5E have
  slots but no producer in this firmware ([protection.md](protection.md)). P46 = spare tail of E2.
- P47–P4E = 0 (E3; first word cleared by 0x755E). Spare.
- Event counters, bumped by 0x7648(n) (u16):
  - FF64C (P4F lo, n=0) = 506. Bumped at boot from 0x9C1B, so a reset/boot count.
  - FF64E (P4F hi, n=1) = 506. Sleep/shutdown entry (0x9CFA/0x9D23); also flushes the P73/P74/P7B
    sub-counters.
  - FF650 (P50 lo, n=2) = 387. Cycle events (0x815D, next to CycleCount++).
  - FF652 (P50 hi, n=3) = 6227 = **full-charge detections**: event 23 (0x7F6A) when 0x8259 holds for
    120 ticks (max cell ≥ 4100 mV, charge current ≤ 100 mA); handler 0x954A also logs event code 6.
  - FF654 (P51 lo, n=4) = 38 = **fully-discharged entries**: event 30 (0x7FBA) when UV fault bit 2
    (code 0x14) is first set; equals the 0x14 lifetime count. Handler 0x9552 logs event code 7.
- Lifetime min/max (0x76AF) with their timestamps in P5B-hour units:

| field | value | timestamp field |
|---|---|---|
| FF656 (P51 b2) max-cell index+1 | 6 | |
| FF657 (P51 b3) min-cell index+1 | 3 | |
| FF658 (P52 lo) max cell voltage | 4395 mV | FF66A = 0x7D51 |
| FF65A (P52 hi) min cell voltage | **0 mV** (the dead cell) | FF66C = 0x8F54 = the PF trip |
| FF65C (P53 lo) max P+ voltage | 26042 mV | FF66E |
| FF65E (P53 hi) max charge current | 138 × 10 mA = 1.38 A | FF670 |
| FF660 (P54 lo) max discharge current | −3199 × 10 mA = −32.0 A (s16) | FF672 |
| FF662 (P54 hi) max temp | 3549 = 81.8 °C (0.1 K) | FF674 |
| FF664 (P55 lo) min temp | 2750 = 1.9 °C (0.1 K) | FF676 |
| FF668 (P56 lo) max cell delta | 3658 mV | FF67A |

  P55 hi (FF666) and FF678 = 0, spare.
- Hour counters, ticked from P73 sub-counters that wrap at 60 (consts 0xD532/0xD534 = 60/60), so
  1 count = 3600 ticks ≈ 1 h:
  - P5B lo (FF67C) = powered hours = 0x910D. This is also the log timestamp.
  - P5B hi (FF67E) = discharging hours = 54.
  - P5C lo (FF680) = **charging hours** (0x7D55 no-carry = I > 0) = 2310.
- Throughput, rolled over every 0xDBBA00 = 14 400 000 FFE30 units = 1 Ah (one FFE30 unit = 1 mA ·
  250 ms): P5C hi (FF682) = **504 Ah discharged** (I < 0) and P5D lo (FF684) = **991 Ah charged**
  (I > 0 only, 0x7769).

**Histograms, P5D hi–P6A + P73–P7A, verified-static.**
- 25 u16 hour counters FF686–FF6B7 (P5D hi..P69) = 5 avg-cell-voltage bins (pack mV/6 vs 0xD516:
  0/3000/3300/3700/4000) × 5 temp bins (0.1 K vs 0xD51E: 2831/3031/3181/3331/4000). Index = 5·vbin +
  tbin. Hourly sub-counters are the 25 bytes FF6E0–FF6F8 (P74–P7A lo, block ED). Roll-over is in 0x7898.
- P6A lo (FF6B8) = hours with max cell ≥ 4000 mV (0xD528) = 36316. P6A hi (FF6BA) = hours with min
  cell ≤ 3000 mV (0xD52A) = 437. Their sub-counters are FF6F9/FF6FA (P7A b1/b2).
- P6B–P6D (FF6BC, 6 u16) with sub-counter bytes FF6FC–FF701 (P7B–P7C). Rolled by 0x7901, but no
  incrementer found. All zero. P6E–P72 and P7D–P7E: zero, spare.
- P73 b0/b1/b2 (FF6DC/DD/DE) = minute-level sub-counters for P5B lo / P5B hi / P5C lo.

**Logs, verified-static.** P7F b0 (FF70C) = snapshot ring index 1..3, P7F b1 (FF70D) = fault-log
ring index 1..8, P99 hi (FF776) = event-log ring index 1..4. Snapshots FF70E/FF726/FF73E (24 B each,
words 6..11 = cell mV) = P7F hi–P91 lo. Fault log FF756–FF775 (8 × [ts u16][minute][code]; the middle byte is P73 b0, the minute within
powered hour P5B, [events-boot.md](events-boot.md)) = P91
hi–P99 lo. Event log FF778–FF787 (4 × 4 B) = P9A–P9D. Writers: 0x7B6F (fault, via 0x760F) and 0x7C85
(event).

## Notes

- The config header @0xD400 (returned by SBS 0x78 with 0xD400) contains the string **"21700_30T"** at
  0xD410. Confirmed: the cells are Samsung **INR21700-30T**. SBS 0x21 (DeviceChemistry/DeviceName)
  returns 7 spaces (0xD422) and does not show it.
- The 0xF555/0xF556 immediates at 0x95C2/0xB587/0x2602 look like P11 refs but are the −2731/−2730
  K→°C offsets. Ignore them.

## Open questions

- P6B–P6D aux hour counters: rolled by 0x7901, but no incrementer found.
- The tick source of FFE92 behind all hour counters (1 s assumed from the ~1/h timestamp rate).
- The exact name of P1A and which ROM R tables feed P1B–P31 (see [gauge-scaling.md](gauge-scaling.md)).

## PARAM_NAMES (merged into bms.py)

Confidence in the evidence field: vs = verified-static. inf = inferred. The fields inside each param
are separated by `;`.

```python
PARAM_NAMES = {
    0x00: ("cal checksum (b0) / 0xA5 sig (b1); cell1 ADC @2200mV (hi)", "u8;u8;u16 cnt", "vs 0x4539/0xAD91, SBS 0x58 mode 2"),
    0x01: ("cell2 / cell3 ADC @2200mV", "u16;u16 cnt", "vs 0x44C9, SBS 0x58 mode 2"),
    0x02: ("cell4 / cell5 ADC @2200mV", "u16;u16 cnt", "vs 0x44D9, SBS 0x58 mode 2"),
    0x03: ("cell6 ADC @2200mV (FFB36-FFB28)", "u16 cnt", "vs 0x44E7 via 0x504A"),
    0x04: ("spare (in cal checksum range)", "u32", "vs no xref"),
    0x05: ("spare; cell1 ADC @4200mV (hi)", "u16;u16 cnt", "vs 0x44F0, SBS 0x58 mode 3"),
    0x06: ("cell2 / cell3 ADC @4200mV", "u16;u16 cnt", "vs 0x44F7, SBS 0x58 mode 3"),
    0x07: ("cell4 / cell5 ADC @4200mV", "u16;u16 cnt", "vs 0x4507, SBS 0x58 mode 3"),
    0x08: ("cell6 ADC @4200mV", "u16 cnt", "vs 0x4515"),
    0x09: ("spare (in cal checksum range)", "u32", "vs no xref"),
    0x0A: ("spare; P+ voltage ADC @13200mV (hi)", "u16;u16 cnt", "vs 0x451D, ref 0xD44A, used 0x9F0F"),
    0x0B: ("P+ voltage ADC @25200mV; current ADC zero offset (hi)", "u16 cnt;u16 cnt", "vs 0x4525/0x44AF, 0x4FB6"),
    0x0C: ("current ADC at cal current; spare", "u16 cnt;u16", "vs 0x44B8 (SBS 0x58 mode 1)"),
    0x0D: ("spare; cal reference temperature (hi)", "u16;0.1K", "vs 0x452C (=2993, 26.2C)"),
    0x0E: ("thermistor ADC at cal temp; cell/lot date (hi, SBS 0x94)", "u16 cnt;SBS date", "vs 0x4532, 0x4A11/0x4A23; date meaning inf"),
    0x0F: ("SBS 0x95 value (lot no.?); spare", "u16;u16", "vs 0x4A33/0x4A45; meaning inf"),
    0x10: ("const 'PL' (lo); ManufactureDate SBS 0x1B (hi)", "u16;SBS date", "vs 0x438A/0x439C; nonzero blocks 0x80 mode 5 (0x47E3) and arms the fuse drive (0x8769-0x8783, afe-map.md)"),
    0x11: ("SerialNumber SBS 0x1C", "u16", "vs 0x43AC/0x43C4"),
    0x12: ("spare", "u32", "vs no xref; zero in defaults 0xDA3A"),
    0x13: ("spare", "u32", "vs no xref"),
    0x14: ("spare", "u32", "vs no xref"),
    0x15: ("spare", "u32", "vs no xref"),
    0x16: ("spare", "u32", "vs no xref"),
    0x17: ("PF fault-mask bits 48-63 (lo); protection-disable mask FFB50 / SBS 0xB2 (hi)", "bitmask;bitmask", "vs 0x839D/0xAB41, 0x83CA/0x8417; hi bits 1=V,2=I,3=T checks off (protection.md); clear 0xAA55"),
    0x18: ("Qmax: learned chemical capacity (SBS 0xA3)", "float mAh", "seed 3195.0 @0xD98C x parallel 0xD982 (0x7D9A/0x7E14); SOC denom 0x8200; gauge-scaling.md"),
    0x19: ("FullChargeCapacity", "float mAh", "SBS 0x10; seed 2850 @0xD960; learned 0x3610 (>=40% SOC span), clamped <=2850; gauge-scaling.md"),
    0x1A: ("SOC at charge-term OCV (4160 mV)", "float %", "seed 0xA32F OCV->SOC tables @0xD6B0/0xD630 of 4160 @0xD96E; gauge-scaling.md"),
    **{0x1B + i: (f"learned cell R vs SOC [{p}%]", "float ohm", "15-pt grid @0xD7B0, default @0xD904, RAM FF818 (SBS 0xAA); meaning inf; gauge-scaling.md")
       for i, p in enumerate((0, 4, 8, 12, 16, 20, 28, 36, 44, 52, 60, 68, 76, 84, 100))},
    **{0x2A + i: (f"learned R table 2 [{p}% SOC]", "float ohm", "8-pt grid @0xD7EC, default @0xD940, RAM FF854 (SBS 0xAB); meaning inf; gauge-scaling.md")
       for i, p in enumerate((10, 20, 30, 50, 70, 80, 90, 96))},
    0x32: ("gauge-valid marker 0xBEEF (lo); model string len (b2), 'S' (b3)", "u16;u8;char", "vs 0x7E03/0x7F17, 0xAF9B (SBS 0x2F)"),
    0x33: ("model string 'EC_V'", "ascii", "vs SBS 0x2F 0xAF9B"),
    0x34: ("model string 'S900'", "ascii", "vs SBS 0x2F"),
    0x35: ("model string '0NL\\0'", "ascii", "vs SBS 0x2F"),
    0x36: ("spare", "u32", "vs no xref"),
    0x37: ("spare", "u32", "vs no xref"),
    0x38: ("spare; CycleCount SBS 0x17 (hi)", "u16;u16", "vs 0x4351/0x7FFC"),
    0x39: ("cycle accumulator % toward next cycle", "u16 %", "vs 0x803E (int of FF8E6)"),
    0x3A: ("discharge time, low power bin 10-130", "u32 ticks(s?)", "vs 0x7A8E, edges @0xD4F8; SBS 0xFB"),
    0x3B: ("discharge time, mid power bin 130-370", "u32 ticks(s?)", "vs 0x7AAD; SBS 0xFB"),
    0x3C: ("discharge time, high power bin >370", "u32 ticks(s?)", "vs 0x7AC7; SBS 0xFB"),
    0x3D: ("charge after leaving full while on charger (dock top-up)", "u32 x10 mAh", "FFE30/144000 while FFB71 & I>0 (0x77E7-0x7840); gauge-scaling.md"),
    0x3E: ("spare", "u32", "vs no xref"),
    0x3F: ("lifetime block signature 0x00239FD5", "u32", "vs 0x7552 (reset 0x7547); SBS 0xE2"),
    0x40: ("fault count code 0A/0B/14/15", "4x u8", "vs 0x760F, table @0x2312; SBS 0xE2"),
    0x41: ("fault count code 16/1E/28/29", "4x u8", "vs 0x760F"),
    0x42: ("fault count code 32/33/34/3C", "4x u8", "vs 0x760F"),
    0x43: ("fault count code 3D/3E/3F/46", "4x u8", "vs 0x760F"),
    0x44: ("fault count code 47/50/51/5A", "4x u8", "vs 0x760F"),
    0x45: ("fault count code 5B/5C/5D/5E", "4x u8", "vs 0x760F"),
    0x46: ("spare (E2 tail)", "u32", "vs no xref"),
    **{0x47 + i: ("spare (E3)", "u32", "vs zero, cleared by 0x755E") for i in range(8)},
    0x4F: ("boot count; sleep-entry count", "u16;u16", "vs 0x7648 n=0 (0x9C1B), n=1 (0xAA8A)"),
    0x50: ("cycle events; full-charge detections (event 23)", "u16;u16", "n=2 0x815D; n=3 0x954A, detect 0x8259; gauge-scaling.md"),
    0x51: ("fully-discharged entries (UV bit 2, event 30); max-cell idx+1 (b2); min-cell idx+1 (b3)", "u16;u8;u8", "n=4 0x9552 via 0x7FBA; 0x76BD/0x76D9; gauge-scaling.md"),
    0x52: ("lifetime max cell V; min cell V", "mV;mV", "vs 0x76AF/0x76D3"),
    0x53: ("lifetime max P+ voltage; max charge current", "mV;10 mA", "0x76EC/0x7708; current unit from 0x95E5; gauge-scaling.md"),
    0x54: ("lifetime max discharge current; max temp", "s16 10 mA;0.1K", "0x7720/0x772E; current unit from 0x95E5; gauge-scaling.md"),
    0x55: ("lifetime min temp; spare", "0.1K;u16", "vs 0x7747"),
    0x56: ("lifetime max cell delta; ts of max cell V", "mV;P5B hours", "vs 0x775A/0x76C5"),
    0x57: ("ts min cell V; ts max P+ V", "P5B hours;P5B hours", "vs 0x76E6/0x76F7"),
    0x58: ("ts max chg current; ts max dsg current", "P5B hours;P5B hours", "vs 0x7710/0x7728"),
    0x59: ("ts max temp; ts min temp", "P5B hours;P5B hours", "vs 0x7739/0x774F"),
    0x5A: ("spare; ts max cell delta", "u16;P5B hours", "vs 0x7763"),
    0x5B: ("powered hours (log timestamp); discharging hours (I<0)", "h;h", "0x78AB/0x78BF, 0x7AE7; gauge-scaling.md"),
    0x5C: ("charging hours (I>0); discharge throughput", "h;Ah", "0x7AEC/0x78D3; 0x77CD rollover 14400000 FFE30 units = 1 Ah; gauge-scaling.md"),
    0x5D: ("charge throughput; hist[0] (V0,T0)", "Ah;h", "0x7769 I>0 only, 0x778E 1 Ah rollover; 0x79F4; gauge-scaling.md"),
    **{0x5E + i: (f"V x T histogram hours [{2*i+1}],[{2*i+2}]", "h;h", "vs 0x79F4: idx=5*vbin+tbin, bins @0xD516/0xD51E") for i in range(12)},
    0x6A: ("hours max cell >= 4000mV; hours min cell <= 3000mV", "h;h", "vs 0x78E7/0x78FB, consts 0xD528/0xD52A"),
    0x6B: ("aux hour counters [0],[1] (no incrementer found)", "h;h", "vs 0x7901 roll-over"),
    0x6C: ("aux hour counters [2],[3]", "h;h", "vs 0x7901"),
    0x6D: ("aux hour counters [4],[5]", "h;h", "vs 0x7901"),
    **{0x6E + i: ("spare (EA)", "u32", "vs zero, no xref") for i in range(5)},
    0x73: ("sub-hour ticks: powered/discharging/charge-state (b0-b2)", "3x u8", "vs 0x7ADF/0x7AE7/0x7AF1; b0 = log minute; SBS 0xEC"),
    **{0x74 + i: (f"histogram sub-counters bytes {4*i}-{4*i+3}", "4x u8", "vs 0x7B3D; SBS 0xED") for i in range(6)},
    0x7A: ("hist sub-counter 24 (b0); >=4000mV sub (b1); <=3000mV sub (b2)", "u8;u8;u8", "vs 0x7B5B/0x7B66"),
    0x7B: ("aux sub-counters 0-3", "4x u8", "vs 0x7908; SBS 0xEE"),
    0x7C: ("aux sub-counters 4-5; spare", "u8;u8;u16", "vs 0x7908"),
    0x7D: ("spare (EE)", "u32", "vs no xref"),
    0x7E: ("spare (EE)", "u32", "vs no xref"),
    0x7F: ("snapshot ring idx (b0); fault-log ring idx (b1); snapshot1 w0 (hi)", "u8;u8;u16", "vs 0x7B8D/0x7BAF; SBS 0xEF/0xF0"),
    **{0x80 + i: ("fault snapshot data (F0-F2, 3x24 B)", "u16;u16", "vs 0x7B75; words 6..11 = cell mV") for i in range(0x11)},
    0x91: ("snapshot3 last word; fault log entry0 ts (hi)", "u16;u16", "vs F2/F3"),
    **{0x92 + i: ("fault log (F3, 8x [ts u16][minute][code])", "bytes", "vs 0x7BC5 (base FF752+4*idx)") for i in range(7)},
    0x99: ("fault log entry7 minute/code (lo); event-log ring idx (b2)", "u8;u8;u8", "vs 0x7C97; SBS 0xF4"),
    0x9A: ("event log entry 0 [ts][minute][code]", "u16;u8;u8", "vs 0x7CA6 (base FF774+4*idx); SBS 0xF5"),
    0x9B: ("event log entry 1", "u16;u8;u8", "vs 0x7C85"),
    0x9C: ("event log entry 2", "u16;u8;u8", "vs 0x7C85"),
    0x9D: ("event log entry 3", "u16;u8;u8", "vs 0x7C85"),
}
assert len(PARAM_NAMES) == 158
```

Cross-refs: [balancing.md](balancing.md) (no balance params); [protection.md](protection.md) (all
protection thresholds are code constants 0xD550–0xD5E4, none in params; FFB50 bits; SBS 0x47);
[../protocol.md](../protocol.md) (0x87 mode effects, SBS 0x94/0x95 R/W); [gauge-scaling.md](gauge-scaling.md)
(gauge params, current unit, throughput and hour counters).
