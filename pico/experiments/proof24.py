# Prove cmd 0x24 programs a data-flash byte. Target = middle of the ERASED spare EEL block
# (self-heals on next GC). Multi-read verify + active-block witness. One bl session.
from machine import Pin, SoftI2C
import time
A = 0x0B
def crc8(data, c=0):
    for b in data:
        c ^= b
        for _ in range(8):
            c = ((c << 1) ^ 0x07) & 0xFF if c & 0x80 else (c << 1) & 0xFF
    return c
Pin(0, Pin.IN); Pin(1, Pin.OUT, value=0)
Pin(2, Pin.OUT, value=0); time.sleep_ms(10); Pin(2, Pin.IN); time.sleep_ms(1500)
I = SoftI2C(sda=Pin(4), scl=Pin(5), freq=40_000)

def rd(a, n):
    I.writeto(A, bytes([0xFC, a & 0xFF, a >> 8 & 0xFF, a >> 16 & 0xFF, n & 0xFF, n >> 8]), False)
    return I.readfrom(A, n)
def rd_ok(a, n):
    seen, ff = [], 0
    for _ in range(16):
        try: d = rd(a, n)
        except OSError: time.sleep_ms(15); continue
        if d == b"\xff" * n:
            ff += 1
            if ff >= 7: return d
            continue
        if d in seen: return d
        seen.append(d)
    return None

# detect active vs spare block
b0 = rd_ok(0xF1000, 16); b1 = rd_ok(0xF1800, 16)
active = 0xF1000 if (b0 and b0 != b"\xff"*16) else 0xF1800
spare = 0xF1800 if active == 0xF1000 else 0xF1000
TGT = spare + 0x400
print("active block %05X, spare %05X, scratch TGT %05X" % (active, spare, TGT))
print("TGT before:", (rd_ok(TGT, 8) or b'?').hex())
WIT = [active, active+0x80, active+0x140, active+0x200]
w0 = {a: rd_ok(a, 16) for a in WIT}

try: I.readfrom_mem(A, 0x55, 3); print("0x55 mode entered")
except OSError: print("0x55 entered (stretch)")

payload = bytes([TGT & 0xFF, TGT >> 8 & 0xFF, TGT >> 16 & 0xFF, 0x01, 0x00, 0xA5])  # addr3,len2=1,data
variants = [
    ("count,noPEC", bytes([0x24, len(payload)]) + payload),
    ("count,PEC",   bytes([0x24, len(payload)+1]) + payload + bytes([crc8(bytes([A<<1, 0x24, len(payload)+1]) + payload)])),
    ("noCount",     bytes([0x24]) + payload),
]
for tag, frame in variants:
    try:
        I.writeto(A, frame); ack = "ACK"
    except OSError as e:
        ack = "NAK%d" % e.args[0]
    time.sleep_ms(120)
    got = rd_ok(TGT, 8)
    print("%-12s %-22s -> ACK:%s  TGT:%s" % (tag, frame.hex(), ack, (got or b'?').hex()))
    if got and got[0] != 0xFF:
        print("  *** PROGRAMMED ***")
        break

try: I.readfrom_mem(A, 0x59, 3)
except OSError: pass
w1 = {a: rd_ok(a, 16) for a in WIT}
bad = [hex(a) for a in WIT if w0[a] != w1[a]]
print("active-block witnesses changed:", bad or "none (intact)")
Pin(1, Pin.IN); Pin(2, Pin.OUT, value=0); time.sleep_ms(10); Pin(2, Pin.IN)
print("reset to firmware")
