# AFE register map

Sources: `~/Downloads/RAJ240080.PDF` (data sheet R01DS0299EJ0100, 73 pp), `firmware/code.dis`, and a live
RAM read through the gated SBS read ([../protocol.md](../protocol.md); `_board_log.md`, 05:31:07Z).

## Data-sheet coverage

- The data sheet is not a user's manual. It gives AFE addresses for only three registers:
  **ADCON 0x50**, **ADCON1 0x51** and **VBSE 0x02**. Everything else (FCON, AFECON2/3, COND, the
  OC registers, INTIR) appears by name and bit field only, with no address. The register map for
  0x60–0x6D below comes from the firmware's access pattern matched to those field names.
- **Part mismatch:** the RAJ240080 is specified for **2–5 series cells** (VIN1–VIN5 only, p.1,
  pin table). This board is 6S (taps B-, B1–B5, B+), and the firmware handles 6 cells. The marking
  in `images/board-front.jpg` reads "240080". How cell 6 is measured, and whether the die is a
  6-cell variant, is open. The RAJ240090/100 (3–8 / 3–10S) data sheet is a different AFE and has no
  register addresses either.
- No user's manual for the RAJ2400x0 family turned up in a web search (Renesas site, Mouser,
  datasheetarchive).

## Register map as used by this firmware

| AFE reg | Written / read | Meaning | Confidence | Evidence |
|---|---|---|---|---|
| 0x02 | write 0 (0x51D3) | **VBSE**: analog output select; bits 3:0 = 1101 records the bootloader's 10-min SMBus timeout. The firmware clears it | verified-static (data sheet address) | DS p.40 |
| 0x50 / 0x51 | write 6 / 0 (0x51B4/0x51B9) | **ADCON** = 6: channel AO (battery-voltage output), ADST/ADSLP off. **ADCON1** = 0: 1 ms conversion time | verified-static | DS p.38–39 |
| 0x30 / 0x31 | 0x81/0, channel table @0x235C | ADC automatic-mode control and channel sequence. Field layout not in the DS | inferred | DS p.36 mentions "ADC automatic mode control register" |
| **0x58** | read; write 0x40, 0xC0 (0x51E3–0x520E); write 0 (0x5213) | **Current-integration (coulomb counter) control.** 0x40 = enable, 0xC0 = enable + start/reset. Not FET drive. The paired interrupt is 0x4C bit 2 | verified-static (role); bit names inferred | 0x5240 reads 3 bytes from 0x59 = CCRH/M/L (DS: 18-bit, 250 ms/conversion, ±0.1 V input) |
| 0x59–0x5B | read 3 bytes (0x5240) | Current integration result H/M/L, 18-bit | verified-static | as above |
| 0x4C | shadow 0xFFEB3, set/clear bits 1/2/4/0x20 | AFE interrupt enable. bit 2 = current integration (set with the 0x58 start); bit 5 (0x20) = wake-current interrupt, set only after wake-comparator calibration (0x5C38) | verified-static | **live 0xFFEB3 = 0x15** (bits 0, 2, 4) |
| 0x4E | write-1-to-clear | AFE interrupt flags | verified-static | (balancing.md) |
| 0x60–0x65 | **00 E2 E6 E0 10 F9** from code flash 0xD4AA–0xD4AF, at boot (0x540A) and periodic re-check (0x594E) | **Overcurrent / short-circuit detector configuration** (BCDCON/SCDCON/DOCDCON/COCDCON plus the CMP/ITIM fields). The per-field split is unknown | role: inferred-strong; values verified-static | each write is preceded by the 0x6C write-enable bit for that register (below). The detectors' flags/restarts in 0x6A/0x6B prove they are enabled |
| 0x66 | calibrated code 0xFFEB1 | **WUCMP[6:0]**: discharge wake-current comparator level, 0..116 = −145..+145 mV in 2.5 mV steps | verified-static | 0x5B5B: steps 0→116 until 0x6A.4 stops tripping, +4 codes, clamp 116. DS: wakeup range −145..145 mV, 2.5 mV |
| 0x67 | 1 → 0x81 (calibrate), 0x80, 0xC0 | discharge wake-current control (bit 7 = enable; 0x01/0x40 = calibrate/run mode) | inferred | 0x5B5B/0x5C07 |
| 0x68 | calibrated code 0xFFEB2 | **CWUCMP[6:0]**: charge wake-current comparator level | verified-static | 0x5C75: steps 116→0 until 0x6A.5 stops tripping, −4 codes |
| 0x69 | 0x80, 0xC0, 0 | charge wake-current control | inferred | 0x5C75/0x5D2A |
| **0x6A** | read | **Detection flags**: b0 BCDFLG (discharge short-circuit 1), b1 SCDFLG (discharge short-circuit 2), b2 DOCDFLG (discharge OC), b3 COCDFLG (charge OC), b4 WUDFLG, b5 CWUDFLG | verified-static | the wake searches poll b4 and b5. 0x5A8B treats b0–2 as the discharge group (restart 7) and b3 alone (restart 8), the same order as the DS figure 4-10 BC/SC/DOC/COC/WU/CWU/TB |
| 0x6B | 7, 8, 0x10, 0x20 | **Restart bits**, same bit order as 0x6A: 7 = restart BC+SC+DOC, 8 = restart COC, 0x10/0x20 = restart wake comparators | verified-static | 0x5A9F, 0x5AB8, 0x5B96, 0x5CAE |
| 0x6C | 1<<n before writing 0x60+n (n = 0..7), then 0 | **Write enable for the protected registers 0x60–0x67** (bit n ↔ reg 0x60+n). Not a cell select and not balance switches | verified-static | 0x540A–0x5466: 0x6C=1 → 0x60, 2 → 0x61 … 0x20 → 0x65. 0x5C43 0x6C=0x40 → 0x66. 0x5C6D 0x6C=0x80 → 0x67 |
| 0x6D | 1, 2, 4 before 0x68, 0x69, 0x6A/0x6B, then 0 | Write enable for 0x68–0x6B | verified-static | 0x5D18 (1 → 0x68), 0x5D1F (2 → 0x69), 0x5C4B (4 → 0x6B) |
| 0x04 | 0 or 4 (0x56DD), after 0x20=1 key | Mode bit from 0xFFE8D.1 / 0xFFE8E.1. Candidate for FCON or AFECON, unconfirmed | inferred | — |
| 0x05/0x07/0x0E/0x11/0x13–0x1B/0x20/0x23/0x70/0x78/0x79/0x7D | constants / trims | see balancing.md table; 0x20/0x23 are the write keys for the trim block | as balancing.md | — |

