from bl import *
import smb
smb.i2c = I2C(0, sda=Pin(4), scl=Pin(5), freq=10_000)
from smb import i2c as I
def blkr(c, tries=3):
    for _ in range(tries):
        try:
            r = smb.i2c.readfrom_mem(A, c, 5)
            n = r[0]
            if 1 <= n <= 3 and crc8(bytes([A << 1, c, A << 1 | 1]) + r[:n + 1]) == r[n + 1]:
                return r[1:1 + n].hex()
            return "raw " + r.hex()
        except OSError as e:
            err = e.args[0]
    return "E%s" % err
enter_bl()
seen = {}
for c in range(256):
    r = blkr(c)
    if not r.startswith("E") and r != "raw ffffffffff":
        seen[c] = r
print({hex(k): v for k, v in seen.items()})
print("repeat:", {hex(c): blkr(c) for c in seen})
leave_bl()
