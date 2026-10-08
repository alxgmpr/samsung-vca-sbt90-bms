# Events and boot checks: 0xA7, P13.7, event dispatch, 0x80 modes, event log, 0xB4 flag, log minute byte

Static analysis of `firmware/code.dis`. Live RAM values come from the gated SBS RAM read ([../protocol.md](../protocol.md))
on 2026-10-08 at 05:31:07Z (logged in `_board_log.md`).
Confidence tags: **VS** = verified-static, **VB** = verified on the board, **INF** = inferred.

## Summary

| # | Question | Answer | Conf |
|---|---|---|---|
| 1 | Code 0xA7 | Data-flash (EEL) write failure. When params are dirty and no deferred events are pending, the main loop runs one flush step; if the EEL error byte 0xFFE96 is 4 (read-back mismatch) or 5 (PFDL erase error / out of retries), it sets bit 39 | VS (error meanings INF) |
| 2 | P13.7 "detect" | Package pin 30 = P137/INTP0, input only. The flag 0xFFB55.2 = P13.7 low for 8 consecutive samples. Live: P13 = 0x00, FFB55 = 0x24, so the detect is active on the bench with no charger. The board net is not traced | VS + VB (net open) |
| 3 | Event 6 / 0x7A re-lock | Dispatcher event 6 is never posted, so re-lock 0x3FE8 is dead code. The unlock clears only when 0x7A is written with another value, or on reset | VS + VB (0x7A = 0 after reset) |
| 3b | 0x7E01 | Gauge-context load. It copies P18–P31 into the gauge; if 0xBEEF is missing, it seeds them from factory constants first (FCC 2850.0) | VS |
| 4 | SBS 0x80 modes | 1 = reset, 2 = ship/shutdown, 3 = direct FET override, 4 = FET-request override, 5 = coulomb-counter (CC) calibration (factory only), 10 = flag with no reader; the others do nothing | VS (mode semantics partly INF) |
| 5 | 0xF5 event codes | A separate numbering from the fault codes. **Event code 10 = "a cell moved ≥ 500 mV"**, which is why `0x0A` appears at the trip | VS |
| 6 | 0xB4 flag | 0xFFB50.1 is persisted in P17 bit 17 (P17 hi bit 1) and survives reset. It clears through set-param P17 hi = 0, or through 0x87 (clear-all) | VS |
| 7 | Log middle byte | **Not a state.** It is P73 lo = minutes past the hour (0–59) of the timestamp P5B (hours) | VS |
| — | **Log freeze** | The fault log, the event log and event counters n0–n4 are **frozen now** (live 0xFFE94 = 1), and they stay frozen across resets. A single set-param can unfreeze them; see "Log freeze and unfreeze" | VS + VB |

## 1. Code 0xA7 (bit 39)

Main loop at 0x9CBE:
```
if (FFE97 /*params dirty*/ && FFE5C == 0 /*deferred queue empty*/) {
    7031(1);                         // one EEL flush step
    if (FFE96 == 4 || FFE96 == 5) { fault-log 0xA7 (callt [0xB2]); set bit 39 (0x5EF6) }
}
```
- 0xFFE97 is the params-dirty flag. It is set by mark-dirty 0x6FE0 (CALLT [0xB0]) and cleared when a flush completes (0x7052, 0x7366, 0x73BA), or by 0x9CF0 when 0xFFEA0.3 is set.
- 0xFFE95 is the EEL writer state. State 4 means stopped/failed; 0x7031 forces 0xFFE97 to 0 when 0xFFE95 is 4.
- 0xFFE96 is the EEL error code. Its setters:

| Value | Set at | Condition (INF) |
|---|---|---|
| 3 | 0x7195, 0x71A8 | block header bytes not 0xFF / footer byte ≠ 63 (block format) |
| 4 | 0x6F10, 0x6FAA | read-back/compare mismatch after a record write (verify) |
| 5 | 0x7219, 0x7473 | PFDL status 0x1A after an erase (0xB63E), or retry count 0xFFE9A ≥ 3 |
| 7 | 0x6D07 | EEL/PFDL open failure at init (0x9BB3 skips the param load when it is 7) |

