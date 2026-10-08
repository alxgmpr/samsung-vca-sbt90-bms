# unlock-exec: running the approved unlock proposal (steps 1 and 2)

Owner: unlock-exec fork. Date 2026-10-08 (UTC 05:30–05:32). Approved by the user: steps 1 and 2 of
[unlock.md](unlock.md). Step 3 (0x87 reset) was **not** run; it waits until new cells are fitted.
Every board action is in [_board_log.md](_board_log.md).

## Result

| Item | Result | Confidence |
|---|---|---|
| `WriteWord(0x7A, 0x835A)` unlocks; 0x7A reads back 0x835A | yes | verified-on-board |
| `WriteWord(0x7A, 0)` re-locks; 0x7A reads 0, and 0x8A reads return nothing | yes | verified-on-board |
| 0x84 `[5C 00]` + read 0x8A returns P17..P1E | byte-identical to the data-flash image | verified-on-board |
| Write 0x8A `00 00 00 00` at offset 0x5C (P17 = 0, same value) | the firmware appended exactly one record, `17 E8 00 00 00 00` at 0xF1E28; full 4 KB diff = those 6 bytes only | verified-on-board |
| 0xFFE80 after reset | 0 (0x7A = 0 after the bootloader-session reset) | verified-on-board |
| Gated RAM read: 0x82 `[lo hi]` sets the 16-bit near pointer 0xFFAFA, 0x89 reads 32 B, 0x83 reads one word | works | verified-on-board |
| Firmware status after everything | 0x00C0, PF clear | verified-on-board |

## Framing (re-checked statically before running)

- SBS ISR (0x8A9E..0x8B5F): block writes take `count` (must be < 33), then `count` bytes. The validator
  (table fn1) runs once they have arrived, and an extra trailing byte is checked as PEC
  (`crc8([0x16, cmd, count, data...])`). The `smb.py` `ww`/`wb` with `pec=True` frames are correct.
- 0x84 executor (0x4886) copies `count` bytes to 0xFFAFE; the param offset is the 16-bit word there
  (0x48BF: `hl = 0xF510 + [0xFFAFE]`). `[5C 00]` = P17 byte 0.
- 0x8A executor (0x49D0) copies `count` bytes to 0xFF510 + offset with e=1, so each byte is marked
  dirty (callt [0xB0] = 0x6FE0) and persisted by the main-loop EEL writer.
- 0x82 executor (0x4834) copies `count` bytes to 0xFFAFA. 0x89 read (0x4985) and 0x83 read (0x4845)
  are pure reads from that pointer (DFLEN set around them). 0x83 *write* (0x4860) and 0x89 *write*
  (0x49A6) poke RAM; neither was used.

## Exact sequence run (Pico, SoftI2C 40 kHz, PEC on all writes)

Step 1 (no flash change):
```
rw(0x7A)                          -> 0
rb(0x8A)                          -> b''          (locked)
ww(0x7A, 0x835A)
rw(0x7A)                          -> 0x835A
wb(0x84, [5C 00]); rb(0x84)       -> 5c0000
rb(0x8A)                          -> 00000000 f4bf3645 c76c1545 8359c542 5a44cc3e c4718a3e 5d3e113e 2412333d
for a in FE40 FE80 FEA0 FB40: wb(0x82, [a lo, a hi]); rb(0x89)   (sibling requests, raw hex in _board_log.md)
wb(0x82, [0C FF]); rw(0x83)       -> 0x0018  (P12 = 0x18, P13 = 0x00)
ww(0x7A, 0); rw(0x7A)             -> 0
rb(0x8A)                          -> b''
```
Step 2 (writes data flash, value unchanged), after `bms.py backup` → `backups/df_pre_unlock_20261007_233054.bin`:
```
ww(0x7A, 0x835A); assert rw(0x7A) == 0x835A
wb(0x84, [5C 00]); assert rb(0x84)[:2] == 5C 00
rb(0x8A)[:4] == 00 00 00 00       (abort otherwise)
wb(0x8A, [00 00 00 00]); sleep 2 s
rb(0x8A)                          -> unchanged
rw(0x88)                          -> 0 (EEL writer idle)
ww(0x7A, 0); rw(0x7A)             -> 0
```
Then `bms.py backup` → `backups/df_post_unlock_20261007_233118.bin`. Diff: F1E28..F1E2D `FF` → `17 E8 00 00 00 00`.

