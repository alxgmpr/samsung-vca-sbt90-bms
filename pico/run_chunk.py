# Fuzz ManufacturerAccess (0x00) single-word writes; log any change in a stable "signature" of the BMS.
# START/END are substituted per chunk by the host.
from smb import *
START, END = 0x0000, 0xFFFF
PEC = True
BLOCK = False
import smb; smb.i2c = I2C(0, sda=Pin(4), scl=Pin(5), freq=100_000)
WORDS = (0x00, 0x03, 0x14, 0x15, 0x16, 0x82, 0x84, 0x8A, 0xA2, 0xB0, 0xB1, 0xB6, 0xB8)
PROBES = (0x24, 0x27, 0x30, 0x44, 0x45, 0x51, 0x55, 0x59, 0x60, 0x70, 0x86, 0x90, 0xC6, 0xF6)

def sig():
    s = []
    for c in WORDS:
        try: s.append(rw(c))
        except OSError: s.append(-1)
    for c in PROBES:
        try: s.append(rw(c))
        except OSError: s.append(-1)
    try: s.append(rb(0x23))
    except OSError: s.append(-1)
    return s

NAMES = ["w%02x" % c for c in WORDS] + ["p%02x" % c for c in PROBES] + ["b23"]
def diff(a, b):
    return " ".join("%s:%s>%s" % (n, x if not isinstance(x, int) else hex(x), y if not isinstance(y, int) else hex(y))
                    for n, x, y in zip(NAMES, a, b) if x != y)

def volts():
    try: return rw(0x09)
    except OSError: return None

print("reset", reset()); T0 = time.ticks_ms()
base = sig(); v0 = volts()
print("start %04x-%04x pec=%s block=%s base ok, V=%s" % (START, END, PEC, BLOCK, v0))
for v in range(START, END + 1):
    try:
        if BLOCK: wb(0x00, bytes([v & 0xFF, v >> 8]), pec=PEC)
        else: ww(0x00, v, pec=PEC)
    except OSError:
        print("%04x write NAK" % v)
    s = sig()
    if s != base:
        time.sleep_ms(200); s2 = sig()
        if all(x == -1 for x in s2[:len(WORDS)]):
            print("%04x DEVICE SILENT -> reset" % v)
            t = reset(); print("   reset ->", t)
            if t is None:
                print("STOP: no recovery"); break
            s2 = sig()
        print("%04x t=%ds CHANGE %s" % (v, time.ticks_diff(time.ticks_ms(), T0) // 1000, diff(base, s2) or "(transient: %s)" % diff(base, s)))
        base = s2
    if v & 0xFF == 0xFF:
        vv = volts()
        if vv is None or v0 is None or abs(vv - v0) > 400:
            print("STOP: voltage reading moved %s -> %s at %04x" % (v0, vv, v)); break
        print("..%04x V=%s" % (v, vv))
print("done", hex(v))