- 0xFFEA0.3 (set at 0x6E81) is the fatal-EEL flag. With it set, 0x7031 does nothing and 0x9CE6 drops the dirty flag.
- **Meaning: 0xA7 = data-flash write/erase failure.** Live 0xFFE96 = 0 and 0xFFE97 = 0 (healthy).

## 2. P13.7 detect (0xFFB55.2)

- 0x5E1E returns `!(P13 >> 7)`, where P13 is SFR 0xFFF0D. The debounce at 0x8853 shifts in samples until 8 in a row agree: all 1 sets 0xFFB55.2, all 0 clears it. So **0xFFB55.2 = 1 means P13.7 is low**.
- Datasheet (RAJ240080 pin table): pin 30 = **P137/INTP0**, digital input only ("connect to GND1 through a resistor if not used").
- Live: P13 = 0x00 (P13.7 low) and FFB55 = 0x24 (bit 2 set). This is on the bench with the resistor ladder, about 22.2 V at the terminal and no charger. So the detect is **active in the normal idle state**: something on the board holds pin 30 low. Charger or MODE detect is not confirmed.
- Users of 0xFFB55.2: the 0x5C terminal-OV branch at 0x8615, the full-charge detect at 0x827C, and about 20 others (grep `#0xfb55`).
- Open: which net reaches pin 30. One check, with the board unpowered: continuity from U1 pin 30 to the MODE pad (CN4) and to the P+ / C+ dividers.

## 3. Event dispatch, event 6, 0xFFE80 lifetime, 0x7E01

**Event queue (0xB1B0).** Event A < 128 goes into the 20-slot ring at 0xFFA5E (write index 0xFFB6F, pending count 0xFFE5D). Event A ≥ 128 goes into the 48-slot ring at 0xFF988 as A & 0x7F (write index 0xFFB6D, pending count 0xFFE5C); if that ring overflows, 0xFFEA0.0 is set (reset). The reader at 0xB161/0xB16E calls the dispatcher **0x93B4** (the switch on A).

Dispatcher case map (event → handler): 0→0x947C, 1→0x950A, 2→0x94E7, 3→0x9499, 4→0x9510, **6→0x9522**, 7→0x9533, 8/10/11/13/31–34→0x955D,
12→0x953B, 17→0x94EB, 19→0x9544 (persist P17, 0xAB10), 23→0x954A, 30→0x9552, 35→0x9562, 36→0x956B, 37→0x957C, 38→0x9585, 39→0x958B,
40→0x9591, 41→0x959A, 48→0x964F, 49→0x9657, 50→0x965C, 73→0x9661, 74→0x95E0, 75→0x9637, 78→0x9641.

Posters: all 42 `call !0xB1B0` sites are enumerated, and 0xB1B0 is the only writer to either ring.

| Event | Posted at | Source |
|---|---|---|
| 0,1,2,3,4,7,31–34 | 0x9C43–0x9CB8 | timer flag bits in 0xFFE7C/0xFFE7D |
| 5 | 0x8927 | — |
| 8, 9 | 0xAA25, 0xAA40 | — |
| 19 | 0x83EE | PF check |
| 23 | 0x7F6A, 0x7F90 | full-charge detect |
| 30 | 0x7FBC | UV bit 2 first set |
| 35–41, 48–50, 73–75, 78 | — | deferred (posted as 163–206) |

- **Event 6 and event 12 have no poster.** The 0x7A re-lock (0x9522 → 0x3FE8 → 0xFFE80 = 0) and the event-12 path (0x953B, shutdown timer + log code 3) are dead code.
- So the 0x7A unlock stays on until 0x7A is written with any other value (the 0x45BB writer) or the MCU resets. 0xFFE80 = 0 after reset (VB).
- Not verified: whether the unlock survives sleep. HALT/STOP keep RAM, so if the pack sleeps without a reset it probably stays unlocked. Re-lock explicitly.
- `mov a,#6` at 0x954E is **event-log code 6** (CALLT [0xBC] = 0xAA82 → 0x7C85), not dispatcher event 6, so a full charge does not touch 0x7A.

