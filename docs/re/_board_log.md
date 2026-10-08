# Board action log

Append-only. One line per board action: time | slug | exact command | result summary.

- 2026-10-08T05:18:10Z–05:18:15Z | fault-codes | `mpremote cp pico/smb.py : + exec` SBS rw 0x09,0x0A,0x16,0x47,0x3A-0x3F,0x08 (SoftI2C 40 kHz) | 0x0A=0 mA, 0x16=0x00C0, 0x47=22253 (≈pack, FETs on; was 4397 with PF latched → 0xFFE6E = pack-terminal/charger-side voltage), cells 3722/3712/3700/3704/3698/3704 mV, 0x08=3023 (29.1 °C)
- 2026-10-08T05:19:22Z | thresholds | `mpremote cp pico/smb.py : + exec` SBS rb 0xEB, rw 0x1A/0x14/0x15 (SoftI2C 40 kHz) | 0x1A=0x1031 (IPScale x10), 0x14=150, 0x15=25600; EB line lost to output filter
- 2026-10-08T05:19:28Z | thresholds | same, SBS rb 0xEB only | EB = b80be40c740ea00f0f0bd70b6d0c030da00fb80b = code flash 0xD518..0xD52B byte-identical
- 2026-10-08T05:20:16Z | lead | `uv run bms.py report` | rc=0, wrote reports/20261007_232027.{json,md}; status 0x00C0, PF clear
