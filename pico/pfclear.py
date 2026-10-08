from smb import *
import smb
smb.i2c = I2C(0, sda=Pin(4), scl=Pin(5), freq=50_000)
FET = {0: "DSG on CHG on", 1: "DSG on CHG off", 2: "DSG off CHG off", 3: "DSG off CHG on"}
FAIL = {0: "fuse/no PF detail", 1: "cell imbalance", 2: "over voltage", 3: "FET failure"}
def dec(w):
    return "%04x [%s | fail=%s | state=%x]" % (w, FET[w >> 14 & 3], FAIL[w >> 12 & 3], w >> 8 & 0xF)
def state(tag):
    try:
        print("%-34s 00=%s 16=%04x 14=%d 15=%d 03=%04x" % (tag, dec(rw(0)), rw(0x16), rw(0x14), rw(0x15), rw(0x03)))
    except OSError as e:
        print(tag, "read error", e)

print("reset", reset()); state("baseline")
print("== 0x71/0x73 gate")
for g in (0x0214, 0x0215, 0x0216, 0x0217):
    try:
        ww(0x71, g); time.sleep_ms(150)
        try: print("gate %04x -> 0x73: %s" % (g, i2c.readfrom_mem(A, 0x73, 34).hex()))
        except OSError as e: print("gate %04x -> 0x73 read NAK" % g)
    except OSError: print("gate %04x write NAK" % g)

SEQS = [
    ("PF clear", [0x2673, 0x1712]),
    ("unseal + PF clear", [0x0414, 0x3672, 0x2673, 0x1712]),
    ("full access + PF clear", [0xFFFF, 0xFFFF, 0x2673, 0x1712]),
    ("unseal + full + PF clear", [0x0414, 0x3672, 0xFFFF, 0xFFFF, 0x2673, 0x1712]),
    ("PF clear reversed", [0x1712, 0x2673]),
]
for pec in (False, True):
    for name, seq in SEQS:
        reset()
        for v in seq:
            ww(0x00, v, pec=pec); time.sleep_ms(50)
        time.sleep_ms(500)
        state("%s%s" % (name, " +PEC" if pec else ""))
