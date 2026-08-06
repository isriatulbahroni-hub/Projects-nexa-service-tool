from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent

ADB_PATH = Path.home() / "platform-tools" / "platform-tools" / "adb.exe"
FASTBOOT_PATH = Path.home() / "platform-tools" / "platform-tools" / "fastboot.exe"
