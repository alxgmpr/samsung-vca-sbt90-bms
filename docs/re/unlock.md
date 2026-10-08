# unlock — SBS "unlock word" 0xFFE80 and the gated vendor commands

Owner: unlock fork. All findings verified-static (from `firmware/code.dis` / `codeflash.bin`) unless
marked otherwise. No board actions were taken (register_dump.txt already has the 0x7A readback).

## Summary

- **0xFFE80 is SBS word register 0x7A, and it is written directly.** There is no key, challenge or
  sequence: `WriteWord(0x7A, 0x835A)` sets the unlock state. No seal check, PEC optional.
- The earlier sweeps targeted ManufacturerAccess 0x00, whose write handler only reacts to 0x0010.
  0x7A was never written, so nothing unlocked. TI keys mean nothing to this firmware.
- With 0x7A = 0x835A the firmware exposes: arbitrary RAM/data-flash read (0x82/0x83/0x89), RAM write
  (0x83/0x89), **param RAM read/write with persistence (0x84 + 0x85/0x8A)**, **gauge/PF reset (0x87)**,
  calibration (0x58), test/FET modes (0x80), and more.
- This is a usable no-bootloader path for param writes and the gauge reset: firmware running, pack
  awake, no TOOL0/reset clip. Writes go through the firmware's own EEL writer (dirty bitmap ->
  0x7031), so block rotation is handled by the firmware.

## SBS command table (@0x2008)

6-byte entries `[cmd][flags][fn1 u16][fn2 u16]`, terminated by cmd 0xFF at 0x22B4. Lookup 0xB842.
Flags: bit7 = block, bit6 = writable, bit5 = readable, bits4..0 = length-1 (word: 1 → 2 bytes).
- fn1 runs at the start of a read (fills the reply buffer 0xFFA0A) **and** as a validator after all
  write data bytes arrive (0x8B4E). Returning 0 aborts the write. Gated commands do the 0x835A check here.
- fn2 is the write executor, run at STOP (0x8940) if all bytes arrived. After it, 0x8962 copies
  cmd/flags to 0xFFE48/0xFFE49 and 0xFFE4A = the written word.
- PEC (0x8B37..0x8B41): optional. If a PEC byte is sent it must be correct, or the transaction is
  dropped. Without one the write still runs.
- `callt [0xAA]` (0xB3B9) = received word, LE from 0xFFA0A. `callt [0x9C]` = load reply word.
  Block writes: 0xFFA0A = SMBus count byte, data from 0xFFA0B. `callt [0xA8]` (0xB3E4) copies
  `count` bytes to the destination and, with e=1, calls `callt [0xB0]` (0x6FE0, mark param dirty) per byte.

## How 0xFFE80 changes

| Where | What |
|---|---|
| 0x45B1 (cmd 0x7A read) | returns 0xFFE80 (register_dump: 0x7A = 0x0000 = locked) |
| 0x45BB (cmd 0x7A write) | new word → 0xFFE80. If the old value was 0x835A and the new one differs: `0x405D(0)` (clears test-mode flags 0xFFEB4, calls 0xA955), restores 0xFFB65 if 0xFFB82==1, clears 0xFFA5C |
| 0x3FE8 | `0x405D(0)`, 0xFFE80 = 0. Called from event 6 in the event dispatcher (0x9522) only when timer 0xFFE5E == 0. The source of event 6 is not traced |
| reset | RAM, so presumably 0 after reset/wake (inferred, no zero-init trace) |

There is no unlock timeout. The 7200-tick counter 0xFFB4A (0x4076/0x407D) times out the 0x80 test
modes (0xFFEB4), not the unlock.

## Gated commands (fn1 calls 0x48DE: `cmpw 0xFFE80, #0x835A`)

