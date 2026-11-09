"""Deep Scan: deteksi kerusakan lanjutan lewat ADB (hanya membaca).

Alurnya tiga tahap:
1. Probe: menjalankan perintah baca-saja di HP (`collect_facts`). Setiap probe
   yang gagal dicatat sebagai "tidak terbaca" dan tidak pernah ditebak.
2. Parser: mengubah keluaran mentah jadi fakta terstruktur (fungsi murni, bisa
   dites tanpa HP).
3. Penyimpul (`analyze`): aturan yang menggabungkan fakta jadi temuan, lalu
   dugaan komponen rusak lengkap dengan tingkat keyakinan dan buktinya.

Batas yang jujur: ADB hanya bisa melihat HP yang sudah menyala. Kerusakan board
tanpa gejala di software, kerusakan fisik, dan kena cairan tidak terbaca. Hasil
berupa petunjuk untuk teknisi, bukan vonis.

Aturan yang sama ada di web/src/deepscan-engine.js; ubah keduanya bersamaan.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from typing import Callable

from .adb import ADBError, run_adb

# ---------------------------------------------------------------------------
# Komponen dan saran tindakan
# ---------------------------------------------------------------------------

BATTERY = "Baterai"
CHARGE = "Port charge / IC pengisian"
STORAGE = "Penyimpanan (eMMC/UFS)"
TOUCH = "Layar / touch panel"
BOARD = "Mainboard / catu daya"
MODEM = "Modem / sinyal"
SENSOR = "Sensor"
CAMERA = "Kamera"
SOFTWARE = "Software / sistem"
THERMAL = "Panas berlebih / pendinginan"

ACTIONS = {
    BATTERY: "Uji dengan baterai pengganti atau ganti baterai. Jangan dipakai kalau menggembung.",
    CHARGE: "Bersihkan port, coba kabel dan adaptor lain, lalu periksa flex/port charge dan IC pengisian.",
    STORAGE: "Backup data sekarang. Kalau sudah lambat atau umur flash tinggi, siapkan ganti/reball storage.",
    TOUCH: "Coba layar lain untuk membandingkan. Periksa flex touch dan IC touch kalau layar baru pun sama.",
    BOARD: "Cek baterai dan konektor dulu. Kalau tetap restart sendiri, periksa IC power (PMIC) dan jalur power di board.",
    MODEM: "Cek SIM tray dan antena. Kalau baseband hilang, periksa IC/EMMC modem atau lakukan perbaikan IMEI/baseband resmi.",
    SENSOR: "Cek flex sensor dan konektor. Bandingkan dengan HP sejenis yang normal.",
    CAMERA: "Cek konektor modul kamera dan coba modul pengganti.",
    SOFTWARE: "Update/flash firmware resmi setelah backup. Kalau gejala tetap ada, curigai hardware.",
    THERMAL: "Bersihkan debu, periksa pasta/pad panas dan baterai. Panas saat idle sering tanda korsleng atau baterai rusak.",
}

SEVERITY_WEIGHT = {"info": 0.0, "warn": 1.2, "fail": 3.0}


@dataclass(frozen=True)
class Finding:
    code: str
    component: str
    severity: str  # info | warn | fail
    title: str
    detail: str
    weight: float | None = None  # None = pakai bobot default dari severity

    @property
    def effective_weight(self) -> float:
        return SEVERITY_WEIGHT[self.severity] if self.weight is None else self.weight


@dataclass(frozen=True)
class Suspect:
    component: str
    confidence: float
    level: str  # Tinggi | Sedang | Rendah
    reasons: tuple[str, ...]
    action: str


@dataclass
class DeepScanReport:
    score: int
    verdict: str
    suspects: list[Suspect] = field(default_factory=list)
    findings: list[Finding] = field(default_factory=list)
    unreadable: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Parser (fungsi murni)
# ---------------------------------------------------------------------------

def _int(value: str | None) -> int | None:
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return None


def _kv(text: str, key: str) -> str | None:
    m = re.search(rf"^\s*{re.escape(key)}:\s*(.+?)\s*$", text, re.M | re.I)
    return m.group(1) if m else None


def _bool(text: str, key: str) -> bool | None:
    v = _kv(text, key)
    if v is None:
        return None
    return v.lower() == "true"


def parse_battery(dumpsys_battery: str, sysfs: str = "") -> dict:
    sysvals: dict[str, int | None] = {}
    for line in sysfs.splitlines():
        if "=" in line:
            k, v = line.split("=", 1)
            sysvals[k.strip()] = _int(v)
    temp = _int(_kv(dumpsys_battery, "temperature"))
    return {
        "present": _bool(dumpsys_battery, "present"),
        "health_code": _int(_kv(dumpsys_battery, "health")),
        "status_code": _int(_kv(dumpsys_battery, "status")),
        "level": _int(_kv(dumpsys_battery, "level")),
        "temp_c": temp / 10 if temp is not None else None,
        "voltage_mv": _int(_kv(dumpsys_battery, "voltage")),
        "ac": _bool(dumpsys_battery, "AC powered"),
        "usb": _bool(dumpsys_battery, "USB powered"),
        "wireless": _bool(dumpsys_battery, "Wireless powered"),
        "cycle_count": sysvals.get("cycle_count"),
        "charge_full": sysvals.get("charge_full"),
        "charge_full_design": sysvals.get("charge_full_design"),
    }


def parse_storage(life_text: str, diskstats: str, df_text: str = "") -> dict:
    lives = []
    for tok in re.findall(r"0x[0-9a-fA-F]+|\b[0-9a-fA-F]{1,2}\b", life_text or ""):
        try:
            n = int(tok, 16)
        except ValueError:
            continue
        if 1 <= n <= 11:
            lives.append(n)
    latency = None
    m = re.search(r"Latency:\s*(\d+)\s*ms\s*\[512B Data Write\]", diskstats or "", re.I)
    if m:
        latency = int(m.group(1))
    free_pct = None
    m = re.search(r"Data-Free:.*?=\s*(\d+)%\s*free", diskstats or "", re.I)
    if m:
        free_pct = int(m.group(1))
    elif df_text:
        last = df_text.strip().splitlines()[-1].split()
        try:
            total, used = float(last[1]), float(last[2])
            if total > 0:
                free_pct = round(100 - used / total * 100)
        except (IndexError, ValueError):
            pass
    return {"life": max(lives) if lives else None, "write_latency_ms": latency, "free_percent": free_pct}


_ABNORMAL_BOOT = ("kernel_panic", "panic", "watchdog", "wdt", "hard_reset", "hw_reset",
                  "pmic", "undervoltage", "brownout", "shutdown,thermal", "thermal",
                  "shutdown,battery", "power_loss", "cold")
_POWER_BOOT = ("pmic", "undervoltage", "brownout", "shutdown,battery", "power_loss", "cold")

_DROPBOX_TAGS = ("system_server_watchdog", "system_server_crash", "system_tombstone",
                 "system_last_kmsg", "system_fsck", "system_restart", "system_boot")


def parse_boot(history: str, current_reason: str, dropbox: str) -> dict:
    lines = [l.strip().lower() for l in (history or "").splitlines() if l.strip()]
    if current_reason and current_reason.strip():
        lines.append(current_reason.strip().lower())
    abnormal = [l for l in lines if any(k in l for k in _ABNORMAL_BOOT)]
    power = [l for l in lines if any(k in l for k in _POWER_BOOT)]
    kernel = [l for l in lines if "panic" in l or "watchdog" in l or "wdt" in l]
    counts = {tag: len(re.findall(tag, dropbox or "", re.I)) for tag in _DROPBOX_TAGS}
    return {
        "history_count": len(lines),
        "abnormal": len(abnormal),
        "power": len(power),
        "kernel": len(kernel),
        "dropbox": counts,
    }


def parse_thermal(zones_text: str, thermalservice: str) -> dict:
    zones: dict[str, float] = {}
    for line in (zones_text or "").splitlines():
        if "=" not in line:
            continue
        name, raw = line.split("=", 1)
        try:
            v = float(raw.strip())
        except ValueError:
            continue
        if abs(v) >= 1000:
            v /= 1000
        if -20 <= v <= 150:
            zones[name.strip() or "zone"] = v
    for m in re.finditer(r"mValue=([\-\d.]+),\s*mType=\d+,\s*mName=([^,}]+)", thermalservice or ""):
        v = float(m.group(1))
        if -20 <= v <= 150:
            zones[m.group(2).strip()] = max(v, zones.get(m.group(2).strip(), v))
    status = None
    m = re.search(r"Thermal Status:\s*(\d+)", thermalservice or "")
    if m:
        status = int(m.group(1))
    return {
        "zones": zones,
        "max_c": max(zones.values()) if zones else None,
        "status": status,
    }


def parse_input_devices(getevent_lp: str) -> list[dict]:
    """Daftar perangkat input dengan rentang koordinat sentuh."""
    devices: list[dict] = []
    blocks = re.split(r"^add device \d+:\s*", getevent_lp or "", flags=re.M)
    for block in blocks[1:]:
        path = block.splitlines()[0].strip()
        name_m = re.search(r'name:\s*"([^"]*)"', block)
        xm = re.search(r"ABS_MT_POSITION_X\s*:.*?max\s+(\d+)", block) or re.search(r"\bABS_X\s*:.*?max\s+(\d+)", block)
        ym = re.search(r"ABS_MT_POSITION_Y\s*:.*?max\s+(\d+)", block) or re.search(r"\bABS_Y\s*:.*?max\s+(\d+)", block)
        if xm and ym:
            devices.append({
                "path": path,
                "name": name_m.group(1) if name_m else "",
                "x_max": int(xm.group(1)),
                "y_max": int(ym.group(1)),
            })
    return devices


_TOUCH_NAME_HINT = re.compile(r"ts|touch|fts|goodix|synaptics|focaltech|himax|nvt|novatek|gt9|atmel|elan|sec_", re.I)


def pick_touchscreen(devices: list[dict]) -> dict | None:
    if not devices:
        return None
    hinted = [d for d in devices if _TOUCH_NAME_HINT.search(d["name"] or "")]
    pool = hinted or devices
    return max(pool, key=lambda d: d["x_max"] * d["y_max"])


def touch_coverage(events_text: str, x_max: int, y_max: int, cols: int = 6, rows: int = 10) -> dict:
    """Hitung sel layar yang pernah disentuh dari keluaran `getevent -l`.

    Posisi baru dicatat saat SYN_REPORT (satu bingkai sentuhan lengkap) dan
    dipisah per jari (ABS_MT_SLOT), supaya X dari satu titik tidak dipasangkan
    dengan Y dari titik lain. Kalau keluaran tidak punya SYN_REPORT sama sekali,
    posisi dicatat setiap kali X dan Y sama-sama baru.
    """
    text = events_text or ""
    has_syn = "SYN_REPORT" in text
    abs_pat = re.compile(r"ABS_(MT_POSITION_|MT_SLOT|)([XY]?)\s+([0-9a-fA-F]+)")
    visited: set[tuple[int, int]] = set()
    points = 0
    slot = 0
    pos: dict[int, list] = {}      # slot -> [x, y]
    dirty: dict[int, set] = {}     # slot -> {"X","Y"}

    def commit(sl: int) -> None:
        nonlocal points
        x, y = pos.get(sl, [None, None])
        if x is None or y is None:
            return
        cx = min(cols - 1, max(0, int(x / (x_max + 1) * cols)))
        cy = min(rows - 1, max(0, int(y / (y_max + 1) * rows)))
        visited.add((cx, cy))
        points += 1

    for line in text.splitlines():
        if "SYN_REPORT" in line:
            for sl in list(dirty):
                if dirty[sl]:
                    commit(sl)
            dirty = {}
            continue
        m = abs_pat.search(line)
        if not m:
            continue
        kind, axis, raw = m.group(1), m.group(2), int(m.group(3), 16)
        if kind == "MT_SLOT":
            slot = raw
            continue
        if kind == "" and "ABS_MT" in line:
            continue
        if axis not in ("X", "Y"):
            continue
        entry = pos.setdefault(slot, [None, None])
        entry[0 if axis == "X" else 1] = raw
        dirty.setdefault(slot, set()).add(axis)
        if not has_syn and dirty[slot] == {"X", "Y"}:
            commit(slot)
            dirty[slot] = set()
    for sl in list(dirty):
        if dirty[sl]:
            commit(sl)

    total = cols * rows
    uncovered = [(c, r) for r in range(rows) for c in range(cols) if (c, r) not in visited]
    return {
        "cols": cols,
        "rows": rows,
        "points": points,
        "coverage": len(visited) / total,
        "uncovered": uncovered,
    }


def parse_modem(props: dict[str, str], radio_log: str = "") -> dict:
    sim = (props.get("gsm.sim.state") or "").strip()
    base = (props.get("gsm.version.baseband") or "").strip()
    return {
        "sim_state": sim,
        "baseband": base,
        "radio_unavailable": len(re.findall(r"RADIO_NOT_AVAILABLE|radio not available", radio_log or "", re.I)),
    }


def parse_sensors(text: str) -> dict:
    low = (text or "").lower()
    return {
        "read": bool(low.strip()),
        "accelerometer": "accelerometer" in low,
        "proximity": "proximity" in low,
        "light": "light" in low,
        "gyroscope": "gyroscope" in low,
    }


def parse_camera(dumpsys_camera: str, features: str) -> dict:
    m = re.search(r"Number of camera devices:\s*(\d+)", dumpsys_camera or "")
    return {
        "count": int(m.group(1)) if m else None,
        "claimed": "android.hardware.camera" in (features or ""),
    }


def parse_software(logcat_crash: str) -> dict:
    return {
        "crashes": len(re.findall(r"FATAL EXCEPTION", logcat_crash or "")),
        "anrs": len(re.findall(r"ANR in ", logcat_crash or "")),
        "core_crashes": len(re.findall(
            r"Process:\s*(?:com\.android\.systemui|com\.android\.phone|system_server)", logcat_crash or "")),
    }


# ---------------------------------------------------------------------------
# Penyimpul
# ---------------------------------------------------------------------------

def _f(findings: list[Finding], code, component, severity, title, detail, weight=None):
    findings.append(Finding(code, component, severity, title, detail, weight))


def analyze(facts: dict) -> DeepScanReport:
    """Gabungkan fakta jadi temuan dan dugaan komponen rusak."""
    findings: list[Finding] = []
    unreadable = list(facts.get("unreadable", []))
    notes: list[str] = []

    b = facts.get("battery") or {}
    usb_connected = facts.get("usb_connected")

    # --- baterai ---
    if b.get("present") is False:
        _f(findings, "BAT_ABSENT", BATTERY, "fail", "Baterai tidak terdeteksi", "Sistem melaporkan baterai tidak ada.", 4.0)
    hc = b.get("health_code")
    health_names = {3: "Overheat", 4: "Dead", 5: "Over voltage", 6: "Unspecified failure", 7: "Cold"}
    if hc in health_names:
        _f(findings, "BAT_HEALTH", BATTERY, "fail", f"Kesehatan baterai: {health_names[hc]}",
           "Android sendiri menandai baterai bermasalah.", 4.0 if hc in (4, 6) else 3.0)
    full, design = b.get("charge_full"), b.get("charge_full_design")
    if full and design and design > 0 and 0.3 <= full / design <= 1.3:
        wear = max(0.0, (1 - full / design) * 100)
        if wear >= 40:
            _f(findings, "BAT_WEAR", BATTERY, "fail", f"Baterai aus {wear:.0f}%", "Kapasitas penuh jauh di bawah kapasitas desain.", 3.5)
        elif wear >= 25:
            _f(findings, "BAT_WEAR", BATTERY, "warn", f"Baterai mulai aus {wear:.0f}%", "Kapasitas penuh turun dari kapasitas desain.")
    cyc = b.get("cycle_count")
    if cyc is not None and cyc > 0:
        if cyc >= 1000:
            _f(findings, "BAT_CYCLE", BATTERY, "fail", f"{cyc} siklus charge", "Siklus sangat tinggi; baterai lazimnya sudah aus.", 3.0)
        elif cyc >= 700:
            _f(findings, "BAT_CYCLE", BATTERY, "warn", f"{cyc} siklus charge", "Siklus tinggi; pantau kapasitas baterai.")
    t = b.get("temp_c")
    if t is not None:
        if t >= 50:
            _f(findings, "BAT_TEMP", BATTERY, "fail", f"Suhu baterai {t:.1f} °C", "Terlalu panas; cek korsleng atau baterai rusak.", 3.0)
            _f(findings, "BAT_TEMP_T", THERMAL, "warn", f"Suhu baterai {t:.1f} °C", "Panas berlebih.")
        elif t >= 42:
            _f(findings, "BAT_TEMP", THERMAL, "warn", f"Suhu baterai {t:.1f} °C", "Lebih hangat dari wajar.")
    v, lvl = b.get("voltage_mv"), b.get("level")
    if v and lvl is not None and v < 3300 and lvl > 20:
        _f(findings, "BAT_SAG", BATTERY, "warn", f"Tegangan {v} mV tidak cocok dengan level {lvl}%",
           "Level tinggi tapi tegangan rendah menandakan sel baterai lemah.")

    # --- pengisian ---
    powered = any(b.get(k) for k in ("ac", "usb", "wireless"))
    known_power = any(b.get(k) is not None for k in ("ac", "usb", "wireless"))
    if usb_connected and known_power and not powered:
        _f(findings, "CHG_NONE", CHARGE, "fail", "Tersambung USB tapi tidak ada daya masuk",
           "Data lewat tapi HP tidak mengisi. Coba kabel/port lain untuk memastikan.", 3.0)
    if b.get("status_code") == 4 and powered:
        _f(findings, "CHG_BLOCKED", CHARGE, "warn", "Status 'Not charging' padahal terhubung daya",
           "Pengisian diblokir; bisa karena suhu, baterai, atau IC pengisian.")

    # --- penyimpanan ---
    s = facts.get("storage") or {}
    life = s.get("life")
    if life is not None:
        if life >= 10:
            _f(findings, "STO_LIFE", STORAGE, "fail", f"Umur flash hampir habis (tingkat {life}/11)",
               "Estimasi umur eMMC/UFS 90% terpakai atau lebih.", 4.0)
        elif life >= 8:
            _f(findings, "STO_LIFE", STORAGE, "warn", f"Umur flash menurun (tingkat {life}/11)", "Estimasi 70-80% terpakai.")
    lat = s.get("write_latency_ms")
    if lat is not None:
        if lat >= 500:
            _f(findings, "STO_SLOW", STORAGE, "fail", f"Tulis ke storage sangat lambat ({lat} ms)", "Latensi tulis 512B sangat tinggi.", 3.0)
        elif lat >= 100:
            _f(findings, "STO_SLOW", STORAGE, "warn", f"Tulis ke storage lambat ({lat} ms)", "Latensi tulis 512B di atas normal.")
    fp = s.get("free_percent")
    if fp is not None and fp <= 3:
        _f(findings, "STO_FULL", SOFTWARE, "warn", f"Penyimpanan hampir penuh ({fp}% bebas)",
           "Penyimpanan penuh membuat HP lambat dan error; belum tentu rusak.")

    # --- restart sendiri / catu daya ---
    bt = facts.get("boot") or {}
    dbx = bt.get("dropbox") or {}
    if bt.get("kernel", 0) >= 1 or dbx.get("system_last_kmsg", 0) >= 1:
        n = max(bt.get("kernel", 0), dbx.get("system_last_kmsg", 0))
        _f(findings, "BOOT_PANIC", BOARD, "fail", f"Jejak kernel panic/watchdog ({n}x)",
           "HP pernah restart karena kernel crash atau watchdog.", 3.5 if n >= 2 else 3.0)
    if bt.get("power", 0) >= 1:
        sev = "fail" if bt["power"] >= 3 else "warn"
        _f(findings, "BOOT_POWER", BOARD, sev, f"Restart karena daya ({bt['power']}x)",
           "Alasan boot menunjukkan tegangan jatuh atau daya terputus mendadak.")
        _f(findings, "BOOT_POWER_B", BATTERY, "warn", "Restart karena daya", "Baterai lemah ikut dicurigai.")
    if bt.get("abnormal", 0) >= 4:
        _f(findings, "BOOT_MANY", BOARD, "fail", f"{bt['abnormal']} restart tidak normal", "Restart sendiri berulang.", 3.0)
    elif bt.get("abnormal", 0) >= 2:
        _f(findings, "BOOT_MANY", BOARD, "warn", f"{bt['abnormal']} restart tidak normal", "Restart sendiri lebih dari sekali.")
    if dbx.get("system_server_watchdog", 0) >= 1:
        _f(findings, "SYS_WDT", SOFTWARE, "warn", f"Watchdog system_server ({dbx['system_server_watchdog']}x)",
           "Sistem Android pernah macet dan dimatikan watchdog.")
    if dbx.get("system_fsck", 0) >= 1:
        _f(findings, "FS_FSCK", STORAGE, "warn", "Pemeriksaan sistem file (fsck) pernah jalan",
           "Biasanya karena mati mendadak atau sektor storage bermasalah.")
    if dbx.get("system_tombstone", 0) >= 8:
        _f(findings, "TOMBSTONES", SOFTWARE, "warn", f"{dbx['system_tombstone']} crash native", "Banyak crash tingkat sistem.")

    # --- panas ---
    th = facts.get("thermal") or {}
    mx = th.get("max_c")
    if mx is not None:
        if mx >= 85:
            _f(findings, "THERMAL_MAX", THERMAL, "fail", f"Suhu internal {mx:.0f} °C", "Terlalu panas saat diperiksa.", 3.0)
            _f(findings, "THERMAL_BOARD", BOARD, "warn", f"Suhu internal {mx:.0f} °C", "Panas ekstrem sering berasal dari korsleng di board.")
        elif mx >= 70:
            _f(findings, "THERMAL_MAX", THERMAL, "warn", f"Suhu internal {mx:.0f} °C", "Lebih panas dari wajar untuk kondisi diam.")
    if th.get("status") is not None and th["status"] >= 3:
        _f(findings, "THERMAL_STATUS", THERMAL, "warn", f"Status thermal {th['status']}", "Sistem sedang membatasi performa karena panas.")

    # --- touch ---
    inp = facts.get("input") or {}
    if inp.get("touch_found") is False:
        _f(findings, "TOUCH_NONE", TOUCH, "fail", "Panel sentuh tidak terdeteksi",
           "Tidak ada perangkat input sentuh di sistem.", 3.5)
    tc = facts.get("touch_test")
    if tc:
        cov = tc.get("coverage", 0)
        unc = tc.get("uncovered") or []
        if cov < 0.7:
            notes.append(f"Uji sentuh: sapuan baru menutup {cov*100:.0f}% layar. Ulangi dengan menyapu seluruh layar.")
        elif unc:
            cells = ", ".join(f"({c+1},{r+1})" for c, r in unc[:8])
            sev = "fail" if len(unc) >= 4 else "warn"
            _f(findings, "TOUCH_DEAD", TOUCH, sev, f"{len(unc)} area layar tidak merespons",
               f"Sel kolom,baris: {cells}. Pastikan layar bersih dan tidak ada pelindung rusak.", 3.5 if sev == "fail" else None)

    # --- modem ---
    m = facts.get("modem") or {}
    sim = (m.get("sim_state") or "").upper()
    sim_present = sim and sim not in ("ABSENT", "UNKNOWN", "NOT_READY")
    base = (m.get("baseband") or "").lower()
    if sim_present and (not base or base == "unknown"):
        _f(findings, "MODEM_BASEBAND", MODEM, "fail", "Baseband tidak terbaca padahal ada SIM",
           "Modem tidak melapor; cek IC modem atau baseband/IMEI.", 3.5)
    if m.get("radio_unavailable", 0) >= 3:
        _f(findings, "MODEM_RADIO", MODEM, "warn", f"Radio tidak tersedia ({m['radio_unavailable']}x di log)",
           "Lapisan radio sering gagal.")
    if sim == "NOT_READY":
        _f(findings, "MODEM_SIM", MODEM, "warn", "SIM belum siap", "Bisa SIM tray/SIM rusak atau modem bermasalah.")

    # --- sensor ---
    se = facts.get("sensors") or {}
    if se.get("read"):
        if not se.get("accelerometer"):
            _f(findings, "SENSOR_ACC", SENSOR, "warn", "Accelerometer tidak terdaftar", "Hampir semua HP punya accelerometer.")
        if not se.get("proximity"):
            _f(findings, "SENSOR_PROX", SENSOR, "info", "Sensor proximity tidak terdaftar",
               "Bisa memang tidak ada di HP entry-level; layar bisa tetap menyala saat telepon.")

    # --- kamera ---
    c = facts.get("camera") or {}
    if c.get("claimed") and c.get("count") == 0:
        _f(findings, "CAM_NONE", CAMERA, "fail", "Tidak ada kamera terdeteksi", "HP mengaku punya kamera tapi sistem tidak menemukan satu pun.", 3.0)

    # --- software ---
    sw = facts.get("software") or {}
    if sw.get("core_crashes", 0) >= 3:
        _f(findings, "SW_CORE", SOFTWARE, "warn", f"Komponen inti crash {sw['core_crashes']}x", "SystemUI/telepon/system_server berulang crash.")
    if sw.get("crashes", 0) + sw.get("anrs", 0) >= 15:
        _f(findings, "SW_MANY", SOFTWARE, "warn", f"{sw.get('crashes', 0)} crash, {sw.get('anrs', 0)} ANR", "Banyak crash aplikasi/sistem di log.")

    # --- ringkasan ---
    scores: dict[str, float] = {}
    reasons: dict[str, list[str]] = {}
    for f in findings:
        w = f.effective_weight
        if w <= 0:
            continue
        scores[f.component] = scores.get(f.component, 0.0) + w
        reasons.setdefault(f.component, []).append(f.title)

    suspects = []
    for comp, sc in sorted(scores.items(), key=lambda kv: -kv[1]):
        conf = 1 - math.exp(-sc / 3.0)
        level = "Tinggi" if conf >= 0.7 else "Sedang" if conf >= 0.4 else "Rendah"
        suspects.append(Suspect(comp, round(conf, 2), level, tuple(reasons[comp]), ACTIONS[comp]))

    penalty = sum(f.effective_weight for f in findings)
    # Pembulatan setengah-naik (sama dengan Math.round di JS); round() Python membulatkan ke genap.
    score = max(0, min(100, math.floor(100 - penalty * 5 + 0.5)))
    if not findings:
        verdict = "Tidak ada tanda kerusakan yang terbaca"
    elif suspects and suspects[0].level == "Tinggi":
        verdict = f"Kemungkinan besar bermasalah di: {suspects[0].component}"
    elif suspects:
        verdict = f"Ada tanda masalah, dugaan utama: {suspects[0].component}"
    else:
        verdict = "Hanya catatan informasi"

    total_probes = max(1, int(facts.get("probe_count", 0)))
    if unreadable and len(unreadable) / total_probes >= 0.6:
        notes.append("Banyak data tidak terbaca (batas izin atau versi Android), jadi kesimpulan kurang lengkap.")
    notes.append("Hasil berupa petunjuk. Kerusakan fisik, cairan, dan board yang tidak menimbulkan gejala di software tidak terbaca lewat ADB.")

    return DeepScanReport(score=score, verdict=verdict, suspects=suspects,
                          findings=findings, unreadable=unreadable, notes=notes)


# ---------------------------------------------------------------------------
# Probe ke HP
# ---------------------------------------------------------------------------

Runner = Callable[[str, str], str]


def _default_runner(serial: str, command: str) -> str:
    return run_adb("-s", serial, "shell", command, timeout=25)


_SYSFS_BATTERY = (
    "for f in cycle_count charge_full charge_full_design; do "
    "echo \"$f=$(cat /sys/class/power_supply/battery/$f 2>/dev/null)\"; done"
)
_LIFE_CMD = (
    "cat $(find /sys/devices /sys/block -maxdepth 7 \\( -name life_time "
    "-o -name life_time_estimation_a -o -name life_time_estimation_b \\) "
    "2>/dev/null | head -4) 2>/dev/null; true"
)
_ZONES_CMD = (
    "for z in /sys/class/thermal/thermal_zone*; do "
    "echo \"$(cat $z/type 2>/dev/null)=$(cat $z/temp 2>/dev/null)\"; done"
)
_PROP_NAMES = ("gsm.sim.state", "gsm.version.baseband")


def collect_facts(
    serial: str,
    *,
    runner: Runner = _default_runner,
    usb_connected: bool | None = None,
) -> dict:
    """Jalankan semua probe baca-saja. Probe yang gagal masuk `unreadable`."""
    unreadable: list[str] = []
    probes = 0

    def probe(name: str, command: str, required_text: bool = False) -> str:
        nonlocal probes
        probes += 1
        try:
            out = runner(serial, command)
        except (ADBError, OSError) as exc:  # noqa: BLE001
            unreadable.append(f"{name} ({exc})")
            return ""
        out = out or ""
        if required_text and not out.strip():
            unreadable.append(name)
        return out

    bat_raw = probe("Baterai", "dumpsys battery", True)
    bat_sys = probe("Baterai (sysfs)", _SYSFS_BATTERY)
    life = probe("Umur storage", _LIFE_CMD)
    disk = probe("Latensi storage", "dumpsys diskstats", True)
    df = probe("Kapasitas storage", "df -k /data")
    hist = probe("Riwayat boot", "getprop persist.sys.boot.reason.history")
    cur = probe("Alasan boot", "getprop sys.boot.reason")
    dropbox = probe("Dropbox sistem", "dumpsys dropbox")
    zones = probe("Suhu zona", _ZONES_CMD)
    thermal = probe("Thermal service", "dumpsys thermalservice")
    ev_lp = probe("Perangkat input", "getevent -lp", True)
    props = {p: probe(f"Prop {p}", f"getprop {p}").strip() for p in _PROP_NAMES}
    radio = probe("Log radio", "logcat -d -b radio -t 500")
    sensors = probe("Sensor", "dumpsys sensorservice", True)
    cam = probe("Kamera", "dumpsys media.camera")
    feats = probe("Fitur", "pm list features")
    crash = probe("Log crash", "logcat -d -b crash -t 500")

    devices = parse_input_devices(ev_lp)
    touch = pick_touchscreen(devices)

    facts = {
        "battery": parse_battery(bat_raw, bat_sys),
        "usb_connected": usb_connected,
        "storage": parse_storage(life, disk, df),
        "boot": parse_boot(hist, cur, dropbox),
        "thermal": parse_thermal(zones, thermal),
        "input": {"touch_found": (touch is not None) if ev_lp.strip() else None, "device": touch},
        "modem": parse_modem(props, radio),
        "sensors": parse_sensors(sensors),
        "camera": parse_camera(cam, feats),
        "software": parse_software(crash),
        "unreadable": unreadable,
        "probe_count": probes,
    }
    return facts


def run_touch_test(serial: str, device: dict, seconds: int = 12, *, runner=None) -> dict:
    """Rekam sentuhan selama `seconds` detik, lalu hitung sel yang tersentuh.

    HP harus disentuh/disapu seluruh layarnya selama uji berjalan.
    """
    seconds = max(5, min(30, int(seconds)))
    path = device["path"]
    if not re.fullmatch(r"/dev/input/event\d+", path):
        raise ADBError("Path perangkat input tidak valid.")
    # `timeout` keluar dengan kode 124 saat waktunya habis; "; true" mencegah itu dianggap gagal.
    cmd = f"timeout {seconds} getevent -l {path}; true"
    if runner is not None:
        out = runner(serial, cmd)
    else:
        out = run_adb("-s", serial, "shell", cmd, timeout=seconds + 10)
    return touch_coverage(out, device["x_max"], device["y_max"])


# ---------------------------------------------------------------------------
# Tampilan (HTML untuk panel hasil)
# ---------------------------------------------------------------------------

def is_usb_serial(serial: str) -> bool:
    """True kalau serial ADB berasal dari kabel USB (bukan IP:port atau mDNS Wi-Fi)."""
    s = (serial or "").strip()
    return bool(s) and ":" not in s and "_adb-tls" not in s and not s.startswith("adb-")


def render_html(report: DeepScanReport, touch_test: dict | None = None) -> str:
    from html import escape as e

    colors = {"Tinggi": "#ff6b6b", "Sedang": "#ffb454", "Rendah": "#9aa59a"}
    sev_color = {"fail": "#ff6b6b", "warn": "#ffb454", "info": "#7aa2f7"}
    sev_label = {"fail": "RUSAK?", "warn": "CEK", "info": "INFO"}
    out = [
        "<div style='font-family:sans-serif;color:#d7ded7'>",
        f"<h2 style='margin:0'>Skor {report.score}/100</h2>",
        f"<p style='font-size:15px;margin:4px 0 14px'>{e(report.verdict)}</p>",
    ]
    if report.suspects:
        out.append("<h3>Dugaan komponen</h3>")
        for s in report.suspects:
            pct = round(s.confidence * 100)
            out.append(
                f"<div style='margin:0 0 12px'><b>{e(s.component)}</b> "
                f"<span style='color:{colors[s.level]}'>keyakinan {s.level} ({pct}%)</span>"
                f"<div style='background:#1e241e;height:6px;border-radius:3px;margin:4px 0'>"
                f"<div style='background:{colors[s.level]};width:{pct}%;height:6px;border-radius:3px'></div></div>"
                f"<div style='color:#9aa59a'>Bukti: {e('; '.join(s.reasons))}</div>"
                f"<div>Saran: {e(s.action)}</div></div>"
            )
    if report.findings:
        out.append("<h3>Semua temuan</h3><table cellpadding='4' style='border-collapse:collapse'>")
        for f in report.findings:
            out.append(
                f"<tr><td style='color:{sev_color[f.severity]}'><b>{sev_label[f.severity]}</b></td>"
                f"<td>{e(f.component)}</td><td><b>{e(f.title)}</b><br><span style='color:#9aa59a'>{e(f.detail)}</span></td></tr>"
            )
        out.append("</table>")
    if touch_test:
        cols, rows = touch_test["cols"], touch_test["rows"]
        dead = {tuple(c) for c in touch_test["uncovered"]}
        out.append(f"<h3>Peta uji sentuh ({touch_test['coverage']*100:.0f}% tersentuh)</h3>"
                   "<table cellspacing='2'>")
        for r in range(rows):
            out.append("<tr>" + "".join(
                f"<td width='22' height='14' style='background:{'#ff6b6b' if (c, r) in dead else '#3ddc84'}'></td>"
                for c in range(cols)) + "</tr>")
        out.append("</table><div style='color:#9aa59a'>Hijau = merespons, merah = tidak tersentuh.</div>")
    if report.unreadable:
        out.append("<h3>Tidak terbaca</h3><ul>" + "".join(f"<li>{e(u)}</li>" for u in report.unreadable) + "</ul>")
    for n in report.notes:
        out.append(f"<p style='color:#9aa59a'>{e(n)}</p>")
    out.append("</div>")
    return "".join(out)
