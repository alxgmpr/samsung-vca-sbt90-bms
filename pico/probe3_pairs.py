# Characterise the three ManufacturerAccess values that changed the 0x00 readback (0xA000 -> 0x8000).
from smb import *
import smb
smb.i2c = I2C(0, sda=Pin(4), scl=Pin(5), freq=100_000)
CAND = (0xC3BE, 0xC428, 0xDB4E)
CTRL = (0xC3BD, 0xC3BF, 0x1234)

def r00(n=4, gap=0):
    out = []
    for _ in range(n):
        try: out.append("%04x" % rw(0x00))
        except OSError: out.append("NAK")
        if gap: time.sleep_ms(gap)
    return " ".join(out)

def nakmap():
    m = bytearray(256)
    for c in range(256):
        try: rw(c); m[c] = 1
        except OSError: pass
    return m

def ee_writable():
    try:
        wb(0xEE, bytes([0x5A]) + bytes(15)); time.sleep_ms(50)
        ok = rb(0xEE)[0] == 0x5A
        if ok: wb(0xEE, bytes(16)); time.sleep_ms(50)
        return ok
    except OSError:
        return "NAK"

def mode_writable():
    o = rw(0x03)
    ww(0x03, o & ~0x6000); time.sleep_ms(30)
    n = rw(0x03); ww(0x03, o)
    return n != o

print("reset", reset()); base_map = nakmap()
print("baseline 00:", r00(), "| readable cmds:", sum(base_map))

print("== pairs/triples, then unlock checks")
seqs = [(a, b) for a in CAND for b in CAND] + [CAND, tuple(reversed(CAND))]
for seq in seqs:
    reset()
    for v in seq: ww(0x00, v)
    after = r00(3)
    m = nakmap(); newly = [hex(c) for c in range(256) if m[c] and not base_map[c]]
    gone = [hex(c) for c in range(256) if base_map[c] and not m[c]]
    print(" ".join("%04x" % v for v in seq), "| 00:", after, "| EE w:", ee_writable(), "| mode w:", mode_writable(),
          "| new cmds:", newly, "| lost:", gone, "| 16=%04x" % rw(0x16))
print("final reset", reset())
