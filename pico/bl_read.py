from bl import *
enter_bl()
for c in CMDS:
    res = []
    for n in (1, 2, 3, 4, 5, 6, 8):
        try: res.append("%d:%s" % (n, rraw(c, n).hex()))
        except OSError as e: res.append("%d:E%s" % (n, e.args[0]))
    print("%02x" % c, " ".join(res))
for c in CMDS:
    r = rraw(c, 3); n = r[0]
    print("%02x pec over [len,data] ok=%s ; pec over [data] as word ok=%s" % (c,
          crc8(bytes([A << 1, c, A << 1 | 1]) + r[:2]) == r[2], None))
leave_bl()
