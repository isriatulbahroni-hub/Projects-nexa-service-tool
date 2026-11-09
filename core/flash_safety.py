"""Mesin flash aman. Semua pemeriksaan dilakukan SEBELUM satu pun partisi ditulis (all-or-nothing).

Aturan: device harus eksplisit, bootloader terkunci diblokir, partisi kritis diblokir,
partisi logical hanya dari fastbootd, ukuran image tidak boleh melebihi partisi, codename
harus cocok, dan SHA-256 dicek bila diberikan.
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable

from .firmware import (
    CRITICAL_PARTITIONS,
    LOGICAL_PARTITIONS,
    FastbootError,
    flash_partition,
    get_fastboot_vars,
    list_fastboot_devices,
)

# Partisi yang tidak pernah masuk antrean otomatis (data pengguna / identitas perangkat).
QUEUE_SKIP = frozenset({"userdata", "metadata", "persist", "efs", "frp"})


class FlashSafetyError(RuntimeError):
    def __init__(self, problems: Iterable[str]):
        self.problems = list(problems)
        super().__init__("; ".join(self.problems))


@dataclass(frozen=True)
class FlashItem:
    partition: str
    image_path: str
    sha256: str | None = None


def sha256_file(path: str | Path, chunk: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        while True:
            block = handle.read(chunk)
            if not block:
                break
            digest.update(block)
    return digest.hexdigest()


def parse_size(value) -> int | None:
    try:
        return int(str(value).strip(), 0)
    except (TypeError, ValueError):
        return None


def partition_size(fb_vars: dict[str, str], partition: str) -> int | None:
    slot = fb_vars.get("current-slot", "").strip()
    keys = []
    if slot:
        keys.append(f"partition-size:{partition}_{slot}")
    keys.append(f"partition-size:{partition}")
    for key in keys:
        size = parse_size(fb_vars.get(key))
        if size:
            return size
    return None


def bootloader_state(fb_vars: dict[str, str]) -> bool | None:
    """True = terkunci, False = terbuka, None = tidak diketahui."""
    unlocked = fb_vars.get("unlocked", "").strip().lower()
    if unlocked in ("yes", "true"):
        return False
    if unlocked in ("no", "false"):
        return True
    secure = fb_vars.get("securestate", "").strip().lower()
    if "unlocked" in secure:
        return False
    if "locked" in secure:
        return True
    return None


def validate_queue(
    items: Iterable[FlashItem], fb_vars: dict[str, str], expected_codename: str | None = None
) -> tuple[list[str], list[str]]:
    """Kembalikan (errors, warnings). Ada error = tidak boleh flash apa pun."""
    errors: list[str] = []
    warnings: list[str] = []
    items = list(items)
    if not items:
        return ["Antrean flash kosong."], warnings

    state = bootloader_state(fb_vars)
    if state is True:
        errors.append("Bootloader terkunci: flash diblokir. Buka kunci bootloader dulu (menghapus data).")
    elif state is None:
        warnings.append("Status kunci bootloader tidak terbaca; fastboot akan menolak sendiri jika terkunci.")

    if expected_codename:
        product = fb_vars.get("product", "").strip()
        if not product:
            errors.append("Codename perangkat tidak terbaca, tidak bisa dicocokkan dengan firmware.")
        elif product.lower() != expected_codename.strip().lower():
            errors.append(f"Codename tidak cocok: perangkat '{product}', firmware untuk '{expected_codename}'.")

    userspace = fb_vars.get("is-userspace", "").strip().lower() == "yes"
    seen: set[str] = set()
    for item in items:
        name = item.partition.strip().lower()
        base = re.sub(r"_[ab]$", "", name)
        if not re.fullmatch(r"[a-z0-9_]+", name):
            errors.append(f"Nama partisi tidak valid: '{item.partition}'.")
            continue
        if name in seen:
            errors.append(f"Partisi {name} muncul lebih dari sekali.")
            continue
        seen.add(name)
        if base in CRITICAL_PARTITIONS:
            errors.append(f"Partisi {name} kritis dan diblokir.")
            continue
        if base in QUEUE_SKIP:
            errors.append(f"Partisi {name} tidak boleh masuk antrean flash.")
            continue
        if base in LOGICAL_PARTITIONS and not userspace:
            errors.append(f"Partisi {name} adalah partisi logical: pindah ke fastbootd dulu.")
        path = Path(item.image_path)
        if not path.is_file():
            errors.append(f"File image {name} tidak ditemukan: {item.image_path}")
            continue
        size = path.stat().st_size
        if size == 0:
            errors.append(f"File image {name} kosong.")
            continue
        limit = partition_size(fb_vars, name)
        if limit and size > limit:
            errors.append(f"Image {name} ({size} byte) lebih besar dari partisi ({limit} byte).")
        if item.sha256 and sha256_file(path).lower() != item.sha256.strip().lower():
            errors.append(f"SHA-256 image {name} tidak cocok.")
    return errors, warnings


def build_queue_from_folder(folder: str | Path) -> tuple[list[FlashItem], list[str]]:
    """Petakan *.img di folder ke partisi. Partisi kritis/QUEUE_SKIP dilewati; kembalikan (items, nama file dilewati)."""
    items: list[FlashItem] = []
    skipped: list[str] = []
    for image in sorted(Path(folder).glob("*.img")):
        name = image.stem.lower()
        base = re.sub(r"_[ab]$", "", name)
        if base in QUEUE_SKIP or base in CRITICAL_PARTITIONS:
            skipped.append(image.name)
        else:
            items.append(FlashItem(name, str(image)))
    return items, skipped


def execute_queue(
    serial: str,
    items: Iterable[FlashItem],
    expected_codename: str | None = None,
    progress: Callable[[int, int, str], None] | None = None,
    *,
    flasher=flash_partition,
    vars_reader=get_fastboot_vars,
    device_lister=list_fastboot_devices,
) -> list[tuple[str, str]]:
    serial = (serial or "").strip()
    if not serial:
        raise FlashSafetyError(["Pilih perangkat secara eksplisit (serial kosong)."])
    if serial not in device_lister():
        raise FlashSafetyError([f"Perangkat {serial} tidak terdeteksi di fastboot."])

    items = list(items)
    errors, _warnings = validate_queue(items, vars_reader(serial), expected_codename)
    if errors:
        raise FlashSafetyError(errors)

    results: list[tuple[str, str]] = []
    for index, item in enumerate(items, 1):
        name = item.partition.strip().lower()
        if progress:
            progress(index, len(items), name)
        try:
            output = flasher(name, item.image_path, serial=serial)
        except FastbootError as exc:
            done = ", ".join(n for n, _ in results) or "tidak ada"
            raise FastbootError(f"Gagal flash {name}: {exc}. Sudah berhasil: {done}.") from exc
        results.append((name, output))
    return results