**0x7E01 = gauge context load.** Called at boot (0x247B, in the init chain 0x939F) and after the 0x87 reset (0x7F16 clears 0xBEEF, then 0x7F20).
- **If P32 lo = 0xBEEF:** copy P18/P19/P1A, the 15-float table at 0xFF57C and the 8-float table at 0xFF5B8 into the gauge structs at 0xFF8CE/0xFF818.
- **Otherwise, seed first:**
  - P18 ← RAM 0xFF9F6/8;
  - P19 (FCC) ← float **2850.0** @0xD960;
  - P1A ← f(**4160** @0xD96E) via 0xB503/0xA32F (also copied to 0xFF8D8);
  - 0xFF57C ← 15 floats @0xD904 (0.399, 0.2704, 0.1418, 0.0437, 0.0276, 0.0261, 0.0267, 0.0255, 0.0233, 0.0219, 0.024, 0.023, 0.0229, 0.0217, 0.0181);
  - 0xFF5B8 ← 8 floats @0xD940 (0.0444 … 0.0456);
  - 0xFF5F2 ← 0xDAE2 (0);
  - then set 0xBEEF and save 106 B from 0xFF570.
- **Always:** 0xFFB22 ← 4100 @0xD488. This is the full-charge cell threshold used by 0x8259.
- So after a 0x87 reset, FCC restarts at the 2850 mAh design value and has to re-learn.

## 4. SBS 0x80 test/FET modes (validator 0x46D0, writer 0x46EC)

- Needs the unlock (0x48DE). Word: **low byte = mode (1–13 accepted), high byte = argument bits**.
- A read returns the last word written (0xFFB48).
- Every mode except 1 sets a bit in 0xFFEB4. While 0xFFEB4 ≠ 0, a 7200-tick counter 0xFFB4A runs (0x407D, reloaded at 0x4076 whenever the mode changes). When it expires, 0x405D clears all modes. Writing 0x7A to re-lock calls 0x405D(0), which clears them too.

| Mode | Effect | Conf |
|---|---|---|
| 1 | sets 0xFFEA0.0; the main loop (0x9CF6) writes AFE reg 3 = 0 (0xAA86), event-log code 4, EEL flush, then **watchdog reset** (0x9B98 writes 0xFE to WDTE 0xFFFAB) | VS |
| 2 | same as ManufacturerAccess 0x0010: 0xFFEB4.4, shutdown timer 0xB418 (0xFFE5E = 8+1 ticks, @0xD4F0), event-log code 1. After the delay, FETs are forced off (0xFFE8E = 0x80). If terminal ≥ 19800 mV (@0xD4F6, charger present) it cancels; once terminal < 1800 mV (@0xD4F2) it sets 0xFFEA0.1 → AFE reg 3 = 0, flush, ~2000-loop wait, WDT reset as fallback. **Ship / power-off mode** | VS (ship meaning INF) |
| 3 | 0xFFEB4.0; argument bits b0→0xFFE8E.2, b1→.0, b2→.1, and sets 0xFFE8E.7 (0xA949/0xA951). **Direct FET override**: 0xFFE8E.7 makes 0x5505 drive P1 from 0xFFE8E. 0xFFE8E.2 → P1 bits 2+6 (0xFFEA5 \|= 0x44) | VS (FET mapping INF) |
| 4 | argument b7 = exit: toggles 0xFFEB4.1 and clears 0xFFE35/0xFFB60. Otherwise 0xFFEB4.1 is set and 0xFFB60[3:0] = argument b0–b3, which replaces the FET request byte 0xFFE35 in 0x54B1/0x556C (→ 0xFFB78 bits 2–4). Argument b4 sets 0xFFB65 = 1 (saved to 0xFFB83) and calls CALLT [0x98](2); b5 sets 0xFFB65 = 0. **FET-request override** | VS (bit meanings INF) |
| 5 | refused (0xFFB84 = 3) if 0xFFE36.3 is set or P10 (0xFF552) ≠ 0, i.e. ManufactureDate set. Otherwise: AFE reg 0x58 = 0 (CC off), 0xFFFD4.6 set / 0xFFFD0.6 cleared, CALLT [0x90] (0x51AB), 0xFFEB4.3, 0xFFEB7 = 2. **Factory CC/offset calibration**, blocked on this unit | VS (purpose INF) |
| 6 | nothing | VS |
| 10 | 0xFFEB4.2; no reader found | VS |
| 7–9, 11–13 | accepted, nothing happens | VS |

