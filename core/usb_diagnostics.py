"""Read-only USB/connection diagnostics for Windows.

This module intentionally does not change USB configurations, send AT commands,
write to devices, or execute device payloads. It only reports what Windows and
ADB can currently see.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
import os
import shutil
import subprocess
from typing import Any


@dataclass(frozen=True)
class UsbDevice:
    status: str
    class_name: str
    friendly_name: str
    instance_id: str = ""
    vendor_id: str = ""
    product_id: str = ""


@dataclass(frozen=True)
class SerialPort:
    name: str
    description: str
    instance_id: str = ""


@dataclass(frozen=True)
class UsbDiagnosticsReport:
    platform: str
    pnp_available: bool
    usb_devices: list[UsbDevice]
    serial_ports: list[SerialPort]
    adb_available: bool
    adb_devices: list[dict[str, str]]
    pyusb_backend: str
    samsung_usb_detected: bool

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _run_powershell(script: str) -> tuple[bool, str]:
    if os.name != "nt":
        return False, ""
    try:
        completed = subprocess.run(
            ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", script],
            capture_output=True,
            text=True,
            timeout=8,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return False, ""
    return completed.returncode == 0, completed.stdout


def _parse_pnp_line(line: str) -> UsbDevice | None:
    parts = line.split("\t")
    if len(parts) < 3:
        return None
    status, class_name, friendly_name = (p.strip() for p in parts[:3])
    instance_id = parts[3].strip() if len(parts) > 3 else ""
    vendor_id = ""
    product_id = ""
    upper_id = instance_id.upper()
    for token in upper_id.split("\\"):
        if token.startswith("VID_"):
            vendor_id = token[4:]
        elif token.startswith("PID_"):
            product_id = token[4:]
    return UsbDevice(
        status=status,
        class_name=class_name,
        friendly_name=friendly_name,
        instance_id=instance_id,
        vendor_id=vendor_id,
        product_id=product_id,
    )


def enumerate_usb_devices() -> list[UsbDevice]:
    """Return present Windows USB-related PnP devices without modifying them."""
    script = (
        "Get-PnpDevice -PresentOnly | "
        "Where-Object { $_.Class -match 'USB|Modem|Ports' } | "
        "ForEach-Object { '{0}`t{1}`t{2}`t{3}' -f "
        "$_.Status,$_.Class,$_.FriendlyName,$_.InstanceId }"
    )
    ok, output = _run_powershell(script)
    if not ok:
        return []
    devices: list[UsbDevice] = []
    for line in output.splitlines():
        device = _parse_pnp_line(line)
        if device:
            devices.append(device)
    return devices


def enumerate_serial_ports() -> list[SerialPort]:
    """Return present Windows Ports/COM devices without opening them."""
    script = (
        "Get-PnpDevice -PresentOnly | "
        "Where-Object { $_.Class -eq 'Ports' } | "
        "ForEach-Object { '{0}`t{1}`t{2}' -f "
        "$_.FriendlyName,$_.FriendlyName,$_.InstanceId }"
    )
    ok, output = _run_powershell(script)
    if not ok:
        return []
    ports: list[SerialPort] = []
    for line in output.splitlines():
        parts = line.split("\t")
        if len(parts) >= 3:
            ports.append(SerialPort(parts[0].strip(), parts[1].strip(), parts[2].strip()))
    return ports


def check_pyusb_backend() -> str:
    """Report PyUSB backend availability without enumerating or changing devices."""
    try:
        import usb.backend.libusb1  # type: ignore
    except ImportError:
        return "pyusb-not-installed"
    try:
        backend = usb.backend.libusb1.get_backend()
    except Exception:
        return "backend-error"
    return "available" if backend is not None else "unavailable"


def _resolve_adb() -> str | None:
    configured = os.environ.get("NEXA_ADB_PATH")
    if configured and os.path.isfile(configured):
        return configured
    path = shutil.which("adb")
    if path:
        return path
    try:
        from core.config import ADB_PATH

        if ADB_PATH.exists():
            return str(ADB_PATH)
    except Exception:
        pass
    return None


def enumerate_adb_devices() -> tuple[bool, list[dict[str, str]]]:
    """Return ADB availability and current device states."""
    adb_path = _resolve_adb()
    if not adb_path:
        return False, []
    try:
        completed = subprocess.run(
            [adb_path, "devices", "-l"],
            capture_output=True,
            text=True,
            timeout=8,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return False, []
    if completed.returncode != 0:
        return True, []

    devices: list[dict[str, str]] = []
    for line in completed.stdout.splitlines():
        line = line.strip()
        if not line or line.startswith("List of devices"):
            continue
        fields = line.split()
        if len(fields) < 2:
            continue
        item = {"serial": fields[0], "state": fields[1]}
        for field in fields[2:]:
            if ":" in field:
                key, value = field.split(":", 1)
                item[key] = value
        devices.append(item)
    return True, devices


def collect_usb_diagnostics() -> UsbDiagnosticsReport:
    """Collect a complete read-only USB/ADB connectivity snapshot."""
    usb_devices = enumerate_usb_devices()
    serial_ports = enumerate_serial_ports()
    adb_available, adb_devices = enumerate_adb_devices()
    samsung_detected = any(
        device.vendor_id.upper() == "04E8"
        or "SAMSUNG" in device.friendly_name.upper()
        for device in usb_devices
    )
    return UsbDiagnosticsReport(
        platform=os.name,
        pnp_available=os.name == "nt",
        usb_devices=usb_devices,
        serial_ports=serial_ports,
        adb_available=adb_available,
        adb_devices=adb_devices,
        pyusb_backend=check_pyusb_backend(),
        samsung_usb_detected=samsung_detected,
    )
