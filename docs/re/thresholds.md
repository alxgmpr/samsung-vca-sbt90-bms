# Protection thresholds and timers (slug: thresholds)

Source: static analysis of `firmware/codeflash.bin` / `firmware/code.dis`. Constants are code-flash words
(firmware reads them through the 0xFDxxx mirror). Confidence: **VS** = verified-static,
**VB** = verified-on-board, **I** = inferred.

## How the checks run

- Main protection tick `0x6B2C`, called from `0x95CE`. It copies a 26-byte measurement struct from the
  stack (built at `0x959A`) to RAM `0xFFA2C`, then runs `0x5F37` (idle timer), `0x6803`/`0x6868`/`0x68D8`/
  `0x69BD` (PF class), then `0x5F96 .. 0x6721` (recoverable faults). It finishes with FET enables `0x6A86`/`0x6ADC`. **VS**
- Tick = 250 ms (**I**: timers compare `count` against `const*4`, and the idle timer adds 240 per tick in
  sleep, which gives 1 s units in run mode and a 60 s sleep tick). fault-codes reached the same 250 ms independently.
  Below, a timer const `T` means `T*4` ticks = `T` seconds.
- Fault-mask argument = 4 words pushed high word first (first `push` = bits 48-63, last = bits 0-15). **VS**
- Each check has three states: alert/pending `0x5E64` while counting, `0x5E72` clears the alert, and `0x5EF6` sets the fault, `0x5F1A` clears it.
- Signed 32-bit compare `0xAEE1`: CY when (AX:BC) < pushed i32. Signed 16-bit compare `0xB8AC`: CY when AX < BC. **VS**

### Measurement struct @0xFFA2C (VS)

| RAM | Source | Meaning | Units |
|---|---|---|---|
| 0xFFA2C (i32) | 0xFFE54 | current, + = charge (SBS 0x0A) | 10 mA (**I**, see below) |
| 0xFFA30 (u32) | 0xFFE58 | \|current\| | 10 mA |
| 0xFFA34 | 0xFFE6A | min cell | mV |
| 0xFFA36 | 0xFFE68 | max cell | mV |
| 0xFFA38 | max−min | cell delta | mV |
| 0xFFA3A | 0xFFE6C | sum of cells = SBS 0x09 Voltage | mV |
| 0xFFA3C | 0xFFE6E = 0xFFA4A (AFE) | SBS 0x47, pack-terminal / charger voltage | mV (**VB**) |
| 0xFFA3E, 0xFFA40 | 0xFFE60 − 2731 | temperature (same value twice, one thermistor) | 0.1 °C |

Cell min/max/sum are computed at `0xB055` over `0xD404` cells from the cell array `0xFFA86`. **VS**

**Current units = 10 mA (I, strong).** SpecificationInfo (SBS 0x1A, handler `0x4383`) returns the
constant `0x1031`, which encodes IPScale = 1 (×10) (**VB**: board reads 0x1031, ChargingCurrent 150, ChargingVoltage 25600). The charge request (`0xB690`) is `0xD46A` = 150 → 1.5 A for a 2850 mAh
pack, or `0xD470` = 20 → 0.2 A precharge when min cell < `0xD46E` = 3000 mV. In plain mA (150 mA charge,
4 A discharge cut-off) the vacuum couldn't run. Capacity registers stay in mAh (design 2850).

**0xFFE6E = pack-terminal / charger voltage (I).** Charger-present test `0x836C`: ≥ `0xD4F6` = 19800 mV.
"Nothing connected": < `0xD4F4` = 1800 mV. Upper sanity limit 28000 mV. **VB** (fault-codes): SBS 0x47 reads
22253 mV with FETs on, 4397 mV while the PF was latched (see `_board_log.md`).

## Recoverable faults (bits 0-31)

Disable gates come from `0xFFB50` (restored from **P17[31:16]** at boot, `0x83CA`):
bit1 = voltage class, bit2 = current class, bit3 = temperature class. If the gate is set, the check clears its bit and returns.

