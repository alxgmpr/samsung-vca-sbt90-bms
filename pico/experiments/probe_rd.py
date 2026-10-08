from dfw import *
enter()
try:
    for n in (64, 32, 16):
        for a in (0xF1840, 0xF1880, 0xF1900):
            rs = []
            for _ in range(6):
                try: rs.append(rd(a, n).hex()[:24])
                except OSError as e: rs.append("E%d" % e.args[0])
            print(n, "%05X" % a, rs)
    print("seq64:", [rd(a, 64)[:4].hex() for a in range(0xF1800, 0xF1C00, 64)])
finally:
    leave()