## Observations

- The active block (F1800) records after the PF clear: `17=0` at F1DE6 (pf_append), `17=0` at F1E10
  (the earlier `bms.py set-param`), now `17=0` at F1E28. Between them, P39 (partial-cycle accumulator)
  counts 0x2D → 0x35, about one record per bench session.
- Raw RAM (read while unlocked): 0xFFE80 = `5A 83` (the unlock word itself), 0xFFE82 = 0x89 (last
  SBS cmd), 0xFFB50 (P17-hi protection-disable mask, mirrored) = 0x0000 at offset 0x10 of the FB40 block.
  Interpretation of the other bytes belongs to afe-map and events-boot.

## Undo / leftovers

None needed: P17 was 0 before and after. Two extra records in the EEL block (6 bytes each); the
firmware's block rotation handles them. Board left locked (0x7A = 0), status 0x00C0, lock dir removed.

## Step 3 (deferred): extra side effect not in unlock.md

From events-boot, checked here statically: every 0x87 mode ends at 0x491A `call 0xAA55`, which
- sets P17 low and high words to 0 (0xFF56C/0xFF56E, marked dirty);
- clears the whole live fault mask (`0x5F1A` with mask −1) and 0xFFB50 (`0xB224(−1)`);
- calls 0x7547: memset of 380 B at 0xFF60C (= P3F..P9D), then re-seeds the lifetime signature
  (0xFF60C = 0x9FD5, +2 = 35) and the min/max sentinels (0xFF656/7 = 0xFF, 0xFF65A = 0xFFFF).

So any 0x87 mode erases the lifetime history: P40–P45 fault counters, min/max with timestamps,
hour counters, histograms, snapshots, and both fault and event logs. Take `bms.py backup` (and a
`bms.py report`) before any 0x87 run; the backup image is the only copy afterwards. The live fault
mask being cleared also means 0x87 takes effect without the reset unlock.md assumed.

From gauge-scaling (not re-checked here): the gauge reseeds when P32 lo (the 0xBEEF marker,
0xFF5D8) is cleared, which every 0x87 mode does through 0x7F16 → 0x7E01. A full charge does not
re-lock 0x7A: 0x954A posts event-log code 6 (callt [0xBC] → 0xAA82 → 0x7C85), not dispatcher
event 6. Only another 0x7A write or a reset re-locks (reset verified on board above).

## Addendum PROPOSAL for the lead: unlock-based set-param in bms.py

`bms.py set-param` currently uses the bootloader (TOOL0 + reset). The unlock path needs only SBS with
the firmware running and was just proven. Suggested `set-param --sbs IDX VALUE`:
1. `backup` image via the bootloader as today (keep the pre-write image and the diff check).
2. Pico: `ww(0x7A,0x835A)`, assert readback; `wb(0x84,[4*idx & 0xFF, 4*idx >> 8])`; assert `rb(0x84)`;
   `wb(0x8A, value.to_bytes(4,'little'))`; sleep 2 s; assert `rb(0x8A)[:4]` == value; `ww(0x7A,0)` in a
   `finally`; assert `rw(0x7A) == 0`.
3. Bootloader image again; require the diff to be exactly one `[idx][~idx][u32]` record.
Guard `idx < 158` (offset ≤ 0x274; 0x84 has no range check and larger offsets write arbitrary RAM).
The benefit is small (both paths work); the main use is when the bootloader clip isn't fitted, e.g.
after cells are installed. The bootloader path stays the default.
