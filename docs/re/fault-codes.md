# Fault codes: code → bit → condition → threshold

Author: fault-codes fork, 2026-10-08. Source: `firmware/code.dis` (static) plus one read-only SBS read (see `_board_log.md`).
Confidence: **VS** = verified-static, **VB** = verified-on-board, **INF** = inferred.

## Mechanics (VS)

- Fault mask 64 bit @0xFFA9E. Helpers take the mask as 4 pushed words (first push = bits 48-63, last = bits 0-15):
  `0x5EF6` SET (also clears the pending bit), `0x5F1A` CLR, `0x5ED4` TEST, `0x5E64` PEND / `0x5E72` UNPEND
  on the pending (warning) mask @0xFFAA6, `0x5E42` TEST pending. Shared tails: `0x612A`/`0x6126` = SET, `0x623A`/`0x6238` = CLR.
- All checks live in `0x6B2C` (called from the 250 ms measurement task at 0x95CE). Debounce counters compare against
  `const*4`, so **timer constants are seconds** (1 tick = 250 ms). Order: 0x5F37 rest timer, 0x6803 (b48), 0x6868 (b50),
  0x68D8 (b52), 0x69BD (b55), b40 restore, 0x5F96 (b0), 0x602D (b2), 0x60B9 (b4), 0x6175 (b6), 0x6242 (b7), 0x62C1 (b8),
  0x637C (b9), 0x63F5 (b10), 0x646E (b11), 0x6525 (b12), 0x65DC (b15), 0x667E (b16), 0x6721 (b17), then 0x83D3 → 0x84C6 (b24),
  0x85BC (b21), 0x8646 (b55 second path).
- Logging: `0x8420` diffs the mask against @0xFFAAE and, for each newly set bit in table @0x2422, logs its code
  (`callt [0xB2]` → 0x760F: fault log 0xF3 + lifetime counter P40-P45). Logging is **suppressed while a PF bit
  (48-62) was already set**. Boot checks log directly (0xA3/0xA4/0xA5/0xA7).
- Measurement struct @0xFFA2C (built at 0x959A):

  | RAM | source | meaning |
  |---|---|---|
  | 0xFFA2C i32 | 0xFFE54 sign-ext | current, SBS 0x0A raw. **Unit 10 mA** (IPScale x10 per SpecificationInfo 0x1031; thresholds fork, INF strong) |
  | 0xFFA30 u32 | 0xFFE58 | used only by rest timer 0x5F37 (< 5 → "rested") |
  | 0xFFA34 | 0xFFE6A | min cell mV |
  | 0xFFA36 | 0xFFE68 | max cell mV |
  | 0xFFA38 | max-min | cell delta mV |
  | 0xFFA3A | 0xFFE6C | pack voltage mV (SBS 0x09) |
  | 0xFFA3C | 0xFFE6E | **terminal voltage mV** (SBS 0x47): 22253 now with FETs on, 4397 with PF latched → pack-terminal / charger-side voltage. VB |
  | 0xFFA3E, 0xFFA40 | 0xFFE60-2731 | temperature 0.1 °C (both the same sensor) |

- Flags used as gates: `0xFFB55.2` = port P13.7 low, debounced 8 samples (0x8853-0x8870), INF charger/MODE detect.
  `0xFFB86`/`0xFFB87` = charge / discharge FET allowed (0x6A86 / 0x6ADC). `0xFFAC0` = rested ≥ 30 min (0x5F37: 0xFFA30 < 5
  for 0xD56A=30 min). `0xFFB50` = protection-disable flags, restored from **P17[31:16]** at boot (0x83CA):
  bit1 (0x0002) suppresses V checks b0/b2/b48/b50/b52 and is set by b40; bit2 (0x0004) suppresses b6/b7/b8/b9/b10/b17/b55;
  bit3 (0x0008) suppresses b11/b12/b15/b16; bit7 (0x0080) lets b4 run with a charger present (pending only). Currently 0.

## Table

Currents below are converted at 10 mA/LSB (raw value in brackets). Constants are code-flash addresses (RAM mirror 0xF_xxxx).

