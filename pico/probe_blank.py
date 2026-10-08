from dfw import *
leave(); check(); enter()
try:
    print("status0", status())
    for a in (0xF1000, 0xF1400, 0xF1800, 0xF1C00, 0xF1CC0):
        print("blank %05X len16 ->" % a, blank(a, 16))
finally:
    leave(); check()
