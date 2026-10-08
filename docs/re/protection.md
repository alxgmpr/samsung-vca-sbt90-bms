# Protection: fault codes, thresholds, timers

Merged from the thresholds and fault-codes RE docs (2026-10-08; originals in git history). Source: `firmware/code.dis`
(static) plus read-only SBS reads (see `_board_log.md`). Every limit is a fixed constant in code flash 0xD4F0-0xD5E4;
none comes from a param. Constants are code-flash addresses, read through the 0xFDxxx mirror.
Confidence: **VS** = verified-static, **VB** = verified-on-board, **INF** = inferred.

## How the checks run

- All checks run in `0x6B2C`, called from the 250 ms measurement task at `0x95CE`. The 250 ms tick is **VS**: the gauge
  integrator uses dt = 250 ms, see [gauge-scaling.md](gauge-scaling.md).
- Debounce counters compare against `const*4`, so **timer constants are seconds**. In sleep the idle timer adds 240 per tick,
  giving a 60 s tick.
- Order: 0x5F37 rest timer, PF checks 0x6803 (b48) / 0x6868 (b50) / 0x68D8 (b52) / 0x69BD (b55), b40 restore, then
  0x5F96 (b0), 0x602D (b2), 0x60B9 (b4), 0x6175 (b6), 0x6242 (b7), 0x62C1 (b8), 0x637C (b9), 0x63F5 (b10), 0x646E (b11),
  0x6525 (b12), 0x65DC (b15), 0x667E (b16), 0x6721 (b17), then 0x83D3 → 0x84C6 (b24), 0x85BC (b21), 0x8646 (b55 second path).
  It ends with the FET enables 0x6A86 / 0x6ADC. **VS**
- **Fault mask:** 64 bits at 0xFFA9E. Helpers take the mask as 4 pushed words (first push = bits 48-63, last = bits 0-15).
  **VS**
  - `0x5EF6` SET (also clears the pending bit), `0x5F1A` CLR, `0x5ED4` TEST.
  - Pending (warning) mask at 0xFFAA6: `0x5E64` PEND, `0x5E72` UNPEND, `0x5E42` TEST.
  - Shared tails: `0x612A`/`0x6126` = SET, `0x623A`/`0x6238` = CLR.
- **Compares:** signed 32-bit `0xAEE1` (CY when AX:BC < pushed i32), signed 16-bit `0xB8AC` (CY when AX < BC). **VS**
- **Current unit = 10 mA/LSB.** **VS**
  - The gauge integrator receives `0xFFE54 × 10` at `0x95E5` and integrates mA ([gauge-scaling.md](gauge-scaling.md)).
  - This agrees with SpecificationInfo (SBS 0x1A, handler 0x4383) = 0x1031, IPScale ×10 (**VB**: the board reads 0x1031).
  - Raw values are shown in [brackets] below.

### Measurement struct at 0xFFA2C (built at 0x959A) — VS

| RAM | Source | Meaning | Units |
|---|---|---|---|
| 0xFFA2C i32 | 0xFFE54 sign-ext | current, + = charge (SBS 0x0A) | 10 mA |
| 0xFFA30 u32 | 0xFFE58 | \|current\|; used only by the rest timer 0x5F37 (< 5 → "rested") | 10 mA |
| 0xFFA34 | 0xFFE6A | min cell | mV |
| 0xFFA36 | 0xFFE68 | max cell | mV |
| 0xFFA38 | max − min | cell delta | mV |
| 0xFFA3A | 0xFFE6C | sum of cells = SBS 0x09 Voltage | mV |
| 0xFFA3C | 0xFFE6E = 0xFFA4A (AFE) | pack-terminal / charger-side voltage (SBS 0x47) | mV. **VB**: 22253 with FETs on, 4397 with PF latched |
| 0xFFA3E, 0xFFA40 | 0xFFE60 − 2731 | temperature, one thermistor (same value twice) | 0.1 °C |

Cell min/max/sum are computed at `0xB055` over `0xD404` = 6 cells from the cell array 0xFFA86. **VS**

### Terminal voltage and gate flags

