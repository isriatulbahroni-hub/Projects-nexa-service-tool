"""Memasang halaman 'Perbaikan HP' dan flash aman ke MainWindow tanpa mengedit app.py.

Dipanggil sekali dari main.py, sebelum MainWindow dibuat:

    from ui.repair_integration import install_repair_tools
    install_repair_tools(MainWindow)

Pola sama dengan ui/mirror_integration.py: patch kecil pada kelas, mudah ditinjau dan dibatalkan.
"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QInputDialog, QMessageBox, QPushButton

from core.async_worker import AsyncWorker
from core.firmware import FastbootError, list_fastboot_devices
from core.flash_safety import FlashItem, execute_queue
from core.repair_session import prepare_flash
from ui.repair_page import RepairPage

FLASH_LABEL = "Flash Partition Sekarang"


def _reset_flash_button(win) -> None:
    win.firmware_flash_button.setEnabled(True)
    win.firmware_flash_button.setText(FLASH_LABEL)


def safe_run_flash_partition(self) -> None:
    """Pengganti MainWindow.run_flash_partition: pilih device eksplisit, periksa dulu, baru flash."""
    if not self._firmware_image_path:
        QMessageBox.warning(self, "Belum pilih file", "Pilih file image (.img) terlebih dahulu.")
        return

    partition = self.firmware_partition_combo.currentText()
    image_path = self._firmware_image_path

    try:
        devices = list_fastboot_devices()
    except FastbootError as exc:
        QMessageBox.critical(
            self, "Fastboot Tidak Terdeteksi", f"{exc}\n\nPastikan device dalam mode Bootloader dan terhubung."
        )
        return
    if not devices:
        QMessageBox.warning(
            self,
            "Device Tidak Terdeteksi",
            "Tidak ada device dalam mode Fastboot/Bootloader.\n\nKlik 'Reboot ke Bootloader' terlebih dahulu.",
        )
        return

    if len(devices) == 1:
        serial = devices[0]
    else:
        serial, ok = QInputDialog.getItem(
            self, "Pilih perangkat", "Ada lebih dari satu perangkat fastboot. Pilih yang akan diflash:", devices, 0, False
        )
        if not ok or not serial:
            return

    codename, ok = QInputDialog.getText(
        self,
        "Codename firmware",
        "Codename (ro.product.device) tujuan firmware ini.\nKosongkan jika tidak tahu (kecocokan model tidak diperiksa):",
    )
    if not ok:
        return
    codename = codename.strip()

    self.firmware_flash_button.setEnabled(False)
    self.firmware_flash_button.setText("Memeriksa...")
    self.firmware_flash_log.appendPlainText(f"Memeriksa '{partition}' pada device {serial}...")

    prep = AsyncWorker(lambda: prepare_flash(serial, partition, image_path, codename or None), self)
    prep.succeeded.connect(lambda result: _after_prepare(self, serial, partition, image_path, codename, result))
    prep.failed.connect(lambda message: _prepare_failed(self, message))
    self._flash_prep_worker = prep
    prep.start()


def _prepare_failed(self, message: str) -> None:
    self.firmware_flash_log.appendPlainText(f"ERROR pemeriksaan: {message}")
    _reset_flash_button(self)
    QMessageBox.critical(self, "Pemeriksaan Gagal", message)


def _after_prepare(self, serial, partition, image_path, codename, result) -> None:
    if result["errors"]:
        text = "\n".join(f"- {e}" for e in result["errors"])
        self.firmware_flash_log.appendPlainText(f"DIBLOKIR:\n{text}")
        _reset_flash_button(self)
        QMessageBox.critical(self, "Flash Diblokir", text)
        return

    warnings = "".join(f"\n- {w}" for w in result["warnings"])
    reply = QMessageBox.question(
        self,
        "Konfirmasi Flash - RISIKO TINGGI",
        f"Partisi: {partition}\nDevice: {serial} ({result['product'] or 'codename tidak terbaca'})\n"
        f"File: {image_path}\nSHA-256: {result['sha256']}\n"
        + (f"\nPeringatan:{warnings}\n" if warnings else "")
        + "\nFlash bisa membuat HP tidak bisa boot jika file tidak sesuai. Lanjutkan?",
        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        QMessageBox.StandardButton.No,
    )
    if reply != QMessageBox.StandardButton.Yes:
        self.firmware_flash_log.appendPlainText("Dibatalkan.")
        _reset_flash_button(self)
        return

    self.firmware_flash_button.setText("Sedang Flashing... Jangan cabut kabel!")
    self.firmware_flash_log.appendPlainText(f"Flashing '{partition}' pada device {serial}...")
    worker = AsyncWorker(
        lambda: execute_queue(serial, [FlashItem(partition, image_path)], codename or None), self
    )

    def _on_success(results):
        output = "\n".join(out for _name, out in results if out)
        self.firmware_flash_log.appendPlainText(output or "Flash selesai.")
        self.firmware_flash_log.appendPlainText("--- SELESAI ---")
        _reset_flash_button(self)
        self.log_action("Flash Partition", detail=f"{partition} <- {image_path}", status="OK", serial=serial)
        QMessageBox.information(self, "Flash Berhasil", f"Partition '{partition}' berhasil diflash.")

    def _on_error(message: str):
        self.firmware_flash_log.appendPlainText(f"ERROR: {message}")
        _reset_flash_button(self)
        self.log_action("Flash Partition", detail=f"{partition} <- {image_path}: {message}", status="GAGAL", serial=serial)
        QMessageBox.critical(self, "Flash Gagal", message)

    worker.succeeded.connect(_on_success)
    worker.failed.connect(_on_error)
    self._flash_worker = worker
    worker.start()


def _attach_repair_page(self) -> None:
    page = RepairPage(lambda: self.current_serial)
    anchor = self.nav_buttons.get("firmware")
    layout = anchor.parentWidget().layout() if anchor is not None else None
    button = QPushButton("Perbaikan HP")
    button.setObjectName("navBtn")
    button.setCheckable(True)
    button.clicked.connect(lambda _=False: self.switch_page("repair"))
    if layout is not None:
        layout.insertWidget(layout.indexOf(anchor) + 1, button)
    self.nav_buttons["repair"] = button
    self.pages.addWidget(page)
    self.page_widgets["repair"] = page
    if page.layout() is not None:
        page.layout().setAlignment(Qt.AlignmentFlag.AlignTop)


def install_repair_tools(window_cls) -> None:
    if getattr(window_cls, "_repair_tools_installed", False):
        return
    original_init = window_cls.__init__

    def __init__(self, *args, **kwargs):
        original_init(self, *args, **kwargs)
        _attach_repair_page(self)

    window_cls.__init__ = __init__
    window_cls.run_flash_partition = safe_run_flash_partition
    window_cls._repair_tools_installed = True
