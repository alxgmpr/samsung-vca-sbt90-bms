"""Offline regression checks: dumps are intact, firmware facts the docs cite hold, the data-flash
history is what the README says it is, and the host/Pico code still decodes it.
Run: uv run --with pytest pytest -q"""
import glob, hashlib, importlib, os, struct, sys, types

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
import bms

def read(p): return open(os.path.join(ROOT, p), "rb").read()

CODE = read("firmware/codeflash.bin")
PRE_CLEAR = bytes.fromhex(read("firmware/df_pre_pfclear.hex").decode().strip())
# data-flash images in the order they were taken
HISTORY = [("df_pre_pfclear.hex", PRE_CLEAR)] + [(os.path.basename(p), read(p)) for p in (
    "backups/df_20261007_221649.bin", "backups/df_pre_P17_20261007_221744.bin",
    "backups/df_pre_unlock_20261007_233054.bin", "backups/df_post_unlock_20261007_233118.bin",
    "backups/df_pre_P10_20261007_235458.bin")]

def pico_module(name):
    """Import a pico/ MicroPython module with a stub `machine`."""
    class Dummy:
        def __init__(self, *a, **k): pass
    sys.modules["machine"] = types.SimpleNamespace(Pin=Dummy, I2C=Dummy, SoftI2C=Dummy)
    sys.path.insert(0, os.path.join(ROOT, "pico"))
    try: return importlib.import_module(name)
    finally: sys.path.pop(0)

def test_verified_backup_hashes():
    d = "backups/verified_20261007"
    for line in read(f"{d}/SHA256SUMS").decode().splitlines():
        h, f = line.split()
        assert hashlib.sha256(read(f"{d}/{f}")).hexdigest() == h, f
    assert read("firmware/codeflash.bin") == read(f"{d}/codeflash.bin")
    assert read("firmware/dataflash.bin") == read(f"{d}/dataflash.bin")
    assert len(CODE) == 0x10000 and len(read("firmware/dataflash.bin")) == 0x1000

def test_code_bit_table_matches_firmware():  # protection.md "Code table at 0x2422": [bit][code] pairs, 0-terminated
    tbl, a = {}, 0x2422
    while CODE[a + 1]:  # code byte 0 ends it (first pair has bit 0)
        tbl[CODE[a + 1]] = CODE[a]; a += 2
    assert tbl == bms.CODE_BIT

def test_firmware_constants_cited_in_docs():
    assert CODE[0xD400:0xD402] == b"SV"                                   # config signature (0xA5 check)
    assert CODE[0xD412:0xD41B] == b"21700_30T"                            # cell type, hardware.md
    assert struct.unpack_from("<f", CODE, 0xD960)[0] == 2850.0            # FCC seed / cap
    assert struct.unpack_from("<f", CODE, 0xD98C)[0] == 3195.0            # Qmax seed
    assert struct.unpack_from("<H", CODE, 0xD96E)[0] == 4160              # charge-term OCV

def test_crc8_pico_and_firmware_agree():
    smb, dfw = pico_module("smb"), pico_module("dfw")
    table = bytes(smb.crc8([i]) for i in range(256))
    assert table == read("firmware/cksum_table.bin") == CODE[0xDD4A:0xDD4A + 256]
    assert smb.crc8(b"123456789") == dfw.crc8(b"123456789") == 0xF4

def test_data_flash_history():
    for name, img in HISTORY:
        assert len(img) == 4096 and len(bms.records(img)) == 158, name
    p = lambda img, i: bms.records(img)[i][1]
    assert p(PRE_CLEAR, 0x17) == 4 and p(PRE_CLEAR, 0x87) >> 24 == 0xCA  # PF bit 50 = 0xCA dead cell
    assert all(p(img, 0x17) == 0 for _, img in HISTORY[1:])
    assert all(p(img, 0x10) == 0x52394C50 for _, img in HISTORY)          # date intact up to the P10 write
    assert read("firmware/dataflash.bin") != PRE_CLEAR and p(read("firmware/dataflash.bin"), 0x17) == 4

def test_data_flash_writes_are_append_only():
    for (a, x), (b, y) in zip(HISTORY, HISTORY[1:]):
        d = [k for k in range(4096) if x[k] != y[k]]
        assert all(x[k] == 0xFF for k in d), f"{a} -> {b} rewrote programmed bytes"
    first = min(k for k in range(4096) if PRE_CLEAR[k] != HISTORY[1][1][k])
    assert HISTORY[1][1][first:first + 6] == bytes.fromhex("17e800000000")  # the PF clear record

def test_bms_selftest():
    bms._selftest()

def test_all_python_compiles():
    for f in [os.path.join(ROOT, "bms.py")] + glob.glob(os.path.join(ROOT, "pico", "**", "*.py"), recursive=True):
        compile(open(f).read(), f, "exec")
