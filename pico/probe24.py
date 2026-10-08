# Probe cmd 0x24 as a DATA-flash accessor (READ-only phase, fully safe).
# Compare against the known 0xFC read of 0xF1880.
from machine import Pin, SoftI2C
import time
A = 0x0B
Pin(0, Pin.IN); Pin(1, Pin.OUT, value=0)
Pin(2, Pin.OUT, value=0); time.sleep_ms(10); Pin(2, Pin.IN); time.sleep_ms(1500)
I = SoftI2C(sda=Pin(4), scl=Pin(5), freq=30_000)
TGT = 0xF1080

def fc_read(a, n):
    I.writeto(A, bytes([0xFC, a & 0xFF, a >> 8 & 0xFF, a >> 16 & 0xFF, n & 0xFF, n >> 8]), False)
    return I.readfrom(A, n)
ref = fc_read(TGT, 16)
print("0xFC reference @%05X:" % TGT, ref.hex())

def tryit(tag, fn):
    try:
        r = fn(); print("%-38s %s" % (tag, r.hex() if isinstance(r, (bytes, bytearray)) else r))
    except OSError as e:
        print("%-38s OSError %d" % (tag, e.args[0]))

setup = bytes([TGT & 0xFF, TGT >> 8 & 0xFF, TGT >> 16 & 0xFF, 0x10, 0x00])  # addr3,len2=16
# A: like 0xFC — write [0x24][count][addr3][len2] no-stop, then read 16
tryit("A 0x24 setup no-stop + read16", lambda: (I.writeto(A, bytes([0x24, len(setup)]) + setup, False), I.readfrom(A, 16))[1])
# B: block-read mem 0x24 (register-style)
tryit("B readfrom_mem(0x24,18)", lambda: I.readfrom_mem(A, 0x24, 18))
# C: write setup with stop, then plain read16
tryit("C 0x24 setup +stop, then read16", lambda: (I.writeto(A, bytes([0x24, len(setup)]) + setup), I.readfrom(A, 16))[1])
# D: write setup, then read buffer via 0x59
tryit("D 0x24 setup, then readfrom_mem(0x59,18)", lambda: (I.writeto(A, bytes([0x24, len(setup)]) + setup), I.readfrom_mem(A, 0x59, 18))[1])
# E: enter 0x55 first, then A
try: I.readfrom_mem(A, 0x55, 3)
except OSError: pass
tryit("E after 0x55: setup no-stop + read16", lambda: (I.writeto(A, bytes([0x24, len(setup)]) + setup, False), I.readfrom(A, 16))[1])

Pin(1, Pin.IN); Pin(2, Pin.OUT, value=0); time.sleep_ms(10); Pin(2, Pin.IN)
print("reset to firmware")
