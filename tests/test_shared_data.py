import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

import export_shared  # noqa: E402


def test_web_data_in_sync_with_python():
    committed = (ROOT / "web" / "src" / "shared" / "repair-data.js").read_text(encoding="utf-8")
    assert committed == export_shared.render(), "Jalankan: python tools/export_shared.py"
    assert committed.startswith("// DIBUAT OTOMATIS")
