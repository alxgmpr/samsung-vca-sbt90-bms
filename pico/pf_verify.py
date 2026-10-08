from dfw import *
import smb
check()
for k in range(3):
    r = smb.reset(); time.sleep_ms(1500)
    print("reset", k, "ms", r, "stat %04X ma %04X chgI %s chgV %s" % (smb.rw(0x16), smb.rw(0x00), smb.rw(0x14), smb.rw(0x15)))
for t in range(6):
    time.sleep(10)
    print("t+%ds stat %04X ma %04X chgI %d chgV %d volt %d" % (10*(t+1), smb.rw(0x16), smb.rw(0x00), smb.rw(0x14), smb.rw(0x15), smb.rw(0x09)))
check()
