# STEP 0: prove bootloader 0xFD write on an ERASED scratch byte. Safe: bounds-checked,
# target is FF, full data-flash snapshot before/after to catch any unintended change.
from bl import *
import smb
I = I2C(0, sda=Pin(4), scl=Pin(5), freq=50_000); smb.i2c = I
TGT = 0x0F1400          # scratch in the unused first 2KB of data flash (reads FF)
def rd(addr, n):
    I.writeto(A, bytes([0xFC, addr & 0xFF, addr >> 8 & 0xFF, addr >> 16 & 0xFF, n & 0xFF, n >> 8]), False)
    return I.readfrom(A, n)
def rd_ok(addr, n):
    seen, ff = [], 0
    for _ in range(12):
        try: d = rd(addr, n)
        except OSError: time.sleep_ms(20); continue
        if d == b"\xff" * n:
            ff += 1
            if ff >= 6: return d
            continue
        if d in seen: return d
        seen.append(d)
    return None
def snap():
    out = {}
    for a in range(0xF1000, 0xF2000, 64):
        d = rd_ok(a, 64)
        if d is None: return None
        out[a] = d
    return out

enter_bl()
print("target %05X before:" % TGT, rd_ok(TGT, 16).hex())
pre = snap()
print("pre snapshot:", "OK" if pre else "FAILED")

# One well-formed write: cmd 0xFD, addr(3 LE), len(2 LE)=1, data=0xA5
payload = bytes([TGT & 0xFF, TGT >> 8 & 0xFF, TGT >> 16 & 0xFF, 0x01, 0x00, 0xA5])
cmd = bytes([0xFD, len(payload)]) + payload   # [cmd][count][addr3][len2][data]
try:
    I.writeto(A, cmd); print("0xFD write issued:", cmd.hex())
except OSError as e:
    print("0xFD write NAK:", e)
time.sleep_ms(50)

print("target %05X after: " % TGT, rd_ok(TGT, 16).hex())
post = snap()
if pre and post:
    changed = [(a, pre[a].hex(), post[a].hex()) for a in pre if pre[a] != post[a]]
    print("changed 64B rows:", len(changed))
    for a, b, c in changed: print("  %05X\n   pre  %s\n   post %s" % (a, b, c))
else:
    print("post snapshot:", "OK" if post else "FAILED")
leave_bl()
