# MicroPython on a Pico. Read-only probe of the RAJ240080's RL78 boot ROM (serial programming mode, single-wire UART).
# Wiring: GP1 --- TP32 TOOL0 (board has 1k pull-up to 3.3 V);  GP2 --- TP33 RESET;  GND --- TP14.
# GP0 (via 1k to TOOL0) is left as an input - unused. Keep supply+ clipped on C+ the whole time.
# TOOL0 is driven open-drain by PIO: '0' pulls low, '1' releases to the board pull-up. Never drives high.
from machine import Pin
import rp2, time

BAUD = 115200
ALLOWED = {0x9A: "baud rate set", 0xC0: "silicon signature", 0xA1: "security get"}  # nothing that erases/writes
SOH, STX, ETX = 0x01, 0x02, 0x03

@rp2.asm_pio(out_shiftdir=rp2.PIO.SHIFT_RIGHT, set_init=rp2.PIO.IN_LOW, out_init=rp2.PIO.IN_LOW)
def od_tx():  # bits arrive inverted: 1 = drive low (pindir out), 0 = release
    pull()
    set(pindirs, 1)          [7]   # start bit
    set(x, 7)
    label("bit")
    out(pindirs, 1)          [6]
    jmp(x_dec, "bit")
    set(pindirs, 0)          [7]   # stop bits
    nop()                    [7]

@rp2.asm_pio(in_shiftdir=rp2.PIO.SHIFT_RIGHT, fifo_join=rp2.PIO.JOIN_RX)
def rx():
    label("start")
    wait(0, pin, 0)
    set(x, 7)                [10]
    label("bit")
    in_(pins, 1)
    jmp(x_dec, "bit")        [6]
    jmp(pin, "ok")
    wait(1, pin, 0)                # framing error: drop byte
    jmp("start")
    label("ok")
    push(block)

def cs(b):
    return (-sum(b)) & 0xFF

def getb(n, timeout_ms=300):
    out, t = bytearray(), time.ticks_ms()
    while len(out) < n and time.ticks_diff(time.ticks_ms(), t) < timeout_ms:
        if srx.rx_fifo():
            out.append(srx.get() >> 24)
    return bytes(out)

def recv():
    h = getb(2)
    if len(h) < 2 or h[0] != STX:
        return h + getb(64, 50), None          # raw bytes for debugging
    n = h[1] or 256
    body = getb(n + 2)
    return body[:n], len(body) == n + 2 and body[n] == cs(h[1:] + body[:n])

def cmd(c, data=b""):
    assert c in ALLOWED, "refusing command %02x" % c
    f = bytes([len(data) + 1, c]) + data
    f = bytes([SOH]) + f + bytes([cs(f), ETX])
    for b in f:
        stx.put(~b & 0xFF)
    getb(len(f))                                # discard our own echo
    return recv()

for p in (0, 4, 5):
    Pin(p, Pin.IN)                              # nothing else touching the board
stx = rp2.StateMachine(0, od_tx, freq=8 * BAUD, set_base=Pin(1), out_base=Pin(1))
srx = rp2.StateMachine(1, rx, freq=8 * BAUD, in_base=Pin(1), jmp_pin=Pin(1))

POWER_ON = True  # True: TOOL0 low before power-up, wait for the AFE to release RESET. False: pulse RESET.

def attempt(hold_ms):
    global stx
    stx.active(0); srx.active(0)
    Pin(1, Pin.OUT, value=0)                    # TOOL0 hard low (3.3 mA into the 1k pull-up)
    if POWER_ON:
        rst = Pin(2, Pin.IN, Pin.PULL_DOWN)
        print("TOOL0 low. Turn the supply on now (C+ clipped) - 120 s")
        t = time.ticks_ms()
        while not rst.value():
            if time.ticks_diff(time.ticks_ms(), t) > 120_000:
                raise SystemExit("RESET never went high")
    else:
        Pin(2, Pin.OUT, value=0); time.sleep_ms(10); Pin(2, Pin.IN)   # pulse RESET (AFE drives it high again)
    time.sleep_ms(hold_ms)
    low = Pin(1).value() == 0
    stx = rp2.StateMachine(0, od_tx, freq=8 * BAUD, set_base=Pin(1), out_base=Pin(1))  # re-claims GP1 for PIO
    stx.exec("set(pins, 0)"); stx.exec("set(pindirs, 0)")       # release -> pull-up high
    srx.restart(); srx.active(1); stx.active(1)
    time.sleep_ms(2)
    while srx.rx_fifo(): srx.get()
    stx.put(~0x3A & 0xFF); echo = getb(1)
    time.sleep_ms(2)
    r = cmd(0x9A, bytes([0x00, 33]))
    if not r[1]:
        r = (r[0] + getb(64, 500), r[1])          # anything at all on the line?
    print("hold %3d ms  TOOL0 low=%s  echo=%s  baud reply=%s" % (hold_ms, low, echo.hex(), r))
    return r[1]

try:
    for h in ((30,) if POWER_ON else (3, 10, 30, 100)):
        if attempt(h):
            st = cmd(0xC0); sig = recv(); print("sig  :", st, sig)
            if sig[1]:
                d = sig[0]
                print("  device", d[3:13], "code end %06x" % int.from_bytes(d[13:16], "little"),
                      "data end %06x" % int.from_bytes(d[16:19], "little"), "boot fw", d[19:22].hex())
            st = cmd(0xA1); sec = recv(); print("sec  :", st, sec)
            break
finally:
    stx.active(0); srx.active(0)
    Pin(1, Pin.IN)                              # TOOL0 released high
    Pin(2, Pin.OUT, value=0); time.sleep_ms(10); Pin(2, Pin.IN)   # reboot into normal firmware
