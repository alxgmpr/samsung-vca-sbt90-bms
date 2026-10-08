from dfw import *
import binascii
enter()
try:
    a = snap(); b = snap()
    for i in range(0, 4096, 64):
        tag = "" if a[i:i+64] == b[i:i+64] else " MISMATCH"
        print("DF %05X %s%s" % (0xF1000+i, binascii.hexlify(a[i:i+64]).decode(), tag))
        if tag: print("DB %05X %s" % (0xF1000+i, binascii.hexlify(b[i:i+64]).decode()))
finally:
    leave(); check()