Live: 0xFFB48 = 0x0000, 0xFFB4A = 0 (no mode active).

**The earlier ManufacturerAccess sweep:** writing 0x0010 to 0x00 started ship mode (0xAF7A). With the bench supply holding the terminal above 19.8 V it was probably cancelled, apart from the 8-tick FET-off window. The write also logged event code 1, but only if the log wasn't frozen (see "Log freeze and unfreeze").

## 5. Event log 0xF5 (writer 0x7C85)

- Entry = `[P5B hours u16][P73 lo minutes][code]`, a 4-entry ring at 0xFF774 (index 0xFF776).
- Codes 0–11 are accepted (`cmp a,#12`). Nothing is written while 0xFFE94 is set.
- **These are not fault codes.**

| Code | Source | Meaning | Conf |
|---|---|---|---|
| 1 | 0x4715, 0xAF81 | ship/shutdown request (SBS 0x80 mode 2 or ManufacturerAccess 0x0010) | VS |
| 2 | 0x85A6 | deep-discharge power-off: fault bit 24 set, I > −100 mA (0xD498 = −10 units), terminal < 1800 mV (0xD4F4), counter 0xFFE50 reaches 2400 (0xD47E), then 0xFFEA0.1 | VS |
| 3 | 0x9540 | shutdown timer via dispatcher event 12; never posted (dead) | VS |
| 4 | 0x9CFF, 0x9D28 | firmware reset/power-down (0xFFEA0.0: 0x80 mode 1, queue overflow, 0xB15D, 0x40BF; 0xFFEA0.2: 0x4A6D in the 0xA0 path) | VS |
| 5 | 0xAB0C (boot 0x9C1B) | boot/wake; also counts n0 (P4F lo, boots) | VS |
| 6 | 0x954E (event 23) | full charge reached: 0xFFE68 ≥ 4100 mV (0xFFB22) and \|I\| ≤ 10 units for 120 ticks (0xD48A/0xD48C), or 0xFFB75. Counts n3 (0xFF652 = 6227). Re-armed when RSOC < 98 % (0xD4A0) | VS (0xFFE68 = max cell INF) |
| 7 | 0x9556 (event 30) | under-voltage fault bit 2 (code 0x14) first set. Counts n4 (0xFF654 = 38, which matches the 0x14 lifetime count of 38) | VS |
| 8 | 0x7CFC | charge started: I > 0 for 12 consecutive ticks (0xD52C) | VS |
| 9 | 0x7CE0 | charge ended: I ≤ 0 for 12 ticks (0xD52E) | VS |
| 10 | 0x7D40 | **a cell moved ≥ 500 mV (0xD530)** from the last logged cell set (0xFFA86 vs the live array 0xFFE24, 0xD404 = 6 cells) | VS |

The current event log is four entries of code 10 at ts 0x8F54, minute 22: cells collapsing in the same minute as the 0xCA trip. After that the PF froze the log, so there are no boot entries since.

```python
# event-log (SBS 0xF5) codes; merged into bms.py
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
```

## 6. The 0xB4 "voltage checks off" flag

- Storage: **0xFFB50 bit 1** (the protection-disable word; 0xB216 sets bits, 0xB224 clears them, 0xB20A tests them).
- **Persisted:** 0x83CA–0x83CD ORs P17 hi (0xFF56E) into 0xFFB50 at boot, and 0xAB10 (event 19) saves it. The flag is P17 bit 17.
- **Survives reset: yes.** While it is set, 0x6B72 sets fault bit 40 (0xB4) again once per boot (0xFFB88 latch).
- **How it clears:**
  - the clear-all 0xAA55, reached only from SBS 0x87 (0x491A);
  - or a P17 write with the high word 0: set-param 0x17, or the unlock route 0x84/0x8A.
- No other code clears 0xFFB50.
- Live: 0xFFB50 = 0x0000, and P17 hi = 0.

## 7. The log middle byte = minutes past the hour

