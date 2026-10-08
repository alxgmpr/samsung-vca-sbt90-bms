# Board action log

Append-only. One line per board action: time | slug | exact command | result summary.

- 2026-10-08T05:18:10Z–05:18:15Z | fault-codes | `mpremote cp pico/smb.py : + exec` SBS rw 0x09,0x0A,0x16,0x47,0x3A-0x3F,0x08 (SoftI2C 40 kHz) | 0x0A=0 mA, 0x16=0x00C0, 0x47=22253 (≈pack, FETs on; was 4397 with PF latched → 0xFFE6E = pack-terminal/charger-side voltage), cells 3722/3712/3700/3704/3698/3704 mV, 0x08=3023 (29.1 °C)
- 2026-10-08T05:19:22Z | thresholds | `mpremote cp pico/smb.py : + exec` SBS rb 0xEB, rw 0x1A/0x14/0x15 (SoftI2C 40 kHz) | 0x1A=0x1031 (IPScale x10), 0x14=150, 0x15=25600; EB line lost to output filter
- 2026-10-08T05:19:28Z | thresholds | same, SBS rb 0xEB only | EB = b80be40c740ea00f0f0bd70b6d0c030da00fb80b = code flash 0xD518..0xD52B byte-identical
- 2026-10-08T05:20:16Z | lead | `uv run bms.py report` | rc=0, wrote reports/20261007_232027.{json,md}; status 0x00C0, PF clear
- 2026-10-08T05:30:54Z | unlock-exec | `uv run bms.py backup backups/df_pre_unlock_20261007_233054.bin` | OK, active F1800, 158 params
- 2026-10-08T05:31:07Z | unlock-exec | step 1 (approved): `ww(0x7A,0x835A,pec)`, `wb(0x84,[5C 00])`, `rb(0x8A)`, RAM reads via `wb(0x82,[lo hi])`+`rb(0x89)`, `rw(0x83)`@FF0C, `ww(0x7A,0)` (SoftI2C 40 kHz, PEC on) | 7A 0→0x835A→0; 0x84=5c0000; 0x8A=00000000f4bf3645c76c15458359c5425a44cc3ec4718a3e5d3e113e2412333d (= P17..P1E); 0x8A locked = empty
  - RAM FFE40: ffffff005aa55a00890602400400280000000000000000000000000000000000
  - RAM FFE80: 5a83890d6a210000802004000002000005010300010000000001000000000000 (read while unlocked, so FFE80=5A83)
  - RAM FFEA0: 00000000e0041900ff00f100f00d3f000a362c15000000ff210100b103000000
  - RAM FFB40: 000286100a0000600000000000000000000000000024000000006f566f560000
  - word @FFF0C (0x83, LE): 0x0018 → P12=0x18, P13=0x00
- 2026-10-08T05:31:13Z | unlock-exec | step 2 (approved): unlock, `wb(0x84,[5C 00])`, `wb(0x8A,00 00 00 00,pec)`, 2 s, `ww(0x7A,0)` | 0x8A before/after identical, 0x88 (EEL state)=0, relock 0
- 2026-10-08T05:31:18Z | unlock-exec | `uv run bms.py backup backups/df_post_unlock_20261007_233118.bin` | diff vs pre = 6 bytes only: F1E28 `17 E8 00 00 00 00` (new P17=0 record)
- 2026-10-08T05:31:28Z | unlock-exec | SBS `rw(0x7A)`, `rw(0x16)` after the bootloader-session reset | 0x7A=0 (locked after reset), status 0x00C0
- 2026-10-08T05:54:40Z | lead | `uv run bms.py set-param 0x10 0x00004C50 -y` (user-approved fuse disarm) | 1st write try not accepted, retry OK; slot F1E2E, PFDL 0, diff = new record only; P10 0x52394C50 -> 0x00004C50; status 0x00C0, mfg reads 1980-00-00, PF clear; pre-image backups/df_pre_P10_20261007_235458.bin
- 2026-10-08 | lead | `bms.py status`, `log`, `backup` (tmp, not kept) read-only | status 0x00C0, PF clear, mfg 1980-00-00, cells 3677-3699 mV (spread 22), charge req 150 mA @ 25.6 V; data flash = df_pre_P10 + P10 record (F1E2E `10 EF 50 4C 00 00`) + 3 firmware P39 records, append-only
- 2026-10-08 | lead | status polled after a bootloader session | charge request reads 0 for ~3 s after the reset back into firmware, then 150 mA
- 2026-10-08 | lead | `BMS_BOARD=1 pytest tests/test_board.py` (read-only HIL suite) | 6/6 pass
- 2026-10-08 | fcc-patch | read-only 0xFC dump 0xD800-0xDBFF (pico/run_dump.py with REGIONS edited) | all 16 chunks failed; diag: I2C scan empty both before and after enter_bl, 0xFC read EIO at 0xD960 and 0x0000. Board not answering at all (power or wiring), no writes made
- 2026-10-08 | fcc-patch | read-only 0xFC dump 0xD800-0xDBFF (rerun after board powered) | 16/16 chunks OK, 1024 B identical to firmware/codeflash.bin; no writes
- 2026-10-08 | fcc-patch | step 1 (approved): bms.py status/backup (backups/df_pre_fccpatch_20261008_165628.bin), then bootloader: 0x25 [36] blank check -> (0x26=54, 0x70=27) not blank; block 0xD800-0xDBFF re-read identical to codeflash.bin; FD header-only probes (no data): 0xD800 n=4 and n=0x400 6/6 ACK; 0xDC00 n=4, 0xD800 n=0x404, 0xD800 n=2 each 5/6 (last byte NACK) = matches static trace; no writes
- 2026-10-08 | fcc-patch | step 1b (approved) rehearsal on spare block 0x2F (0xBC00): blank (0xFF,0x70=0); FD 00 BC 00 04 00 DE AD BE EF -> 10/10 ACK, 11 ms, 0x70=0, readback DEADBEEF, 0x25 -> not blank (47); 0x20 [2F 2F] -> 0x70=0, 0x25 blank, 1024 B read all FF. Block restored to all FF. Firmware back up: status 0x00C0, PF clear
- 2026-10-08 | fcc-patch | step 2 (approved) no-op rewrite of code-flash block 0x36 (0xD800-0xDBFF): 0x20 [36 36] status 0, 0x25 blank (0xFF,0), 256 FD word writes each fully ACKed with 0x70=0, read-back 1024 B identical to codeflash.bin, first attempt. Left bootloader; firmware back up
- 2026-10-08 | fcc-patch | step 3 (approved) patched code-flash block 0x36: D961 20->00, D962 32->7A (FCC clamp/seed 2850.0 -> 4000.0), D98D B0->40, D98E 47->83 (Qmax seed 3195.0 -> 4200.0). Erase 0, blank, 256 FD words OK, read-back identical to intended image first attempt; independent re-read after a bootloader exit/re-entry also identical. Firmware boots: status 0x00C0, PF clear. Undo = rewrite block 0x36 from firmware/codeflash.bin the same way
