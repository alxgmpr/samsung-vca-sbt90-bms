from dfw import *
import dfw
from machine import I2C
enter()
try:
    img0 = rd_ok(0xF1000, 16); base = 0xF1000 if img0 != b"\xff"*16 else 0xF1800
    print("active %05X" % base)
    for off, n in ((0x40,64),(0x40,32),(0x60,32),(0x40,16),(0x50,16),(0x44,16),(0x3C,16),(0x40,8),(0x00,64),(0x100,64),(0x100,16),(0x110,16)):
        a = base + off
        try: r = [rd(a, n).hex()[:32] for _ in range(3)]
        except OSError as e: r = "E%d" % e.args[0]
        print("%05X n=%2d" % (a, n), r)
finally:
    leave()
