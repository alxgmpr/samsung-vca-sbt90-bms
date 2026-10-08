# Data-flash access through the SMBus bootloader (decoded from the 0xEC25 slave ISR).
#  read : write [0xFC a0 a1 a2 n0 n1] no-stop, read n
#  write: [0xFB][count=3+n][a0 a1 a2][n data][PEC]  -> runs PFDL write (cmd 4) at STOP (0xE7CD/0xE7E3)
#         bounds (0xE6AC): 0xF1000 <= addr, addr+n <= 0xF2000, n <= 160
#  status: read 0x70 -> [ff4e7 = last PFDL result, 0 = OK][PEC]
from machine import Pin, SoftI2C
import time
A = 0x0B
I = SoftI2C(sda=Pin(4), scl=Pin(5), freq=40_000)

def crc8(data, c=0):
    for b in data:
        c ^= b
        for _ in range(8):
            c = ((c << 1) ^ 0x07) & 0xFF if c & 0x80 else (c << 1) & 0xFF
    return c

def enter():
    Pin(0, Pin.IN); Pin(1, Pin.OUT, value=0)
    Pin(2, Pin.OUT, value=0); time.sleep_ms(10); Pin(2, Pin.IN); time.sleep_ms(1500)

def leave():  # release TOOL0, pin reset into firmware
    Pin(1, Pin.IN); Pin(2, Pin.OUT, value=0); time.sleep_ms(10); Pin(2, Pin.IN)

def rd(a, n):
    I.writeto(A, bytes([0xFC, a & 0xFF, a >> 8 & 0xFF, a >> 16 & 0xFF, n & 0xFF, n >> 8]), False)
    return I.readfrom(A, n)

JUNK = [bytes([b]) for b in (0x02, 0x08, 0x20, 0x80)]  # reads sometimes return a uniform walking bit

def rd_ok(a, n):  # single bootloader reads are flaky: drop walking-bit junk, need 2 matches, or 7x all-FF
    seen, ff = [], 0
    for _ in range(30):
        try: d = rd(a, n)
        except OSError: time.sleep_ms(15); continue
        if d[:1] in JUNK and d == d[:1] * n: continue
        if d == b"\xff" * n:
            ff += 1
            if ff >= 7: return d
            continue
        if d in seen: return d
        seen.append(d)
    return None

def snap(lo=0xF1000, hi=0xF2000, step=64):
    out = bytearray()
    for a in range(lo, hi, step):
        d = rd_ok(a, step)
        if d is None: raise OSError("unreadable %05X" % a)
        out += d
    return bytes(out)

def rbyte(c):  # bootloader read reply = [count][data][PEC] (0xEF81); 0x70 = PFDL result ff4e7, 0x26 = blank result ff4e6
    for _ in range(8):
        r = I.readfrom_mem(A, c, 3)
        if r[0] == 1 and crc8(bytes([A << 1, c, A << 1 | 1]) + r[:2]) == r[2]: return r[1]
        time.sleep_ms(10)
    return -1
def status(): return rbyte(0x70)

def cmd(c, payload):  # block-write style command: [c][count][payload][PEC], executes at STOP
    body = bytes([c, len(payload)]) + payload
    I.writeto(A, body + bytes([crc8(bytes([A << 1]) + body)]))
    time.sleep_ms(60)

def blank(a, n):  # 0x24 -> PFDL blank check; returns (ff4e6, ff4e7)
    cmd(0x24, bytes([a & 0xFF, a >> 8 & 0xFF, a >> 16 & 0xFF, n & 0xFF, n >> 8]))
    return rbyte(0x26), status()

def wr(a, data):
    body = bytes([0xFB, 3 + len(data), a & 0xFF, a >> 8 & 0xFF, a >> 16 & 0xFF]) + data
    I.writeto(A, body + bytes([crc8(bytes([A << 1]) + body)]))
    time.sleep_ms(60)

def active(img):  # img = snap() of 0xF1000-0xF1FFF; active EEL block = the non-FF half
    return 0xF1000 if img[:16] != b"\xff" * 16 else 0xF1800

def check():  # firmware-side intact check (call after leave())
    global I
    import smb  # its import grabs GP4/5 for hardware I2C; take them back
    I = smb.i2c = SoftI2C(sda=Pin(4), scl=Pin(5), freq=40_000)
    rw, rb = smb.rw, smb.rb
    time.sleep_ms(1500)
    r = {}
    for k, c in (("fcc", 0x10), ("cyc", 0x17), ("stat", 0x16), ("ma", 0x00)):
        try: r[k] = rw(c)
        except OSError: r[k] = None
    try: r["cells"] = [rw(c) for c in range(0x3A, 0x40)]
    except OSError: r["cells"] = None
    try: r["model"] = rb(0x2F)
    except OSError: r["model"] = None
    print("CHECK", r)
    return r

assert crc8(b"123456789") == 0xF4
