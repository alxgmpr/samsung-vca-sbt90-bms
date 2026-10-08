# Prove the 0xFB data-flash write on one erased byte in the middle of the spare EEL block.
from dfw import *
leave(); check()
enter()
try:
    pre = snap()
    act = active(pre); spare = 0xF1000 if act == 0xF1800 else 0xF1800
    TGT = spare + 0x400
    print("active %05X spare %05X TGT %05X" % (act, spare, TGT))
    assert pre[spare - 0xF1000:spare - 0xF1000 + 0x800] == b"\xff" * 0x800, "spare not blank"
    print("status before", status())
    print("blank TGT", blank(TGT, 1))
    wr(TGT, b"\xa5")
    print("status after wr", status())
    print("blank TGT", blank(TGT, 1))
    post = snap()
    d = [(0xF1000 + i, pre[i], post[i]) for i in range(4096) if pre[i] != post[i]]
    print("DIFF", ["%05X:%02X>%02X" % x for x in d])
finally:
    leave(); check()
