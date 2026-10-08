# Write plan — clearing the latched PF (DRAFT, not yet executed)

Status: read-only trace done. No flash write attempted yet. This is the plan for
your review before we write anything.

## What the trace established

- **Read path** (0xFC) confirmed working.
- **Write path** exists: bootloader command **0xFD**, handler at 0xE591. It takes a
  24-bit target address from the command buffer and **bounds-checks it** before
  programming (compares against limits incl. 0xDBFF / 0xFF4F0), so the bootloader
  will refuse out-of-range writes — a built-in guard rail.
- **Erase** uses a block table indexed by RAM 0xFF510; teardown via 0xF12A.
- **Bootloader privileged-op key**: two 10-byte key tables (ptrs at 0xDD0E / 0xDD22)
  that the handler compares an input buffer against. On THIS unit both tables read
  as all-zero — i.e. the "password" appears unset. Promising, but only provable by
  trying it.

## What the trace could NOT pin down

The single exact data-flash record that latches the PF. The data flash is a
Renesas EEL (EEPROM-emulation) image of 157 parameter records; the index→meaning
map is NDA, and the EEL far-pointer indexing isn't fully reversed. So we can't
name "record P## = PF flag" purely from static analysis with confidence.

Because data-flash writes are **reversible** (full verified backup in
`backups/verified_20261007/`, and we can rewrite any record), the safe way to
both *identify* and *clear* the PF is a controlled, reversible experiment.

## Safety preconditions (every step)

- Bench ladder only (no real cells). F1 stays bridged. C+ clipped so the board
  stays awake.
- Full backup verified (done: code SHA stable across 2 dumps; all 157 params
  stable across 3 dumps).
- A bad write is recoverable: re-dump, compare to backup, rewrite the affected
  1 KB data-flash block from `firmware/dataflash.bin`.

## Step 0 — prove the write path harmlessly (no real data touched)

Before touching anything meaningful, confirm 0xFD actually programs, on an
already-erased (0xFF) scratch byte inside the allowed range, and that we can read
it back. If 0xFD needs the 10-byte key first, send all-zero key and retry.
Success criterion: one known 0xFF byte in data-flash free space becomes our test
value and reads back. Then (if possible) restore it. If 0xFD won't program at
all, STOP — the whole approach is blocked and we regroup.

## Step 1 — identify the PF record (reversible)

Preferred (append-only, no erase): the firmware reads the *latest* EEL record per
index. If we can craft a valid EEL record (correct [idx][~idx][u32]+framing/CRC)
for a candidate index with a "no fault" value and append it into already-erased
EEL free space (0xE22+ reads FF), the firmware picks it up with **no block erase**
and nothing else disturbed. Requires finalizing the EEL record/CRC format first
(more RE) — lowest risk if we get it.

Fallback (block rewrite): erase the 1 KB data-flash block holding the parameter
table and rewrite it from backup with ONE record changed. Higher blast radius,
but fully scripted from the verified backup.

Candidate records to try first (small flag-like values, not the float/voltage/
capacity params): to be finalized — current suspects are the status/flag records
rather than P18–P31 (floats) or P01–P07 (voltage thresholds). We change one
candidate, reset into firmware, and read:
  - BatteryStatus 0x16 (now 0x48C0 — want the TCA/TDA bits gone)
  - ManufacturerAccess 0x00 (now 0xA000, failure field "over voltage")
  - Q10 gate (now 3.3 V — want 0 V)
If no change, restore that record and try the next. All reversible.

## Step 2 — confirm the fix

- BatteryStatus no longer shows TERMINATE CHARGE / DISCHARGE.
- MA failure field clear; charging current/voltage (0x14/0x15) non-zero when a
  charger is presented.
- Q10 gate stays 0 V after reset (firmware no longer asserting the fuse).
- Re-dump data flash, diff against backup: confirm ONLY the intended record moved.

## Step 3 — hardware

Only after the PF is confirmed clear:
- Replace F1 (Dexerials SCP 45 A, same voltage class, or from a like board).
- Remove the F1 bench bridge and the C+ wake clip.
- Fit 6 matched, balanced cells; connect taps B-…B+ in order.
- Re-check on the ladder/charger before trusting it.

## Open items before we execute

1. Verify 0xFD programs a scratch byte (Step 0), incl. all-zero key if gated.
2. Decide append-only vs block-rewrite (depends on how cleanly we can craft an EEL
   record).
