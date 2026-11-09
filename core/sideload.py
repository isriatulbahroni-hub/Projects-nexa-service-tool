"""Validasi paket OTA resmi lalu `adb sideload`."""
from __future__ import annotations

import zipfile
from dataclasses import dataclass, field
from pathlib import Path

from .adb import ADBError, get_devices_with_state, run_adb

METADATA_PATH = "META-INF/com/android/metadata"
UPDATE_BINARY = "META-INF/com/google/android/update-binary"


@dataclass
class OtaCheck:
    problems: list[str] = field(default_factory=list)
    metadata: dict[str, str] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return not self.problems


def parse_metadata(text: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for line in text.splitlines():
        if "=" in line:
            key, value = line.split("=", 1)
            out[key.strip()] = value.strip()
    return out


def validate_ota_package(path: str | Path, expected_codename: str | None = None) -> OtaCheck:
    check = OtaCheck()
    path = Path(path)
    if not path.is_file():
        check.problems.append("File paket tidak ditemukan.")
        return check
    if not zipfile.is_zipfile(path):
        check.problems.append("Bukan file zip, bukan paket OTA.")
        return check
    with zipfile.ZipFile(path) as archive:
        names = set(archive.namelist())
        if METADATA_PATH not in names:
            check.problems.append("Bukan paket OTA resmi: metadata tidak ada.")
        else:
            check.metadata = parse_metadata(archive.read(METADATA_PATH).decode("utf-8", errors="replace"))
        if "payload.bin" not in names and UPDATE_BINARY not in names:
            check.problems.append("Isi paket tidak lengkap: payload.bin atau update-binary tidak ada.")
    if expected_codename and check.metadata:
        devices = [d.strip().lower() for d in check.metadata.get("pre-device", "").split(",") if d.strip()]
        if devices and expected_codename.strip().lower() not in devices:
            check.problems.append(
                f"Paket untuk {', '.join(devices)}, bukan untuk '{expected_codename}'."
            )
    return check


def sideload_package(
    serial: str,
    path: str | Path,
    expected_codename: str | None = None,
    timeout: int = 1800,
    *,
    runner=run_adb,
    state_reader=get_devices_with_state,
) -> str:
    if state_reader().get(serial) != "sideload":
        raise ADBError("Perangkat belum dalam mode sideload. Pilih 'Apply update from ADB' di recovery.")
    check = validate_ota_package(path, expected_codename)
    if not check.ok:
        raise ADBError("Paket ditolak: " + " ".join(check.problems))
    try:
        return runner("-s", serial, "sideload", str(path), timeout=timeout)
    except ADBError as exc:
        message = str(exc)
        # adb sideload sering keluar non-zero di akhir walau transfer selesai.
        if "Total xfer" in message or "failed to read command: Success" in message:
            return message
        raise
