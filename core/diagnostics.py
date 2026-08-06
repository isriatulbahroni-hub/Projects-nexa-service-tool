from dataclasses import dataclass

from .adb import run_adb


@dataclass
class DiagnosticResult:
    battery_level: str
    battery_status: str
    battery_health: str
    storage: str
    screen_state: str
    usb_debugging: str


def compute_health_score(diag: "DiagnosticResult") -> tuple[int, list[str]]:
    """
    Hitung skor kesehatan device (0-100) berdasarkan hasil diagnostics,
    plus rekomendasi tindakan yang relevan untuk teknisi.
    """
    score = 100
    recommendations: list[str] = []

    # --- Battery health ---
    if diag.battery_health == "Overheat":
        score -= 30
        recommendations.append(
            "Baterai overheat - cek sirkulasi udara & kondisi fisik baterai."
        )
    elif diag.battery_health == "Dead":
        score -= 50
        recommendations.append("Baterai mati - sarankan penggantian baterai.")
    elif diag.battery_health == "Over voltage":
        score -= 30
        recommendations.append(
            "Tegangan baterai tidak normal - cek IC charging & baterai."
        )
    elif diag.battery_health == "Unspecified failure":
        score -= 25
        recommendations.append(
            "Battery health tidak terbaca normal - cek ulang dengan tools lain."
        )
    elif diag.battery_health == "Cold":
        score -= 10
        recommendations.append("Suhu baterai rendah - pastikan device di suhu normal.")
    elif diag.battery_health == "Unknown":
        score -= 5

    # --- Battery level ---
    try:
        level_num = int(diag.battery_level.replace("%", "").strip())

        if level_num <= 15 and diag.battery_status not in ("Charging", "Full"):
            score -= 10
            recommendations.append(
                "Baterai rendah dan tidak sedang mengisi - sambungkan charger."
            )
    except ValueError:
        pass

    # --- Storage ---
    if "Total:" in diag.storage and "Used:" in diag.storage and "Free:" in diag.storage:
        try:
            free_part = diag.storage.split("Free:")[1].strip()
            free_val = free_part.rstrip("GgMm")
            unit = free_part[-1].upper()
            free_num = float(free_val)

            if unit == "M" or free_num < 1:
                score -= 20
                recommendations.append(
                    "Storage hampir penuh - sarankan hapus cache/data tidak perlu."
                )
            elif unit == "G" and free_num < 2:
                score -= 10
                recommendations.append(
                    "Storage tersisa sedikit (<2GB) - pantau penggunaan storage."
                )
        except (ValueError, IndexError):
            pass
    else:
        score -= 5
        recommendations.append("Informasi storage tidak terbaca dengan jelas.")

    # --- Screen state ---
    if diag.screen_state == "Unknown":
        score -= 5
        recommendations.append(
            "Status layar tidak terbaca - cek koneksi ADB atau driver display."
        )

    # --- USB debugging ---
    if diag.usb_debugging == "Disabled":
        recommendations.append(
            "USB debugging nonaktif - beberapa fitur service tool mungkin terbatas."
        )
    elif diag.usb_debugging == "Unknown":
        recommendations.append("Status USB debugging tidak dapat dipastikan.")

    score = max(0, min(100, score))

    if not recommendations:
        recommendations.append("Semua indikator normal - device dalam kondisi baik.")

    return score, recommendations


def health_score_label(score: int) -> str:
    if score >= 85:
        return "Excellent"
    elif score >= 70:
        return "Good"
    elif score >= 50:
        return "Fair"
    elif score >= 30:
        return "Poor"
    else:
        return "Critical"


def get_diagnostics(serial: str) -> DiagnosticResult:
    battery = run_adb(
        "-s", serial,
        "shell", "dumpsys", "battery"
    )

    level = "Unknown"
    status = "Unknown"
    health = "Unknown"

    for line in battery.splitlines():
        line = line.strip()

        if line.startswith("level:"):
            level = line.split(":", 1)[1].strip() + "%"

        elif line.startswith("status:"):
            status_code = line.split(":", 1)[1].strip()

            status_map = {
                "1": "Unknown",
                "2": "Charging",
                "3": "Discharging",
                "4": "Not charging",
                "5": "Full",
            }

            status = status_map.get(status_code, status_code)

        elif line.startswith("health:"):
            health_code = line.split(":", 1)[1].strip()

            health_map = {
                "1": "Unknown",
                "2": "Good",
                "3": "Overheat",
                "4": "Dead",
                "5": "Over voltage",
                "6": "Unspecified failure",
                "7": "Cold",
            }

            health = health_map.get(health_code, health_code)

    storage = run_adb(
        "-s", serial,
        "shell", "df", "-h", "/data"
    )

    storage_info = "Unknown"

    lines = storage.splitlines()

    if len(lines) >= 2:
        parts = lines[-1].split()

        if len(parts) >= 5:
            storage_info = (
                f"Total: {parts[1]} | "
                f"Used: {parts[2]} | "
                f"Free: {parts[3]}"
            )

    screen = run_adb(
        "-s", serial,
        "shell", "dumpsys", "power"
    )

    screen_state = "Unknown"

    for line in screen.splitlines():
        line = line.strip()

        if "Display Power" in line:
            if "state=ON" in line:
                screen_state = "ON"
            elif "state=OFF" in line:
                screen_state = "OFF"

    usb_debugging = "Unknown"

    try:
        adb_enabled = run_adb(
            "-s", serial,
            "shell", "settings", "get", "global", "adb_enabled"
        ).strip()

        if adb_enabled == "1":
            usb_debugging = "Enabled"
        elif adb_enabled == "0":
            usb_debugging = "Disabled"
    except Exception:
        pass

    return DiagnosticResult(
        battery_level=level,
        battery_status=status,
        battery_health=health,
        storage=storage_info,
        screen_state=screen_state,
        usb_debugging=usb_debugging,
    )