| Code | Bit | Condition (set) | Release | Thresholds (addr = value) | Setter | Conf |
|---|---|---|---|---|---|---|
| 0x0A | 0 | cell OV: max cell > 4230 mV for 3 s | max < 4100 mV for 0 s | D554=4230 mV, D556=3 s, D558=4100 mV, D55A=0 s | 0x5FF0 → 0x6010 | VS |
| 0x14 | 2 | cell UV: min cell < 2600 mV and I < 50 mA [5] for 1 s | terminal V ≥ 19800 mV (charger) or 0xFFB55.2 | D55C=2600 mV, D55E=5, D560=1 s, D4F6=19800 mV | 0x6067 → 0x609A | VS |
| 0x16 | 4 | deep UV: min cell < 2500 mV and terminal V < 1800 mV for 5 s (with charger present and flag 0x80: pending only) | none of its own; only reset or clear-all 0xAA6C | D562=2500 mV, D564=1800 mV, D566=5 s | 0x60CA → 0x6106 | VS |
| 0x28 | 6 | SW charge OC: I > 2.5 A [250] for 3 s | at once on discharge I < -100 mA [-10], else after 30 s; 3 trips in 300 s latch until 0xFFB55.2 drops | D56C=250, D56E=3 s, D570=-10, D572=30 s, D578=3 trips, D57A=300 s | 0x61E0 → 0x620B | VS (units INF) |
| 0x29 | 7 | AFE HW flag: reg 0x6A bit3 (charge-side OC comparator, INF) | as 0x28 (D574=-10, D576=30 s, shared latch @0xFFAC2) | AFE comparator (cal regs 0x66-0x6D) | 0x629F → 0x62AB | VS / name INF |
| 0x32 | 8 | SW discharge OC: I < -40 A [-4000] for 3 s | 30 s, timer reset while charging (I > 0) | D57C=-4000, D57E=3 s, D580=30 s | 0x6323 → 0x634A | VS (units INF) |
| 0x33 | 9 | AFE HW flag: reg 0x6A bit2 (discharge OC comparator, INF) | 30 s (D582) | — | 0x63D3 → 0x63DF, also 0x88AD (AFE ISR path) | VS / name INF |
| 0x34 | 10 | AFE HW flag: reg 0x6A bit0 or bit1 (short circuit, INF) | 30 s (D584) | — | 0x644C → 0x6458, also 0x88D1/0x88F9 | VS / name INF |
| 0x3C | 11 | charge over-temp: T > 55.0 °C and I > 50 mA [5] | T < 54.0 °C | D58E=550, D58C=5, D590=0 s, D592=540, D594=0 s | 0x64CE → 0x6506 | VS |
| 0x3D | 12 | charge under-temp: T < 0.0 °C and I > 50 mA [5] | T > 5.0 °C | D598=0, D596=5, D59A=0 s, D59C=50, D59E=0 s | 0x6585 → 0x65BD | VS |
| 0x46 | 15 | over-temp (any state): T > 76.0 °C | T < 60.0 °C | D5A0=760, D5A2=0 s, D5A4=600, D5A6=0 s | 0x663C → 0x665F | VS |
| 0x47 | 16 | under-temp (any state): T < -20.0 °C | T > -15.0 °C | D5A8=-200, D5AA=0 s, D5AC=-150, D5AE=0 s | 0x66DC → 0x66FD | VS |
| 0x50 | 17 | charge timeout: cumulative time with I > 50 mA [5] ≥ 360 min | discharge I < -100 mA [-10] for 1 s | D5B0=5, D5B2=360 min, D5B4=-10, D5B6=1 s | 0x6789 → 0x67D2 | VS |
| 0x51 | 18 | no setter in this firmware | — | — | — | VS |
| 0x5B | 20 | no setter in this firmware | — | — | — | VS |
| 0x5C | 21 | terminal over-voltage: terminal V ≥ 26000 mV with 0xFFB55.2 set, 5 consecutive cycles | 1800 < V < 26000 for 5 cycles, or V ≤ 1800 (unplugged) at once | imm 0x6590=26000 mV @0x85E5, D4F4=1800 mV, count 5 | 0x85BC → 0x8640 | VS (V identity VB) |
| 0xA3 | 35 | boot: config checksum 0xFFB02 ≠ word @0xD3FE | — | — | 0x9BE1 → 0x9BF6 | VS |
| 0xA4 | 36 | boot: byte-sum of 56 B @0xFF512 ≠ P00[7:0] (3 tries); data-flash param checksum | — | — | 0xADA3 → 0xADC6 | VS |
| 0xA5 | 37 | boot: signature @0xD400 ≠ "SV" | — | — | 0x9BFB → 0x9C13 | VS |
| 0xA6 | 38 | no setter (only tested at 0x6B6D) | — | — | — | VS |
| 0xA7 | 39 | boot/wake: 0xFFE97 ≠ 0, 0xFFE5C = 0, state 0xFFE96 ∈ {4,5} (meaning not traced) | — | — | 0x9CBE → 0x9CE1 | VS cond / meaning open |
| 0xB4 | 40 | measurement implausible: while a V fault is pending (bits 0,2,4,5,21,48,50,52), min < 0 or max > 5000 mV or terminal > 28000 mV for 1 s; sets 0xFFB50.1 (persisted in P17 bit 17), which disables V checks. Re-set every boot while that flag is on (0x6B72) | clear-all only | D5DE=0, D5E0=5000 mV, D5E2=1 s, D5E4=28000 mV | 0xB23F → 0xB295, 0x6B87 | VS |
| 0xB5/B6/B7 | 41-43 | no setter | — | — | — | VS |
| 0xB9/BA | 46-47 | no setter | — | — | — | VS |
| 0xC8 | 48 PF | cell OV PF: max cell > 4300 mV for 5 s | latched (P17) | D5C2=4300 mV, D5C4=5 s | 0x6820 → 0x683D | VS |
| 0xC9 | 49 PF | no setter; can only come back from P17 at boot | — | — | (0x83C7 restore) | VS |
| 0xCA | 50 PF | dead cell: min cell < 1000 mV for 5 s before any good reading since wake | latched | D5C6=1000 mV, D5C8=5 s | 0x6895 → 0x68B3 | VS (known) |
| 0xCC | 52 PF | imbalance: (charging I > 50 mA, max > 3700 mV, delta > 195 mV) or (rested 30 min and either 3615 < max ≤ 3785 with delta > 170 mV, or max > 3785 with delta > 200 mV), 20 s | latched | D5CA=5, D5CC=3700, D5CE=195, D5D0=3615, D5D2=3785, D5D4=170, D5D6=200 mV, D5D8=20 s | 0x68F9 / 0x695C → 0x69AD | VS |
| 0xDC | 55 PF | FET failure: charge FET off and I > 1 A [100], or discharge FET off and I < -1 A [-100], 20 s. Second path 0x8646: charger present + charge FET off, I > 100 mA [10], pack V rising > 8 mV/cycle, terminal−pack < 1250 mV for 80 cycles; or discharge FET off, I < -300 mA [-30], pack V falling < -40 mV/cycle for 400 cycles | latched | D5DA=100, D5DC=20 s, D500=10, D502=8, D504=-30, D506=-40 | 0x69E4/0x6A31 → 0x6A5F; 0x8646 → 0x872C | VS |

