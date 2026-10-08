#!/usr/bin/env python3
"""Host CLI for the VCA-SBT90 BMS via the Pico (mpremote). Pico runs pico/smb.py + pico/dfw.py;
decoding happens here.

  uv run bms.py status [--json]        decoded SBS readout (firmware mode)
  uv run bms.py params [--json]        all data-flash params, newest record per index (bootloader)
  uv run bms.py backup [FILE]          save 4 KB data-flash image (default backups/df_<time>.bin)
  uv run bms.py set-param IDX VALUE    append one EEL record (asks first), verify, show status
  uv run bms.py log [--json]           decoded fault/event log + snapshots (firmware mode)
  uv run bms.py report                 status + log + named params + raw image -> reports/<time>.json/.md
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

def read_status():
    r = {int(k): v for k, v in pico(snip_status()).items()}
    if r[0x09] is None:
        sys.exit("no SBS answer: pack asleep? touch bench supply+ to C+ for ~1 s and retry")
    return decode_status(r)

def decode_status(r):
    s16 = lambda v: v - 0x10000 if v is not None and v & 0x8000 else v
    d, cells = r[0x1B] or 0, [r[c] for c in range(0x3A, 0x40)]
    return {"model": r[0x2F], "mfg_name": r[0x20], "device": r[0x21], "chem": r[0x22], "serial": r[0x1C],
            "mfg_date": f"{1980 + (d >> 9)}-{d >> 5 & 15:02}-{d & 31:02}",
            "pack_mv": r[0x09], "current_ma": s16(r[0x0A]), "avg_current_ma": s16(r[0x0B]),
            "temp_c": round(r[0x08] / 10 - 273.15, 1), "cells_mv": cells, "spread_mv": max(cells) - min(cells),
            "rsoc_pct": r[0x0D], "remaining_mah": r[0x0F], "fcc_mah": r[0x10], "design_mah": r[0x18],
            "design_mv": r[0x19], "cycles": r[0x17], "charge_req_ma": r[0x14], "charge_req_mv": r[0x15],
            "status": r[0x16], "status_flags": status_flags(r[0x16]), "mfr_access": r[0x00],
            # PF heuristic: charge+discharge terminated and no charge request
            "pf_likely": r[0x16] & 0x4800 == 0x4800 and not r[0x14]}

def print_status(s):
    print(f"model      {s['model']}  ({s['mfg_name']} {s['device']} {s['chem']})  serial {s['serial']}  mfg {s['mfg_date']}")
    print(f"pack       {s['pack_mv']} mV  {s['current_ma']} mA (avg {s['avg_current_ma']})  {s['temp_c']:.1f} C")
    print(f"cells      " + "  ".join(map(str, s["cells_mv"])) + f" mV  (spread {s['spread_mv']} mV)")
    print(f"capacity   {s['rsoc_pct']}%  {s['remaining_mah']}/{s['fcc_mah']} mAh (design {s['design_mah']} mAh, {s['design_mv']} mV)  cycles {s['cycles']}")
    print(f"charge req {s['charge_req_ma']} mA @ {s['charge_req_mv']} mV")
    print(f"status     0x{s['status']:04X}  {' '.join(s['status_flags'])}")
    print(f"mfr access 0x{s['mfr_access']:04X}")
    print("PF         " + ("LIKELY LATCHED (charge+discharge terminated, no charge request)" if s["pf_likely"] else "clear"))

def cmd_status(a):
    s = read_status()
    print(json.dumps(s, indent=1)) if getattr(a, "json", False) else print_status(s)

def read_image():
    return bytes.fromhex(pico(SNIP_SNAP))

# fault-mask bit -> logged code (table @0x2422); bits 48-62 are permanent faults (PF)
CODE_BIT = {0x0A: 0, 0x14: 2, 0x16: 4, 0x28: 6, 0x29: 7, 0x32: 8, 0x33: 9, 0x34: 10, 0x3C: 11, 0x3D: 12,
            0x46: 15, 0x47: 16, 0x50: 17, 0x51: 18, 0x5B: 20, 0x5C: 21, 0xA3: 35, 0xA4: 36, 0xA5: 37,
            0xA6: 38, 0xA7: 39, 0xB4: 40, 0xB5: 41, 0xB6: 42, 0xB7: 43, 0xB9: 46, 0xBA: 47, 0xC8: 48,
            0xC9: 49, 0xCA: 50, 0xCC: 52, 0xDC: 55}
# per-code condition, from docs/re/fault-codes.md
CODE_NOTE = {
    0x0A: "cell OV: max cell > 4230 mV 3 s (rel < 4100)",
    0x14: "cell UV: min cell < 2600 mV, not charging, 1 s (rel when charger seen)",
    0x16: "deep UV: min cell < 2500 mV with terminal < 1.8 V, 5 s (0x60CA)",
    0x28: "charge OC (SW): I > 2.5 A 3 s; 3 trips/300 s latches",
    0x29: "charge OC (AFE comparator, reg 0x6A b3)",
    0x32: "discharge OC (SW): I < -40 A 3 s, rel 30 s",
    0x33: "discharge OC (AFE comparator, reg 0x6A b2)",
    0x34: "short circuit (AFE, reg 0x6A b0/b1), rel 30 s",
    0x3C: "charge over-temp: T > 55.0 C while charging (rel < 54.0)",
    0x3D: "charge under-temp: T < 0.0 C while charging (rel > 5.0)",
    0x46: "over-temp: T > 76.0 C (rel < 60.0)",
    0x47: "under-temp: T < -20.0 C (rel > -15.0)",
    0x50: "charge timeout: > 360 min charging",
    0x5C: "terminal/charger OV: >= 26.0 V for 5 cycles",
    0xA3: "boot: config checksum mismatch",
    0xA4: "boot: data-flash param checksum mismatch",
    0xA5: "boot: config signature 'SV' missing",
    0xA7: "data-flash write failure (0xFFE96 = 4 verify / 5 erase-retry)",
    0xB4: "measurement implausible (cell > 5 V / terminal > 28 V); disables V checks",
    0xC8: "PF: cell OV, max cell > 4300 mV 5 s",
    0xC9: "PF: no setter (only restored from P17)",
    0xCA: "PF: dead cell, min cell < 1000 mV for ~20 checks after wake (0x6890)",
    0xCC: "PF: cell imbalance, delta > 195 mV charging (> 170/200 mV at rest) 20 s",
    0xDC: "PF: FET failure, current with FET off (> 1 A) 20 s",
}
# event-log (SBS 0xF5) codes are their own numbering, from docs/re/events-boot.md
EVENT_NOTE = {
    1: "ship/shutdown request (MA 0x0010 or SBS 0x80 mode 2)",
    2: "deep-discharge power-off (UV, terminal < 1.8 V, ~2400 ticks idle)",
    3: "shutdown timer via event 12 (dead in this firmware)",
    4: "firmware reset / power-down (0x80 mode 1, queue overflow, 0xA0 path)",
    5: "boot / wake",
    6: "full charge reached (cell >= 4100 mV, taper current, 120 ticks)",
    7: "under-voltage fault 0x14 first set",
    8: "charge started (I > 0 for 12 ticks)",
    9: "charge ended (I <= 0 for 12 ticks)",
    10: "cell voltage jump: a cell moved >= 500 mV since last logged set",
}

def snip_log():
    return f"""
