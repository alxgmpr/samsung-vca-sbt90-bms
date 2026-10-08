# Cell balancing — VCA-SBT90 firmware

## Answer

The firmware does no cell balancing. No code path writes a per-cell mask derived from cell
voltages to the AFE or to a port pin. Confidence: **verified-static**. The AFE does have per-cell
balance switches (data-sheet "conditioning circuit", COND register), but the firmware never writes
them ([afe-map.md](afe-map.md) §4). A live read can't show the absence of a code path, so this was
not checked on the board.

## Evidence

### 1. Every AFE access goes through two routines, and every write is enumerated

- Write `0x4E53` (callt [0x8A], A=reg, X=val): sends a 3-byte frame `[0xA1][reg][val]` over the
  internal serial unit (SDR 0xFFF4A, CS = P7.3). If reg == 0x4C it also stores val in shadow 0xFFEB3.
- Read `0x4EBB` (callt [0x8E], A=reg, X=count, BC=dest): frame starts `[reg|0x40]`.
- Transport helpers 0x4E39/0x4E46/0x4F3D/0x4F48/0x4F51/0x4F5A/0x4F71 are called only from these two.
  The other users of SDR 0xFFF4A are the bootloader (0xDE60/0xDECC) and an unreferenced copy of the
  write routine at 0x1130 (no `call`/`br`/callt/data reference to 0x1130 anywhere in the image).
- No `call !0x4E53`/`!0x4EBB` exists. The only other entry is `br !0x4EBB` at 0x2278 (a read).

That makes the 143 `callt [0x8A]` sites the complete AFE write set. The table lists every register
they write and where each value comes from. Roles are from [afe-map.md](afe-map.md) where it
decodes them, otherwise inferred from usage:

| AFE reg | Values written | Value source | Writer(s) | Role |
|---|---|---|---|---|
| 0x02, 0x03, 0x0D | 0 | const | 0x51D3, 0x5162/0x5D65, 0x51BE | 0x02 = VBSE (analog output select); ADC/CC stop/clear |
| 0x04 | 0 or 4 | bit 0xFFE8D.1 / 0xFFE8E.1 / 0xFB54.1 | 0x56DD | mode bit (FCON/AFECON candidate, inferred) |
| 0x05 | 0x8A | const, read back and rewritten if changed (0x5A30) | 0x5905/0x5A4B | config |
| 0x07 | 9 | const | 0x5D7A | config |
| 0x0E | 1 | const, read back (0x5A15) | 0x5921/0x5A29 | config |
| 0x11 | 2, 5, 7, 0 (sequence) | const | 0x5DDC..0x5DED | wake / start sequence |
| 0x13–0x1A | per-unit trims | code flash 0xDC60–0xDC67 via table 0x239C (masked) | 0x58DA, 0x59E5 | factory trim, re-checked periodically by 0x59A5 |
| 0x1B | 0x2F | const, read back (0x5A58) | 0x5911/0x5A6D | config |
| 0x20, 0x23 | 1/2/4/0x80 then 0 | const | around each protected write | write-enable key for the trim/config regs |
| 0x30 | 0x81 / 0 | const | 0x5192, 0x51AE | ADC conversion start/stop |
| 0x31 | channel byte | table 0x235C indexed by ADC state 0xFFEB0 (0x15, 0x14, 0x43, 0x54, 0x52, 0x6F, 0x6E, 0x17, 0x1C, 0x18, …) | 0x514B, 0x519C | ADC channel mux (results to 0xFB26…) |
| 0x4C | shadow OR/AND bit 1/2/4/0x20 | helpers 0x4F83 (set) / 0x4F8B (clear) | 0x516E, 0x51C2, 0x51FE, 0x521A, 0x5C38, 0x5D97 | AFE interrupt enable |
| 0x4D | 0 | const | 0x5AF6 | int enable 2 |
| 0x4E | ~bit | helper 0x4F92 (write-1-to-clear) | ISR 0x527B / 0x52C5 etc. | AFE interrupt flags |
| 0x4F | 0 / 0xEF | const | 0x593A, 0x52B1 | int flags 2 |
| 0x50, 0x51 | 6, 0 | const | 0x51B4, 0x51B9 | ADCON / ADCON1 |
| 0x58 | 0x40, 0xC0, 0 | const | 0x5208/0x520E, 0x5216 | coulomb-counter control (0x40 enable, 0xC0 enable + start) |
| 0x60–0x65 | `00 E2 E6 E0 10 F9` | code flash 0xD4AA–0xD4AF | 0x540C–0x5461, 0x594E–0x5998 | hardware OC/short-circuit detector configuration |
| 0x66–0x69, 0x6B, 0x6D | search result / const | DAC successive approximation 0x5B5B / 0x5C75, results 0xFFEB1/0xFFEB2 | 0x5B5B–0x5D52 | wake-current comparator levels/control, detector restarts, write enables |
| 0x6C | 1<<n (n=0..7), then 0 | const | 0x540A–0x545A, 0x5944–0x599D, 0x5C3E | write enable: bit n unlocks reg 0x60+n |
| 0x70, 0x7D | 0 | const | 0x53B3, 0x52AB/0x593F | — |
| 0x78, 0x79 | 0/1, 7 | const | 0x5DA0–0x5DAB | — |

