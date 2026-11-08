from dataclasses import dataclass

from .adb import run_adb, ADBError


@dataclass
class SecurityCheckResult:
    is_rooted: bool
    root_indicator: str
    bootloader_state: str
    verified_boot_state: str
    security_patch: str
    selinux_status: str
    warnings: list[str]


ROOT_PATHS = [
    "/system/bin/su",
    "/system/xbin/su",
    "/sbin/su",
    "/system/app/Superuser.apk",
    "/data/local/xbin/su",
]


def _getprop(serial: str, prop: str) -> str:
    try:
        result = run_adb("-s", serial, "shell", "getprop", prop).strip()
        return result if result else "Unknown"
    except ADBError:
        return "Unknown"


def _check_root(serial: str) -> tuple[bool, str]:
    try:
        which_su = run_adb("-s", serial, "shell", "which", "su").strip()

        if which_su:
            return True, f"Binary 'su' ditemukan di {which_su}"
    except ADBError:
        pass

    for path in ROOT_PATHS:
        try:
            output = run_adb(
                "-s", serial, "shell", "ls", path
            ).strip()

            if output and "No such file" not in output:
                return True, f"File root indicator ditemukan: {path}"
        except ADBError:
            continue

    return False, "Tidak ditemukan indikator root."


def run_security_check(serial: str) -> SecurityCheckResult:
    is_rooted, root_indicator = _check_root(serial)

    verified_boot_state = _getprop(serial, "ro.boot.verifiedbootstate")

    # ro.boot.flash.locked tidak ada di semua merek (banyak HP MediaTek dan
    # Samsung tidak mengisinya), jadi pakai cadangan yang umum.
    bootloader_state = _getprop(serial, "ro.boot.flash.locked")
    if bootloader_state == "0":
        bootloader_state = "Unlocked"
    elif bootloader_state == "1":
        bootloader_state = "Locked"
    else:
        vbmeta = _getprop(serial, "ro.boot.vbmeta.device_state").lower()
        if vbmeta in ("locked", "unlocked"):
            bootloader_state = vbmeta.capitalize()
        elif verified_boot_state.lower() == "orange":
            bootloader_state = "Unlocked"
    security_patch = _getprop(serial, "ro.build.version.security_patch")

    try:
        selinux_status = run_adb("-s", serial, "shell", "getenforce").strip()
    except ADBError:
        selinux_status = "Unknown"

    warnings = []

    if is_rooted:
        warnings.append(
            "Device terdeteksi root - beberapa fitur keamanan bawaan mungkin nonaktif."
        )

    if bootloader_state == "Unlocked":
        warnings.append(
            "Bootloader unlocked - device rentan terhadap flashing tidak resmi."
        )

    if verified_boot_state not in ("green", "Unknown"):
        warnings.append(
            f"Verified Boot state '{verified_boot_state}' - integritas sistem perlu dicek."
        )

    if selinux_status.lower() == "permissive":
        warnings.append(
            "SELinux dalam mode Permissive - proteksi keamanan sistem berkurang."
        )

    if security_patch != "Unknown":
        try:
            from datetime import datetime

            patch_date = datetime.strptime(security_patch, "%Y-%m-%d")
            age_days = (datetime.now() - patch_date).days

            if age_days > 365:
                warnings.append(
                    f"Security patch sudah {age_days} hari - device tertinggal update keamanan."
                )
        except ValueError:
            pass

    if not warnings:
        warnings.append("Tidak ada indikasi masalah keamanan yang signifikan.")

    return SecurityCheckResult(
        is_rooted=is_rooted,
        root_indicator=root_indicator,
        bootloader_state=bootloader_state,
        verified_boot_state=verified_boot_state,
        security_patch=security_patch,
        selinux_status=selinux_status,
        warnings=warnings,
    )
