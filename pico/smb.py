# SMBus helpers for the VCA-SBT90 BMS at 0x0B (Pico: SDA GP4, SCL GP5).
from machine import I2C, Pin
import time
A = 0x0B
i2c = I2C(0, sda=Pin(4), scl=Pin(5), freq=50_000)

def crc8(data, c=0):
    for b in data:
        c ^= b
        for _ in range(8):
            c = ((c << 1) ^ 0x07) & 0xFF if c & 0x80 else (c << 1) & 0xFF
    return c

def rw(cmd, pec=False):
    b = i2c.readfrom_mem(A, cmd, 3 if pec else 2)
    if pec and crc8(bytes([A << 1, cmd, A << 1 | 1]) + b[:2]) != b[2]:
        raise ValueError("bad PEC")
    return b[0] | b[1] << 8

def rb(cmd, pec=False):
    b = i2c.readfrom_mem(A, cmd, 34)
    n = min(b[0], 32)
    if pec and crc8(bytes([A << 1, cmd, A << 1 | 1]) + b[:n + 1]) != b[n + 1]:
        raise ValueError("bad PEC")
    return bytes(b[1:1 + n])

def ww(cmd, val, pec=False):
    d = bytes([val & 0xFF, val >> 8 & 0xFF])
    if pec:
        d += bytes([crc8(bytes([A << 1, cmd]) + d)])
    i2c.writeto_mem(A, cmd, d)

def wb(cmd, data, pec=False):
    d = bytes([len(data)]) + data
    if pec:
        d += bytes([crc8(bytes([A << 1, cmd]) + d)])
    i2c.writeto_mem(A, cmd, d)

def reset():  # pin-reset MCU via TP33, wait for firmware to answer again
    Pin(2, Pin.OUT, value=0); time.sleep_ms(10); Pin(2, Pin.IN)
    t = time.ticks_ms()
    while time.ticks_diff(time.ticks_ms(), t) < 5000:
        try:
            rw(0x09); return time.ticks_diff(time.ticks_ms(), t)
        except OSError:
            time.sleep_ms(20)
    return None

# self-check: SMBus spec example CRC-8 of b"123456789" is 0xF4
assert crc8(b"123456789") == 0xF4