The only register that ever sees a 1<<n pattern is **0x6C**. It gets the fixed sequence 1, 2, 4,
8, 16, 32 (then 0x40, 0x80), each followed by a constant write to 0x60+n from 0xD4AA+n, and is
written back to 0 at the end (0x599D, 0x5466 via 0x5C63). That is a write-enable walk over the
protected registers, independent of cell voltage. No register receives a voltage-derived cell mask.

### 2. No GPIO balancing either
Port writes are full-byte inits from shadows 0xFFEA3–0xFFEAE / 0xFFB76–0xFFB7E (0x55DB–0x56A9),
plus these bit-level writers:
- P5.2/P5.3/P5.4 (0x558D–0x55BD): 3 bits from 0xFFB60/0xFFE35, blink toggle 0xFFB80 = the 3 LEDs.
- P5.0 (0x50F6/0x510C): set/cleared from the ADC state machine 0xFFEB0.
- P1 shadow 0xFFEA5: bit 1 = fuse drive (P1.1), bits 2/6 = FET enables (inferred, [afe-map.md](afe-map.md) §3).
  Bit 6 is cleared when fault test 0x5ED4 returns bit 2 or 4 (0x55F9–0x561F).
- P7.3 = AFE chip select, P7.6 = strobe (0x5D82/0x11A4).

Nothing drives 6 per-cell outputs.

### 3. No balance thresholds
There are no xrefs that compare individual cells against min/max + delta and emit a mask. The
uses of min cell 0xFFA34 / max cell 0xFFA36 / 0xFFA3C are fault checks: 0x6890 (dead cell),
0x60CA (code 0x16), and 0xB25E, which compares min ≥ 0xD5DE, max ≤ 0xD5E0 and 0xFFA3C ≥ 0xD5E4
for 0xD5E2×4 ticks and then sets a fault bit through 0x5EF6 (see [protection.md](protection.md)).
None of these touch the AFE.

## Effect on the cell-install procedure
- The pack never balances itself. Whatever imbalance the cells start with stays, and it grows
  with cycling. Match the 6 cells to within ~10–20 mV at the same SoC (top-charge each to 4.20 V
  individually, or parallel them for a few hours) **before** spot-welding.
- Imbalance latches a PF (0xCC: spread > 195 mV while charging with max cell > 3700 mV, or
  > 170/200 mV at rest, for 20 s; [protection.md](protection.md)).
- After each of the first few charges, run `uv run bms.py status` and check `spread`. If spread
  creeps past ~50 mV at full charge, rebalance by hand through the taps.
- The original failure (cell 3 at 0 V, two more collapsed to ~1.17 V) fits a pack with no
  balancing, where the weakest cell gets driven down every cycle.
- ChargingVoltage reads 25600 mV = 4.267 V/cell average. With no balancing, a high cell can sit
  above that at end of charge. The per-cell limits are cell OV 0x0A (> 4230 mV, 3 s) and PF 0xC8
  (> 4300 mV, 5 s). Check cell max at the end of the first charge.

## Open questions
- The COND register address isn't in the data sheet, so the AFE balance switches can't be driven
  without it (and no SBS command writes arbitrary AFE registers). Balance current on the RAJ240080
  is unspecified; on the RAJ240100 it is ~10–40 mA, too small to fix a mismatched pack anyway.
- Whether the PCB populates bleed resistors on the AFE cell inputs is a board-inspection
  question. Irrelevant while the firmware never enables them.
- Unreferenced AFE write copy at 0x1130 (library leftover or function-pointer target?). No data
  word 0x1130 exists in the image, so treat it as dead.
