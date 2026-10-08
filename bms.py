#!/usr/bin/env python3
"""Host CLI for the VCA-SBT90 BMS via the Pico (mpremote). Pico runs pico/smb.py + pico/dfw.py;
decoding happens here.

  uv run bms.py status                 decoded SBS readout (firmware mode)
  uv run bms.py params [--json]        all data-flash params, newest record per index (bootloader)
  uv run bms.py backup [FILE]          save 4 KB data-flash image (default backups/df_<time>.bin)
  uv run bms.py set-param IDX VALUE    append one EEL record (asks first), verify, show status
"""
import argparse, datetime, json, os, struct, subprocess, sys

ROOT = os.path.dirname(os.path.abspath(__file__))
PORT = os.environ.get("BMS_PORT", "/dev/cu.usbmodem1101")
TAG = "@@"  # Pico prints TAG+json; everything else is passed through as log

def pico(code):
    """Push helpers, exec code on the Pico, return the TAG json payload."""
    cmd = ["mpremote", "connect", PORT, "cp", f"{ROOT}/pico/smb.py", f"{ROOT}/pico/dfw.py", ":",
           "+", "exec", "import json\nfrom dfw import *\n" + code]
    out = subprocess.run(cmd, capture_output=True, text=True)
    lines = (out.stdout + out.stderr).splitlines()
    data = [l[len(TAG):] for l in lines if l.startswith(TAG)]
    for l in lines:  # pass Pico-side log lines (retries etc.) through
        if data and not l.startswith((TAG, "cp ", "Up to date")): print("pico:", l, file=sys.stderr)
    if not data:
        sys.exit("pico call failed:\n" + "\n".join(l for l in lines if not l.startswith(("cp ", "Up to date"))))
    return json.loads(data[-1])

# ---- Pico-side snippets ----
SBS_WORDS = {0x08: "temp", 0x09: "volt", 0x0A: "curr", 0x0B: "avg_curr", 0x0D: "rsoc", 0x0F: "rem_cap",
             0x10: "fcc", 0x14: "chg_curr", 0x15: "chg_volt", 0x16: "status", 0x17: "cycles",
             0x18: "design_cap", 0x19: "design_volt", 0x1B: "mfg_date", 0x1C: "serial", 0x00: "ma"}
SBS_BLOCKS = {0x20: "mfg_name", 0x21: "device", 0x22: "chem", 0x2F: "model"}

def snip_status():
    return f"""
import smb

smb.i2c = SoftI2C(sda=Pin(4), scl=Pin(5), freq=40_000)
r = {{}}
for c in {list(SBS_WORDS)} + list(range(0x3A, 0x40)):
    try: r[c] = smb.rw(c)
    except OSError: r[c] = None
for c in {list(SBS_BLOCKS)}:
    try: r[c] = smb.rb(c).decode()
    except Exception: r[c] = None
print("{TAG}" + json.dumps(r))
"""

SNIP_SNAP = f"""
import binascii
enter()
try: img = snap()
finally: leave()
print("{TAG}" + json.dumps(binascii.hexlify(img).decode()))
"""

def snip_append(rec):
    return f"""
import binascii
enter()
try:
    pre = snap(); act = active(pre); i = act - 0xF1000 + 4
    while pre[i:i+6] != b"\\xff" * 6:
        assert pre[i] ^ pre[i+1] == 0xFF, "bad record at %05X" % (0xF1000 + i)
        i += 6
    assert pre[i:i+64] == b"\\xff" * 64, "free area not blank"
    wr(0xF1000 + i, bytes({list(rec)}))
    st = status(); post = snap()
finally: leave()
print("{TAG}" + json.dumps({{"slot": 0xF1000 + i, "pfdl": st, "pre": binascii.hexlify(pre).decode(),
      "diff": [[0xF1000 + k, pre[k], post[k]] for k in range(4096) if pre[k] != post[k]]}}))
"""

# ---- host-side decoding ----
STATUS_BITS = [(15, "OVER_CHARGED_ALARM"), (14, "TERMINATE_CHARGE_ALARM"), (12, "OVER_TEMP_ALARM"),
               (11, "TERMINATE_DISCHARGE_ALARM"), (9, "REMAINING_CAPACITY_ALARM"),
               (8, "REMAINING_TIME_ALARM"), (7, "INITIALIZED"), (6, "DISCHARGING"),
               (5, "FULLY_CHARGED"), (4, "FULLY_DISCHARGED")]

def status_flags(s):
    return [n for b, n in STATUS_BITS if s >> b & 1] + ([f"ERROR_CODE={s & 0xF}"] if s & 0xF else [])

def active_block(img):
    return 0 if img[:16] != b"\xff" * 16 else 0x800

def records(img):
    """Latest value per index from the active EEL block: {idx: (addr, u32)}."""
    o = active_block(img); i, out = o + 4, {}
    while i + 6 <= o + 0x7F0 and img[i:i + 6] != b"\xff" * 6:
        if img[i] ^ img[i + 1] != 0xFF:
            raise ValueError(f"corrupt record at {0xF1000 + i:05X}")
        out[img[i]] = (0xF1000 + i, struct.unpack("<I", img[i + 2:i + 6])[0])
        i += 6
    return out

