# Append an EEL record P0x17 = VAL into the active block's first free slot (no erase).
# P0x17[15:0] = persistent fault-mask bits 48..63 (0xAB10 writes it, 0x839D restores it at boot).
from dfw import *
import binascii
VAL = 0x00000000
leave(); before = check(); enter()
try:
    pre = snap()
    with open("pre.hex", "w") as f: f.write(binascii.hexlify(pre).decode())
    act = active(pre); o = act - 0xF1000
    i = o + 4
    while pre[i:i + 6] != b"\xff" * 6:
        assert pre[i] ^ pre[i + 1] == 0xFF, "bad record at %05X" % (0xF1000 + i)
        i += 6
    slot = 0xF1000 + i
    assert pre[i:i + 64] == b"\xff" * 64, "free area not blank"
    rec = bytes([0x17, 0xE8]) + VAL.to_bytes(4, "little")
    print("active %05X, slot %05X (record #%d), writing %s" % (act, slot, (i - o - 4) // 6, rec.hex()))
    wr(slot, rec)
    print("PFDL status", status())
    post = snap()
    d = ["%05X:%02X>%02X" % (0xF1000 + k, pre[k], post[k]) for k in range(4096) if pre[k] != post[k]]
    print("DIFF", d)
finally:
    leave(); after = check()