| Code | Bit | Check | Trip condition | Delay | Recovery | Constants | Conf. |
|---|---|---|---|---|---|---|---|
| 0x0A | 0 | 0x5F96 | cell OV: max cell > 4230 mV | 3 s | max < 4100 mV, immediate | D554, D556, D558, D55A | VS |
| 0x14 | 2 | 0x602D | cell UV: min cell < 2600 mV **and** I < 50 mA (not charging) | 1 s | charger present (0xFFE6E ≥ 19800 mV, D4F6) or 0xFFB55.2 | D55C, D55E, D560 | VS |
| 0x16 | 4 | 0x60B9 | deep UV: min cell < 2500 mV **and** (0xFFE6E < 1800 mV or 0xFFB50.7) | 5 s | none in the check; only the clear-all at 0xAA6C (reset) | D562, D564, D566 | VS |
| 0x28 | 6 | 0x6175 | charge OC (SW): I > 2.5 A | 3 s | 30 s, or immediate on discharge > 100 mA; latches after 3 trips in 300 s (counter 0xFFAC2, cleared when 0xFFB55.2 = 0) | D56C, D56E, D570, D572, D578, D57A | VS (A = I) |
| 0x29 | 7 | 0x6242 | charge OC (HW): AFE reg 0x6A bit 3 | AFE | 30 s / discharge > 100 mA, same latch as bit 6 | D574, D576 | VS |
| 0x32 | 8 | 0x62C1 | discharge OC (SW): I < −40 A | 3 s | 30 s; latch counter 0xFFAC8 limit D586 = 0xFFFF (never latches) | D57C, D57E, D580, D586, D588 | VS (A = I) |
| 0x33 | 9 | 0x637C / 0x88AD | discharge OC (HW): AFE 0x6A bit 2 (also set from the AFE IRQ path) | AFE | 30 s | D582 | VS |
| 0x34 | 10 | 0x63F5 / 0x88D1 / 0x88F9 | short circuit (HW): AFE 0x6A bits 1:0 | AFE | 30 s | D584 | VS |
| 0x3C | 11 | 0x646E | charge OT: T > 55.0 °C **and** I > 50 mA | immediate (D590 = 0) | T < 54.0 °C, immediate | D58E, D58C, D590, D592, D594 | VS |
| 0x3D | 12 | 0x6525 | charge UT: T < 0.0 °C **and** I > 50 mA | immediate | T > 5.0 °C | D598, D596, D59A, D59C, D59E | VS |
| 0x46 | 15 | 0x65DC | OT (any state): T > 76.0 °C | immediate | T < 60.0 °C | D5A0, D5A2, D5A4, D5A6 | VS |
| 0x47 | 16 | 0x667E | UT (any state): T < −20.0 °C | immediate | T > −15.0 °C | D5A8, D5AA, D5AC, D5AE | VS |
| 0x50 | 17 | 0x6721 | charge timeout: I > 50 mA accumulated > 360 min (u32 counter 0xFF94A vs D5B2·4·60) | 6 h | discharge > 100 mA for 1 s | D5B0, D5B2, D5B4, D5B6 | VS |
| 0x5C | 21 | 0x85BC | charger OV: 0xFFE6E ≥ 26000 mV (immediate 0x6590 at 0x85E5) with 0xFFB55.2 set | 5 evaluations | 1800 < V < 26000 for 5 evaluations, or V ≤ 1800 mV immediately | imm. 0x6590 (D5B8 = 26000 unused), D4F4 | VS |
| — | 24 | 0x84C6 | current-sense consistency (0xFFE86 / D47C / D47D counters) | — | 0xAA07 | D47C, D47D | VS (meaning I) |

Hardware OC/SC comparator levels are written to AFE regs 0x66-0x69/0x6B/0x6D by the calibration routine
`0x5B5B-0x5D52` (DAC successive approximation, results 0xFFEB1/0xFFEB2). The absolute A/µs values need
the RAJ240080 register definitions, which aren't in the repo. **Open.**

### Bit 0x5C (122 lifetime events)
It is a voltage check on the pack-terminal / charger input, not a cell check. The firmware latches it once the terminal reads ≥ 26.0 V
for 5 consecutive evaluations while charging (0xFFB55.2). The charge request is 25600 mV (0xD46C), so a charger
that sits ~0.4 V above its setpoint, or overshoots on plug-in, trips it. That fits a count of 122 over the pack's life.

## Permanent faults (bits 48-62, persisted in P17[15:0])

| Code | Bit | Check | Trip condition | Delay | Constants | Conf. |
|---|---|---|---|---|---|---|
| 0xC8 | 48 | 0x6803 | cell over-voltage PF: max cell > 4300 mV | 5 s | D5C2, D5C4 | VS |
| 0xCA | 50 | 0x6868 | dead cell: min cell < 1000 mV, armed until the first reading ≥ 1000 mV after reset (0xFFB89) | 5 s | D5C6, D5C8 | VS |
| 0xCC | 52 | 0x68D8 | imbalance. (a) charging I > 50 mA **and** max > 3700 mV **and** Δ > 195 mV; (b) rested ≥ 30 min (0xFFAC0) **and** Δ > 170 mV if 3615 < max ≤ 3785 mV, Δ > 200 mV if max > 3785 mV | 20 s | D5CA, D5CC, D5CE, D5D0, D5D2, D5D4, D5D6, D5D8 | VS |
| 0xDC | 55 | 0x69BD | FET failure: I > 1 A while charge FET disabled (0xFFB86 = 0), or I < −1 A while discharge FET disabled (0xFFB87 = 0) | 20 s | D5DA, D5DC | VS |
| 0xDC | 55 | 0x8646 | FET failure (V-slope): charger present, CHG FET off, I > 100 mA, ΔVsum > 8 mV and Vchg − Vsum < 1250 mV for 80 calls; or DSG FET off, I < −300 mA, ΔVsum < −40 mV for 400 calls | 80 / 400 | D500, D502, D504, D506 | VS |
| 0xC9, 0xB5-0xBA | 49, 41-47 | not set through 0x5EF6; fault-codes owns them | | | | |