def cmd_status(a):
    r = {int(k): v for k, v in pico(snip_status()).items()}
    if r[0x09] is None:
        sys.exit("no SBS answer: pack asleep? touch bench supply+ to C+ for ~1 s and retry")
    s16 = lambda v: v - 0x10000 if v is not None and v & 0x8000 else v
    d = r[0x1B] or 0
    print(f"model      {r[0x2F]}  ({r[0x20]} {r[0x21]} {r[0x22]})  serial {r[0x1C]}  mfg {1980 + (d >> 9)}-{d >> 5 & 15:02}-{d & 31:02}")
    print(f"pack       {r[0x09]} mV  {s16(r[0x0A])} mA (avg {s16(r[0x0B])})  {r[0x08] / 10 - 273.15:.1f} C")
    print(f"cells      " + "  ".join(f"{r[c]}" for c in range(0x3A, 0x40)) + f" mV  (spread {max(r[c] for c in range(0x3A, 0x40)) - min(r[c] for c in range(0x3A, 0x40))} mV)")
    print(f"capacity   {r[0x0D]}%  {r[0x0F]}/{r[0x10]} mAh (design {r[0x18]} mAh, {r[0x19]} mV)  cycles {r[0x17]}")
    print(f"charge req {r[0x14]} mA @ {r[0x15]} mV")
    print(f"status     0x{r[0x16]:04X}  {' '.join(status_flags(r[0x16]))}")
    print(f"mfr access 0x{r[0x00]:04X}")
    pf = r[0x16] & 0x4800 == 0x4800 and not r[0x14]
    print("PF         " + ("LIKELY LATCHED (charge+discharge terminated, no charge request)" if pf else "clear"))

def read_image():
    return bytes.fromhex(pico(SNIP_SNAP))

def cmd_params(a):
    img = read_image()
    recs = records(img)
    if a.json:
        print(json.dumps({f"0x{k:02X}": v for k, (_, v) in sorted(recs.items())}, indent=1)); return
    print(f"active block {0xF1000 + active_block(img):05X}, {len(recs)} params")
    for k, (addr, v) in sorted(recs.items()):
        f = struct.unpack("<f", struct.pack("<I", v))[0]
        fs = f"{f:.6g}" if 1e-6 < abs(f) < 1e9 else ""
        note = "  <- persistent fault bits 48-63 (PF)" if k == 0x17 else ""
        print(f"P{k:02X}  {addr:05X}  {v:08X}  {v:>11}  {fs:>12}{note}")

def cmd_backup(a):
    img = read_image()
    path = a.file or os.path.join(ROOT, "backups", f"df_{datetime.datetime.now():%Y%m%d_%H%M%S}.bin")
    open(path, "wb").write(img)
    print(f"saved {path} (active block {0xF1000 + active_block(img):05X}, {len(records(img))} params)")

def cmd_set_param(a):
    idx, val = int(a.idx, 0), int(a.value, 0)
    if not (0 <= idx < 158 and 0 <= val <= 0xFFFFFFFF):
        sys.exit("idx must be 0..0x9D, value a u32")
    rec = bytes([idx, idx ^ 0xFF]) + val.to_bytes(4, "little")
    if not a.yes and input(f"append P{idx:02X} = 0x{val:08X} ({rec.hex(' ')}) to data flash? [y/N] ").lower() != "y":
        sys.exit("aborted")
    r = pico(snip_append(rec))
    pre = bytes.fromhex(r["pre"])
    path = os.path.join(ROOT, "backups", f"df_pre_P{idx:02X}_{datetime.datetime.now():%Y%m%d_%H%M%S}.bin")
    open(path, "wb").write(pre)
    old = records(pre).get(idx, (0, None))[1]
    print(f"pre-write image saved to {path}")
    print(f"slot {r['slot']:05X}  PFDL status {r['pfdl']}  P{idx:02X}: {old if old is None else hex(old)} -> {hex(val)}")
    diff = r["diff"]; want = [[r["slot"] + k, 0xFF, b] for k, b in enumerate(rec)]
    print("diff OK (only the new record)" if diff == want else f"UNEXPECTED DIFF: {diff}")
    cmd_status(a)

def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sp = p.add_subparsers(dest="cmd", required=True)
    sp.add_parser("status").set_defaults(fn=cmd_status)
    q = sp.add_parser("params"); q.add_argument("--json", action="store_true"); q.set_defaults(fn=cmd_params)
    q = sp.add_parser("backup"); q.add_argument("file", nargs="?"); q.set_defaults(fn=cmd_backup)
    q = sp.add_parser("set-param"); q.add_argument("idx"); q.add_argument("value")
    q.add_argument("-y", "--yes", action="store_true"); q.set_defaults(fn=cmd_set_param)
    a = p.parse_args(); a.fn(a)

def _selftest():
    img = bytearray(b"\xff" * 4096)
    img[0x804:0x816] = bytes([0x17, 0xE8, 4, 0, 0, 0, 0x01, 0xFE, 1, 0, 0, 0, 0x17, 0xE8, 0, 0, 0, 0])
    assert records(bytes(img)) == {0x17: (0xF1810, 0), 0x01: (0xF180A, 1)}  # newest wins, block 2
    assert status_flags(0x48C0) == ["TERMINATE_CHARGE_ALARM", "TERMINATE_DISCHARGE_ALARM", "INITIALIZED", "DISCHARGING"]

if __name__ == "__main__":
    _selftest()
    main()
