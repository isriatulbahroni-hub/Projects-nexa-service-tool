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
        weights = {"PASS": 1.0, "INFO": 0.8, "WARN": 0.5, "FAIL": 0.0}
        total = sum(weights.get(item.status, 0.0) for item in self.results)
        # Binary floats can't represent values like 2.3/4 exactly, so a true
        # x.5 sometimes lands a hair under (e.g. 57.49999999999999) and
        # round() truncates it down instead of up. A tiny epsilon corrects
        # that representation error without affecting any other value.
        return round(total / len(self.results) * 100 + 1e-9)


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


def run_hardware_test(serial: str) -> HardwareTestReport:
    """Run safe, read-only checks against one authorized ADB device."""
    checks = [
        check_battery,
        check_storage,
        check_display,
        check_audio,
        check_camera,
        check_sensors,
        check_usb,
        check_network,
    ]

    results: list[HardwareTestResult] = []
    for check in checks:
        try:
            results.append(check(serial))
        except Exception as exc:  # Keep the service-center UI resilient.
            key = check.__name__.removeprefix("check_")
            results.append(_result(key, key.title(), "FAIL", "Error", str(exc)))

    return HardwareTestReport(serial=serial, results=results)
