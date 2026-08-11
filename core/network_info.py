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


def _get_imei(serial: str) -> str:
    # IMEI biasanya butuh permission khusus, coba beberapa metode fallback.
    try:
        output = run_adb(
            "-s", serial, "shell", "service", "call", "iphonesubinfo", "1"
        ).strip()

        if output and "Parcel" in output:
            chars = []
            for line in output.splitlines()[1:]:
                parts = line.split("'")
                if len(parts) >= 2:
                    segment = parts[1].replace(".", "")
                    chars.append(segment)
            imei = "".join(chars).strip()

            if imei and any(c.isdigit() for c in imei):
                return imei
    except ADBError:
        pass

    try:
        output = run_adb("-s", serial, "shell", "dumpsys", "iphonesubinfo").strip()

        if output:
            return output[:100]
    except ADBError:
        pass

    return "Tidak dapat dibaca (perlu permission khusus)"


def get_network_info(serial: str) -> NetworkInfo:
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
