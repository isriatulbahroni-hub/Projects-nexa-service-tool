"""Safe, read-only hardware diagnostics for connected Android devices.

The module intentionally avoids destructive operations. It gathers information
that a service technician can use for an initial hardware health report.
"""

from dataclasses import dataclass
import re

from .adb import ADBError, run_adb


@dataclass(frozen=True)
class HardwareTestResult:
    key: str
    name: str
    status: str  # PASS, WARN, FAIL, INFO
    value: str
    detail: str = ""


@dataclass(frozen=True)
class HardwareTestReport:
    serial: str
    results: list[HardwareTestResult]

    @property
    def passed(self) -> int:
        return sum(item.status == "PASS" for item in self.results)

    @property
    def warnings(self) -> int:
        return sum(item.status == "WARN" for item in self.results)

    @property
    def failed(self) -> int:
        return sum(item.status == "FAIL" for item in self.results)

    @property
    def score(self) -> int:
        """Conservative score for the read-only checks we can verify remotely."""
        if not self.results:
            return 0
        # Gunakan bobot dalam skala integer (x10) supaya tidak kena galat
        # pembulatan floating-point (mis. 57.5 yang malah jadi 57.49999...).
        weights = {"PASS": 10, "INFO": 8, "WARN": 5, "FAIL": 0}
        total = sum(weights.get(item.status, 0) for item in self.results)
        # total * 10 (skala persen) dibagi (len * 10), lalu round-half-up manual.
        numerator = total * 100
        denominator = len(self.results) * 10
        return (numerator + denominator // 2) // denominator


def _shell(serial: str, *args: str, timeout: int = 10) -> str:
    return run_adb("-s", serial, "shell", *args, timeout=timeout).strip()


def _prop(serial: str, name: str) -> str:
    try:
        return _shell(serial, "getprop", name) or "Unknown"
    except ADBError:
        return "Unknown"


def _result(key: str, name: str, status: str, value: str, detail: str = "") -> HardwareTestResult:
    return HardwareTestResult(key, name, status, value, detail)


def check_battery(serial: str) -> HardwareTestResult:
    try:
        raw = _shell(serial, "dumpsys", "battery")
    except ADBError as exc:
        return _result("battery", "Battery", "FAIL", "Unavailable", str(exc))

    level = re.search(r"level:\s*(\d+)", raw)
    temp = re.search(r"temperature:\s*(-?\d+)", raw)
    status = re.search(r"status:\s*(\d+)", raw)

    level_text = f"{level.group(1)}%" if level else "Unknown"
    temp_text = f"{int(temp.group(1)) / 10:.1f}°C" if temp else "Unknown"
    status_text = status.group(1) if status else "Unknown"

    if level and int(level.group(1)) < 10:
        state = "WARN"
        detail = "Battery level is low. Charge before extended diagnostics."
    else:
        state = "PASS"
        detail = f"Temperature {temp_text}; charging status code {status_text}."

    return _result("battery", "Battery", state, level_text, detail)


def check_storage(serial: str) -> HardwareTestResult:
    try:
        raw = _shell(serial, "df", "/data")
    except ADBError as exc:
        return _result("storage", "Internal Storage", "FAIL", "Unavailable", str(exc))

    lines = [line for line in raw.splitlines() if line.strip()]
    if len(lines) < 2:
        return _result("storage", "Internal Storage", "WARN", "Unknown", "Could not parse df output.")

    parts = lines[-1].split()
    if len(parts) < 5:
        return _result("storage", "Internal Storage", "WARN", "Unknown", "Unexpected df output.")

    # Android builds commonly report: filesystem blocks used available use% mounted
    usage = next((p for p in parts if p.endswith("%") and p[:-1].isdigit()), None)
    if usage is None:
        return _result("storage", "Internal Storage", "INFO", "Detected", "Storage detected but usage was not parsed.")

    percent = int(usage[:-1])
    state = "WARN" if percent >= 90 else "PASS"
    detail = "Storage is critically full." if percent >= 90 else f"/data usage {percent}%."
    return _result("storage", "Internal Storage", state, usage, detail)


def check_display(serial: str) -> HardwareTestResult:
    try:
        size = _shell(serial, "wm", "size")
        density = _shell(serial, "wm", "density")
    except ADBError as exc:
        return _result("display", "Display", "FAIL", "Unavailable", str(exc))

    value = size.splitlines()[-1].strip() if size else "Unknown"
    detail = f"Density: {density.splitlines()[-1].strip() if density else 'Unknown'}"
    return _result("display", "Display", "INFO", value, detail)


def check_audio(serial: str) -> HardwareTestResult:
    try:
        output = _shell(serial, "dumpsys", "audio")
    except ADBError as exc:
        return _result("audio", "Audio", "FAIL", "Unavailable", str(exc))

    if not output:
        return _result("audio", "Audio", "WARN", "No data", "Audio service returned no diagnostic data.")
    return _result("audio", "Audio", "INFO", "Detected", "Remote check confirms Android audio service is available; speaker/mic still require physical testing.")


def check_camera(serial: str) -> HardwareTestResult:
    try:
        output = _shell(serial, "dumpsys", "media.camera")
    except ADBError:
        try:
            output = _shell(serial, "pm", "list", "features")
        except ADBError as exc:
            return _result("camera", "Camera", "FAIL", "Unavailable", str(exc))

    detected = "camera" in output.lower()
    if detected:
        return _result("camera", "Camera", "INFO", "Detected", "Camera presence detected; image capture still requires a live test.")
    return _result("camera", "Camera", "WARN", "Not detected", "Could not confirm a camera service from ADB.")


def check_sensors(serial: str) -> HardwareTestResult:
    try:
        output = _shell(serial, "dumpsys", "sensorservice")
    except ADBError as exc:
        return _result("sensors", "Sensors", "FAIL", "Unavailable", str(exc))

    count = len(re.findall(r"(?im)^\s*(?:handle|0x)[^\n]*", output))
    if count > 0:
        return _result("sensors", "Sensors", "INFO", f"{count}+ entries", "Presence detected; motion/proximity/fingerprint functionality still needs physical interaction tests.")
    return _result("sensors", "Sensors", "WARN", "Unknown", "Sensor service is available but entries could not be parsed reliably.")


def check_usb(serial: str) -> HardwareTestResult:
    try:
        state = _prop(serial, "sys.usb.state")
        config = _prop(serial, "persist.sys.usb.config")
    except Exception as exc:
        return _result("usb", "USB", "FAIL", "Unavailable", str(exc))

    if state == "Unknown" and config == "Unknown":
        return _result("usb", "USB", "WARN", "Unknown")
    return _result("usb", "USB", "PASS", state, f"Configured: {config}")


def check_network(serial: str) -> HardwareTestResult:
    try:
        output = _shell(serial, "ip", "addr", "show")
    except ADBError as exc:
        return _result("network", "Network", "FAIL", "Unavailable", str(exc))

    addresses = re.findall(r"inet\s+(\d+\.\d+\.\d+\.\d+)", output)
    private = [addr for addr in addresses if not addr.startswith("127.")]
    if private:
        return _result("network", "Network", "PASS", private[0], f"Detected {len(private)} IPv4 address(es).")
    return _result("network", "Network", "WARN", "No IPv4", "No non-loopback IPv4 address detected at test time.")


def check_battery_health(serial: str) -> HardwareTestResult:
    """Baca kode 'health' dari dumpsys battery - sinyal kerusakan baterai
    fisik (overheat/overvoltage/dead) yang terpisah dari level/suhu sesaat.
    """
    try:
        raw = _shell(serial, "dumpsys", "battery")
    except ADBError as exc:
        return _result("battery_health", "Battery Health", "FAIL", "Unavailable", str(exc))

    # Kode health standar Android: 1=UNKNOWN 2=GOOD 3=OVERHEAT 4=DEAD
    # 5=OVER_VOLTAGE 6=UNSPECIFIED_FAILURE 7=COLD
    health_codes = {
        "1": ("Unknown", "WARN"),
        "2": ("Good", "PASS"),
        "3": ("Overheat", "FAIL"),
        "4": ("Dead", "FAIL"),
        "5": ("Over Voltage", "FAIL"),
        "6": ("Unspecified Failure", "FAIL"),
        "7": ("Cold", "WARN"),
    }
    match = re.search(r"health:\s*(\d+)", raw)
    code = match.group(1) if match else None
    label, state = health_codes.get(code, ("Unknown", "WARN"))

    detail = (
        "Baterai perlu diganti - indikasi kerusakan fisik dari sistem Android."
        if state == "FAIL"
        else "Health code dari Android battery service."
    )
    return _result("battery_health", "Battery Health", state, label, detail)


def check_thermal(serial: str) -> HardwareTestResult:
    """Deteksi throttling/overheat via thermalservice - indikasi masalah
    pendinginan (thermal paste kering, kipas/vapor chamber rusak, dll)."""
    try:
        raw = _shell(serial, "dumpsys", "thermalservice")
    except ADBError as exc:
        return _result("thermal", "Thermal", "FAIL", "Unavailable", str(exc))

    if not raw:
        return _result("thermal", "Thermal", "INFO", "No data", "Thermal service tidak mengembalikan data.")

    # Severity level di Android (ThrottlingSeverity): 0=NONE 1=LIGHT
    # 2=MODERATE 3=SEVERE 4=CRITICAL 5=EMERGENCY 6=SHUTDOWN. Sebelumnya
    # kode regex ini di-assign ke severe_hit tapi TIDAK PERNAH dipakai -
    # keputusan PASS/WARN/FAIL cuma dari substring text ("severe",
    # "critical", dst) yang tidak selalu muncul di output (banyak build
    # Android cuma melaporkan angka status, bukan kata). Itu bisa bikin
    # device yang sebenarnya throttling parah malah lolos sebagai "Normal".
    numeric_match = re.search(r"mStatus\s*=\s*(\d+)", raw)
    lowered = raw.lower()

    severity_from_code = None
    if numeric_match:
        code = int(numeric_match.group(1))
        if code >= 3:
            severity_from_code = "severe"
        elif code >= 1:
            severity_from_code = "light"

    if "shutdown" in lowered or "emergency" in lowered or (
        numeric_match and int(numeric_match.group(1)) >= 6
    ):
        return _result("thermal", "Thermal", "FAIL", "Critical", "Device pernah/sedang thermal shutdown - cek pendinginan internal.")
    if "severe" in lowered or "critical" in lowered or severity_from_code == "severe":
        return _result("thermal", "Thermal", "WARN", "Throttling", "Device mengalami thermal throttling tingkat tinggi.")
    return _result("thermal", "Thermal", "PASS", "Normal", "Tidak ada indikasi thermal throttling parah.")


def check_memory(serial: str) -> HardwareTestResult:
    """Ringkasan RAM - tekanan memori tinggi bisa jadi gejala RAM
    bermasalah atau sistem kelebihan beban aplikasi background."""
    try:
        raw = _shell(serial, "dumpsys", "meminfo", "--summary")
    except ADBError as exc:
        return _result("memory", "RAM", "FAIL", "Unavailable", str(exc))

    total = re.search(r"Total RAM:\s*([\d,]+)K", raw)
    free = re.search(r"Free RAM:\s*([\d,]+)K", raw)
    # Sebelumnya low_ram dihitung tapi tidak pernah dipakai di keputusan
    # akhir - device yang jelas-jelas dilaporkan Android dalam status "low
    # ram"/lowmemorykiller aktif tetap bisa lolos PASS kalau percent_free
    # (yang dihitung manual dari parsing) kebetulan >= 5%.
    low_ram = "low ram" in raw.lower() or "lowmemorykiller" in raw.lower()

    if not total:
        return _result("memory", "RAM", "INFO", "Detected", "Tidak bisa parse ringkasan meminfo.")

    total_mb = int(total.group(1).replace(",", "")) // 1024
    free_mb = int(free.group(1).replace(",", "")) // 1024 if free else 0
    percent_free = (free_mb / total_mb * 100) if total_mb else 0

    value = f"{total_mb} MB total, {free_mb} MB free"
    if low_ram:
        return _result("memory", "RAM", "WARN", value, "Android melaporkan device dalam status low-memory (lowmemorykiller aktif) - RAM kemungkinan sering habis saat multitasking.")
    if percent_free < 5:
        return _result("memory", "RAM", "WARN", value, "RAM tersisa sangat sedikit - device mungkin sering lag/force-close aplikasi.")
    return _result("memory", "RAM", "PASS", value, "Penggunaan RAM dalam batas wajar.")


def check_wifi_radio(serial: str) -> HardwareTestResult:
    """Cek status radio WiFi secara spesifik - terpisah dari check_network
    yang cuma cek IP address aktif (device bisa saja radio WiFi mati tapi
    masih ada IP dari mobile data)."""
    try:
        raw = _shell(serial, "dumpsys", "wifi")
    except ADBError as exc:
        return _result("wifi_radio", "WiFi Radio", "FAIL", "Unavailable", str(exc))

    if not raw:
        return _result("wifi_radio", "WiFi Radio", "WARN", "No data", "WiFi service tidak merespons - kemungkinan modul WiFi bermasalah.")

    lowered = raw.lower()
    if "wi-fi is enabled" in lowered or "wifi is enabled" in lowered or "state: enabled" in lowered:
        return _result("wifi_radio", "WiFi Radio", "PASS", "Enabled", "WiFi radio aktif dan merespons normal.")
    if "wi-fi is disabled" in lowered or "wifi is disabled" in lowered:
        return _result("wifi_radio", "WiFi Radio", "INFO", "Disabled", "WiFi radio terdeteksi tapi sedang dimatikan user.")
    return _result("wifi_radio", "WiFi Radio", "INFO", "Detected", "WiFi service tersedia; status detail tidak terparsing.")


def check_bluetooth(serial: str) -> HardwareTestResult:
    try:
        features = _shell(serial, "pm", "list", "features")
    except ADBError as exc:
        return _result("bluetooth", "Bluetooth", "FAIL", "Unavailable", str(exc))

    if "bluetooth" not in features.lower():
        return _result("bluetooth", "Bluetooth", "WARN", "Not detected", "Modul Bluetooth tidak terdeteksi dari system features.")
    return _result("bluetooth", "Bluetooth", "INFO", "Detected", "Hardware Bluetooth terdeteksi; pairing test tetap perlu manual.")


def check_gps(serial: str) -> HardwareTestResult:
    try:
        features = _shell(serial, "pm", "list", "features")
    except ADBError as exc:
        return _result("gps", "GPS", "FAIL", "Unavailable", str(exc))

    if "location.gps" not in features.lower():
        return _result("gps", "GPS", "WARN", "Not detected", "Modul GPS tidak terdeteksi dari system features.")
    return _result("gps", "GPS", "INFO", "Detected", "Hardware GPS terdeteksi; fix satelit tetap perlu test outdoor.")


def check_nfc(serial: str) -> HardwareTestResult:
    try:
        features = _shell(serial, "pm", "list", "features")
    except ADBError as exc:
        return _result("nfc", "NFC", "FAIL", "Unavailable", str(exc))

    if "nfc" not in features.lower():
        return _result("nfc", "NFC", "INFO", "Not present", "Device ini tidak punya hardware NFC (bukan berarti rusak).")
    return _result("nfc", "NFC", "INFO", "Detected", "Hardware NFC terdeteksi; tap test tetap perlu manual.")


def check_vibrator(serial: str) -> HardwareTestResult:
    try:
        features = _shell(serial, "pm", "list", "features")
    except ADBError as exc:
        return _result("vibrator", "Vibration Motor", "FAIL", "Unavailable", str(exc))

    if "vibrator" not in features.lower():
        return _result("vibrator", "Vibration Motor", "WARN", "Not detected", "Modul vibrator tidak terdeteksi dari system features.")
    return _result("vibrator", "Vibration Motor", "INFO", "Detected", "Hardware vibrator terdeteksi; getaran fisik tetap perlu test manual.")


def check_fingerprint(serial: str) -> HardwareTestResult:
    try:
        features = _shell(serial, "pm", "list", "features")
    except ADBError as exc:
        return _result("fingerprint", "Fingerprint Sensor", "FAIL", "Unavailable", str(exc))

    if "fingerprint" not in features.lower():
        return _result("fingerprint", "Fingerprint Sensor", "INFO", "Not present", "Device ini tidak punya sensor fingerprint (bukan berarti rusak).")
    return _result("fingerprint", "Fingerprint Sensor", "INFO", "Detected", "Sensor fingerprint terdeteksi; akurasi scan tetap perlu test manual.")


def check_modem_radio(serial: str) -> HardwareTestResult:
    """Cek status radio seluler/modem - berguna buat device yang sering
    'no service' atau nggak kebaca sinyal padahal kartu SIM normal."""
    try:
        raw = _shell(serial, "dumpsys", "telephony.registry")
    except ADBError as exc:
        return _result("modem", "Modem/Radio", "FAIL", "Unavailable", str(exc))

    if not raw:
        return _result("modem", "Modem/Radio", "WARN", "No data", "Telephony service tidak merespons - device mungkin tidak punya modem seluler (tablet WiFi-only) atau modem bermasalah.")

    lowered = raw.lower()
    if "mservicestate=0" in lowered or "in service" in lowered:
        return _result("modem", "Modem/Radio", "PASS", "In Service", "Modem terdaftar ke jaringan seluler.")
    if "out of service" in lowered or "mservicestate=1" in lowered:
        return _result("modem", "Modem/Radio", "WARN", "Out of Service", "Modem tidak terdaftar ke jaringan - cek sinyal area atau kemungkinan modem bermasalah.")
    return _result("modem", "Modem/Radio", "INFO", "Detected", "Telephony service tersedia; status detail tidak terparsing.")


def check_crash_stability(serial: str) -> HardwareTestResult:
    """Hitung crash/ANR aplikasi dari logcat terkini - indikator masalah
    software (bukan hardware) yang sering bikin device 'terasa rusak'
    padahal sebenarnya software/RAM/storage yang bermasalah."""
    try:
        raw = run_adb("-s", serial, "shell", "logcat", "-d", "-t", "3000", "*:E", timeout=15)
    except ADBError as exc:
        return _result("crash_stability", "Software Stability", "FAIL", "Unavailable", str(exc))

    crash_count = len(re.findall(r"FATAL EXCEPTION|AndroidRuntime.*FATAL", raw))
    anr_count = len(re.findall(r"ANR in |Input dispatching timed out", raw))

    total = crash_count + anr_count
    value = f"{crash_count} crash, {anr_count} ANR"
    detail = "Dihitung dari 3000 baris log error terakhir (indikatif, bukan angka absolut)."

    if total >= 5:
        return _result("crash_stability", "Software Stability", "WARN", value, f"{detail} Frekuensi tinggi - kemungkinan masalah software/RAM/storage, bukan hardware.")
    if total > 0:
        return _result("crash_stability", "Software Stability", "INFO", value, detail)
    return _result("crash_stability", "Software Stability", "PASS", "Stable", "Tidak ada crash/ANR terdeteksi di log terkini.")


def run_hardware_test(serial: str) -> HardwareTestReport:
    """Run safe, read-only checks against one authorized ADB device."""
    checks = [
        check_battery,
        check_battery_health,
        check_storage,
        check_display,
        check_audio,
        check_camera,
        check_sensors,
        check_usb,
        check_network,
        check_wifi_radio,
        check_bluetooth,
        check_gps,
        check_nfc,
        check_vibrator,
        check_fingerprint,
        check_modem_radio,
        check_thermal,
        check_memory,
        check_crash_stability,
    ]

    results: list[HardwareTestResult] = []
    for check in checks:
        try:
            results.append(check(serial))
        except Exception as exc:  # Keep the service-center UI resilient.
            key = check.__name__.removeprefix("check_")
            results.append(_result(key, key.title(), "FAIL", "Error", str(exc)))

    return HardwareTestReport(serial=serial, results=results)