PF bits block both FETs (mask 0x7FFF<<48 in `0x6A86` and `0x6ADC`). The fuse drive is a separate path.

### Sensor-plausibility check (bit 40 / 0xB4), `0xB23F`
It runs only while a voltage fault is active (mask bits 0,2,4,5,21,48,50,52). If min cell < 0 mV (D5DE), max cell > 5000 mV
(D5E0) or 0xFFE6E > 28000 mV (D5E4) for 1 s (D5E2), it sets bit 40 **and 0xFFB50.1**, which disables the whole voltage class.
`0x6B77` also sets bit 40 once per boot when 0xFFB50.1 is already set from P17. **VS**

## FET enable masks (VS)

- Charge FET `0x6A86`: off if bits 32-62, an alert on bit 50, discharge > 100 mA (D550 = −10), or any of bits
  {0,1,2,4,6,7,11,12,13,14,15,16-23}, or `0x5EA0(31)`.
- Discharge FET `0x6ADC`: off if bits 32-62, an alert on bit 50, or any of bits {2,3,4,8,9,10,15,16,24},
  or `0x5EA0(27)`.

## Non-protection limits found on the way

| Const | Value | Use | Conf. |
|---|---|---|---|
| D46A / D470 / D46E | 150 / 20 / 3000 | ChargingCurrent ×10 mA, precharge when min cell < 3000 mV (0xB690) | VS |
| D46C | 25600 mV | ChargingVoltage | VS |
| D488 → 0xFFB22 | 4100 mV | full-charge: max cell ≥ 4100 and I < 100 mA (D48A = 10) for 120 counts (D48C) at 0x8259 | VS |
| D48E | 4380 mV | max-cell compare at 0x7F33, termination/learning path | I |
| D554 | 4230 | also read at 0xB59B | VS |
| D568 / D56A | 5 / 30 | idle (rest) detector 0x5F37: \|I\| < 50 mA for 30 min sets 0xFFAC0 | VS |
| D4F0 / D4F2 / D4F6 | 8 / 1800 / 19800 | sleep/shutdown and charger-detect on 0xFFE6E (0xB418-0xB44B) | I |
| D518..D52A (SBS 0xEB) | 3000,3300,3700,4000 / 2831,3031,3181,3331 / 4000,3000 | usage-histogram bins, not protection (0x75D5 copies 20 B from D518; param-names traced its use at 0x7AF4) | VS |

## Cross-check with SBS 0xEB
SBS 0xEB is a straight 20-byte copy of code flash 0xD518 (`0x75D5`), so it holds no protection limits.
**VB**: the live SBS 0xEB read (2026-10-08 05:19Z) = `b80be40c…a00fb80b`, byte-identical to code flash 0xD518-0xD52B.

## Impact on the cell install

- **0xCC imbalance PF:** a rested pack with Δ > 170 mV (cells 3.6-3.8 V), or Δ > 195 mV while charging above 3.7 V,
  for 20 s latches a PF. Match the new cells to well under 100 mV before fitting.
- **0xC8:** any cell > 4300 mV for 5 s is a PF. Don't fit cells charged above 4.2 V.
- **0xCA:** unchanged (connect all taps before wake).
- Charger above 26.0 V on P+ sets 0x5C (recoverable; it blocks charge only).
- Cells < 3000 mV get the 0.2 A precharge request; < 2600 mV with no charger sets UV (0x14); < 2500 mV with nothing
  on P+ sets 0x16, which only clears on reset.

## Open questions
1. Absolute hardware COC/DOC/SC thresholds (AFE regs 0x66-0x6D): needs the datasheet register map.
2. Bit 24 (0x84C6) exact meaning and units of D47C/D47D.
3. `0x5EA0(27)`/`0x5EA0(31)` extra FET-off conditions.
4. 0xFFB55.2 is used as "charger present / charging"; the setter isn't traced.
