# Dump memory via bootloader 0xFC read (write [FC a0 a1 a2 n0 n1] with no STOP, then read n bytes).
from bl import *
import smb, sys
I = I2C(0, sda=Pin(4), scl=Pin(5), freq=50_000); smb.i2c = I
CH = 64
def rd(addr, n):
    I.writeto(A, bytes([0xFC, addr & 0xFF, addr >> 8 & 0xFF, addr >> 16 & 0xFF, n & 0xFF, n >> 8]), False)
    return I.readfrom(A, n)
def rd_ok(addr, n):
    seen, ff = [], 0
    for _ in range(12):
        try:
            d = rd(addr, n)
        except OSError:
            time.sleep_ms(20); continue
        if d == b"\xff" * n:
            ff += 1
            if ff >= 6: return d
            continue
        if d in seen: return d
        seen.append(d)
    return None
enter_bl()
for start, end in REGIONS:
    bad = 0
    for addr in range(start, end, CH):
        d = rd_ok(addr, CH)
        if d is None:
            bad += 1; print("X %05x" % addr)
        else:
            print("D %05x %s" % (addr, d.hex()))
    print("# region %05x-%05x bad chunks %d" % (start, end, bad))
leave_bl()
