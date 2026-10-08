# Samsung VCA-SBT90 BMS — reverse engineering & repair notes

Device: Samsung VCA-SBT90 vacuum battery (Jet 90/75), 6S1P, 21.6 V nominal.
Board: SEC VS9000N 6S1P, Rev R1.1, P01P-00200A, 2018-07-25.
Goal: rebuild the pack (6× 21700) and clear the latched permanent-failure (PF)
that keeps the BMS trying to blow the fuse.

Session date: 2026-10-07.

## Hardware summary

- **U1 = Renesas RAJ240080** battery-management IC. RL78 core + analog front end
  (AFE) in one package. 64 KB code flash, 4 KB data flash, 5.5 KB RAM.
  Datasheet: R01DS0299EJ0100 (local copy was ~/Downloads/RAJ240080.PDF).
- **F1 = Dexerials SCP "SF 45A"** 3-terminal chemical fuse across the pack. BLOWN.
  The MCU blows it on fault via FUSEOUT; a 2nd-protection path can also blow it.
- **Q10** = low-side FET that drives the F1 heater. Its gate = 3.3 V whenever the
  firmware is running (still trying to blow the fuse) and 0 V when the firmware is
  held off. => the PF is firmware/data-flash latched, NOT a stuck external part.
- Cell taps B-, B1..B5, B+ (7 points = 6S). Current sense SR1/SR2 = 2×1 mΩ.
- Edge connector (L→R): C-, P- (CN7), P- (CN8), MODE (CN4), P+ (CN5), P+ (CN6), C+.
  C- is continuous with B-. Charging and discharging use separate FET paths.

## Key pads / connectors

- **CN1** = real 4-pin connector: GND (TP14), SCL (TP40), SDA (TP39), +.  <-- use this
- SMBus/I2C also on TP39/TP40. BMS answers at address **0x0B** (Smart Battery).
- **TP32 = TOOL0**, **TP33 = RESET(MCU)**, **TP31 = 3.3 V (CREG2 out)**.
  TOOL0 has a **1 kΩ pull-up to TP31** — drive it open-drain, don't fight it.

## Waking the board (no cells needed)

Bench "fake cells": six 100 Ω resistors in series across B-..B+, 22.2 V @ 100 mA
limit. Each junction to a cell tap. Gives 3.7 V per "cell".
The pack powers down when idle. **Wake it by touching supply+ to C+ for ~1 s**
(LEDs flash blue, TP31 -> 3.3 V, stays latched while firmware runs).

## Pico wiring (RP2040, MicroPython v1.29.0)

SMBus:  GP4 -> SDA (TP39),  GP5 -> SCL (TP40),  GND -> TP14.  Pico 3V3 NOT connected.
TOOL0:  GP1 -> TP32 (direct, driven open-drain via PIO).  GP2 -> TP33 (RESET).
        (GP0 + its 1k to TP32 is left unused — earlier wiring, harmless.)
The board's own pull-ups serve both buses, so no Pico pull-ups.

## What the SBS interface told us (firmware running)

- Manufacturer "SDI" (Samsung SDI), model "SEC_VS9000NL" (vendor reg 0x2F).
- Design V 21.9 V, design cap 2850 mAh, FCC 2390 mAh, cycle count 387,
  mfg date 2021-01-25, 6 cell voltages at SBS 0x3A-0x3F.
- **BatteryStatus (0x16) = 0x48C0** = TERMINATE CHARGE + TERMINATE DISCHARGE alarms.
- ManufacturerAccess (0x00) readback = 0xA000 (present + sealed); decoded failure
  field = "over voltage". ChargingCurrent/Voltage (0x14/0x15) = 0 (asks for nothing).
- Vendor blocks 0xE0-0xFB hold event log / snapshots (cell V, timestamps).

## Dead ends (don't repeat)

- Standard RL78 boot-ROM serial programming over TOOL0: entered (firmware stops)
  but NO reply across 24 timing/mode-byte combos. Disabled or non-standard.
- E1/E2 OCD debug protocol: closed/Renesas-only, no Pico implementation, risk of
  erase-on-auth-fail. We have no E2 anyway.
