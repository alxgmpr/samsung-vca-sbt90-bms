# Protocol: SMBus bootloader, data flash, SBS commands and unlock

Current facts only. Wiring and pads: [hardware.md](hardware.md). Param meanings:
[re/param-names.md](re/param-names.md). Protection logic: [re/protection.md](re/protection.md).
Confidence tags: verified-static (from `firmware/code.dis`), verified-on-board, inferred.

## 1. SMBus bootloader

**Entry:** hold TOOL0 (TP32) low across a pin reset (TP33) or power-up. The normal firmware does not
run; a flash bootloader (code 0xDC00+) answers at 0x0B instead. Leave with `[0x00][count][0xD0][PEC]`
or a reset with TOOL0 released. Use SoftI2C, 20–50 kHz. Each bootloader session resets the board, and
firmware SBS readings are meaningless for ~2 s after leaving. Verified-on-board.

**Slave ISR** 0xEC25: state 0xFF4E9, command 0xFF4E8, buffer 0xF3E0, count 0xFF4EB, exec length 0xFF4EC,
running PEC 0xFF514 (= SMBus PEC, CRC-8 poly 0x07 init 0, over `[0x16, cmd, count, payload]`), exec flag
0xFF513 (cleared by a bad PEC). Commands execute at STOP via dispatch 0xE445 (cmd − 0xFA jump table for
0xFA–0xFD). Reads reply block-style `[count][data][PEC]` (state 5, 0xEF81). Verified-static.

| Cmd | Framing | Action | Notes |
|---|---|---|---|
| 0xFC | write `[FC a0 a1 a2 n0 n1]` **no STOP**, then read n bytes | memory read, any address | 64-byte reads at 50 kHz reliable; single reads sometimes return walking-bit junk, so read twice and treat 6–7× all-FF as genuine blank (`dfw.rd_ok`). Verified-on-board |
| 0xFB | `[FB][3+n][a0 a1 a2][n data][PEC]` | **data-flash write** (PFDL cmd 4) at STOP | exec check 0xE445→0xE59D→0xE6AC: 0xF1000 ≤ addr, addr+n ≤ 0xF2000, n ≤ 160. Program path 0xE7CD → 0xE7E3 (request block @0xFF508: index = addr & 0xFFFF, src 0xF3E3, len). Verified-on-board |
| 0x70 | read | last PFDL result (0xFF4E7): 0 OK, 0x1B not blank, 0xFF busy | verified-on-board |
| 0x24 | `[24][5][a0 a1 a2][len lo hi][PEC]` | PFDL blank check (cmd 8), read-only | result via 0x26 |
| 0x26 | read | blank-check result (0xFF4E6): 0xFF blank, 0x00 not blank, 0xCA error | verified-on-board |
| 0x21 | `[21][1][blk][PEC]` | data-flash 1 KB block **erase** (blk 0..3, PFDL cmd 3) | not used |
| 0x20, 0x27 `[b0 b1]`, 0x25 `[b]` | block-write style | code-flash block ops | guards exclude blocks 0x37–0x3E (the bootloader). Not used |
| 0xFD | `[FD][addr3][len2][data…]` (no count byte) | code-flash write; bounds ≤ ~0xDBFF plus a 0x0F0000–0x0F0FFF window | 0xE82F word write. Not a data-flash path |
| 0xFA | block-write style | flash → buffer read | |
| 0x00 | `[00][1][D0][PEC]` | leave bootloader, run the app | |
| 0x55, 0x59, 0x7C, 0xF0 | read | status/handshake reads. 0x55 is not a mode switch; no mode is needed for writes | |

Bootloader privileged-op key tables (pointers 0xDD0E/0xDD22) read all-zero on this unit; no key was
needed for any command above.

## 2. Data flash (EEPROM emulation)

- 0xF1000–0xF1FFF = two 2 KB EEL blocks, 0xF1000 and 0xF1800. The **active block** is the non-FF one
  (`bms.py active_block`: first 16 bytes not all FF). Footer bytes `5A A5 5A` near the end of the image.
- Records start at block offset +4: `[idx][~idx][u32 LE]`, 6 bytes, appended in order. **Newest record
  per index wins.** 158 params, P00–P9D, mirrored in RAM at **0xFF510 + 4·idx** (one packed 632-byte
  struct; many params hold two u16 fields).
- Firmware writer: 0x6FE0 marks a param dirty, the main loop (0xFFE97 → 0x7031) appends records; block
  switch at 338 records (the copy of the live set to the other block and erase of the old one is inferred). Resets
  often trigger a rotation, so detect the active block every session. Verified-static, rotation seen on board.
