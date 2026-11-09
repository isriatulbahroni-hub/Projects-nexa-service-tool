import re
from dataclasses import dataclass

from .adb import run_adb, ADBError


@dataclass
class PackageInfo:
    package_name: str
    is_system: bool


def list_packages(serial: str, include_system: bool = False) -> list[PackageInfo]:
    flag = "-3" if not include_system else ""
    # --user 0 dipaksa eksplisit karena beberapa device (mis. yang punya
    # Private Space / secondary user profile di Android 14+) membuat ADB
    # shell gagal resolve "current user" dan melempar SecurityException
    # saat mencoba mengakses user tersembunyi (mis. user 999).
    args = ["-s", serial, "shell", "pm", "list", "packages", "--user", "0"]

    if flag:
        args.append(flag)

    output = run_adb(*args)
    names = []

    for line in output.splitlines():
        line = line.strip()

        if line.startswith("package:"):
            names.append(line[len("package:"):].strip())

    if not include_system:
        # Query di atas sudah difilter "-3" (third-party only), jadi semua
        # hasil pasti bukan system app.
        packages = [PackageInfo(package_name=n, is_system=False) for n in names]
    else:
        # Query tanpa filter mengembalikan SEMUA package (system + third-
        # party bercampur). Sebelumnya di sini semuanya asal ditandai
        # is_system=True, yang salah untuk app pihak ketiga (mis. NexaPay,
        # Shopee, dll ikut ke-mark sebagai system app). Query tambahan
        # "-3" dipakai untuk tahu mana yang sebenarnya third-party.
        try:
            third_party_output = run_adb(
                "-s", serial, "shell", "pm", "list", "packages", "--user", "0", "-3"
            )
            third_party = {
                line.strip()[len("package:"):].strip()
                for line in third_party_output.splitlines()
                if line.strip().startswith("package:")
            }
        except ADBError:
            third_party = set()

        packages = [
            PackageInfo(package_name=n, is_system=n not in third_party) for n in names
        ]

    return sorted(packages, key=lambda p: p.package_name.lower())


def get_package_version(serial: str, package_name: str) -> str:
    try:
        output = run_adb(
            "-s", serial, "shell", "dumpsys", "package", package_name
        )

        for line in output.splitlines():
            line = line.strip()

            if line.startswith("versionName="):
                return line.split("=", 1)[1].strip()
    except ADBError:
        pass

    return "Unknown"


def install_apk(serial: str, apk_path: str) -> str:
    return run_adb("-s", serial, "install", "-r", apk_path, timeout=120)


def uninstall_package(serial: str, package_name: str, keep_data: bool = False) -> str:
    args = ["-s", serial, "uninstall"]

    if keep_data:
        args.append("-k")

    args.append(package_name)

    return run_adb(*args, timeout=60)


def force_stop(serial: str, package_name: str) -> str:
    return run_adb("-s", serial, "shell", "am", "force-stop", package_name)


def clear_app_data(serial: str, package_name: str) -> str:
    return run_adb("-s", serial, "shell", "pm", "clear", package_name)


def trim_caches(serial: str) -> str:
    """Bersihkan cache SEMUA aplikasi (bukan data user) - operasi aman
    setara 'Free up space' di Settings Android. Android tidak menyediakan
    perintah shell untuk clear cache SATU app spesifik tanpa root (cuma
    lewat Settings UI manual), jadi ini system-wide trim via pm."""
    # Angka besar (bytes) supaya Android trim maksimal yang bisa ditrim.
    return run_adb("-s", serial, "shell", "pm", "trim-caches", "999999999999")


_PACKAGE_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_]*(\.[A-Za-z0-9_]+)+$")

# Paket yang kalau dimatikan bisa membuat HP tidak bisa dipakai.
PROTECTED_PACKAGES = frozenset({
    "android",
    "com.android.systemui",
    "com.android.settings",
    "com.android.phone",
    "com.android.shell",
    "com.android.vending",
    "com.google.android.gms",
    "com.google.android.packageinstaller",
    "com.android.packageinstaller",
})


def _checked_package(package_name: str) -> str:
    package_name = (package_name or "").strip()
    if not _PACKAGE_RE.match(package_name):
        raise ADBError("Nama package tidak valid.")
    if package_name in PROTECTED_PACKAGES or package_name.startswith("com.android.providers."):
        raise ADBError(f"{package_name} penting bagi sistem, diblokir.")
    return package_name


def disable_app(serial: str, package_name: str) -> str:
    """Nonaktifkan aplikasi untuk user 0 (bisa diaktifkan lagi)."""
    package_name = _checked_package(package_name)
    return run_adb("-s", serial, "shell", "pm", "disable-user", "--user", "0", package_name)


def enable_app(serial: str, package_name: str) -> str:
    """Aktifkan lagi aplikasi yang tadi dinonaktifkan."""
    package_name = (package_name or "").strip()
    if not _PACKAGE_RE.match(package_name):
        raise ADBError("Nama package tidak valid.")
    return run_adb("-s", serial, "shell", "pm", "enable", package_name)
