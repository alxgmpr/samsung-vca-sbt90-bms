# Bootloader-mode helpers: enter by holding TOOL0 low across a pin reset.
from smb import *
def enter_bl():
    Pin(0, Pin.IN)
    Pin(1, Pin.OUT, value=0)
    Pin(2, Pin.OUT, value=0); time.sleep_ms(10); Pin(2, Pin.IN)
    time.sleep_ms(1500)
def leave_bl():
    Pin(1, Pin.IN); return reset()
CMDS = (0x27, 0x55, 0x59, 0x70, 0x7C, 0xF0, 0xFC)
def rraw(c, n=36):
    return i2c.readfrom_mem(A, c, n)
def blk(c):
    r = rraw(c); n = r[0]
    if n > 32: return None, r
    ok = crc8(bytes([A << 1, c, A << 1 | 1]) + r[:n + 1]) == r[n + 1]
    return r[1:1 + n], ok