- SMBus writes to vendor blocks: ACKed but ignored (sealed). TI default unseal/full-
  access keys (0x0414/0x3672, 0xFFFF/0xFFFF) and 045A20 PF-clear keys (0x2673/0x1712),
  gate 0x71/0x73 — all no effect. Full 16-bit sweep of ManufacturerAccess 0x00
  (with and without PEC): no lasting change.

## THE WAY IN: SMBus bootloader (works)

Hold **TOOL0 (GP1) low across a pin reset** (or across power-up). The normal
firmware does not run; a flash bootloader answers at 0x0B instead.
Reliable at **20 kHz** I2C. Answers only these commands: 0x26, 0x55, 0x59, 0x70,
0x7C, 0xF0 (status/handshake), and 0xFC (memory read, write-only setup).

**Memory read (R2J240 style, confirmed):**
  write [0xFC, addr&0xFF, (addr>>8)&0xFF, (addr>>16)&0xFF, len&0xFF, (len>>8)&0xFF]
  with NO stop, then read `len` bytes.
  64-byte reads at 50 kHz are reliable; retry, and treat 6× consecutive all-FF
  as genuine blank.

**Write/erase exist** (from firmware disassembly, dispatch at 0xE445):
  command byte - 0xFA => jump table: 0xFA, 0xFB, **0xFC read**, **0xFD write**, + more.
  0xF15C = flash-erase HW setup (block table indexed by RAM 0xFF510);
  0xF12A = flash operation teardown. NOT yet exercised — see PLAN below.

## Firmware dump (DONE, verified)

- `firmware/codeflash.bin`  — 64 KB code flash. SHA256 matches across 2 independent dumps.
- `firmware/dataflash.bin`  — 4 KB data flash (0xF1000-0xF1FFF).
- `firmware/code.dis`       — full RL78 disassembly.
- Data flash = 157 Renesas R-BMS parameter records, format
  [idx][~idx][u32 LE], 6 bytes each, at 0x808-0xEC8; EEL fill (17 e8 04 00 00 00)
  after; block footer 5A A5 5A at 0xFFA. Floats visible (P19 = 2390.7 = FCC).
- Across dumps, ONLY the EEL free-space + two counters + one footer byte change
  (normal wear-leveling). All 157 parameter records are byte-stable = full config
  and calibration captured. Backups archived in backups/verified_20261007/.

## Disassembler

Built GNU objdump with RL78 support (binutils 2.42) in a scratchpad; a copy of the
output is firmware/code.dis. To rebuild:
  configure --target=rl78-elf --disable-gdb --disable-ld --disable-gas \
            --with-system-zlib --without-zstd ; make MAKEINFO=true all-binutils
  objdump -b binary -m rl78 -D --start-address=0xADDR --stop-address=0xADDR firmware/codeflash.bin

## Scripts (pico/)

- smb.py       — SMBus helpers (rw/rb/ww/wb, PEC/CRC-8, reset). Self-checks CRC.
- bl.py        — bootloader entry (TOOL0 low across reset) + block helpers.
- bl_dump.py   — memory dumper via 0xFC (edit REGIONS). Double-read verified.
- pico/experiments/pfclear.py   — SBS-side PF-clear / unseal attempts (all negative so far).
- pico/experiments/fuzz_ma.py   — ManufacturerAccess fuzzer (negative).

## STATUS / NEXT

PF CLEARED (2026-10-07). Data-flash write decoded (bootloader cmd 0xFB) and the latched
fault (param P0x17 = 4, fault bit 50) cleared by appending an EEL record P0x17 = 0.
BatteryStatus 0x48C0 -> 0x00C0, Q10 gate 0 V. Full detail at the end of WRITE_PLAN.md.
Next: hardware rebuild (new F1, 6 cells).

## Rebuild reminder

6× Samsung INR21700-30T (original cell per config header), matched & balanced before assembly,
spot-weld (don't solder cells). Connect taps in order B- ... B+.
Before fitting cells: REMOVE the F1 bench bridge and the C+ wake clip.
F1 replacement: Dexerials SCP, 45 A, same voltage class (or pull from a like board).