| cmd | flags | read | write (when unlocked) |
|---|---|---|---|
| 0x80 | 61 | 0xFFB48 (last mode word) | Test/mode word, low byte = mode 1..13, high byte = argument bits. 1: 0xFFEA0.0 → main loop flushes and resets (0x9B98, inferred reset). 2: 0xFFEB4.4 + 0xB418 timer + event-log write. 3: 0xFFEB4.0, arg bits → 0xA949/0xA951 (AFE/FET). 4: 0xFFEB4.1, arg bits 0-3 → 0xFFB60 (FET overrides?), bit4/5 → 0xFFB65/82, bit7 toggles. 5: unless 0xFFE36.3 or P10 (0xFF552) ≠ 0: callt [0xA4], 0xFFEB4.3. 10: 0xFFEB4.2. All test modes cleared on re-lock |
| 0x82 | e2 | 3 bytes @0xFFAFA (memory pointer) | block, sets pointer 0xFFAFA |
| 0x83 | 61 | word @[0xFFAFA] (16-bit near addr, DFLEN 0xF0090 = 1 so data flash readable) | **RAM byte poke**: low byte → [0xFFAFA] |
| 0x84 | e2 | 3 bytes @0xFFAFE (param offset) | block, sets param byte offset 0xFFAFE. No range check |
| 0x85 | 61 | word @0xFF510+off | **param byte write**: low byte → 0xFF510+off, then mark dirty (persisted) |
| 0x87 | 41 | — | **reset mode**, low byte 2/3/4 only (validator 0x48C8), see below |
| 0x88 | 21 | 0xFFE95 (EEL writer state) | — |
| 0x89 | ff | 32 bytes @[0xFFAFA] (DFLEN on) | block write to [0xFFAFA] (no persist) |
| 0x8A | ff | 32 bytes @0xFF510+off | **block param write**, count bytes → 0xFF510+off, each byte marked dirty (persisted) |
| 0x8F | 61 | 0xFFB0C | 0xFFB0C |
| 0x94 | 61 | 0xFF54A (P0E[31:16]), read ungated | write gated, persisted |
| 0x95 | 61 | 0xFF54C (P0F[15:0]), read ungated | write gated, persisted |
| 0x58 | 61 | — | Calibration. When unlocked it accepts only words 0x5Axx. Low byte 0x5A (word 0x5A5A) enters cal mode (0xFB54.1, 0xFFE8A=8). After that, values < 7: 0/1 0xFFB24 → P0B hi / P0C, 2/3 cell ADC 0x4F9A(0..4)+0x504A → P00hi–P03 / P05hi–P08, 4/5 0x4FAE → P0A hi / P0B, 6 → P0D hi/P0E + P00 low byte, P00[15:8]=0xA5, persist 58 bytes. **Overwrites calibration; don't use** |

**Measurement override (simulation) mode, 0xC0–0xC5** (reported by thresholds, gating checked here).
0xFFE83 is not a mode: it holds the per-transaction flags the SBS ISR sets (bit0 = read in
progress, bit1 = write in progress; cleared at 0x8A09).
- 0xC0 write: the validator (0x4B6E) accepts only 0 or 1, and only when unlocked. It sets the
  override enable 0xFFA5C. 0xFFA5C is cleared on re-lock (0x45D9) and on test-mode timeout (0x40AA).
  Readers: 0x9ECF, 0xAB56, 0xADE1 (next to the 0x835A check at 0xADCE).
- 0xC1 → 0xFFA46/48 (current), 0xC2 → 0xFFA4A, 0xC3 block → cell array 0xFFA4C (count must be
  2×[0xD404]), 0xC4 → 0xFFA58, 0xC5 → 0xFFA5A. These writes are **not** gated. Inferred: they only
  take effect while 0xFFA5C ≠ 0. Not proposed. Faking cell voltages bypasses protection.

Not gated by 0x7A but related:
- **0x50** write (0x442B): if the word is 0x835A and the previous completed transaction was also a
  write of 0x835A (0xFFE49.1 and 0xFFE4A), then 0xFFB85 = 1. Read 0x50 returns 0xFFB85.
- **0xA0** write (validator 0x4A55 needs 0xFFB85 ≠ 0): word 0x835A sets 0xFFEA0.2. The main loop
  (0x9D1F) then flushes logs, calls the self-programming library (FSL init/open/prepare at
  0xFA00-0xFA30, 0xFB10), and resets via 0xFB38 (0xF84E). Inferred: jump to the SMBus
  bootloader/firmware-update mode. **Do not use**; the bootloader is already reachable with TOOL0.
- **0x00** ManufacturerAccess write (0xAF6F): only 0x0010 does anything (0xFFEB4.4, timer 0xB418,
  event-log entry via 0xAA82 → 0x7C85). All other values are ignored, which is why the 16-bit sweep
  found nothing. Side effect: the sweep's 0x0010 write probably added an entry to the 0xF5 event log.

## 0x87 reset modes (0x48E4)

> **Correction (events-boot.md, unlock-exec.md):** every 0x87 mode also ends in clear-all 0xAA55 -> 0x7547, which zeroes **P3F-P9D** (lifetime counters, min/max, hours, histograms, snapshots, fault and event logs). Back up first. For a gauge-only reseed prefer clearing the 0xBEEF marker in P32 (gauge-scaling.md).

Every mode runs the common tail: 0xAA55 clears **P17 (PF bits, 0xFF56C) = 0**, copies P3A–P3D from
defaults 0xDAE8 (all zero), then 0x7F16 clears P32[15:0] (0xFF5D8) and calls 0x7E01. All writes
are persisted. Against the current image (backups/df_20261007_221649.bin):

