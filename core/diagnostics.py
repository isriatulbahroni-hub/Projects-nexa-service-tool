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

    usb_debugging = "Enabled"

    return DiagnosticResult(
        battery_level=level,
        battery_status=status,
        battery_health=health,
        storage=storage_info,
        screen_state=screen_state,
        usb_debugging=usb_debugging,
    )
