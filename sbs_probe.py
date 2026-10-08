# MicroPython on a Pico. Wiring: GND->TP14, GP4->TP39 (SDA), GP5->TP40 (SCL). Pico 3V3 NOT connected.
# Board pull-ups only, so no internal pull-ups here. Reads standard Smart Battery (SBS) registers.
from machine import I2C, Pin

i2c = I2C(0, sda=Pin(4), scl=Pin(5), freq=50_000)  # SMBus tops out at 100 kHz; 50k gives margin

found = i2c.scan()
print("devices:", [hex(a) for a in found])
ADDR = 0x0B if 0x0B in found else (found[0] if found else None)

WORDS = {  # cmd: (name, signed, scale, unit)
    0x08: ("Temperature", False, 0.1, "K"),
    0x09: ("Voltage", False, 1, "mV"),
    0x0A: ("Current", True, 1, "mA"),
    0x0D: ("RelativeSOC", False, 1, "%"),
    0x0F: ("RemainingCap", False, 1, "mAh"),
    0x10: ("FullChargeCap", False, 1, "mAh"),
    0x16: ("BatteryStatus", False, None, ""),
    0x17: ("CycleCount", False, 1, ""),
    0x18: ("DesignCap", False, 1, "mAh"),
    0x1C: ("SerialNumber", False, 1, ""),
}
BLOCKS = {0x20: "ManufacturerName", 0x21: "DeviceName", 0x22: "Chemistry"}

if ADDR is None:
    print("nothing answered - check TP31 is 3.3 V and SDA/SCL aren't swapped")
else:
    for cmd, (name, signed, scale, unit) in WORDS.items():
        try:
            v = int.from_bytes(i2c.readfrom_mem(ADDR, cmd, 2), "little")
            if signed and v & 0x8000:
                v -= 0x10000
            print(f"{cmd:#04x} {name:14} {hex(v) if scale is None else round(v * scale, 1)} {unit}")
        except OSError as e:
            print(f"{cmd:#04x} {name:14} NAK ({e})")
    for cmd, name in BLOCKS.items():
        try:
            raw = i2c.readfrom_mem(ADDR, cmd, 33)
            print(f"{cmd:#04x} {name:14} {raw[1:1 + min(raw[0], 32)]}")
        except OSError as e:
            print(f"{cmd:#04x} {name:14} NAK ({e})")
