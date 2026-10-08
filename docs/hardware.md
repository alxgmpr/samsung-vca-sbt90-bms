# Hardware: VCA-SBT90 BMS board

Current facts only. Firmware behaviour is in [protocol.md](protocol.md) and [re/](re/).

## Device and board

- Pack: Samsung **VCA-SBT90** (Jet 90 / Jet 75), 6S1P, 21.6 V nominal (design 21.9 V, 2850 mAh).
  Original cells: Samsung **INR21700-30T** (the config header at code flash 0xD410 names `21700_30T`).
- Board: **SEC VS9000N 6S1P**, Rev R1.1, P01P-00200A, dated 2018-07-25. Pack mfg date 2021-01-25, serial 415.
- SBS identity: manufacturer `SDI` (Samsung SDI), device chemistry `LION`, model `SEC_VS9000NL` (SBS 0x2F).

## U1: Renesas RAJ240080

RL78 MCU and battery analog front end (AFE) in one package. 64 KB code flash (app 0x0000–0xDBFF,
SMBus bootloader 0xDC00+), 4 KB data flash (0xF1000–0xF1FFF), 5.5 KB RAM. Datasheet R01DS0299EJ0100
(local copy `~/Downloads/RAJ240080.PDF`; it has no full AFE register list). The part is specified for
2–5 series cells; how this board measures six is not traced. AFE register use: [re/afe-map.md](re/afe-map.md).

## Fuse F1 and Q10

- **F1** = Dexerials SCP 3-terminal chemical fuse, "SF 45A" (SFK-3045x class), in series with the pack.
  The original is blown; replace with the same part (45 A, same voltage class).
- **Q10** = low-side FET that pulls the F1 heater terminal to ground.
- **The fuse is driven by MCU port P1.1** (to Q10's gate), not by the AFE FUSEOUT/FUSECUT path, which
  the firmware never uses (verified-static; [re/afe-map.md](re/afe-map.md)):
  - 0x8769–0x8783: if any PF bit (fault-mask bits 48–62) is set **and** word 0xFF552 (P10 high half =
    ManufactureDate, SBS 0x1B) ≠ 0, set 0xFFE34.0. 0x5AC9 copies it to P1 shadow 0xFFEA5.1, 0x57F4
    writes the shadow to P1. Only a reset clears 0xFFE34.0.
  - So **ManufactureDate = 0 disarms the fuse drive**: a PF still latches and the FETs still open,
    but P1.1 is never raised. P10 is `0x00004C50` (disarmed) since 2026-10-08 for assembly;
    restore value `0x52394C50`, only once PF reads clear.
  - 0x3FF1 pulses P1.1 for 15 iterations of the busy-wait at 0x5D55 (131 loops; ~0.5 ms total, inferred), interrupts off, and checks input
    P1.3 as feedback (codes 16/17 in 0xFFB84). It is reached only from the gated SBS 0x80 path
    (0x47F8), not at boot. Inferred: fuse-path self-test.
- Bench observation matching this: Q10 gate = 3.3 V (MCU logic level) while the firmware ran with the
  PF latched, 0 V with the firmware held off, 0 V after the PF clear.
- A second-level hardware protector, if fitted, can still fire F1 on cell over-voltage independently
  of the firmware. Not traced.

## Pads and connectors

| Ref | What |
|---|---|
| CN1 | 4-pin connector: GND (TP14), SCL (TP40), SDA (TP39), +. SMBus, BMS at address **0x0B**. Use this |
| TP39 / TP40 | SDA / SCL (same nets as CN1) |
| TP14 | GND |
| TP32 | TOOL0. Has a 1 kΩ pull-up to TP31: drive open-drain, don't fight it |
| TP33 | MCU RESET |
| TP31 | 3.3 V (CREG2 output). 3.3 V while the firmware runs, 0 V when the pack is asleep |
| SR1, SR2 | 1 mΩ current-sense resistors. Inferred in parallel (0.5 mΩ): at 2 mΩ the lowest hardware discharge-OC setting would trip the motor. A meter reading settles it |
| U1 pin 30 | P13.7 / INTP0, input. Read as the "charger present" flag (0xFFB55.2) used by fault 0x5C. Low on the bench with no charger. The board net driving it is not traced (continuity check, board unpowered) |
| Q8, Q9, Q11 | SOT-23 marked "B43L 18", back side, unidentified |

Edge connector, left to right: **C-, P- (CN7), P- (CN8), MODE (CN4), P+ (CN5), P+ (CN6), C+**.
P pins are doubled for current. C- is continuous with B-. Charge and discharge use separate FET paths.

Cell taps: **B-, B1, B2, B3, B4, B5, B+** (7 points, 6S).

## Bench setup (no cells)

- Fake cells: six 100 Ω resistors in series across B-..B+, each junction to its tap. Supply 22.2 V,
  100 mA limit → 3.7 V per "cell".
- F1 position bridged on the bench (remove the bridge when the new F1 goes on).
- **Wake:** the pack powers down when idle (TP31 → 0 V). Touch supply+ to C+ for ~1 s: LEDs flash blue,
  TP31 → 3.3 V, and it stays on while the firmware runs. Each wake is a full boot. C+ can be jumpered to
  B+ to keep it awake. Photo: [../images/bench-wiring.jpg](../images/bench-wiring.jpg).

## Pico wiring (RP2040, MicroPython v1.29.0)

| Pico | Board | Use |
|---|---|---|
| GP4 | TP39 SDA | SMBus |
| GP5 | TP40 SCL | SMBus |
| GND | TP14 | ground |
| GP1 | TP32 TOOL0 | driven open-drain low to enter the bootloader |
| GP2 | TP33 RESET | pin reset |
| GP0 | TP32 via 1 kΩ | earlier boot-ROM UART wiring; tools set it to input |

Pico 3V3 is not connected. No Pico pull-ups: the board's pull-ups serve SMBus and TOOL0.
SMBus: firmware mode at 40–50 kHz; bootloader at 20–50 kHz, SoftI2C (the bootloader clock-stretches,
hardware I2C times out). Port `/dev/cu.usbmodem1101` (`BMS_PORT` overrides).

## Cell install (summary)

Full steps in the README "Cell install procedure". Hardware order: F1 first (no hot air near cells),
then B-, B1..B5 in order, B+ last. Spot-weld cells. Links carry the full pack current (logged peak
−32 A, firmware limit −40 A for 3 s): 0.2 × 10 mm pure nickel doubled or Ni-Cu composite, not 6 mm
strip or nickel-plated steel. No balancing in firmware ([re/balancing.md](re/balancing.md)): match cells
to ~20 mV.

## Dead ends

- **RL78 boot-ROM serial programming over TOOL0:** entered (firmware stops) but no reply across 24
  timing/mode-byte combos. Disabled or non-standard. The SMBus bootloader made it unnecessary.
- **E1/E2 OCD debug:** closed Renesas protocol, no Pico implementation, risk of erase on auth fail.
- **SBS vendor-block writes while locked:** ACKed but ignored. Unlock is SBS 0x7A ([protocol.md](protocol.md)).
- **TI keys** (unseal 0x0414/0x3672, full access 0xFFFF/0xFFFF, 045A20 PF-clear 0x2673/0x1712, gate
  0x71/0x73): not this firmware's scheme, no effect.
- **ManufacturerAccess 0x00 16-bit sweep:** the 0x00 write handler only reacts to 0x0010 (ship/event
  log entry). Nothing to find there.
- **Hardware I2C for the bootloader:** times out on clock stretching. Use SoftI2C.