Codes 0x29/0x33/0x34 are confirmed: **0x29 = 0x6A b3 charge OC (COC)**, **0x33 = b2 discharge OC (DOC)**,
**0x34 = b1:0 discharge short-circuit 2/1**. Hardware confirmation of the polarity would need a trip.

## 1. Hardware OC/SC trip levels and delays

Not resolved to absolute numbers. The firmware programs all four detectors in one shot from the
constants **0xD4AA–0xD4AF = 00 E2 E6 E0 10 F9**, and the data sheet gives the ranges but no field
layout:

| Detector | Level range (step) | Delay range (step) |
|---|---|---|
| Discharge short-circuit 1 (BC) | 0.1–0.8 V (0.1 V), BCCMP[2:0] | 0–427 µs (61 µs), BCITIM[2:0] |
| Discharge short-circuit 2 (SC) | 25–100 mV (12.5) / 100–250 mV (25), SCCMP[4:0] | 0–915 µs (61 µs), SCITIM[3:0] |
| Discharge OC (DOC) | 25–50 mV (2.5) / 50–100 mV (5), DOCCMP[5:0] | 0.916–30.2 ms (1.95 ms), DOCITIM[3:0] |
| Charge OC (COC) | −25…−100 mV (12.5) / −100…−250 mV (25), COCCMP[3:0] | 0–915 µs (61 µs), COCITIM[3:0] |

What can be inferred from the bytes (**inferred, low confidence**): 0x61/0x62/0x63 = E2/E6/E0 share
the top three bits 111. That fits per-detector `EN | FETEN | INTEN` with a 5-bit field below, which
would make SC, DOC and COC enabled with automatic FET-off, and 0x60 = 0 (BC, the 0.1–0.8 V detector)
disabled. 0x64/0x65 = 0x10/0xF9 would then hold the remaining level/time fields. Not decoded.

**Current per mV of sense voltage** depends on SR1/SR2 (2 × 1 mΩ, the "L01" parts next to CN1):
- 0.5 mΩ (parallel): 25 mV = 50 A, 100 mV = 200 A.
- 2 mΩ (series): 25 mV = 12.5 A, 100 mV = 50 A.

The lowest DOC setting at 2 mΩ (12.5 A) is below the firmware's own −40 A software limit (code 0x32)
and would trip the vacuum motor. That makes **0.5 mΩ (parallel) the likely topology** (inferred).
Metering SR1‖SR2 (or decoding the current-cal gain in P00–P0E) settles it.

## 2. Reg 0x6A bits

See the map: b0/b1 short circuit, b2 DOC, b3 COC, b4/b5 wake. Used by codes 0x29/0x33/0x34 in
[protection.md](protection.md). Verified-static.

## 3. Reg 0x58, reg 0x4C, fuse drive

- **0x58 is the coulomb-counter control** (see the map), not FET drive.
- **0x4C** = interrupt enable. Live shadow 0xFFEB3 = 0x15: bit 2 (current integration) is on, bit 5
  (wake current) is off while awake.
