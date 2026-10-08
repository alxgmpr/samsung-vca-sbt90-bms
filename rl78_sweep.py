# Sweep RL78 boot-ROM entry timing / mode byte. Read-only commands only (baud set). Pin-reset entry, C+ must be clipped.
exec(open("rl78_info.py").read().split("for p in (0, 4, 5):")[0])   # reuse PIO programs + helpers
for p in (0, 4, 5):
    Pin(p, Pin.IN)
stx = rp2.StateMachine(0, od_tx, freq=8 * BAUD, set_base=Pin(1), out_base=Pin(1))
srx = rp2.StateMachine(1, rx, freq=8 * BAUD, in_base=Pin(1), jmp_pin=Pin(1))

def enter(hold_ms, idle_ms):
    stx.active(0); srx.active(0)
    Pin(1, Pin.OUT, value=0)
    Pin(2, Pin.OUT, value=0); time.sleep_ms(10); Pin(2, Pin.IN)
    time.sleep_ms(hold_ms)
    g = rp2.StateMachine(0, od_tx, freq=8 * BAUD, set_base=Pin(1), out_base=Pin(1))
    g.exec("set(pins, 0)"); g.exec("set(pindirs, 0)")
    srx.restart(); srx.active(1); g.active(1)
    time.sleep_ms(idle_ms)
    return g

hits = []
for mode in (0x3A, 0x00):
    for hold in (1, 5, 20):
        for idle in (1, 10, 50, 200):
            g = enter(hold, idle)
            pre = getb(64, 5)                      # anything sent spontaneously?
            g.put(~mode & 0xFF); getb(1)
            time.sleep_ms(2)
            r = cmd(0x9A, bytes([0x00, 33]))
            extra = getb(64, 300)
            tag = "mode %02x hold %3d idle %3d" % (mode, hold, idle)
            if pre or r[0] or extra:
                hits.append(tag); print(tag, "pre", pre.hex(), "reply", r, "extra", extra.hex())
print("hits:", hits or "none")
stx.active(0); srx.active(0); Pin(1, Pin.IN)
Pin(2, Pin.OUT, value=0); time.sleep_ms(10); Pin(2, Pin.IN)
