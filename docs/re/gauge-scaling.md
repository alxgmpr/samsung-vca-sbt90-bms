# Gauge scaling, throughput counters, FCC learning

Static analysis of `firmware/codeflash.bin` / `code.dis`; values from `backups/df_20261007_221649.bin`.
Note for reading `code.dis`: objdump (plain rl78) prints the RL78-S3 multiply/divide
instructions as `mov 0xffffb, #n`: `#1` = MULHU (BCAX = AX*BC), `#2` = MULH (signed), `#3` = DIVHU
(AX = AX/DE), `#11` = DIVWU (BCAX = BCAX/HLDE).

## 1. Current unit: SBS 0x0A is in 10 mA units — verified-static

| Step | Address | What |
|---|---|---|
| Current measurement | 0xAB54 (event 39) | ADC (AFE CC, 250 ms conversion) -> 0x8F0B linear interpolation with cal points P0B hi (zero, 32776) / P0C lo (cal) -> deadband (±10 counts zeroed unless FB55.2) -> **FFE54** (signed). FFE58 = \|FFE54\|. SBS 0x0A reads FFE54 directly (0x4269). |
| Gauge integration | 0x95E0 (event 74) | `FFE54 * 10` (MULH, 0x95E7) passed as s32 to the gauge integrator **0x247F**, dt = 250 ms (0xFA) or 60 000 ms (0xEA60) when FB54.2 (sleep/slow-tick mode) is set. With I = 0 a fixed self-discharge value from 0xD478–0xD47B is used. |
| Charge per tick | 0x251A–0x2533 | FF9D4 = I · (dt/1000) / 3600.0 (float) — mAh, accumulated into FF922/FF926. |
| Capacity | | FCC (P19, SBS 0x10) and design 2850.0 (0xD960) are mAh. |

`ΔmAh = I_float · s / 3600` only works if `I_float` is mA, and `I_float = FFE54 · 10`, so one FFE54 count = 10 mA.
SBS AverageCurrent (0x0B, FFE56) = low-pass (τ 3.75 s, 0x2540) of `I_float`, divided by 10.0 (0x82AE): also 10 mA.
This matches IPScale ×10 in SpecificationInfo 0x1A = 0x1031.

The lifetime current extremes are in the same 10 mA units: P53 hi max charge current = 138 → 1.38 A; P54 lo max
discharge current = −3199 → −32.0 A.

## 2. Throughput / time counters — verified-static unless marked

FFE30 (u32, 0xB04F / 0xAC2E) = \|FFE54\| · 10 per 250 ms tick (or · 2400 per 60 s tick; 2400 = 10 · 240), so
one FFE30 unit = 1 mA · 250 ms = 1/14400 mAh. All throughput counters accumulate FFE30 (function 0x76AF,
called from event 41 via 0xAB50):

| Counter | Address | Condition | Rollover | Value → meaning |
|---|---|---|---|---|
| P5D lo | FF684 | I > 0 (0x7D53) | 0x00DBBA00 = 14 400 000 units = **1 Ah** (0x7783) | 991 → **991 Ah charged** |
| P5C hi | FF682 | I < 0 (FFE54 bit 15) | same, **1 Ah** | 504 → **504 Ah discharged** |
| P3D | FF604 (u32) | FFB71 set and I > 0 (0x7812) | 0x23280 = 144 000 units = **10 mAh** (0x782C) | 43620 → **436 Ah of re-charge after a full charge** |

The 0xDBBA00 compare is high word 219 = 0xDB, low word 0xBA00. P5D lo is charge-only (0x7769 `call 0x7D53; bc`).

**P3D logic (0x77E7–0x7812):** FFB72 mirrors the fully-charged flag (FFE9F.0, via callt [0xB4] = 0x81FB). On a
full → not-full transition FFB71 is set; it is cleared when FB55.2 drops (charger/terminal-present flag,
inferred from 0x8375) or the pack is full again. So P3D counts charge accepted after the pack dropped out of
"full" while still on the charger: top-up charging on the dock, in 10 mAh. It is saved every +100 counts (0x785F).
Meaning of FB55.2 = inferred.

