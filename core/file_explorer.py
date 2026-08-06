from dataclasses import dataclass

from .adb import run_adb, ADBError


@dataclass
class RemoteEntry:
    name: str
    is_dir: bool
    size: str
    permissions: str


def list_dir(serial: str, remote_path: str = "/sdcard") -> list[RemoteEntry]:
    output = run_adb("-s", serial, "shell", "ls", "-la", remote_path)
    entries: list[RemoteEntry] = []

    for line in output.splitlines():
        line = line.strip()

        if not line or line.startswith("total"):
            continue

        parts = line.split(None, 8)

        if len(parts) < 9:
            continue

        permissions = parts[0]
        size = parts[4]
        name = parts[8]

        if name in (".", ".."):
            continue

        is_dir = permissions.startswith("d")

        entries.append(
            RemoteEntry(
                name=name,
                is_dir=is_dir,
                size=size if not is_dir else "-",
                permissions=permissions,
            )
        )

    entries.sort(key=lambda e: (not e.is_dir, e.name.lower()))
    return entries


def normalize_path(path: str) -> str:
    if not path.startswith("/"):
        path = "/" + path

    while "//" in path:
        path = path.replace("//", "/")

    return path.rstrip("/") or "/"


def go_up(path: str) -> str:
    path = normalize_path(path)

    if path == "/":
        return "/"

    parent = "/".join(path.split("/")[:-1])
    return parent or "/"


def pull_file(serial: str, remote_path: str, local_path: str) -> str:
    return run_adb("-s", serial, "pull", remote_path, local_path, timeout=120)


def push_file(serial: str, local_path: str, remote_path: str) -> str:
    return run_adb("-s", serial, "push", local_path, remote_path, timeout=120)


def delete_remote(serial: str, remote_path: str) -> str:
    return run_adb("-s", serial, "shell", "rm", "-rf", remote_path)


def make_dir(serial: str, remote_path: str) -> str:
    return run_adb("-s", serial, "shell", "mkdir", "-p", remote_path)
