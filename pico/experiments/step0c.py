# STEP 0c: enter flash-program mode (0x55), one 0xFD write to erased scratch, exit (0x59).
# Safe: FF target, bounds-checked, full snapshot diff, reset restores firmware regardless.
from bl import *
import smb
I = I2C(0, sda=Pin(4), scl=Pin(5), freq=50_000); smb.i2c = I
TGT = 0x0F1400
def rd(a, n):
    I.writeto(A, bytes([0xFC, a & 0xFF, a >> 8 & 0xFF, a >> 16 & 0xFF, n & 0xFF, n >> 8]), False)
    return I.readfrom(A, n)
def rd_ok(a, n):
    seen, ff = [], 0
    for _ in range(12):
        try: d = rd(a, n)
        except OSError: time.sleep_ms(20); continue
        if d == b"\xff" * n:
            ff += 1
            if ff >= 6: return d
            continue
        if d in seen: return d
        seen.append(d)
    return None
def snap():
    o = {}
    for a in range(0xF1000, 0xF2000, 64):
        d = rd_ok(a, 64)
        if d is None: return None
        o[a] = d
    return o
def cmd_rd(c, n=2):
    try: return I.readfrom_mem(A, c, n).hex()
    except OSError as e: return "E%d" % e.args[0]

enter_bl()
print("target before:", rd_ok(TGT, 16).hex())
pre = snap(); print("pre snap:", "OK" if pre else "FAIL")

print("enter mode 0x55 ->", cmd_rd(0x55, 3))
payload = bytes([TGT & 0xFF, TGT >> 8 & 0xFF, TGT >> 16 & 0xFF, 0x01, 0x00, 0xA5])
for frame in (bytes([0xFD]) + payload, bytes([0xFD, len(payload)]) + payload):
    try:
        I.writeto(A, frame); print("0xFD write OK:", frame.hex())
        break
    except OSError as e:
        print("0xFD write NAK (%s):" % e.args[0], frame.hex())
time.sleep_ms(100)
print("exit 0x59 ->", cmd_rd(0x59, 3))

print("target after: ", rd_ok(TGT, 16).hex())
post = snap()
if pre and post:
    ch = [(a, pre[a].hex(), post[a].hex()) for a in pre if pre[a] != post[a]]
    print("changed rows:", len(ch))
    for a, b, c in ch: print("  %05X\n   pre %s\n   post %s" % (a, b, c))
leave_bl()