**Hour counters (0x7ACE–0x7AF1, 0x7898):** a tick counter FFE92 wraps at 60 (0xD534), then FF6DC/DD/DE (P73 b0..b2)
count minutes, and P5B lo / P5B hi / P5C lo get +1 every 60 (0xD532) of those.
- P5B lo: always → powered hours (log timestamp).
- P5B hi: I < 0 → **discharging hours** (54).
- P5C lo: 0x7D55 no-carry = I > 0 → **charging hours** (2310). Settles the open question; it is not "idle".

Which event drives FFE92 (1 s or other) was not traced; "hours" relies on the existing ~1/h timestamp calibration.

**Event counters (dispatch 0x93B4; post-event = 0xB1B0):**
- n=3 (P50 hi, 6227) = **full-charge detections.** Event 23 is posted at 0x7F6A when 0x8259 holds for 0xD48C = 120
  ticks (30 s): max cell FFE68 ≥ FFB22 (= 4100 mV, 0xD488) and charge current ≤ 0xD48A = 10 counts (100 mA).
  The flag (FFE9F.0) clears when RSOC < 0xD4A0. The handler 0x954A then writes **event-log (0xF5) code 6** via
  callt [0xBC] (= 0xAA82) → 0x7C85.
  6227 full charges vs 387 cycles fits a vacuum that tops up on the dock (see P3D).
- n=4 (P51 lo, 38) = **fully-discharged entries.** Event 30 is posted at 0x7FBA when fault bit 2 (code 0x14, UV) is
  first set; it also sets FFE9F.1 and FF934.4. It equals the 0x14 lifetime fault counter (38). Event-log code 7 follows.
- Matches [events-boot.md](events-boot.md).

## 3. Gauge model: P18, P1A, the float tables — addresses verified-static, meanings partly inferred

RAM layout. The cell-model struct is at FF818 (182 B, pointer FF812):
- +0: 15 floats, P1B–P29.
- +60 (FF854): 8 floats, P2A–P31.
- +150 (FF8AE): Qmax, P18.

The gauge-state struct is at FF8CE:
- +0: SOC float.
- +10 (FF8D8): P1A.
- +22 (FF8E4): cycle count.
- +24: cycle-% accumulator.
- +32 (FF8EE): FCC, P19.

Seeding (0x7E01, runs at boot via 0x2472 and after 0x87 via 0x7F16, only when P32 lo != 0xBEEF):

| Param | Seed | Meaning |
|---|---|---|
| P18 | FF9F6 = parallel count (0xD982 = 1) · **3195.0 mAh** (float @0xD98C), 0x7D9A | **Qmax**: chemical capacity per cell group, mAh. Now 2924 (91.5 % of 3195). SBS 0xA3 = int(P18); SOC = remaining·100/P18 (0x8200). verified-static |
| P19 | 2850.0 (0xD960) | FCC, mAh. Learned value is **clamped to ≤ 2850** (0x3725/0x36E0) |
| P1A | 0xA32F(table 1→0, 4160.0 mV) | OCV→SOC interpolation of 4160 mV (0xD96E, charge-termination cell OCV) through the 32-point OCV table. Seed ≈ 99.2 %; now 98.67 %. **SOC at end of charge, %** (mechanism verified-static, name inferred) |
| P1B–P29 | 15 floats @0xD904 (0.399 → 0.018) | Learned per-cell **resistance (Ω) vs SOC**, on the 15-point SOC grid @0xD7B0 (0,4,8,…,100 %). Only P24, P25, P27 and P28 moved (+2–4 %). Inferred from shape, units and grid length |
| P2A–P31 | 8 floats @0xD940 (0.044–0.046) | Second learned **resistance table (Ω)** on the 8-point SOC grid @0xD7EC (10,20,30,50,70,80,90,96 %). Learned values are far above the defaults at high SOC: P30 0.117 vs 0.035, P31 0.179 vs 0.046. That fits aged cells. Inferred |
| P38 hi | 0 (0xDAE2) | Cycle count (387 now) is **also reset by a reseed** |

ROM table registry (copied to RAM FF800 at startup from 0xB9B4; lengths at 0x234E):