- **Appending a record from the bootloader** (`bms.py set-param`, `pico/pf_append.py`): snapshot the
  image, find the first all-FF 6-byte slot after the last valid record in the active block (require
  64 bytes of FF after it), 0xFB-write the record (SoftI2C doesn't report a data NAK, so `dfw.wr` verifies by read-back and retries while the slot is still blank; a first try not being accepted is normal), re-snapshot, require the diff to be exactly those 6
  bytes. Verified-on-board (several times).
- **PF clear:** P17[15:0] = persisted fault-mask bits 48..63 (0xAB10 saves it, 0x839D restores it at
  boot); P17[31:16] = persisted protection-disable mask (0xFFB50). This unit had P17 = 4 (bit 50, code
  0xCA). Cleared 2026-10-07 by appending `17 E8 00 00 00 00`. Undo would be `17 E8 04 00 00 00`.
  Pre-write image: `firmware/df_pre_pfclear.hex`. Verified-on-board.
- Safe scratch proof: 0xA5 written to 0xF1C00 in the spare block, diff = that byte only (`pico/experiments/proofFB.py`).

## 3. SBS command table (@0x2008)

6-byte entries `[cmd][flags][fn1 u16][fn2 u16]`, ending with cmd 0xFF at 0x22B4; lookup 0xB842.
Verified-static.
- flags: bit7 block, bit6 writable, bit5 readable, bits4..0 = length − 1.
- fn1 runs at the start of a read (fills reply buffer 0xFFA0A) **and** as the write validator once all
  data bytes arrive (0x8B4E); returning 0 aborts the write. Gated commands check the unlock here.
- fn2 is the write executor, run at STOP (0x8940). 0x8962 then stores cmd/flags in 0xFFE48/0xFFE49 and the
  written word in 0xFFE4A.
- PEC optional: if a trailing byte is sent it must be the correct PEC or the transaction is dropped
  (0x8B37–0x8B41). Block count must be < 33 (SBS ISR 0x8A9E–0x8B5F).
- `callt [0xAA]` (0xB3B9) = received word; `callt [0x9C]` = load reply word; `callt [0xA8]` (0xB3E4) copies
  block data and, with e = 1, marks each byte's param dirty (`callt [0xB0]` = 0x6FE0).
- Vendor block sources: table at 0x1F3A + 4·cmd maps SBS 0xE2–0xF5 and 0xFB onto P3A–P9D
  ([re/param-names.md](re/param-names.md)). SBS 0xEB is a copy of code flash 0xD518 (histogram bin
  edges), not protection thresholds (verified-on-board, byte-identical).

## 4. SBS unlock and gated commands

**Unlock = `WriteWord(0x7A, 0x835A)`**, no key or sequence. 0x7A reads back RAM word 0xFFE80. Write
any other value to re-lock (0x45BB: also clears the 0x80 test modes via 0x405D(0), restores 0xFFB65,
clears 0xFFA5C). A reset clears it (0xFFE80 = 0 after reset). There is no unlock timeout, and nothing
else re-locks: the 0x3FE8 re-lock hangs off dispatcher event 6, which is never posted. Verified-on-board
(unlock, re-lock, cleared by reset); rest verified-static. Gated validators call 0x48DE
(`cmpw 0xFFE80, #0x835A`).

| Cmd | Read | Write (unlocked) |
|---|---|---|
| 0x82 | 3 bytes @0xFFAFA (pointer) | block: set the 16-bit near memory pointer 0xFFAFA. Verified-on-board |
| 0x83 | word @[0xFFAFA] (DFLEN on, data flash readable). Verified-on-board | RAM byte poke. Not used |
| 0x89 | 32 bytes @[0xFFAFA]. Verified-on-board | block RAM write, not persisted. Not used |
| 0x84 | 3 bytes @0xFFAFE | block: param byte offset (4·idx + byte). **No range check**: offsets ≥ 0x278 write RAM outside the param mirror; 16-bit wrap reaches any near RAM/SFR. Keep idx < 158 |
| 0x85 | word @0xFF510+off | param byte write, persisted |
| 0x8A | 32 bytes @0xFF510+off. Verified-on-board | **block param write**, each byte marked dirty and persisted by the firmware's own EEL writer. Verified-on-board |
| 0x87 | — | reset modes 2/3/4 (validator 0x48C8), see below. **Avoid** |
| 0x88 | 0xFFE95 (EEL writer state, 0 = idle) | — |
| 0x8F | 0xFFB0C | 0xFFB0C |
| 0x94 / 0x95 | P0E hi / P0F lo (read ungated) | gated, persisted |
| 0x58 | — | calibration (word 0x5A5A enters cal mode; then modes 0–6 overwrite P00–P0E lo and re-sign it). **Don't use** |
| 0x80 | 0xFFB48 (last mode word) | test modes, low byte = mode: 1 watchdog reset; 2 ship/power-off (cancelled if terminal ≥ 19.8 V); 3 direct FET override; 4 FET-request override; 5 factory current calibration, blocked only while P10 hi (ManufactureDate) ≠ 0 — **unblocked while the fuse is disarmed**; 10 a flag nothing reads. All expire after 7200 ticks or on re-lock. Details: [re/events-boot.md](re/events-boot.md). Not used |
| 0xC0–0xC5 | — | measurement override: 0xC0 = 0/1 enables (gated), 0xC1–0xC5 (ungated) fake current, cell voltages etc. Bypasses protection. Not used |

Not gated by 0x7A:
- **0x50 then 0xA0:** writing 0x835A to 0x50 twice in a row sets 0xFFB85; then 0x835A to 0xA0 flushes logs,
  opens the self-programming library and resets (inferred: into firmware-update mode). **Don't use.**
- **0x00 ManufacturerAccess:** only 0x0010 does anything (ship request + event-log entry, 0xAF6F).

### 0x87 reset modes (0x48E4) — avoid

Every mode ends in clear-all 0xAA55: P17 (both halves) = 0, live fault mask and 0xFFB50 cleared, P3A–P3D
from zero defaults (0xDAE8), and **0x7547 zeroes 380 B at 0xFF60C = P3F–P9D** (lifetime fault counters,
min/max with timestamps, hour counters, histograms, snapshots, fault and event logs). Then 0x7F16
clears P32 lo (the 0xBEEF gauge marker) and calls 0x7E01, which reseeds the gauge. Verified-static.

| Mode | Extra |
|---|---|
| 4 | none (the firmware's own PF clear) |
| 3 | copies 0xDA5C → P17–P3E (160 B): gauge floats P18–P31, P38 (cycle count), P39 zeroed |
| 2 | copies 0xDA3A → P0E hi–P3E (194 B): also P0E hi, P0F, P10 hi (ManufactureDate), P11 (serial) zeroed |

For a PF clear use a P17 record; for a gauge reseed use the P32 marker below. Both keep the history.

### On-board verification (2026-10-08, approved, firmware running, PEC on)

1. `ww(0x7A,0x835A)` → `rw(0x7A)` = 0x835A; `wb(0x84,[5C 00])`; `rb(0x8A)` = P17–P1E byte-identical
   to the image; `ww(0x7A,0)` → 0x7A = 0 and 0x8A reads return nothing.
2. Same-value write: `wb(0x8A,[00 00 00 00])` at P17, sleep 2 s, re-lock. The firmware appended exactly one
   record `17 E8 00 00 00 00` at 0xF1E28; the full 4 KB diff is those 6 bytes. Images:
   `backups/df_pre_unlock_20261007_233054.bin`, `backups/df_post_unlock_20261007_233118.bin`.
3. 0x7A = 0 after the next reset. Board log: [re/_board_log.md](re/_board_log.md).

### Param write over SBS (no bootloader)

`ww(0x7A,0x835A)`; check readback; `wb(0x84,[4·idx & 0xFF, 4·idx >> 8])`; `wb(0x8A, value LE 4 bytes)`;
wait ~2 s (main-loop flush); check `rw(0x88)` = 0; `ww(0x7A,0)` in a `finally`. Take a bootloader image
before and after when possible and require a one-record diff. Writes take effect in RAM immediately
(e.g. a P10 write re-arms the fuse at once); params read at boot (P17, P87 log freeze) need a reset or
wake. Not yet in `bms.py` (proposed `set-param --sbs`).

### Gauge reseed (recommended over 0x87, for new cells)

Unlock, write P32 `0x530CBEEF` → `0x530C0000` (clears the 0xBEEF marker), re-lock, reset. At boot 0x7E01
reseeds Qmax 3195 mAh, FCC 2850 mAh, the R tables from ROM and cycle count 0; lifetime data and logs stay.
Proposal, not run. Details: [re/gauge-scaling.md](re/gauge-scaling.md).

## 5. Tools

| File | What |
|---|---|
| `bms.py` | host CLI: `status`, `log`, `params`, `backup`, `set-param` (bootloader append, asks, saves a pre-image, verifies the diff), `report` |
| `pico/smb.py` | SMBus helpers at 0x0B: `rw`/`rb`/`ww`/`wb` (optional PEC), `crc8`, `reset` (pin reset via TP33) |
| `pico/dfw.py` | bootloader data-flash helpers: `enter`/`leave`, `rd`/`rd_ok`, `snap`, `wr` (0xFB + read-back), `status` (0x70), `blank` (0x24), `cmd`, `active`, `check` |
| `pico/bl.py` | older bootloader entry + block helpers |
| `pico/bl_dump.py`, `pico/run_dump.py` | memory dumper via 0xFC, double-read verified (edit REGIONS) |
| `pico/pf_append.py` | the original P17 append (PF clear) |
| `pico/pf_verify.py` | post-clear check across several resets |
| `pico/sbs_probe.py` | standard SBS register readout |
| `pico/experiments/` | one-off probes from the investigation (boot ROM, fuzzing, framing tests, `proofFB.py`) |