3. Finalize the candidate record list.

None of 1–3 is done yet. Nothing is written until you say go on this plan.

---
## Step 0 results (2026-10-07, non-destructive)

Confirmed, with zero unintended changes (full/witness snapshot diffs every attempt;
firmware + all config verified intact afterward: FCC 2390, cyc 387, model string,
cell voltages all normal):

- **Write protocol framing solved:** `0xFD` command = `[0xFD][count][addr_lo,addr_mid,
  addr_hi,len_lo,len_hi, data...]`. Accepted (ACK) with the count prefix.
- **Flash-mode handshake:** command `0x55` enters program mode (returns [08 52]),
  `0x59` exits (returns [80 00]). Mode-entry clock-stretches, so use **SoftI2C**
  (hardware I2C times out: ETIMEDOUT). SoftI2C handles it cleanly.
- **BUT 0xFD only writes CODE flash.** Its address bounds restrict writes to the
  user code region (<= ~0x0DBFF) plus a special 0x0F0000-0x0F0FFF window. Writes to
  the 0xF1000-0xF1FFF **data flash were silently rejected** (no change). The read
  command 0xFC has wider bounds, which is why DF reads worked but DF writes don't.
- **Command dispatch (0xE445) decoded:** 0xFC=read, 0xFD=write(code), 0x20/0x21/0x24/
  0x25/0x27 = other flash ops (one of these is the DATA-flash write/erase), 0xFA/0xFB
  framing. Region auto-selected from option bytes at 0x0C0/0x0C2.

### Open question this raises
Where is the PF actually stored — DATA flash (0xF1000 gauge params) or CODE flash
(<=0xDBFF)? 0xFD can already write code flash. If the PF flag is in code flash, we're
much closer than thought. If in data flash, we need the DF-write command (0x20/0x21/
0x24/0x25).

### Next options
A. RE the DF-write command (disassemble e729/e750/e733/e6e6) + locate PF record.
B. Check if the PF flag lives in code flash (trace the fuse-assert read target).
C. If you have the Renesas R-BMS_F tool or a known RAJ240/R2J240 flasher, it already
   speaks this protocol.

---
## 0x24 probe + EEL discovery (2026-10-07, non-destructive, board verified intact)

- **0xFD = code flash only** (confirmed). **0x24/0x20/0x21/0x25** are the data-flash
  commands; 0x24's address bounds include 0xF1000-0xF2000 (reaches the settings area).
- **0x24 framing NOT yet solved**: no-stop-then-read times out; other framings返回
  flaky/0x59-status. Needs the read-back done with multi-read verification (single
  bootloader reads are unreliable) and the correct sub-mode (RAM 0xFF4EC) set.
- **BIG: data flash is an EEL (EEPROM-emulation) with block rotation.** The 157
  parameter records physically MOVED from 0xF1808+ to 0xF1000+ during this session,
  triggered by our many resets (garbage collection). Content byte-identical, just
  relocated by -0x808. Firmware fully intact throughout (FCC 2390, cyc 387, cells,
  model string all normal).

### Implications (important)
1. Record physical addresses are NOT stable — raw fixed-address writes fight the EEL.
2. The correct way to change a param: either (a) append a valid EEL record (6 bytes
   [idx][~idx][u32]) into the ACTIVE block's free space so the firmware reads it as
   the latest, or (b) go through the firmware's own EEL write (not exposed via SBS),
   or (c) erase+rewrite the whole active block with correct EEL block headers.
3. Backups: record VALUES are captured; physical layout shifts. Restore would be via
   EEL-aware rewrite, not raw address copy.
4. Still unknown: which record index = PF.

### Recommended next: switch RE to Ghidra (RL78 supported, mcp__ghidra__* connected)
objdump got us the command map; the EEL block format + active-block selection + the
boot fault-check -> PF-record identification are much easier in Ghidra with xrefs and
decompilation. See BINARY_NINJA_TODO.md (Ghidra is the faster path than BN for RL78).

---
## Protocol understanding update
- Bootloader "running checksum" (RAM 0xFF514, table 0xDD4A) = **SMBus PEC** (CRC-8,
  poly 0x07, init 0). Already implemented in smb.py crc8(). Writes need a trailing PEC.