- 0xFFE92 counts ticks to 60 (0xD534), then P73 b0 (0xFF6DC) increments (0x7ADF). When P73 b0 reaches 60 (0xD532), 0x78A0 clears it and increments P5B (0x74FE).
- P73 b1/b2 are the same minute counters for discharging and charge-state time.
- Log entries store `[P5B][P73 b0]`, so the byte is **minute 0–59 within powered hour P5B**. With a 1 s tick (INF) a log time is `P5B h + minute min`.
- The three 0x5C entries at 0x8E46 (minutes 3, 5, 6) are three trips within one hour.
- There is no state machine behind it. `bms.py log` prints it as `ts 0x8F54+22m`.

## Log freeze and unfreeze

**How the freeze works:**
- 0xFFE94 = 1 blocks the fault-log writer (0x760F), the event-log writer (0x7C85) and the event counters (0x7648, n0–n4).
- It is set in two places:
  - 0x7BE3, when the fault logger writes a code ≥ 200;
  - **at every boot**, by 0x750B (called from 0x9BCF via 0xAA51, after the param load), when the newest fault snapshot's code is ≥ 200.
- It is cleared only by 0x7547 (lifetime wipe: 0x87 clear-all, or boot with 0xFFE98 set because the lifetime block is invalid).
- Live 0xFFE94 = 1. The logs are frozen now and will stay frozen after the rebuild.

**What 0x750B reads:**
- `idx = P7F lo` (0xFF70C, values 1–3).
- Code byte = `[0xF6FF + 24·idx]` = byte 3 of the third u32 in slot idx. Slots are at 0xFF70E / 0xFF726 / 0xFF73E.

| idx | Code byte | Param, byte | Current value |
|---|---|---|---|
| 1 | 0xFF717 | P81, byte 3 | P81 = 0x16168F54 (code 0x16) |
| **2** | 0xFF72F | **P87, byte 3** | **P87 = 0xCA168F54** (code 0xCA, minute 0x16, ts 0x8F54) |
| 3 | 0xFF747 | P8D, byte 3 | P8D = 0x14168F54 (code 0x14) |

Current P7F = 0x00000802: idx 2, and the fault-log ring index is 8 in byte 1. The checked byte is therefore **P87 byte 3 = 0xCA**.

**Yes, one set-param unfreezes the logs and keeps the P3F–P9D history. Two choices:**

| | Option A (recommended) | Option B |
|---|---|---|
| Command | `bms.py set-param 0x87 0x00168F54` | `bms.py set-param 0x7F 0x00000801` |
| What it changes | The newest snapshot's code becomes 0x00. Its ts and cell words (P88–P8C) stay | Points the snapshot index at slot 1 (code 0x16). All three snapshots stay byte-identical for now |
| What happens next | The next new fault code goes to slot 3 and replaces the 0x14 snapshot (P8D–P92) | The next new fault code goes to slot 2 and replaces the 0xCA snapshot. The fault-log ring index (byte 1 = 0x08) must stay as it is |

Notes for both options:
- They take effect at the next boot; 0xFFE94 is RAM, zero after reset.
- Nothing else re-sets 0xFFE94 unless a code ≥ 200 is logged again.
- Take a backup first. The original 0xCA snapshot is also in `backups/df_post_unlock_20261007_233118.bin`.
- `bms.py log` will then show code 0x00 for that snapshot (A), or keep showing 0xCA until it is overwritten (B).
- Option A is step 6 of the README cell install procedure, run after assembly. It is the same kind of write as the P17 clear (one EEL record).

## Open questions

- The net on U1 pin 30 (P13.7), and what holds it low on the bench. Needs a continuity check with the board unpowered.
- The tick period behind 0xFFE7C.0 and dispatcher event 0. 1 s is inferred from the 60 × 60 minute/hour counters matching the ~1/h P5B rate.
- 0xFFE68: assumed to be max cell mV (full-charge detect); not confirmed.
- What AFE reg 3 = 0 (0xAA86) does before shutdown or reset. [balancing.md](balancing.md) lists reg 0x03 as ADC/CC stop (inferred); the data sheet gives no address for it.
- Whether 0xFFE80 (the unlock) survives sleep/STOP without a reset.
