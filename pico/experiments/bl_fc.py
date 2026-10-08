from bl import *
import smb
I = I2C(0, sda=Pin(4), scl=Pin(5), freq=20_000); smb.i2c = I
def hdr(addr, n): return bytes([addr & 0xFF, addr >> 8 & 0xFF, addr >> 16 & 0xFF, n & 0xFF, n >> 8])
def try_read(tag, fn):
    try: print("%-28s %s" % (tag, fn()))
    except OSError as e: print("%-28s E%s" % (tag, e.args[0]))
def fcstate():
    try: return I.readfrom_mem(A, 0xFC, 6).hex()
    except OSError as e: return "E%s" % e.args[0]

enter_bl()
print("0xFC before:", fcstate(), "| 0x70:", I.readfrom_mem(A, 0x70, 3).hex())
for addr in (0xFEF00, 0x00000):
    n = 16
    print("== addr %05x" % addr)
    # V1 karosium: raw write [FC a0 a1 a2 n0 n1], stop, then plain read
    try_read("V1 raw write + read", lambda: (I.writeto(A, bytes([0xFC]) + hdr(addr, n)), I.readfrom(A, n))[1].hex())
    try_read("   0xFC after / 0x70", lambda: fcstate() + " / " + I.readfrom_mem(A, 0x70, 3).hex())
    # V3 repeated start
    try_read("V3 write(no stop) + read", lambda: (I.writeto(A, bytes([0xFC]) + hdr(addr, n), False), I.readfrom(A, n))[1].hex())
    # V2 SMBus block write then block read of FC
    try_read("V2 block write + FC read", lambda: (I.writeto_mem(A, 0xFC, bytes([5]) + hdr(addr, n)), I.readfrom_mem(A, 0xFC, n + 2))[1].hex())
    print("   0x55/0x59/0x70 still:", I.readfrom_mem(A, 0x55, 3).hex(), I.readfrom_mem(A, 0x59, 4).hex(), I.readfrom_mem(A, 0x70, 3).hex())
leave_bl()