- The write side is a **multi-phase SMBus firmware-update protocol**: command byte ->
  count -> address -> data bytes, accumulated by a state machine (0xFF4E9 states,
  buffer 0xF3E0, count 0xFF4EC), executing via 0xE445 on completion. 0xFC read is the
  simple phase; 0x24/0x20 (data flash) use the fuller stateful sequence.
- Remaining to clear PF: (1) finish decoding/driving the 0x24 write transaction
  (prove on an erased DF scratch byte), (2) EEL append format (append a valid 6-byte
  record into the ACTIVE block's free space so firmware reads it as latest), (3)
  identify the PF record index. All tractable; involves real data-flash writes
  (backed up, EEL self-heals the spare block).

---
## 0x24 scratch-write proof attempt (2026-10-07, non-destructive)
Three framings ([0x24][count][addr3][len2][data], +PEC, no-count) all ACKed but did
NOT program; active block verified intact; EEL rotated active->0xF1800 again.

Root cause found (disasm of 0xE750 handler):
- 0x24 dispatches on PAYLOAD LENGTH (RAM 0xFF4EC = received count): ==3, ==4, other.
- **The real DATA-FLASH PROGRAM is at 0xE82F** (count==3 path, high-address sub-branch):
  it sets up FDL (calls 0xF400/0xF462/0xF484 open), source buffer **0xF3E3**, target
  addr **0xFF4F2**, length **0xFF4EE**, then calls **0xF73E = FDL write**, 0xF73A, 0xF468.
- count==4 (0xE79F) = READ flash->buffer. count==3 low-addr (0xE7EB) = FDL blank/verify.
- **Length 0xFF4EE = (received_len - 3)**, i.e. it's DERIVED, not sent as a len field.
  So my 2-byte len field was wrong.
- **The program SOURCE is buffer[3+] (0xF3E3), and length/data must be loaded by a
  PRIOR command (0xFB-style) before the 0x24+addr program.** => DF write is a 2-step
  stateful sequence: (1) load data+length into buffer, (2) 0x24 with [addr3] (count=3)
  programs. The data-load command framing is not yet fully decoded.

### Status: 0x24 write NOT yet proven. Mechanism identified, data-load step TODO.
### Also: EEL rotates the active block on ~every bl session (resets trigger GC) -
### must detect active/spare each session (pico/experiments/proof24.py does this).

---
## DATA-FLASH WRITE SOLVED + PROVEN (2026-10-07, session 3)
Decoded the bootloader SMBus slave ISR (0xEC25; states in 0xFF4E9, cmd 0xFF4E8, buffer 0xF3E0,
count 0xFF4EB, exec length 0xFF4EC, PEC 0xFF514). Corrections to earlier notes:
- It is ONE transaction, not two. **0xFB = DF write**: `[0xFB][count=3+n][a0 a1 a2][n data][PEC]`.
  Exec check (0xE445->0xE59D->0xE6AC) runs after the 3 address bytes: 0xF1000 <= addr,
  addr+n <= 0xF2000, n <= 160. Program runs at STOP (0xEC25 dispatch -> 0xE7CD). In 0xE7CD the
  addr>0xFFFF branch 0xE7E3 is the PFDL write (req @0xFF508: index=addr&0xFFFF, src 0xF3E3, len,
  cmd 4); 0xE82F is the CODE-flash word write (my earlier notes had these swapped).
- PEC is required (crc8 over [0x16, cmd, count, payload]); bad PEC clears the exec flag 0xFF513.
- Reads reply block-style `[count][data][PEC]` (state 5, 0xEF81).
- Other cmds (all [cmd][count][payload][PEC], exec at STOP):
  0x70 read -> last PFDL result (0 OK, 0x1B not blank, 0xFF busy);
  0x26 read -> blank-check result (0xFF blank, 0x00 not blank, 0xCA err);
  0x24 [addr3][len2] = PFDL blank check (cmd 8)  — read-only, good probe;
  0x21 [blk] = DF block ERASE (blk 0..3, 1 KB each, PFDL cmd 3);
  0x20/0x27 [b0 b1], 0x25 [b] = code-flash block ops (guards exclude blocks 0x37-0x3E);
  0x00 [0xD0] = leave bootloader / run app; 0xFA = flash->buffer read; 0xFD = code write
  (no count byte: [0xFD][addr3][len2][data...]); 0x55/0x59/0x7C/0x26/0x70 are plain reads,
  0x55 is NOT a mode switch (no mode needed for writes).
- **Proof:** pico/experiments/proofFB.py wrote 0xA5 to 0xF1C00 (middle of spare block; active was 0xF1000).
  PFDL status 0, blank-check flipped 0xFF->0x00, full 4 KB DF diff = ONLY F1C00:FF>A5.
  Firmware intact after (FCC 2390, cyc 387, cells, model, status 0x48C0).
  Leftover: that 0xA5 byte sits in the spare block until the next EEL rotation erases it.
- Helpers: pico/dfw.py (enter/leave, rd_ok, snap, wr, blank, status, check).
- Earlier "0xFD/0x24 DF writes rejected": wrong framing (no PEC / count / cmd mixups).

---
## PF IDENTIFIED + CLEARED (2026-10-07, session 3)
- Param RAM mirror: P_n at 0xFF510 + 4n (0x6FE0 marks dirty; writer appends [n][~n][u32] to the active
  2 KB block, block switch at 338 records). Newest record per index wins.
- Fault mask = 64 bits at RAM 0xFFA9E (0x5EF6 set, 0x5F1A clear, 0x5ED4 test). Bits 48-62 = PF class
  (0x83E4 tests mask 0x7FFF<<48). **P0x17[15:0] = mask bits 48..63** (persisted by 0xAB10, restored at
  boot by 0x839D). Unit had P0x17 = 4 => PF bit 50. Gated clear handler 0x48E4 (needs 0xFFE80==0x835A)
  mode 3 = gauge-learning reset P17-P3E from defaults @0xDA5C (not used).
- AFE reg 0x58 written 0x40/0xC0 at 0x51E3 (also on every boot) — likely FET enable, not the fuse. **Correction (docs/re/afe-map.md):** reg 0x58 is the coulomb-counter control (0x40 enable, 0xC0 enable+start); the fuse is driven by MCU pin P1.1.
- **Fix applied:** appended `17 E8 00 00 00 00` at 0xF1DE6 (active block 0xF1800, first free slot) via
  pico/pf_append.py. Diff = only those 6 bytes. Pre-write image: firmware/df_pre_pfclear.hex.
- Result after reset (x3, + 60 s): BatteryStatus 0x48C0 -> 0x00C0, MA 0xA000 -> 0x2080,
  ChargingCurrent 0 -> 150 mA, ChargingVoltage 0 -> 25600 mV. FCC 2390, cyc 387, cells, model intact.
- Undo (if ever needed): append `17 E8 04 00 00 00` the same way.
- Q10 gate = 0 V with firmware running (user metered, 2026-10-07). C+ wake clip removed. F1 bridge still on until new fuse.

---
## What tripped the PF (event log decode, 2026-10-07)
- Fault log = vendor block 0xF3 (params P91..P99, ring index 0xFF70D, writer 0x7B6F via 0x760F).
  Entry = [ts u16 = P5B low word][state byte = P73 low byte][code]. Second log 0xF5 (P9A-P9D, 0x7C85).
  Snapshots 0xF0-0xF2 (24 B each, last 3 distinct codes): words 6..11 = the six cell voltages.
- Code <-> fault-mask bit table @0x2422; per-code saturating lifetime counters at P40-P45.
  Lifetime counts: 0x5C x122, 0x3C x58, 0x14 x38, 0x46 x4, 0x16 x1.
- **PF code 0xCA = bit 50 = dead-cell check (0x6890):** min cell (0xFFA34) < 1000 mV (const @0xD5C6)
  for 5*4 checks (const @0xD5C8) before any reading >= 1000 mV since wake; a good reading disarms it
  until the next reset. Same timestamp: 0x14 (bit 2) and 0x16 (bit 4, min cell < 2500 mV @0xD562).
- Snapshot at the trip: cells 3566, 1173, 0, 1178, 3562, 2682 mV — cell 3 at 0 V, two more collapsed.
- Timestamp P5B counts ~1 per powered-on hour; trip at 0x8F54 vs 0x910A at the first bench reading
  => ~440 powered hours before the bench work. Not caused by bench supply cycling.
- **Rebuild risk:** this check fires if the BMS wakes while any tap reads < 1 V (e.g. taps connected
  one at a time). Connect all cells/taps before the board can wake, and confirm `bms.py status`
  shows PF clear BEFORE fitting the new F1 (re-clear with `bms.py set-param 0x17 0` if it re-trips).
- Tool: `uv run bms.py log`.
