"""Ekspor data bersama Python -> web/src/shared/repair-data.js (sumber tunggal).

Jalankan: python tools/export_shared.py   (tests/test_shared_data.py memeriksa sinkron)
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core.firmware import COMMON_PARTITIONS, CRITICAL_PARTITIONS, LOGICAL_PARTITIONS  # noqa: E402
from core.flash_safety import QUEUE_SKIP  # noqa: E402
from core.repair_data import SHARED  # noqa: E402

OUT = ROOT / "web" / "src" / "shared" / "repair-data.js"


def data() -> dict:
    """Hanya data yang dipakai web. Profil gejala & kesehatan baterai sudah punya versi web sendiri."""
    return {
        "bootloop_steps": SHARED["bootloop_steps"],
        "modes": SHARED["modes"],
        "flash": {
            "common_partitions": list(COMMON_PARTITIONS),
            "critical_partitions": sorted(CRITICAL_PARTITIONS),
            "logical_partitions": sorted(LOGICAL_PARTITIONS),
            "queue_skip": sorted(QUEUE_SKIP),
        },
    }


def render() -> str:
    body = json.dumps(data(), indent=2, ensure_ascii=False)
    return "// DIBUAT OTOMATIS oleh tools/export_shared.py - jangan diedit manual.\nexport default " + body + ";\n"


if __name__ == "__main__":
    OUT.write_text(render(), encoding="utf-8")
    print("ditulis:", OUT)