- **Terminal (0xFFE6E):** **VS**
  - charger present at ≥ 19800 mV (0xD4F6, test 0x836C);
  - "nothing connected" below 1800 mV (0xD4F4);
  - sanity limit 28000 mV (0xD5E4).
- **0xFFB55.2:** port P13.7 (U1 pin 30, INTP0) read low for 8 samples in a row (debounced at 0x8853-0x8870).
  - Used as "charger / MODE detect" (**VS**, [events-boot.md](events-boot.md)).
  - **VB**: low on the bench with no charger attached, so the board net driving it is still open.
- **0xFFB86 / 0xFFB87:** charge / discharge FET allowed (0x6A86 / 0x6ADC). **VS**
- **0xFFAC0:** rested ≥ 30 min. 0x5F37 sets it when \|I\| < 50 mA [5] for 0xD56A = 30 min (0xD568 = 5). **VS**

## Code table at 0x2422

- `0x8420` maps each mask bit to its logged code; the table pairs are `[code, bit]`.
- The per-code saturating lifetime counters live in P40-P45 (slot table at 0x2312).
- `bms.py` mirrors this as `CODE_BIT`. **VS**

## Main table

Units: mV, 10 mA [raw], 0.1 °C as stored. "Debounce" is in seconds unless noted.

| Code | Bit | Class | Condition (set) | Threshold (addr = value) | Debounce | Release | Setter | Conf |
|---|---|---|---|---|---|---|---|---|
| 0x0A | 0 | V | cell OV: max cell > 4230 mV | D554 = 4230 mV, D558 = 4100 mV | D556 = 3 s | max < 4100 mV, immediate (D55A = 0) | 0x5F96: 0x5FF0 → 0x6010 | VS |
| 0x14 | 2 | V | cell UV: min cell < 2600 mV **and** I < 50 mA [5] (not charging) | D55C = 2600 mV, D55E = 5 | D560 = 1 s | terminal ≥ 19800 mV (D4F6, charger) or 0xFFB55.2 | 0x602D: 0x6067 → 0x609A | VS |
| 0x16 | 4 | V | deep UV: min cell < 2500 mV **and** terminal < 1800 mV. With terminal ≥ 1800 and 0xFFB50.7 set it only goes pending (0x60DC → 0x6109) | D562 = 2500 mV, D564 = 1800 mV | D566 = 5 s | none of its own; reset or clear-all 0xAA6C. Not persisted, so the next reset clears it | 0x60B9: 0x60CA → 0x6106 | VS |
| 0x28 | 6 | I | SW charge OC: I > 2.5 A [250] | D56C = 250 | D56E = 3 s | immediately on discharge < −100 mA [−10] (D570), else after D572 = 30 s. 3 trips (D578) in 300 s (D57A) latch (counter 0xFFAC2, cleared when 0xFFB55.2 = 0) | 0x6175: 0x61E0 → 0x620B | VS |
| 0x29 | 7 | I | HW charge OC: AFE reg 0x6A bit 3 | AFE comparator (regs 0x60-0x65) | AFE | as 0x28 (D574 = −10, D576 = 30 s, shared latch 0xFFAC2) | 0x6242: 0x629F → 0x62AB | VS |
| 0x32 | 8 | I | SW discharge OC: I < −40 A [−4000] | D57C = −4000 | D57E = 3 s | D580 = 30 s; timer resets while charging. Latch counter 0xFFAC8 limit D586 = 0xFFFF (never latches), D588 | 0x62C1: 0x6323 → 0x634A | VS |
| 0x33 | 9 | I | HW discharge OC: AFE 0x6A bit 2 (also from the AFE IRQ path) | AFE comparator | AFE | D582 = 30 s | 0x637C: 0x63D3 → 0x63DF; 0x88AD | VS |
| 0x34 | 10 | I | HW short circuit: AFE 0x6A bits 1:0 | AFE comparator | AFE | D584 = 30 s | 0x63F5: 0x644C → 0x6458; 0x88D1 / 0x88F9 | VS |
| 0x3C | 11 | T | charge OT: T > 55.0 °C **and** I > 50 mA [5] | D58E = 550, D58C = 5, D592 = 540 | D590 = 0 (immediate) | T < 54.0 °C, immediate (D594 = 0) | 0x646E: 0x64CE → 0x6506 | VS |
| 0x3D | 12 | T | charge UT: T < 0.0 °C **and** I > 50 mA [5] | D598 = 0, D596 = 5, D59C = 50 | D59A = 0 | T > 5.0 °C (D59E = 0) | 0x6525: 0x6585 → 0x65BD | VS |
| 0x46 | 15 | T | OT, any state: T > 76.0 °C | D5A0 = 760, D5A4 = 600 | D5A2 = 0 | T < 60.0 °C (D5A6 = 0) | 0x65DC: 0x663C → 0x665F | VS |
| 0x47 | 16 | T | UT, any state: T < −20.0 °C | D5A8 = −200, D5AC = −150 | D5AA = 0 | T > −15.0 °C (D5AE = 0) | 0x667E: 0x66DC → 0x66FD | VS |
| 0x50 | 17 | I | charge timeout: cumulative time with I > 50 mA [5] ≥ 360 min (u32 counter 0xFF94A vs D5B2·4·60) | D5B0 = 5, D5B2 = 360 min | 6 h | discharge < −100 mA [−10] (D5B4) for 1 s (D5B6) | 0x6721: 0x6789 → 0x67D2 | VS |
| 0x5C | 21 | V | terminal / charger OV: terminal ≥ 26000 mV with 0xFFB55.2 set | immediate 0x6590 = 26000 mV at 0x85E5 (D5B8 = 26000 unused), D4F4 = 1800 mV | 5 consecutive evaluations | 1800 < V < 26000 for 5 evaluations, or V ≤ 1800 mV (unplugged) at once | 0x85BC → 0x8640 | VS (terminal identity VB) |
| 0xA3 | 35 | boot | config checksum 0xFFB02 ≠ word at 0xD3FE | — | — | — | 0x9BE1 → 0x9BF6 | VS |
| 0xA4 | 36 | boot | data-flash param checksum: byte-sum of 56 B at 0xFF512 ≠ P00[7:0] (3 tries) | — | — | — | 0xADA3 → 0xADC6 | VS |
| 0xA5 | 37 | boot | config signature at 0xD400 ≠ "SV" | — | — | — | 0x9BFB → 0x9C13 | VS |
| 0xA7 | 39 | boot | data-flash write failure: 0xFFE97 ≠ 0, 0xFFE5C = 0, error byte 0xFFE96 ∈ {4 = read-back mismatch, 5 = erase error / retries out} ([events-boot.md](events-boot.md)) | — | — | — | 0x9CBE → 0x9CE1 | VS (value meanings INF) |
| 0xB4 | 40 | V | measurement implausible, checked only while a V fault is pending (bits 0, 2, 4, 5, 21, 48, 50, 52): min cell < 0 mV, max cell > 5000 mV, or terminal > 28000 mV. Sets 0xFFB50.1 (persisted as P17 bit 17), which disables the voltage class. Re-set every boot while that flag is on (0x6B72 / 0x6B77 / 0x6B87) | D5DE = 0, D5E0 = 5000 mV, D5E4 = 28000 mV | D5E2 = 1 s | clear-all only, or P17 hi = 0 | 0xB23F → 0xB295 | VS |
| 0xC8 | 48 | PF | cell OV: max cell > 4300 mV | D5C2 = 4300 mV | D5C4 = 5 s | latched (P17) | 0x6803: 0x6820 → 0x683D | VS |
| 0xCA | 50 | PF | dead cell: min cell < 1000 mV, armed until the first reading ≥ 1000 mV after reset (0xFFB89) | D5C6 = 1000 mV | D5C8 = 5 s (20 ticks) | latched | 0x6868: 0x6895 → 0x68B3 | VS (VB: this unit's trip) |
| 0xCC | 52 | PF | imbalance: (a) charging I > 50 mA [5] **and** max > 3700 mV **and** Δ > 195 mV; (b) rested ≥ 30 min (0xFFAC0) **and** either 3615 < max ≤ 3785 mV with Δ > 170 mV, or max > 3785 mV with Δ > 200 mV | D5CA = 5, D5CC = 3700, D5CE = 195, D5D0 = 3615, D5D2 = 3785, D5D4 = 170, D5D6 = 200 mV | D5D8 = 20 s | latched | 0x68D8: 0x68F9 / 0x695C → 0x69AD | VS |
| 0xDC | 55 | PF | FET failure: I > 1 A [100] with charge FET disabled (0xFFB86 = 0), or I < −1 A [−100] with discharge FET disabled (0xFFB87 = 0) | D5DA = 100 | D5DC = 20 s | latched | 0x69BD: 0x69E4 / 0x6A31 → 0x6A5F | VS |
| 0xDC | 55 | PF | FET failure, voltage-slope path: charger present, CHG FET off, I > 100 mA [10], ΔVsum > 8 mV/cycle and terminal − pack < 1250 mV; or DSG FET off, I < −300 mA [−30], ΔVsum < −40 mV/cycle | D500 = 10, D502 = 8, D504 = −30, D506 = −40 | 80 / 400 calls | latched | 0x8646 → 0x872C | VS |
| — | 24 | I | current-sense consistency / sleep path (counters 0xFFE86, D47C / D47D). Set at 0x5733 / 0x84D3 / 0x8511 / 0x8536 / 0xAA1B, cleared on low-power entry 0x5713 and at 0xAA07. No log code | D47C, D47D | — | — | 0x84C6 | VS (meaning INF) |

Lifetime counts on this unit (P40-P45):

| Code | Count | Reading |
|---|---|---|
| 0x5C | 122 | the charger's open-circuit voltage sat above 26.0 V (the request is 25.6 V). Non-latching; no damage implied. |
| 0x3C | 58 | charged above 55 °C (straight after use, or a warm dock). |
| 0x14 | 38 | run down to cutoff 38 times, or a weak cell hit it early. Consistent with the cell that later read 0 V. Matches event counter n4 = 38. |
| 0x46 | 4 | over 76 °C under heavy use. |
| 0x16 | 1 | the same event as the 0xCA trip. |

## Permanent faults (bits 48-62)

- **Persistence:** PF bits are persisted in P17[15:0] (0xAB10) and restored at boot (0x839D). **VS**
- **Effect on the FETs:** both FETs are blocked through mask 0x7FFF<<48 in 0x6A86 and 0x6ADC. **VS**
- **Clearing:** P17 low word = 0, by set-param or the SBS unlock route, then a reset. See [protocol.md](../protocol.md).
- **The fuse is a separate path.** **VS** ([afe-map.md](afe-map.md))
  - 0x8769-0x8783 sets 0xFFE34.0 when a PF bit is set **and** ManufactureDate (P10 hi, 0xFF552) ≠ 0.
  - 0xFFE34.0 drives P1.1 (Q10 gate). Only a reset clears it.
  - P10 hi is 0 during assembly (2026-10-08), so the fuse drive is disarmed.

## Hardware comparators (AFE)

- **Reg 0x6A flags:** bit 3 = charge OC (0x29), bit 2 = discharge OC (0x33), bits 1:0 = short circuit (0x34), bits 4/5 = wake current.
  Reg 0x6B restarts them in the same bit order. **VS** ([afe-map.md](afe-map.md))
- **Detector setup:** regs 0x60-0x65 (write-enabled by 0x6C/0x6D) are loaded from code flash 0xD4AA = `00 E2 E6 E0 10 F9`.
  Regs 0x66 / 0x68 hold the runtime-calibrated wake-current thresholds (routine 0x5B5B-0x5D52, results 0xFFEB1 / 0xFFEB2;
  **VB** codes 54 / 44).
- **Absolute trip levels and delays: open.** The bit layout of regs 0x60-0x65 isn't in the datasheet we have.
  Sense resistance is probably 0.5 mΩ (SR1 ∥ SR2, INF).

## Protection-disable mask (P17 high word)

- 0xFFB50 is restored at boot from **P17[31:16]** (0x83CA-0x83CD) and saved by 0xAB10. If a check's gate bit is set,
  the check clears its own bit and returns. **VS**

  | Bit | Value | Disables |
  |---|---|---|
  | 1 | 0x0002 | voltage class: b0, b2, b48, b50, b52. Set by b40 / 0xB4 |
  | 2 | 0x0004 | current class: b6, b7, b8, b9, b10, b17, b55 |
  | 3 | 0x0008 | temperature class: b11, b12, b15, b16 |
  | 7 | 0x0080 | lets b4 (0x16) go pending while a charger is present instead of being skipped |

- Helpers: 0xB216 sets bits, 0xB224 clears them, 0xB20A tests them.
- It clears only through clear-all 0xAA55 (SBS 0x87) or a P17 write with the high word = 0.
- Live and in data flash: 0. **It must read 0 after the rebuild.**

## FET enable masks — VS

- **Charge FET (`0x6A86`)** is off when any of these holds:
  - any of bits 32-62;
  - an alert on bit 50;
  - discharge current > 100 mA (D550 = −10);
  - any of bits {0, 1, 2, 4, 6, 7, 11-23};
  - `0x5EA0(31)`.
- **Discharge FET (`0x6ADC`)** is off when any of these holds:
  - any of bits 32-62;
  - an alert on bit 50;
  - any of bits {2, 3, 4, 8, 9, 10, 15, 16, 24};
  - `0x5EA0(27)`.

## Dead table entries

These have no setter in this firmware; all **VS**:
- 0x51 (b18), 0x5B (b20), 0xA6 (b38, only tested at 0x6B6D), 0xB5 / 0xB6 / 0xB7 (b41-43), 0xB9 / 0xBA (b46-47).
- 0xC9 (b49) can only come back from P17 at boot (0x83C7).
- Codes 0x0B, 0x15, 0x1E, 0x3E, 0x3F, 0x5A, 0x5D and 0x5E have lifetime-counter slots at 0x2312 but no producer.
- Bit 5 appears only in the 0xB4 pending mask.

## Logging behaviour

- **What gets logged:** `0x8420` diffs the mask against 0xFFAAE. For each newly set bit in the 0x2422 table it logs the code
  via `callt [0xB2]` → 0x760F, which writes the fault log (SBS 0xF3) and the lifetime counter (P40-P45).
  Boot checks (0xA3 / 0xA4 / 0xA5 / 0xA7) log directly. **VS**
- **Logging stops once a PF bit is already set.** **VS**
- **The freeze flag survives resets.** **VS**, live 0xFFE94 = 1 ([events-boot.md](events-boot.md))
  - 0xFFE94 = 1 freezes the fault log, the event log and the event counters.
  - It is set when a code ≥ 200 is logged (0x7BE3).
  - It is set again at every boot by 0x750B whenever the newest snapshot code is ≥ 200.
  - Unfreeze, keeping history: `set-param 0x87 0x00168F54` (README step 6).
- **The event log (SBS 0xF5) uses its own codes 1-10**, not the fault codes.
  - The 0x0A entries at the 0xCA trip are event 10, "a cell moved ≥ 500 mV", not cell OV.
  - `EVENT_NOTE` in `bms.py` decodes them.

## SBS 0xEB is not a threshold block

- SBS 0xEB is a straight 20-byte copy of code flash 0xD518 (0x75D5): the usage-histogram bin edges.
  - **VS** 3000 / 3300 / 3700 / 4000 mV, 2831 / 3031 / 3181 / 3331 (0.1 K), 4000 / 3000.
  - **VB**: the live read on 2026-10-08 at 05:19Z (`b80be40c…a00fb80b`) is byte-identical to 0xD518-0xD52B.
- The histogram usage is traced at 0x7AF4 ([param-names.md](param-names.md)).

## Other limits found on the way

| Const | Value | Use | Conf |
|---|---|---|---|
| D46A / D470 / D46E | 150 / 20 / 3000 | ChargingCurrent 1.5 A [150]; 0.2 A precharge [20] when min cell < 3000 mV (0xB690) | VS |
| D46C | 25600 mV | ChargingVoltage | VS |
| D488 → 0xFFB22 | 4100 mV | full charge: max cell ≥ 4100 and I < 100 mA (D48A = 10) for 120 counts (D48C) at 0x8259 | VS |
| D48E | 4380 mV | max-cell compare at 0x7F33, termination / learning path | INF |
| D554 | 4230 | also read at 0xB59B | VS |
| D568 / D56A | 5 / 30 | rest detector 0x5F37 | VS |
| D4F0 / D4F2 / D4F6 | 8 / 1800 / 19800 | sleep / shutdown and charger detect on 0xFFE6E (0xB418-0xB44B) | INF |

## What this means for the cell install

- **0xCC imbalance PF:**
  - Δ > 195 mV while charging above 3.7 V, or Δ > 170 / 200 mV at rest, for 20 s.
  - The firmware does not balance ([balancing.md](balancing.md)), so match the cells to within about 20 mV.
- **0xC8:** any cell above 4300 mV for 5 s. Don't fit cells charged above 4.2 V. The 4230 mV soft limit (0x0A) leaves little margin.
- **0xCA:** fires when the board wakes with any tap below 1 V. Connect B- first, then B1..B5, B+ last.
  The fuse drive is disarmed while P10 hi = 0.
- **0x16:** below 2500 mV with nothing on P+. It clears on reset.
- **Charge request:** 0.2 A precharge for cells below 3000 mV, 1.5 A otherwise.
- **0x5C:** a charger above 26.0 V on P+ sets it. It is recoverable and blocks charging only.

## Open questions

1. Absolute HW COC / DOC / SC thresholds and delays (AFE regs 0x60-0x65 bit layout). Needs the RAJ2400x0 hardware manual.
2. Bit 24 (0x84C6): exact meaning, and the units of D47C / D47D.
3. `0x5EA0(27)` / `0x5EA0(31)`: the extra FET-off conditions.
4. Which board net drives P13.7 (0xFFB55.2). Settled with a continuity check, board unpowered.
5. Physical meaning of the 0xA7 error states 4 / 5 (which flush step).

## CODE_NOTE for bms.py

```python
CODE_NOTE = {
    0x0A: "cell OV: max cell > 4230 mV 3 s (rel < 4100)",
    0x14: "cell UV: min cell < 2600 mV, not charging, 1 s (rel when charger seen)",
    0x16: "deep UV: min cell < 2500 mV with terminal < 1.8 V, 5 s (0x60CA)",
    0x28: "charge OC (SW): I > 2.5 A 3 s; 3 trips/300 s latches",
    0x29: "charge OC (AFE comparator, reg 0x6A b3)",
    0x32: "discharge OC (SW): I < -40 A 3 s, rel 30 s",
    0x33: "discharge OC (AFE comparator, reg 0x6A b2)",
    0x34: "short circuit (AFE, reg 0x6A b0/b1), rel 30 s",
    0x3C: "charge over-temp: T > 55.0 C while charging (rel < 54.0)",
    0x3D: "charge under-temp: T < 0.0 C while charging (rel > 5.0)",
    0x46: "over-temp: T > 76.0 C (rel < 60.0)",
    0x47: "under-temp: T < -20.0 C (rel > -15.0)",
    0x50: "charge timeout: > 360 min charging",
    0x5C: "terminal/charger OV: >= 26.0 V for 5 cycles",
    0xA3: "boot: config checksum mismatch",
    0xA4: "boot: data-flash param checksum mismatch",
    0xA5: "boot: config signature 'SV' missing",
    0xA7: "data-flash write failure (0xFFE96 = 4 verify / 5 erase-retry)",
    0xB4: "measurement implausible (cell > 5 V / terminal > 28 V); disables V checks",
    0xC8: "PF: cell OV, max cell > 4300 mV 5 s",
    0xC9: "PF: no setter (only restored from P17)",
    0xCA: "PF: dead cell, min cell < 1000 mV for ~20 checks after wake (0x6890)",
    0xCC: "PF: cell imbalance, delta > 195 mV charging (> 170/200 mV at rest) 20 s",
    0xDC: "PF: FET failure, current with FET off (> 1 A) 20 s",
}
```
