from dfw import *
leave(); check(); enter()
try:
    for c in (0x70, 0x26, 0x55, 0x59, 0x7C):
        print("%02X" % c, [I.readfrom_mem(A, c, 4).hex() for _ in range(3)])
    print("status", status())
    for a in (0xF1000, 0xF1800):
        print("blank %05X len16 ->" % a, blank(a, 16))
finally:
    leave(); check()