Not in the code table (no log code): bit 24 (set at 0x5733/0x84D3/0x8511/0x8536/0xAA1B, current-offset /
sleep path, cleared on low-power entry 0x5713), bit 5 (only in the 0xB4 pending mask). Codes 0x0B, 0x15, 0x1E, 0x3E, 0x3F,
0x5A, 0x5D, 0x5E have lifetime-counter slots @0x2312 but no producer in this firmware.

## Lifetime counts on this unit

| Code | Count | Reading |
|---|---|---|
| 0x5C | 122 | terminal ≥ 26.0 V while plugged in. Every time the charger sat at an open-circuit voltage above 26.0 V (charge request is 25.6 V). Repeated non-latching events; no damage implied. |
| 0x3C | 58 | charging above 55 °C (released < 54 °C). The pack was charged hot (after use, or the dock is warm). |
| 0x14 | 38 | cell under 2600 mV while not charging: the pack was run down to cutoff 38 times, or a weak cell hit it early. Consistent with the cell that later read 0 V. |
| 0x46 | 4 | over 76 °C. Heavy-use overheating, 4 times. |
| 0x16 | 1 | under 2500 mV with the terminal off: the same event as the 0xCA trip. |

## Notes for the cell install

- 0x14, 0x16 and 0x5C are not permanent. 0x16 has no self-release: it stays until reset or clear-all, but it is not persisted
  (bit 4 < 48), so the next reset clears it.
- 0xCC (imbalance PF) fires while charging when max cell > 3.70 V and delta > 195 mV for 20 s, or at rest when delta
  exceeds 170/200 mV. The firmware does not balance (see balancing.md). New cells must be matched within well under
  170 mV, ideally < 20 mV, before the first charge.
- 0xC8 trips at 4300 mV max cell for 5 s, not at the 4230 mV soft limit.
- Logging stops after the first PF bit (0x8420), so the logs show nothing after 0xCA.

## Open questions

- Current unit 10 mA is inferred (thresholds fork, IPScale). A known load would confirm it on the board.
- AFE reg 0x6A bit meanings (bit3 charge-side OC, bit2 discharge OC, bits 0-1 short circuit) are inferred from which release
  path each bit uses. Needs the RAJ240080 register map.
- 0xA7 condition (0xFFE97 / 0xFFE96 states 4-5) not traced to a physical meaning.
- 0xFFB55.2 = P13.7 low (debounced): assumed charger/MODE detect, not traced to a board net.
- Event log 0xF5 entries carry code 0x0A at the trip timestamp while the cells were collapsed. The 0xF5 writer (0x7C85)
  may use a separate event-ID namespace. Not checked.

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
    0xA7: "boot: wake-state check (0xFFE96 in 4/5)",
    0xB4: "measurement implausible (cell > 5 V / terminal > 28 V); disables V checks",
    0xC8: "PF: cell OV, max cell > 4300 mV 5 s",
    0xC9: "PF: no setter (only restored from P17)",
    0xCA: "PF: dead cell, min cell < 1000 mV for ~20 checks after wake (0x6890)",
    0xCC: "PF: cell imbalance, delta > 195 mV charging (> 170/200 mV at rest) 20 s",
    0xDC: "PF: FET failure, current with FET off (> 1 A) 20 s",
}
```
