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
