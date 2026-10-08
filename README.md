# Samsung VCA-SBT90 battery — BMS reverse engineering & PF clear

Right-to-repair project on a Samsung **VCA-SBT90** vacuum battery (Jet 90 / Jet 75, 6S1P, 21.6 V).
The pack's BMS had latched a **permanent failure (PF)** and blown its chemical fuse, so it would never
charge or discharge again, even with new cells. This repo holds the tooling and notes used to get into
the BMS over SMBus, dump its flash, and clear the PF so the board can be reused with fresh cells.

![VCA-SBT90 BMS board, front](images/board-front.jpg)

*Board: SEC VS9000N 6S1P, Rev R1.1, P01P-00200A (2018-07-25). U1 = Renesas RAJ240080 (RL78 MCU + analog front end).*

![Bench wiring: 6 × 100 Ω ladder, supply, TOOL0 1 kΩ pull-up](images/bench-wiring.jpg)

*Bench wiring: six 100 Ω resistors between B−…B+ stand in for the cells (22.2 V, 100 mA limit). TOOL0 (TP32) has an on-board 1 kΩ pull-up to TP31 (3.3 V). Q10 is the F1 fuse-blow trigger FET.*

## Status

- PF cleared (2026-10-07). BatteryStatus `0x48C0` → `0x00C0` (TERMINATE CHARGE/DISCHARGE gone),
  charge request 0 → 150 mA / 25.6 V, fuse-drive FET Q10 gate 3.3 V → 0 V. Calibration and config intact
  (FCC 2390 mAh, 387 cycles, model `SEC_VS9000NL`).
- Next: replace F1 (Dexerials SCP 45 A), fit 6 matched cells (Samsung INR18650-30Q).

## How it works (short version)

1. **Access:** a Raspberry Pi Pico (MicroPython) on the board's SMBus connector CN1 (SDA TP39, SCL TP40,
   GND TP14), address `0x0B`. Holding **TOOL0 (TP32) low across a reset (TP33)** starts a flash bootloader
   instead of the battery firmware.
2. **Read:** bootloader cmd `0xFC` — write `[FC a0 a1 a2 n0 n1]` with no STOP, then read `n` bytes.
3. **Write data flash:** bootloader cmd `0xFB` — `[FB][3+n][a0 a1 a2][n bytes][PEC]`, programmed at STOP
   via the Renesas PFDL; result readable with cmd `0x70`. `0x24` = blank check, `0x21` = 1 KB block erase.
4. **Data flash** is an append-only EEPROM emulation: two rotating 2 KB blocks of 6-byte records
   `[idx][~idx][u32 LE]`, newest record per index wins, 158 params (0x00–0x9D).
5. **The PF:** the firmware keeps a 64-bit fault mask in RAM; bits 48–62 are permanent faults and are
   persisted in **param 0x17**. This unit had `P0x17 = 4`: fault bit 50 = code 0xCA, the dead-cell check
   (a cell under 1000 mV after wake). The fault log snapshot shows cell 3 at 0 V when it tripped, ~440
   powered hours before the bench work. Appending the record
   `17 E8 00 00 00 00` to the active block cleared it (`pico/pf_append.py`). Undo = append `17 E8 04 00 00 00`.

Firmware RE (static, from `firmware/code.dis`):

| Doc | Contents |
|---|---|
| [docs/re/thresholds.md](docs/re/thresholds.md) | Every protection limit/timer, constant address, fault code (all fixed in code flash 0xD550-0xD5E4) |
| [docs/re/fault-codes.md](docs/re/fault-codes.md) | Code -> fault bit -> condition table for the @0x2422 table |
| [docs/re/param-names.md](docs/re/param-names.md) | Names/units for all 158 params (P00-P9D), SBS mappings |
| [docs/re/balancing.md](docs/re/balancing.md) | Evidence that the firmware does no cell balancing |
| [docs/re/unlock.md](docs/re/unlock.md) | SBS 0x7A = 0x835A unlock, gated vendor commands, no-bootloader param-write proposal |
| [docs/re/_board_log.md](docs/re/_board_log.md) | Log of every board action taken during the RE |

Full details: [docs/SESSION_NOTES.md](docs/SESSION_NOTES.md) (hardware map, wiring, dead ends) and
[docs/WRITE_PLAN.md](docs/WRITE_PLAN.md) (bootloader protocol decode, write proof, PF identification).

## Layout

| Path | Contents |
|---|---|
| `bms.py` | Host CLI wrapping the Pico tools (status / params / backup / set-param) |
| `pico/` | MicroPython tools: `smb.py` (SMBus/PEC), `bl.py` + `dfw.py` (bootloader read/write, verified snapshots, intact check), `sbs_probe.py`, `bl_dump.py`/`run_dump.py`, `pf_append.py`, `pf_verify.py` |
| `pico/experiments/` | Probes and one-off experiments from the investigation (boot-ROM, fuzzing, write framing tests) |
| `firmware/` | `codeflash.bin` (64 KB), `dataflash.bin` (4 KB), `code.dis` (RL78 disassembly), `df_pre_pfclear.hex` (data flash right before the fix) |
| `backups/` | Verified dumps with SHA256SUMS, SBS register backups |
| `dumps/` | Raw dump/probe outputs |
| `logs/` | Session logs from each run |
| `docs/` | Notes and the write/PF write-up |
| `images/` | Photos |

## Usage

Host CLI (needs `mpremote`; the Pico on `/dev/cu.usbmodem1101`, override with `BMS_PORT`; pack awake with supply on C+):

```
uv run bms.py status                 # decoded SBS: pack/cell volts, capacity, status flags, PF verdict
uv run bms.py params [--json]        # every data-flash param (newest record per index), via the bootloader
uv run bms.py backup [FILE]          # save the 4 KB data-flash image (default backups/df_<time>.bin)
uv run bms.py set-param IDX VALUE    # append one record (asks first, saves a pre-write image, verifies the diff)
uv run bms.py log [--json]           # decoded fault/event log with cell snapshots
uv run bms.py status --json          # same readout as JSON
uv run bms.py report                 # status + log + named params + raw image -> reports/<time>.json + .md
```

Lower-level scripts run directly: `mpremote connect /dev/cu.usbmodem1101 cp pico/dfw.py pico/smb.py : + run pico/pf_verify.py`.

## Safety

Work on a bench supply through a resistor ladder (6 × 100 Ω, 22.2 V, 100 mA limit) with no real cells
fitted, and keep a backup of the data flash before any write. This is a 6S lithium pack; the PF exists
for a reason. Here it was a dead original cell. **When fitting cells:** the dead-cell check re-arms on
every wake, so connect all cells/taps before the board can power up, and confirm `bms.py status` shows
PF clear before fitting the new F1 (a re-trip would blow it).

The firmware does **not balance cells** ([balancing.md](docs/re/balancing.md)), and it latches a PF on imbalance
(code 0xCC: spread > 195 mV while charging above 3.7 V, or > 170/200 mV at rest, for 20 s) and on any cell
> 4300 mV for 5 s (0xC8). Match the six cells to within ~20 mV at the same state of charge, don't fit cells above
4.2 V, and check the spread with `bms.py status` after each of the first charges. P17's high word is a
protection-disable mask restored at every boot; it must read 0 (`bms.py params`). The config header at 0xD410
names `21700_30T`, so the original cells were probably 21700, not 18650: check the holder before buying cells.

Firmware images are Samsung SDI's; keep this repo private.
