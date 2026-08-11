from dataclasses import dataclass

from .adb import run_adb, ADBError


@dataclass
class NetworkInfo:
    imei: str
    wifi_state: str
    mobile_data_state: str
    ip_address: str
    network_operator: str
    sim_state: str
    phone_type: str


def _prop(serial: str, name: str) -> str:
    try:
        return run_adb("-s", serial, "shell", "getprop", name).strip() or "Unknown"
    except ADBError:
        return "Unknown"


def _parse_service_call_parcel(output: str) -> str:
    """Ekstrak digit dari output 'service call iphonesubinfo' (format Parcel)."""
    if not output or "Parcel" not in output:
        return ""

    chars = []
    for line in output.splitlines()[1:]:
        parts = line.split("'")
        if len(parts) >= 2:
            segment = parts[1].replace(".", "")
            chars.append(segment)
    return "".join(chars).strip()


def _get_imei(serial: str) -> str:
    """Coba baca IMEI lewat ADB shell (best-effort, tanpa root).

    CATATAN PENTING: sejak Android 10 (API 29), membaca IMEI/device
    identifier butuh permission READ_PRIVILEGED_PHONE_STATE, yang hanya
    bisa dipegang aplikasi sistem. Shell ADB biasa (non-root) TIDAK bisa
    diberi permission ini. Jadi di kebanyakan device Android 10+ stok,
    fungsi ini akan selalu gagal dan itu BUKAN bug - itu pembatasan OS.
    Fallback di bawah tetap dicoba untuk device lama/ROM custom yang
    tidak menegakkan pembatasan ini secara ketat, tanpa membuat proses
    scan network info gagal total.
    """
    # Transaction code 1 = getDeviceId() pada AIDL lama (pre Android 8).
    # Beberapa ROM/versi memakai code lain (mis. 3) untuk slot SIM kedua
    # atau interface yang berbeda; kita coba beberapa kandidat.
    for transaction_code in ("1", "3"):
        try:
            output = run_adb(
                "-s", serial, "shell", "service", "call",
                "iphonesubinfo", transaction_code,
            ).strip()
            imei = _parse_service_call_parcel(output)
            if imei and any(c.isdigit() for c in imei):
                return imei
        except ADBError:
            continue
        except Exception:
            # Jangan biarkan parsing output yang tidak terduga menjaTUHkan
            # seluruh network info scan - lanjut ke fallback berikutnya.
            continue

    # Fallback: sebagian chipset (mis. beberapa build MediaTek/Spreadtrum
    # debug) mengekspos IMEI lewat getprop non-standar. Aman dicoba karena
    # hanya baca properti, tidak butuh permission tambahan.
    for prop_name in ("persist.radio.imei", "ril.imei", "gsm.imei"):
        value = _prop(serial, prop_name)
        if value and value != "Unknown" and any(c.isdigit() for c in value):
            return value

    try:
        output = run_adb("-s", serial, "shell", "dumpsys", "iphonesubinfo").strip()
        if output:
            return output[:100]
    except ADBError:
        pass
    except Exception:
        pass

    return "Tidak dapat dibaca (perlu permission khusus / root - dibatasi OS sejak Android 10)"


def get_network_info(serial: str) -> NetworkInfo:
    wifi_raw = _prop(serial, "wifi.interface")

    try:
        wifi_status = run_adb("-s", serial, "shell", "dumpsys", "wifi").strip()
        wifi_state = "Enabled" if "Wi-Fi is enabled" in wifi_status else "Disabled/Unknown"
    except ADBError:
        wifi_state = "Unknown"

    try:
        data_status = run_adb(
            "-s", serial, "shell", "settings", "get", "global", "mobile_data"
        ).strip()
        mobile_data_state = "Enabled" if data_status == "1" else "Disabled"
    except ADBError:
        mobile_data_state = "Unknown"

    try:
        ip_output = run_adb("-s", serial, "shell", "ip", "route").strip()
        ip_address = "Unknown"

        for line in ip_output.splitlines():
            if "src" in line:
                parts = line.split()
                if "src" in parts:
                    idx = parts.index("src")
                    if idx + 1 < len(parts):
                        ip_address = parts[idx + 1]
                        break
    except ADBError:
        ip_address = "Unknown"

    network_operator = _prop(serial, "gsm.operator.alpha")
    sim_state = _prop(serial, "gsm.sim.state")
    phone_type = _prop(serial, "gsm.current.phone-type")

    return NetworkInfo(
        imei=_get_imei(serial),
        wifi_state=wifi_state,
        mobile_data_state=mobile_data_state,
        ip_address=ip_address,
        network_operator=network_operator or "Unknown",
        sim_state=sim_state or "Unknown",
        phone_type=phone_type or "Unknown",
    )