| mode (word) | extra copy | params changed vs today |
|---|---|---|
| 4 (`04 00`) | none | P17→0 (already 0), P32 0x530CBEEF→0x530C0000, P3A 0x2971, P3B 0x2099F, P3C 0xEE6F, P3D 0xAA64 → 0 |
| 3 (`03 00`) | 0xDA5C → 0xFF56C, 160 B (P17–P3E) | mode 4 plus P18–P31 (gauge learning floats, e.g. P19 = FCC 2390.7) → 0, P38 0x01830000→0, P39 0x32→0 |
| 2 (`02 00`) | 0xDA3A → 0xFF54A, 194 B (P0E[31:16]–P3E) | mode 3 plus P0E hi 0x5227→0, P0F 0x3B27→0, P10 hi 0x5239→0, P11 0x19F→0 |

The live fault mask 0xFFA9E is not touched. P17 = 0 takes effect at the next boot (0x839D). If a
PF bit is still set live, 0xAB10 can persist it again before then, so reset straight after.

Mode 4 is the firmware's own PF-clear. It does the same as our P17 append, plus zeroing P3A–P3D
and P32[15:0]. The bootloader route is narrower, so it stays the better PF clear. Mode 3 is the
gauge-learning reset for new cells.

## Usable as a no-bootloader path?

Yes. For param writes, prefer 0x84 + 0x8A over 0x87: you choose the bytes and nothing else moves.
- Param offset = 4·idx + byte (LE). 0x84 has no range check: offsets ≥ 632 (0x278) write RAM
  outside the param mirror, which is not persisted, and 16-bit wrap reaches any near RAM/SFR.
  Keep off + count ≤ 0x278.
- The firmware persists from its dirty bitmap in the main loop (0xFFE97 → 0x7031). Allow about
  1 s before resetting.
- Limits: this needs the firmware running, and a pack with a latched PF still answers SBS, so it
  works then too. Writes are byte-granular. One record is appended per marked word (0x6FE0 marks
  by param index, so a 4-byte write produces one record per index).

## PROPOSAL (needs user approval, nothing here has been run)

Uses `pico/smb.py` (`ww`, `wb`, `rw`, `rb`), with PEC on. The board lock and board log apply. Run
it as one `mpremote exec` per step, firmware mode, pack awake.

**Step 1: prove the unlock, no flash change (reversible)**
```
smb.ww(0x7A, 0x835A, pec=True)
assert smb.rw(0x7A) == 0x835A          # expect 0x835A (today 0x0000)
smb.wb(0x84, bytes([0x5C, 0x00]), pec=True)   # param offset = P17 (RAM pointer only, no persist)
print(smb.rb(0x84).hex())              # expect 5c00xx
print(smb.rb(0x8A).hex())              # expect 32 bytes = P17..P1E LE: 00000000 f4bf3645 c76c1545 ...
smb.ww(0x7A, 0x0000, pec=True)         # re-lock
assert smb.rw(0x7A) == 0
```
Expected: 0x8A bytes match `bms.py params` for P17–P1E. Locked, 0x8A reads are rejected (NACK or
stale data). Undo: the re-lock line, or any reset.

**Step 2: param write via SBS, test on a harmless value (writes data flash)**
Take `bms.py backup` first. Example that writes P17 = 0, which it already is: proves the path with
no value change, though the firmware appends one record.
```
smb.ww(0x7A, 0x835A, pec=True)
smb.wb(0x84, bytes([0x5C, 0x00]), pec=True)
smb.wb(0x8A, bytes(4), pec=True)       # P17 bytes 0..3 = 00 00 00 00, persisted by firmware
time.sleep(2)
smb.ww(0x7A, 0x0000, pec=True)
```
Verify with `uv run bms.py params` (bootloader read): there should be a new P17 record = 0 and no
other new records. Undo: none needed, the value is unchanged. For a real change, the undo is the
same sequence with the old 4 bytes from the backup.

**Step 3 (only for new cells, optional): gauge-learning reset**
```
smb.ww(0x7A, 0x835A, pec=True)
smb.ww(0x87, 0x0003, pec=True)         # mode 3; use 0x0004 for PF-only reset
time.sleep(2)
smb.ww(0x7A, 0x0000, pec=True)
# then a reset (smb.reset()) so P17/learning load at boot
```
Expected: the params listed in the 0x87 table go to 0, and FCC (SBS 0x10) falls back to its design
default after the reset. Undo: restore each changed index from the backup image, via
`bms.py set-param` (bootloader) or Step 2's 0x84+0x8A path.

Not proposed: 0x80 test modes, 0x58 calibration, 0x83/0x89 RAM writes, 0x50+0xA0 (likely re-enters
the bootloader).

## Open questions
- What posts event 6 (the re-lock at 0x952D)? Probably sleep or a mode change. Re-lock anyway.
- Is 0xFFE80 zeroed at startup? Inferred yes (RAM); check by reading 0x7A after a reset in Step 1.
- 0x80 mode semantics (FET overrides via 0xFFB60, 0xA949/0xA951) are only partly traced.
- 0x7E01 (called by 0x7F16 in the 0x87 tail) is not decoded.
