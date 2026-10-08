# STEP 0d: SoftI2C (tolerates clock-stretch during flash unlock). Enter 0x55, 0xFD write to
# erased scratch, exit 0x59, read back. Safe: FF targets, witnesses checked, backups exist.
from machine import Pin, SoftI2C
import time
A = 0x0B
# bootloader entry
Pin(0, Pin.IN)
Pin(1, Pin.OUT, value=0)
Pin(2, Pin.OUT, value=0); time.sleep_ms(10); Pin(2, Pin.IN)
time.sleep_ms(1500)
I = SoftI2C(sda=Pin(4), scl=Pin(5), freq=50_000)

def rd(a, n):
    I.writeto(A, bytes([0xFC, a & 0xFF, a >> 8 & 0xFF, a >> 16 & 0xFF, n & 0xFF, n >> 8]), False)
    return I.readfrom(A, n)
def rd_ok(a, n):
    seen, ff = [], 0
    for _ in range(14):
        try: d = rd(a, n)
        except OSError: time.sleep_ms(20); continue
        if d == b"\xff" * n:
            ff += 1
            if ff >= 6: return d
            continue
        if d in seen: return d
        seen.append(d)
    return None
WIT = [0xF1808, 0xF1880, 0xF1940, 0xF19C0, 0xF1A00, 0xF1B80, 0xFFA0 + 0xF1000]
def wsnap(): return {a: rd_ok(a, 16) for a in WIT}

for TGT in (0x0F1400, 0x0F1E20):
    print("=== target %05X ===" % TGT)
    print(" before:", (rd_ok(TGT, 16) or b'').hex())
    w0 = wsnap()
    try:
        r = I.readfrom_mem(A, 0x55, 3); print(" enter 0x55 ->", r.hex())
    except OSError as e:
        print(" enter 0x55 OSError", e.args[0], "(stretch) - continuing")
    payload = bytes([TGT & 0xFF, TGT >> 8 & 0xFF, TGT >> 16 & 0xFF, 0x01, 0x00, 0xA5])
    try:
        I.writeto(A, bytes([0xFD, len(payload)]) + payload); print(" 0xFD write OK")
    except OSError as e:
        print(" 0xFD write OSError", e.args[0])
    time.sleep_ms(150)
    try:
        r = I.readfrom_mem(A, 0x59, 3); print(" exit 0x59 ->", r.hex())
    except OSError as e:
        print(" exit 0x59 OSError", e.args[0])
    print(" after: ", (rd_ok(TGT, 16) or b'').hex())
    w1 = wsnap()
    bad = [hex(a) for a in WIT if w0[a] != w1[a]]
    print(" witnesses changed:", bad or "none")

Pin(1, Pin.IN)
Pin(2, Pin.OUT, value=0); time.sleep_ms(10); Pin(2, Pin.IN)
print("reset to firmware")