| id | addr | n | contents |
|---|---|---|---|
| 0 | 0xD630 | 32 | SOC % axis |
| 1 | 0xD6B0 | 32 | OCV mV per cell, 2729.6 … 4175.0 |
| 2 | 0xD7B0 | 15 | SOC % axis |
| 3 | 0xD810 | 15 | ROM R table, Ω |
| 4 | 0xD84C | 15 | ROM R table, Ω |
| 5 | 0xD7EC | 8 | SOC % axis |
| 6 | 0xD8C4 | 8 | ROM R table, Ω |
| 7 | 0xD8E4 | 8 | ROM R table, Ω |

Tables 3/4 and 6/7 are probably temperature or direction variants (inferred).

## 4. FCC learning (0x3610–0x371D) — verified-static, flag meanings inferred

- **Every tick:** FF926 += ΔmAh (signed net charge since the last anchor, 0x3703).
- **Learning end-points:**
  - (a) a charge-end/relax flag (FF934.7, FF935.0 or FF936.0) with SOC (FF8CE) ≥ 70 %;
  - (b) the discharge-end state (FF934 bits 6:5 = 10, or FF936.0) with SOC < 26 % (0x41D0).
- At an end-point, if \|SOC − SOC_anchor (FF8F2)\| ≥ **40 %** (0x4220): FCC_new = \|FF926\| · 100 / ΔSOC. FCC is then
  low-pass blended toward FCC_new by 0x3CAC (gain from 0x277D, not decoded) and clamped to 2850.
- The anchor (FF8F2) is moved to the current SOC and FF926 cleared at every end-point, qualifying or not.
- So FCC only moves on a ≥40 % SOC span that ends at full (≥70 %) or near empty (<26 %), e.g. a charge from below
  30 % to full, or a discharge from full to below 26 %. Short dock top-ups never update it. Each update is filtered,
  so convergence takes several such cycles.

### Recommendation for the cell swap

Reseed the gauge after the new cells are in and `status` shows PF clear. Otherwise:
- FCC stays at the old cells' 2390 mAh and only creeps toward the real value after several deep cycles.
- The aged P2A–P31 resistance table (up to 4× the defaults at high SOC) skews SOC under load.

Use the surgical reseed (needs the 0x7A unlock, [../protocol.md](../protocol.md); README install step 7,
pending approval):

1. **Surgical.** Clear only the 0xBEEF marker, then let the firmware reseed:
   - `bms.py backup`
   - `ww(0x7A, 0x835A)`
   - `wb(0x84, [0xC8, 0x00])`, the P32 offset (0xC8 = 0x32·4)
   - `wb(0x8A, b'\x00\x00\x0c\x53')`, which writes P32 = 0x530C0000 (model length/'S' bytes unchanged)
   - wait 2 s, `ww(0x7A, 0)`, reset

   Expected: P18 = 3195.0, P19 = 2850.0, P1A ≈ 99.2, P1B–P31 = ROM defaults, P38 hi (cycle count) = 0, P32 lo = 0xBEEF
   again. P3A–P3D and all lifetime/log params are untouched.
   Undo: write the old P18–P39 values from the backup with `set-param`.
   Caveat: whether 0x8A writes take effect only after the persist path, or whether 0x7E01 also runs without a
   reset, was not checked. Read P32 after the write and after the reset.
2. **Not 0x87 mode 3.** It does the same reseed, but every 0x87 mode also runs clear-all 0xAA55 → 0x7547, which
   zeroes P17, P3A–P3D, P39 and all of P3F–P9D (lifetime counters, histograms, snapshots, both logs;
   [events-boot.md](events-boot.md)).

Either way FCC caps at 2850 mAh even if the new cells hold more. That is a reporting limit, not a protection limit.

## Open questions
- FB54.2 (60 s tick) and FB55.2 (charger/terminal present): the setters were not traced.
- The 0x277D gain (FCC learning rate) and the exact meaning of the FF934/FF935/FF936 end-point flags.
- Which of the ROM R tables (ids 3/4, 6/7) feed the learned tables, and on what axis (temperature or direction).
- The tick source of FFE92 (hour counters).

## Param names

The param facts above are merged into the `PARAM_NAMES` dict in [param-names.md](param-names.md) and `bms.py`.