- **Fuse: the MCU drives it from port P1.1, not the AFE FUSEOUT pin.**
  - 0x8769–0x8783: if any PF bit is set (0x5ED4 mask 0x7FFF<<48) **and word 0xFF552 ≠ 0**, set 0xFFE34.0.
  - 0x5AC9 copies 0xFFE34.0 to the P1 shadow 0xFFEA5.1, and 0x57F4 writes the shadow to P1 (0xFFF01).
  - Nothing clears 0xFFE34.0 except RAM init at reset. This matches the bench: Q10 gate at 3.3 V
    (MCU logic level, while the DS gives FUSEOUT high = VCC − 0.5 V ≈ 21 V) until the P17 clear
    plus a reset.
  - 0xFF552 is the high half of P10, **ManufactureDate (SBS 0x1B)**, now 0x5239. **Fuse blowing is
    armed only while ManufactureDate ≠ 0.** Verified-static.
  - The AFE FUSECUT/FUSEMON path is never written (no AFE write carries the 11b fuse-cut pattern), so
    it is unused (inferred).
  - 0x3FF1: drives P1.1 high for 15 ticks, then checks input P1.3. If P1.3 isn't high, it logs
    0xFFB84 = 16; it then drives P1.1 low for 5 ticks, and if P1.3 is still high it logs 17. This
    reads like the fuse-drive self-test with P1.3 as the Q10/fuse sense. The counter is 0xFFEB7, armed
    (= 2) only at 0x47F8 in the gated SBS 0x80 handler, so it never runs at boot. The pulse is
    15 × ~131-iteration busy loops (0x5D55), well under a millisecond. Role inferred.
  - P1 direction (PM1 shadow 0xFFEA6 = 0x19): P1.0/3/4 inputs, P1.1/2/5/6/7 outputs. P1.2 and P1.6 are
    set together (`or 0xffea5,#0x44`, 0x5519) when 0x6ADC (no PF and no FET-off fault) returns 1,
    so they are the FET enables (inferred). Live P1 shadow = 0x04 (P1.2 on, P1.1 off, P1.6 off).
  - The PF test at 0x83E4 also posts event 19 (0xB1B0); see [events-boot.md](events-boot.md).

## 4. Hardware balancing

- **The AFE has balancing hardware**: the data-sheet "conditioning circuit" (4.6.11). COND register
  bits CDRON0–4 switch a MOS discharge path across each cell (5 cells on this part). The switches
  exist, but they only act when the MCU sets them.
- **The firmware never uses it.** No AFE write in the 143-site set carries a voltage-derived cell
  mask. 0x6C, the only register that sees 1<<n, is the write enable for 0x60–0x67 (shown above). The
  firmware does no balancing ([balancing.md](balancing.md)). Verified-static.
- **Enabling it needs either new firmware or a raw AFE write path.** The COND address is not in the
  data sheet, and no SBS command writes an arbitrary AFE register (the unlocked 0x80 test modes
  only touch FET requests, reset, ship mode and current cal; [events-boot.md](events-boot.md)).
- The balance current isn't specified for the RAJ240080. The RAJ240100 lists 100–400 Ω on-resistance
  per cell (≈ 10–40 mA at 4 V); if the 080 is similar, that is too small to fix a mismatched pack
  anyway. Hand-match the cells (README procedure).

## Live values (gated RAM read, 2026-10-08 05:31Z, firmware running, PF clear)

| RAM | Value | Meaning |
|---|---|---|
| 0xFFEB0 | 0x0A | ADC sequencer state |
| 0xFFEB1 | 0x36 (54) | discharge wake threshold code: zero-current offset ≈ code 50, +4 codes (+10 mV at the comparator input; gain mode unknown) |
| 0xFFEB2 | 0x2C (44) | charge wake threshold code: offset ≈ code 48, −4 codes |
| 0xFFEB3 | 0x15 | AFE reg 0x4C shadow (int enables bits 0, 2, 4) |
| 0xFFEA5 / 0xFFEA6 | 0x04 / 0x19 | P1 output shadow / PM1 |

## Open questions

1. Field layout of 0x60–0x65 (00 E2 E6 E0 10 F9) gives the absolute OC/SC levels and delays. Needs the
   RAJ2400x0 user's manual (hardware), or a controlled overcurrent trip test.
2. Whether SR1/SR2 are parallel (0.5 mΩ) or series (2 mΩ). Meter it, or derive it from the current
   cal in P00–P0E ([param-names.md](param-names.md)).
3. How a 5-cell AFE measures cell 6, and whether U1 is really a 5-cell part.
4. Which AFE register is FCON (FET on/off) and which is AFECON2. Reg 0x04 is a candidate. If the
   external P1.2/P1.6 drive the FETs, the AFE FET drivers may be unused.
5. P1.3 net (fuse sense?) and P1.4 (charger detect at 0x56EB).
