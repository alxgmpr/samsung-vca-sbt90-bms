# Map what answers on SMBus 0x0B while TOOL0 is held low across a pin reset (main firmware not running).
from smb import *
import smb
def scan_cmds():
    w, b = {}, {}
    for c in range(256):
        try: w[c] = i2c.readfrom_mem(A, c, 3).hex()
        except OSError: pass
    return w

for p in (0,): Pin(p, Pin.IN)
for trial in range(3):
    Pin(1, Pin.OUT, value=0)                       # TOOL0 low
    Pin(2, Pin.OUT, value=0); time.sleep_ms(10); Pin(2, Pin.IN)
    time.sleep_ms(1500)
    print("trial", trial, "addr scan:", [hex(a) for a in i2c.scan()])
    w = scan_cmds()
    print("  answering cmds (raw3):", {hex(k): v for k, v in w.items()})
    time.sleep_ms(3000)
    w2 = scan_cmds()
    print("  3 s later:", {hex(k): v for k, v in w2.items()})
Pin(1, Pin.IN)
print("normal reset", reset())