import smb
smb.i2c = SoftI2C(sda=Pin(4), scl=Pin(5), freq=40_000)
r = {{}}
for c in (0xF0, 0xF1, 0xF2, 0xF3, 0xF5, 0xE7):
    try: r[c] = smb.rb(c).hex()
    except Exception: r[c] = ""
print("{TAG}" + json.dumps(r))
"""

def read_log():
    r = {int(k): bytes.fromhex(v) for k, v in pico(snip_log()).items()}
    if not r[0xE7]:
        sys.exit("no SBS answer: pack asleep? touch bench supply+ to C+ for ~1 s and retry")
    return decode_log(r)

def code_info(c):
    b = CODE_BIT.get(c)
    return {"code": c, "bit": b, "permanent": b is not None and 48 <= b <= 62, "note": CODE_NOTE.get(c, "")}

def decode_log(r):
    now = int.from_bytes(r[0xE7][:2], "little")
    out = {"now": now}
    for blk, name in ((0xF3, "fault_log"), (0xF5, "event_log")):  # [ts=P5B hour][minute][code]
        info = code_info if blk == 0xF3 else lambda c: {"code": c, "bit": None, "permanent": False, "note": EVENT_NOTE.get(c, "")}
        out[name] = [dict(ts=int.from_bytes(r[blk][k:k + 2], "little"), minute=r[blk][k + 2], **info(r[blk][k + 3]))
                     for k in range(0, len(r[blk]) - 3, 4)]
    out["snapshots"] = []
    for blk in (0xF0, 0xF1, 0xF2):
        w = [int.from_bytes(r[blk][k:k + 2], "little") for k in range(0, len(r[blk]) - 1, 2)]
        if len(w) >= 12:
            out["snapshots"].append({"ts": w[3], "code": w[4] >> 8, "cells_mv": w[6:12], "raw": [w[0], w[1], w[5]]})
    return out

def print_log(L):
    print(f"timestamp now 0x{L['now']:04X} (P5B, ~1 per powered-on hour)")
    for name, title, blk in (("fault_log", "fault log", 0xF3), ("event_log", "event log", 0xF5)):
        print(f"{title} (block 0x{blk:02X}, ring order):")
        for e in L[name]:
            kind = "" if e["bit"] is None else f"bit {e['bit']}" + (" PERMANENT" if e["permanent"] else "")
            print(f"  ts 0x{e['ts']:04X}+{e['minute']:02}m ({L['now'] - e['ts']:>5} h ago)  0x{e['code']:02X} {kind:<14} {e['note']}")
    print("snapshots (last 3 distinct codes):")
    for n in L["snapshots"]:
        print(f"  ts 0x{n['ts']:04X} code 0x{n['code']:02X}  cells {n['cells_mv']} mV  raw {' '.join(map(str, n['raw']))}")

def cmd_log(a):
    L = read_log()
    print(json.dumps(L, indent=1)) if a.json else print_log(L)

# idx -> (name, unit/format, evidence), from docs/re/param-names.md
PARAM_NAMES = {
    0x00: ("cal checksum (b0) / 0xA5 sig (b1); cell1 ADC @2200mV (hi)", "u8;u8;u16 cnt", "vs 0x4539/0xAD91, SBS 0x58 mode 2"),
    0x01: ("cell2 / cell3 ADC @2200mV", "u16;u16 cnt", "vs 0x44C9, SBS 0x58 mode 2"),
    0x02: ("cell4 / cell5 ADC @2200mV", "u16;u16 cnt", "vs 0x44D9, SBS 0x58 mode 2"),
    0x03: ("cell6 ADC @2200mV (FFB36-FFB28)", "u16 cnt", "vs 0x44E7 via 0x504A"),
    0x04: ("spare (in cal checksum range)", "u32", "vs no xref"),
    0x05: ("spare; cell1 ADC @4200mV (hi)", "u16;u16 cnt", "vs 0x44F0, SBS 0x58 mode 3"),
    0x06: ("cell2 / cell3 ADC @4200mV", "u16;u16 cnt", "vs 0x44F7, SBS 0x58 mode 3"),
    0x07: ("cell4 / cell5 ADC @4200mV", "u16;u16 cnt", "vs 0x4507, SBS 0x58 mode 3"),
    0x08: ("cell6 ADC @4200mV", "u16 cnt", "vs 0x4515"),
    0x09: ("spare (in cal checksum range)", "u32", "vs no xref"),
    0x0A: ("spare; P+ voltage ADC @13200mV (hi)", "u16;u16 cnt", "vs 0x451D, ref 0xD44A, used 0x9F0F"),
    0x0B: ("P+ voltage ADC @25200mV; current ADC zero offset (hi)", "u16 cnt;u16 cnt", "vs 0x4525/0x44AF, 0x4FB6"),
    0x0C: ("current ADC at cal current; spare", "u16 cnt;u16", "vs 0x44B8 (SBS 0x58 mode 1)"),
    0x0D: ("spare; cal reference temperature (hi)", "u16;0.1K", "vs 0x452C (=2993, 26.2C)"),
    0x0E: ("thermistor ADC at cal temp; cell/lot date (hi, SBS 0x94)", "u16 cnt;SBS date", "vs 0x4532, 0x4A11/0x4A23; date meaning inf"),
    0x0F: ("SBS 0x95 value (lot no.?); spare", "u16;u16", "vs 0x4A33/0x4A45; meaning inf; unlock fork"),
    0x10: ("const 'PL' (lo); ManufactureDate SBS 0x1B (hi)", "u16;SBS date", "vs 0x438A/0x439C; nonzero blocks 0x80 mode 5 (0x47E3)"),
    0x11: ("SerialNumber SBS 0x1C", "u16", "vs 0x43AC/0x43C4"),
    0x12: ("spare", "u32", "vs no xref; zero in defaults 0xDA3A"),
    0x13: ("spare", "u32", "vs no xref"),
    0x14: ("spare", "u32", "vs no xref"),
    0x15: ("spare", "u32", "vs no xref"),
    0x16: ("spare", "u32", "vs no xref"),
    0x17: ("PF fault-mask bits 48-63 (lo); protection-disable mask FFB50 / SBS 0xB2 (hi)", "bitmask;bitmask", "vs 0x839D/0xAB41, 0x83CA/0x8417; hi bits 1=V,2=I,3=T checks off (fault-codes, thresholds forks); clear 0xAA55"),
    0x18: ("Qmax / learned max capacity (SBS 0xA3)", "float mAh", "vs 0x8008/0x824F; meaning inf"),
    0x19: ("FullChargeCapacity", "float mAh", "vs 0x7FD1 (SBS 0x10 = 2390); default 2850 @0xD960"),
    0x1A: ("gauge %: SOC at charge-term OCV?", "float %", "vs 0x804D, seeded from 4160 @0xD96E; meaning inf"),
    **{0x1B + i: (f"gauge R table A[{i}] (SBS 0xAA)", "float ohm?", "vs 0x7E78/0x8070, default @0xD904; meaning inf") for i in range(15)},
    **{0x2A + i: (f"gauge R table B[{i}] (SBS 0xAB)", "float ohm?", "vs 0x7E91/0x80A1, default @0xD940; meaning inf") for i in range(8)},
    0x32: ("gauge-valid marker 0xBEEF (lo); model string len (b2), 'S' (b3)", "u16;u8;char", "vs 0x7E03/0x7F17, 0xAF9B (SBS 0x2F)"),
    0x33: ("model string 'EC_V'", "ascii", "vs SBS 0x2F 0xAF9B"),
    0x34: ("model string 'S900'", "ascii", "vs SBS 0x2F"),
    0x35: ("model string '0NL\\0'", "ascii", "vs SBS 0x2F"),
    0x36: ("spare", "u32", "vs no xref"),
    0x37: ("spare", "u32", "vs no xref"),
    0x38: ("spare; CycleCount SBS 0x17 (hi)", "u16;u16", "vs 0x4351/0x7FFC"),
    0x39: ("cycle accumulator % toward next cycle", "u16 %", "vs 0x803E (int of FF8E6)"),
    0x3A: ("discharge time, low power bin 10-130", "u32 ticks(s?)", "vs 0x7A8E, edges @0xD4F8; SBS 0xFB"),
    0x3B: ("discharge time, mid power bin 130-370", "u32 ticks(s?)", "vs 0x7AAD; SBS 0xFB"),
    0x3C: ("discharge time, high power bin >370", "u32 ticks(s?)", "vs 0x7AC7; SBS 0xFB"),
    0x3D: ("throughput counter (FFE30/144000, flag FFB71)", "u32", "vs 0x7840; meaning inf; SBS 0xFB"),
    0x3E: ("spare", "u32", "vs no xref"),
    0x3F: ("lifetime block signature 0x00239FD5", "u32", "vs 0x7552 (reset 0x7547); SBS 0xE2"),
    0x40: ("fault count code 0A/0B/14/15", "4x u8", "vs 0x760F, table @0x2312; SBS 0xE2"),
    0x41: ("fault count code 16/1E/28/29", "4x u8", "vs 0x760F"),
    0x42: ("fault count code 32/33/34/3C", "4x u8", "vs 0x760F"),
    0x43: ("fault count code 3D/3E/3F/46", "4x u8", "vs 0x760F"),
    0x44: ("fault count code 47/50/51/5A", "4x u8", "vs 0x760F"),
    0x45: ("fault count code 5B/5C/5D/5E", "4x u8", "vs 0x760F"),
    0x46: ("spare (E2 tail)", "u32", "vs no xref"),
    **{0x47 + i: ("spare (E3)", "u32", "vs zero, cleared by 0x755E") for i in range(8)},
    0x4F: ("boot count; sleep-entry count", "u16;u16", "vs 0x7648 n=0 (0x9C1B), n=1 (0xAA8A)"),
    0x50: ("cycle events; event n=3 count", "u16;u16", "vs 0x7648 n=2 (0x815D), n=3 (0x954C)"),
    0x51: ("event n=4 count; max-cell idx+1 (b2); min-cell idx+1 (b3)", "u16;u8;u8", "vs 0x9554, 0x76BD/0x76D9"),
    0x52: ("lifetime max cell V; min cell V", "mV;mV", "vs 0x76AF/0x76D3"),
    0x53: ("lifetime max P+ voltage; max charge current", "mV;mA", "vs 0x76EC/0x7708"),
    0x54: ("lifetime max discharge current; max temp", "s16 mA;0.1K", "vs 0x7720/0x772E"),
    0x55: ("lifetime min temp; spare", "0.1K;u16", "vs 0x7747"),
    0x56: ("lifetime max cell delta; ts of max cell V", "mV;P5B hours", "vs 0x775A/0x76C5"),
    0x57: ("ts min cell V; ts max P+ V", "P5B hours;P5B hours", "vs 0x76E6/0x76F7"),
    0x58: ("ts max chg current; ts max dsg current", "P5B hours;P5B hours", "vs 0x7710/0x7728"),
    0x59: ("ts max temp; ts min temp", "P5B hours;P5B hours", "vs 0x7739/0x774F"),
    0x5A: ("spare; ts max cell delta", "u16;P5B hours", "vs 0x7763"),
    0x5B: ("powered hours (log timestamp); discharging hours", "h;h", "vs 0x78AB/0x78BF, 60x60 ticks"),
    0x5C: ("charge/idle-state hours; discharge throughput", "h;x900000 units", "vs 0x78D3, 0x77CD (I<0)"),
    0x5D: ("total throughput; hist[0] (V0,T0)", "x900000 units;h", "vs 0x778E, 0x79F4"),
    **{0x5E + i: (f"V x T histogram hours [{2*i+1}],[{2*i+2}]", "h;h", "vs 0x79F4: idx=5*vbin+tbin, bins @0xD516/0xD51E") for i in range(12)},
    0x6A: ("hours max cell >= 4000mV; hours min cell <= 3000mV", "h;h", "vs 0x78E7/0x78FB, consts 0xD528/0xD52A"),
    0x6B: ("aux hour counters [0],[1] (no incrementer found)", "h;h", "vs 0x7901 roll-over"),
    0x6C: ("aux hour counters [2],[3]", "h;h", "vs 0x7901"),
    0x6D: ("aux hour counters [4],[5]", "h;h", "vs 0x7901"),
    **{0x6E + i: ("spare (EA)", "u32", "vs zero, no xref") for i in range(5)},
    0x73: ("sub-hour ticks: powered/discharging/charge-state (b0-b2)", "3x u8", "vs 0x7ADF/0x7AE7/0x7AF1; SBS 0xEC"),
    **{0x74 + i: (f"histogram sub-counters bytes {4*i}-{4*i+3}", "4x u8", "vs 0x7B3D; SBS 0xED") for i in range(6)},
    0x7A: ("hist sub-counter 24 (b0); >=4000mV sub (b1); <=3000mV sub (b2)", "u8;u8;u8", "vs 0x7B5B/0x7B66"),
    0x7B: ("aux sub-counters 0-3", "4x u8", "vs 0x7908; SBS 0xEE"),
    0x7C: ("aux sub-counters 4-5; spare", "u8;u8;u16", "vs 0x7908"),
    0x7D: ("spare (EE)", "u32", "vs no xref"),
    0x7E: ("spare (EE)", "u32", "vs no xref"),
    0x7F: ("snapshot ring idx (b0); fault-log ring idx (b1); snapshot1 w0 (hi)", "u8;u8;u16", "vs 0x7B8D/0x7BAF; SBS 0xEF/0xF0"),
    **{0x80 + i: ("fault snapshot data (F0-F2, 3x24 B)", "u16;u16", "vs 0x7B75; words 6..11 = cell mV") for i in range(0x11)},
    0x91: ("snapshot3 last word; fault log entry0 ts (hi)", "u16;u16", "vs F2/F3"),
    **{0x92 + i: ("fault log (F3, 8x [ts u16][state][code])", "bytes", "vs 0x7BC5 (base FF752+4*idx)") for i in range(7)},
    0x99: ("fault log entry7 state/code (lo); event-log ring idx (b2)", "u8;u8;u8", "vs 0x7C97; SBS 0xF4"),
    0x9A: ("event log entry 0 [ts][state][code]", "u16;u8;u8", "vs 0x7CA6 (base FF774+4*idx); SBS 0xF5"),
    0x9B: ("event log entry 1", "u16;u8;u8", "vs 0x7C85"),
    0x9C: ("event log entry 2", "u16;u8;u8", "vs 0x7C85"),
    0x9D: ("event log entry 3", "u16;u8;u8", "vs 0x7C85"),
}
# gauge/scaling corrections, from docs/re/gauge-scaling.md
PARAM_NAMES_PATCH = {
    0x18: ("Qmax: learned chemical capacity (SBS 0xA3)", "float mAh", "seed 3195.0 @0xD98C x parallel 0xD982 (0x7D9A/0x7E14); SOC denom 0x8200 [gauge-scaling]"),
    0x19: ("FullChargeCapacity", "float mAh", "SBS 0x10; seed 2850 @0xD960; learned 0x3610 (>=40% SOC span), clamped <=2850 [gauge-scaling]"),
    0x1A: ("SOC at charge-term OCV (4160 mV)", "float %", "seed 0xA32F OCV->SOC tables @0xD6B0/0xD630 of 4160 @0xD96E [gauge-scaling]"),
    **{0x1B + i: (f"learned cell R vs SOC [{p}%]", "float ohm", "15-pt grid @0xD7B0, default @0xD904, RAM FF818 (SBS 0xAA); meaning inf [gauge-scaling]")
       for i, p in enumerate((0, 4, 8, 12, 16, 20, 28, 36, 44, 52, 60, 68, 76, 84, 100))},
    **{0x2A + i: (f"learned R table 2 [{p}% SOC]", "float ohm", "8-pt grid @0xD7EC, default @0xD940, RAM FF854 (SBS 0xAB); meaning inf [gauge-scaling]")
       for i, p in enumerate((10, 20, 30, 50, 70, 80, 90, 96))},
    0x3D: ("charge after leaving full while on charger (dock top-up)", "u32 x10 mAh", "FFE30/144000 while FFB71 & I>0 (0x77E7-0x7840) [gauge-scaling]"),
    0x50: ("cycle events; full-charge detections (event 23)", "u16;u16", "n=2 0x815D; n=3 0x954A, detect 0x8259 [gauge-scaling]"),
    0x51: ("fully-discharged entries (UV bit 2, event 30); max-cell idx+1 (b2); min-cell idx+1 (b3)", "u16;u8;u8", "n=4 0x9552 via 0x7FBA; 0x76BD/0x76D9 [gauge-scaling]"),
    0x53: ("lifetime max P+ voltage; max charge current", "mV;10 mA", "0x76EC/0x7708; current unit from 0x95E5 [gauge-scaling]"),
    0x54: ("lifetime max discharge current; max temp", "s16 10 mA;0.1K", "0x7720/0x772E; current unit from 0x95E5 [gauge-scaling]"),
    0x5B: ("powered hours (log timestamp); discharging hours (I<0)", "h;h", "0x78AB/0x78BF, 0x7AE7 [gauge-scaling]"),
    0x5C: ("charging hours (I>0); discharge throughput", "h;Ah", "0x7AEC/0x78D3; 0x77CD rollover 14400000 FFE30 units = 1 Ah [gauge-scaling]"),
    0x5D: ("charge throughput; hist[0] (V0,T0)", "Ah;h", "0x7769 I>0 only, 0x778E 1 Ah rollover; 0x79F4 [gauge-scaling]"),
}
PARAM_NAMES.update(PARAM_NAMES_PATCH)

def param_rows(img):
    rows = []
    for k, (addr, v) in sorted(records(img).items()):
        f = struct.unpack("<f", struct.pack("<I", v))[0]
        name, unit, _ = PARAM_NAMES.get(k, ("", "", ""))
        rows.append({"idx": k, "addr": addr, "raw": v, "float": f if 1e-6 < abs(f) < 1e9 else None,
                     "name": name, "unit": unit})
    return rows

def cmd_params(a):
    img = read_image()
    rows = param_rows(img)
    if a.json:
        print(json.dumps({f"0x{r['idx']:02X}": r["raw"] for r in rows}, indent=1)); return
    print(f"active block {0xF1000 + active_block(img):05X}, {len(rows)} params")
    for r in rows:
        fs = f"{r['float']:.6g}" if r["float"] is not None else ""
        print(f"P{r['idx']:02X}  {r['addr']:05X}  {r['raw']:08X}  {r['raw']:>11}  {fs:>12}  {r['name']} {r['unit']}".rstrip())

def write_report(st, L, img, base):
    """Write base.json (everything) and base.md (summary)."""
    rows = param_rows(img)
    json.dump({"status": st, "log": L, "params": rows, "active_block": 0xF1000 + active_block(img),
               "image_hex": img.hex()}, open(base + ".json", "w"), indent=1)
    md = [f"# BMS report {os.path.basename(base)}", "",
          f"- model {st['model']}, serial {st['serial']}, mfg {st['mfg_date']}, cycles {st['cycles']}",
          f"- pack {st['pack_mv']} mV, {st['current_ma']} mA, {st['temp_c']} C",
          f"- cells {st['cells_mv']} mV (spread {st['spread_mv']} mV)",
          f"- capacity {st['rsoc_pct']}% {st['remaining_mah']}/{st['fcc_mah']} mAh (design {st['design_mah']})",
          f"- charge request {st['charge_req_ma']} mA @ {st['charge_req_mv']} mV",
          f"- status 0x{st['status']:04X} {' '.join(st['status_flags'])}; PF {'LIKELY LATCHED' if st['pf_likely'] else 'clear'}",
          "", f"## Fault log (now 0x{L['now']:04X})", "", "| ts (h+min) | h ago | code | bit | note |", "|---|---|---|---|---|"]
    md += [f"| 0x{e['ts']:04X}+{e['minute']}m | {L['now'] - e['ts']} | 0x{e['code']:02X} | {e['bit']}{' PF' if e['permanent'] else ''} | {e['note']} |"
           for e in L["fault_log"]]
    md += ["", "## Params", "", "| idx | raw | float | name | unit |", "|---|---|---|---|---|"]
    fl = lambda x: "" if x is None else f"{x:.6g}"
    md += [f"| P{r['idx']:02X} | 0x{r['raw']:08X} | {fl(r['float'])} | {r['name']} | {r['unit']} |" for r in rows]
    open(base + ".md", "w").write("\n".join(md) + "\n")

def cmd_report(a):
    st, L = read_status(), read_log()  # firmware mode first; the image read resets into the bootloader
    img = read_image()
    os.makedirs(os.path.join(ROOT, "reports"), exist_ok=True)
    base = os.path.join(ROOT, "reports", f"{datetime.datetime.now():%Y%m%d_%H%M%S}")
    write_report(st, L, img, base)
    print(f"wrote {base}.json and {base}.md")

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
    q = sp.add_parser("status"); q.add_argument("--json", action="store_true"); q.set_defaults(fn=cmd_status)
    q = sp.add_parser("params"); q.add_argument("--json", action="store_true"); q.set_defaults(fn=cmd_params)
    q = sp.add_parser("backup"); q.add_argument("file", nargs="?"); q.set_defaults(fn=cmd_backup)
    q = sp.add_parser("log"); q.add_argument("--json", action="store_true"); q.set_defaults(fn=cmd_log)
    sp.add_parser("report").set_defaults(fn=cmd_report)
    q = sp.add_parser("set-param"); q.add_argument("idx"); q.add_argument("value")
    q.add_argument("-y", "--yes", action="store_true"); q.set_defaults(fn=cmd_set_param)
    a = p.parse_args(); a.fn(a)

def _selftest():
    img = bytearray(b"\xff" * 4096)
    img[0x804:0x816] = bytes([0x17, 0xE8, 4, 0, 0, 0, 0x01, 0xFE, 1, 0, 0, 0, 0x17, 0xE8, 0, 0, 0, 0])
    assert records(bytes(img)) == {0x17: (0xF1810, 0), 0x01: (0xF180A, 1)}  # newest wins, block 2
    assert status_flags(0x48C0) == ["TERMINATE_CHARGE_ALARM", "TERMINATE_DISCHARGE_ALARM", "INITIALIZED", "DISCHARGING"]
    snap = struct.pack("<12H", 0, 0, 0, 0x8F54, 0xCA00, 0, 3566, 1173, 0, 1178, 3562, 2682)
    L = decode_log({0xE7: b"\x0a\x91", 0xF3: bytes([0x54, 0x8F, 0x16, 0xCA]), 0xF5: bytes([0x54, 0x8F, 0x16, 10]), 0xF0: snap, 0xF1: b"", 0xF2: b""})
    assert L["now"] == 0x910A and L["fault_log"][0]["bit"] == 50 and L["fault_log"][0]["permanent"]
    assert L["fault_log"][0]["minute"] == 22 and L["event_log"][0]["note"].startswith("cell voltage jump")
    assert PARAM_NAMES[0x19][0] == "FullChargeCapacity" and len(PARAM_NAMES) == 158
    assert L["snapshots"] == [{"ts": 0x8F54, "code": 0xCA, "cells_mv": [3566, 1173, 0, 1178, 3562, 2682], "raw": [0, 0, 0]}]
    r = dict.fromkeys(list(SBS_WORDS) + list(range(0x3A, 0x40)), 0); r.update(dict.fromkeys(SBS_BLOCKS, "x")); r.update({0x08: 2981, 0x0A: 0xFFFF, 0x16: 0x48C0})
    st = decode_status(r)
    assert st["current_ma"] == -1 and st["pf_likely"] and st["temp_c"] == 25.0
    bk = os.path.join(ROOT, "backups", "df_20261007_221649.bin")
    if os.path.exists(bk):  # real image: P17 cleared, PARAM_NAMES keys valid, report round-trips
        img = open(bk, "rb").read(); rows = param_rows(img)
        assert records(img)[0x17][1] == 0 and len(rows) >= 150 and all(0 <= k < 158 for k in PARAM_NAMES)
        import tempfile
        base = os.path.join(tempfile.mkdtemp(), "t")
        write_report(st, L, img, base)
        assert bytes.fromhex(json.load(open(base + ".json"))["image_hex"]) == img and "| P17 |" in open(base + ".md").read()

if __name__ == "__main__":
    _selftest()
    main()
