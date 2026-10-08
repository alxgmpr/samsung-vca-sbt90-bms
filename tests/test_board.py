"""Read-only checks against the live board (Pico on BMS_PORT, pack awake). Opt-in:
  BMS_BOARD=1 uv run --with pytest pytest -q tests/test_board.py
Takes .board.lock; does SBS reads and one bootloader data-flash read (pin reset in and out). No writes."""
import glob, os, shutil, sys, time
import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
import bms

pytestmark = pytest.mark.skipif(os.environ.get("BMS_BOARD") != "1", reason="set BMS_BOARD=1 with the board attached")
LOCK = os.path.join(ROOT, ".board.lock")

@pytest.fixture(scope="module")
def board():
    os.mkdir(LOCK)  # fails if another session holds the board
    try:
        open(os.path.join(LOCK, "owner"), "w").write("tests/test_board.py | read-only HIL | 120\n")
        st, log = bms.read_status(), bms.read_log()  # firmware mode first; the image read resets via the bootloader
        img = bms.read_image()
        time.sleep(4)  # charge request reads 0 for ~3 s after the reset out of the bootloader
        yield {"status": st, "log": log, "img": img, "after": bms.read_status()}
    finally:
        shutil.rmtree(LOCK)

def test_identity(board):
    s = board["status"]
    assert (s["model"], s["mfg_name"], s["chem"], s["serial"]) == ("SEC_VS9000NL", "SDI", "LION", 415)
    assert s["design_mah"] == 2850 and s["design_mv"] == 21900
    assert s["cycles"] >= 387 and 0 < s["fcc_mah"] <= 2850  # FCC capped at the 0xD960 seed

def test_no_pf(board):
    for s in (board["status"], board["after"]):  # before and after the bootloader session
        assert not s["pf_likely"] and s["status"] & 0x4800 == 0, s["status_flags"]
        assert s["charge_req_ma"] > 0

def test_cells_sane(board):
    s = board["status"]
    assert len(s["cells_mv"]) == 6 and all(2600 < c < 4230 for c in s["cells_mv"])  # inside UV/OV trip points
    assert s["spread_mv"] < 170  # imbalance PF (0xCC) at rest
    assert abs(sum(s["cells_mv"]) - s["pack_mv"]) < 300

def test_params(board):
    r = {k: v for k, (_, v) in bms.records(board["img"]).items()}
    assert sorted(r) == list(range(158))
    assert r[0x17] == 0  # PF mask (lo) and protection-disable mask (hi) both clear
    assert r[0x10] & 0xFFFF == 0x4C50  # 'PL' constant; hi half = ManufactureDate
    date = bms.decode_status({**dict.fromkeys(list(bms.SBS_WORDS) + list(bms.SBS_BLOCKS) + list(range(0x3A, 0x40)), 0), 0x1B: r[0x10] >> 16})["mfg_date"]
    assert date == board["status"]["mfg_date"]  # SBS 0x1B is served from P10 hi

def test_data_flash_extends_latest_backup(board):
    latest = max(glob.glob(os.path.join(ROOT, "backups", "df_*.bin")), key=lambda p: p[-19:])  # ..._YYYYMMDD_HHMMSS.bin
    prev, img = open(latest, "rb").read(), board["img"]
    if bms.active_block(prev) != bms.active_block(img):
        pytest.skip("EEL block rotated since " + os.path.basename(latest))
    assert all(prev[k] == 0xFF for k in range(4096) if prev[k] != img[k]), "programmed bytes changed since " + latest

def test_log_codes_known(board):
    L = board["log"]
    assert L["fault_log"] and all(e["code"] in bms.CODE_BIT for e in L["fault_log"] if e["code"])
    assert all(e["note"] for e in L["event_log"] if e["code"]), [e["code"] for e in L["event_log"]]
    assert all(e["ts"] <= L["now"] for e in L["fault_log"] + L["event_log"])
