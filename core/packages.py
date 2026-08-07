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
    packages = []

    for line in output.splitlines():
        line = line.strip()

        if line.startswith("package:"):
            name = line[len("package:"):].strip()
            packages.append(PackageInfo(package_name=name, is_system=not bool(flag)))

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
