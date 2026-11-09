"""Halaman 'Perbaikan HP' desktop: panduan bootloop, sideload OTA, perbaikan per gejala, tes aktif.

Dipasang ke MainWindow oleh ui/repair_integration.py (tanpa mengedit app.py).
"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from core import bootloop, hardware_active
from core.async_worker import AsyncWorker
from core.repair_actions import run_symptom
from core.repair_data import SYMPTOMS
from core.repair_session import (
    REBOOT_TARGETS,
    detect_current_mode,
    format_symptom_result,
    format_touch,
    reboot_to,
    resolve_sideload_serial,
)
from core.sideload import sideload_package, validate_ota_package

STATE_ICON = {"done": "\u2714", "skipped": "\u23ed", "ready": "\u25b6", "locked": "\U0001f512", "wrong_mode": "\u2014"}
STATE_LABEL = {
    "done": "selesai",
    "skipped": "dilewati",
    "ready": "siap",
    "locked": "terkunci",
    "wrong_mode": "mode tidak sesuai",
}
RISK_LABEL = {"none": "aman", "possible": "bisa hapus data", "all": "HAPUS SEMUA DATA"}
MODE_LABEL = {
    "android": "Android menyala",
    "recovery": "Recovery",
    "sideload": "Sideload",
    "fastboot": "Bootloader (fastboot)",
    "fastbootd": "fastbootd",
    "unauthorized": "ADB belum diizinkan di HP",
    "offline": "ADB offline",
    "none": "Tidak terdeteksi",
}


class RepairPage(QWidget):
    def __init__(self, serial_getter, parent=None):
        super().__init__(parent)
        self._serial_getter = serial_getter
        self._workers: list[AsyncWorker] = []
        self._mode = "none"
        self._mode_serial: str | None = None
        self._done: set[str] = set()
        self._skipped: set[str] = set()
        self._steps: list[dict] = []

        layout = QVBoxLayout(self)
        layout.setContentsMargins(32, 28, 32, 28)
        layout.setSpacing(16)
        title = QLabel("Perbaikan HP")
        title.setObjectName("contentTitle")
        desc = QLabel(
            "Panduan bootloop berurutan, pasang ulang OTA resmi, perbaikan per gejala, dan tes aktif. "
            "Pilih device di bagian atas aplikasi dulu."
        )
        desc.setObjectName("muted")
        desc.setWordWrap(True)
        layout.addWidget(title)
        layout.addWidget(desc)

        self.tabs = QTabWidget()
        self.tabs.addTab(self._build_bootloop_tab(), "Panduan Bootloop")
        self.tabs.addTab(self._build_sideload_tab(), "Sideload OTA")
        self.tabs.addTab(self._build_symptom_tab(), "Perbaikan Gejala")
        self.tabs.addTab(self._build_active_tab(), "Tes Aktif")
        layout.addWidget(self.tabs, 1)
        self._refresh_steps()

    # ---- util ----
    def _run(self, fn, on_ok, on_err=None):
        worker = AsyncWorker(fn, self)
        worker.succeeded.connect(on_ok)
        worker.failed.connect(on_err or self._show_error)
        worker.finished.connect(lambda w=worker: self._workers.remove(w) if w in self._workers else None)
        self._workers.append(worker)
        worker.start()

    def _show_error(self, message: str):
        QMessageBox.critical(self, "Gagal", message)

    def _need_serial(self) -> str | None:
        serial = self._serial_getter()
        if not serial:
            QMessageBox.warning(self, "Belum pilih device", "Pilih device yang terhubung dulu.")
        return serial

    @staticmethod
    def _output() -> QPlainTextEdit:
        box = QPlainTextEdit()
        box.setReadOnly(True)
        box.setMinimumHeight(140)
        return box

    # ---- tab bootloop ----
    def _build_bootloop_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        row = QHBoxLayout()
        self.mode_label = QLabel("Mode: belum dideteksi")
        detect = QPushButton("Deteksi mode")
        detect.clicked.connect(self._detect_mode)
        row.addWidget(self.mode_label, 1)
        row.addWidget(detect)
        layout.addLayout(row)

        self.steps_list = QListWidget()
        self.steps_list.currentItemChanged.connect(self._on_step_selected)
        layout.addWidget(self.steps_list, 1)
        self.step_detail = QLabel("Pilih langkah untuk melihat penjelasan.")
        self.step_detail.setWordWrap(True)
        layout.addWidget(self.step_detail)

        buttons = QHBoxLayout()
        done = QPushButton("Tandai selesai")
        done.clicked.connect(lambda: self._mark("done"))
        skip = QPushButton("Lewati langkah")
        skip.clicked.connect(lambda: self._mark("skipped"))
        reset = QPushButton("Ulangi dari awal")
        reset.clicked.connect(self._reset_steps)
        for button in (done, skip, reset):
            buttons.addWidget(button)
        layout.addLayout(buttons)

        reboot_row = QHBoxLayout()
        for target, label in REBOOT_TARGETS.items():
            button = QPushButton(f"Reboot: {label}")
            button.clicked.connect(lambda _=False, t=target: self._reboot(t))
            reboot_row.addWidget(button)
        layout.addLayout(reboot_row)
        return tab

    def _detect_mode(self):
        serial = self._serial_getter()
        self.mode_label.setText("Mode: mendeteksi...")
        self._run(lambda: detect_current_mode(serial), self._on_mode)

    def _on_mode(self, result):
        mode, serial = result
        self._mode, self._mode_serial = mode, serial
        self.mode_label.setText(f"Mode: {MODE_LABEL.get(mode, mode)}" + (f" ({serial})" if serial else ""))
        self._refresh_steps()

    def _refresh_steps(self):
        self._steps = bootloop.next_steps(self._mode, self._done, self._skipped)
        self.steps_list.clear()
        for step in self._steps:
            text = (
                f"{STATE_ICON[step['state']]} {step['title']}  "
                f"({RISK_LABEL.get(step['data_loss'], step['data_loss'])}) - {STATE_LABEL[step['state']]}"
            )
            item = QListWidgetItem(text)
            item.setData(Qt.ItemDataRole.UserRole, step["id"])
            self.steps_list.addItem(item)

    def _selected_step(self) -> dict | None:
        item = self.steps_list.currentItem()
        if item is None:
            return None
        step_id = item.data(Qt.ItemDataRole.UserRole)
        return next((s for s in self._steps if s["id"] == step_id), None)

    def _on_step_selected(self, *_):
        step = self._selected_step()
        if step is None:
            return
        hint = ""
        if step["state"] == "locked":
            hint = "\n\nTerkunci: selesaikan atau lewati dulu langkah aman di atasnya."
        elif step["state"] == "wrong_mode":
            hint = "\n\nPerangkat harus di mode: " + ", ".join(MODE_LABEL.get(m, m) for m in step["modes"] if m != "none")
        self.step_detail.setText(step["detail"] + hint)

    def _mark(self, kind: str):
        step = self._selected_step()
        if step is None:
            QMessageBox.information(self, "Pilih langkah", "Pilih satu langkah dulu.")
            return
        if step["state"] != "ready":
            QMessageBox.warning(self, "Belum bisa", "Hanya langkah berstatus 'siap' yang bisa ditandai.")
            return
        (self._done if kind == "done" else self._skipped).add(step["id"])
        self._refresh_steps()

    def _reset_steps(self):
        self._done.clear()
        self._skipped.clear()
        self._refresh_steps()

    def _reboot(self, target: str):
        serial = self._mode_serial or self._serial_getter()
        if not serial:
            QMessageBox.warning(self, "Belum ada device", "Tekan 'Deteksi mode' atau pilih device dulu.")
            return
        mode = self._mode
        self._run(lambda: reboot_to(serial, target, mode), lambda _out: self._detect_mode_later())

    def _detect_mode_later(self):
        self.mode_label.setText("Mode: perangkat sedang reboot, tekan 'Deteksi mode' beberapa detik lagi.")

    # ---- tab sideload ----
    def _build_sideload_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        self._ota_path = ""
        self.ota_label = QLabel("Belum ada paket OTA dipilih.")
        self.ota_label.setWordWrap(True)
        pick = QPushButton("Pilih paket OTA (.zip)")
        pick.clicked.connect(self._pick_ota)
        self.ota_codename = QLineEdit()
        self.ota_codename.setPlaceholderText("Codename perangkat (opsional, mis. ro.product.device)")
        row = QHBoxLayout()
        validate = QPushButton("Validasi paket")
        validate.clicked.connect(self._validate_ota)
        go = QPushButton("Mulai sideload")
        go.clicked.connect(self._start_sideload)
        to_sideload = QPushButton("Reboot ke Sideload")
        to_sideload.clicked.connect(lambda: self._reboot("sideload"))
        for button in (validate, go, to_sideload):
            row.addWidget(button)
        self.ota_output = self._output()
        for widget in (pick, self.ota_label, self.ota_codename):
            layout.addWidget(widget)
        layout.addLayout(row)
        layout.addWidget(self.ota_output, 1)
        return tab

    def _pick_ota(self):
        path, _ = QFileDialog.getOpenFileName(self, "Pilih paket OTA", "", "Paket OTA (*.zip)")
        if path:
            self._ota_path = path
            self.ota_label.setText(path)

    def _validate_ota(self):
        if not self._ota_path:
            QMessageBox.warning(self, "Belum pilih paket", "Pilih paket OTA dulu.")
            return
        check = validate_ota_package(self._ota_path, self.ota_codename.text().strip() or None)
        lines = ["Paket valid." if check.ok else "Paket DITOLAK:"] + [f"- {p}" for p in check.problems]
        for key in ("pre-device", "pre-build", "post-build", "ota-type"):
            if key in check.metadata:
                lines.append(f"{key}: {check.metadata[key]}")
        self.ota_output.setPlainText("\n".join(lines))

    def _start_sideload(self):
        if not self._ota_path:
            QMessageBox.warning(self, "Belum pilih paket", "Pilih paket OTA dulu.")
            return
        answer = QMessageBox.question(
            self,
            "Konfirmasi sideload",
            "Pasang paket OTA ini ke perangkat yang sedang di mode Sideload?\nJangan cabut kabel selama proses.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        preferred = self._serial_getter()
        path = self._ota_path
        codename = self.ota_codename.text().strip() or None
        self.ota_output.setPlainText("Sideload berjalan... (bisa beberapa menit)")

        def job():
            serial = resolve_sideload_serial(preferred)
            if not serial:
                raise RuntimeError("Tidak ada perangkat di mode sideload. Pilih 'Apply update from ADB' di recovery.")
            return sideload_package(serial, path, codename)

        self._run(job, lambda out: self.ota_output.setPlainText(f"Selesai.\n{out}"), self._sideload_failed)

    def _sideload_failed(self, message: str):
        self.ota_output.setPlainText(f"GAGAL: {message}")

    # ---- tab gejala ----
    def _build_symptom_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        self.symptom_combo = QComboBox()
        for key, profile in SYMPTOMS.items():
            self.symptom_combo.addItem(profile["title"], key)
        run = QPushButton("Jalankan perbaikan")
        run.clicked.connect(self._run_symptom)
        self.symptom_output = self._output()
        layout.addWidget(self.symptom_combo)
        layout.addWidget(run)
        layout.addWidget(self.symptom_output, 1)
        return tab

    def _run_symptom(self):
        serial = self._need_serial()
        if not serial:
            return
        key = self.symptom_combo.currentData()
        self.symptom_output.setPlainText("Mengukur dan menjalankan perbaikan...")
        self._run(
            lambda: run_symptom(serial, key),
            lambda result: self.symptom_output.setPlainText(format_symptom_result(result)),
            lambda message: self.symptom_output.setPlainText(f"GAGAL: {message}"),
        )

    # ---- tab tes aktif ----
    def _build_active_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        actions = [
            ("Getar", lambda s: f"Getar dipicu dengan: {hardware_active.vibrate(s)}\nTanya pelanggan/rasakan: apakah HP bergetar?"),
            ("Kamera foto", lambda s: "Kamera foto dibuka di HP. Cek preview dan ambil foto." + hardware_active.open_camera(s)[:0]),
            ("Kamera video", lambda s: "Kamera video dibuka di HP. Cek preview." + hardware_active.open_camera(s, video=True)[:0]),
            ("Perekam suara", lambda s: "Perekam suara dibuka di HP. Rekam dan putar ulang untuk cek mikrofon." + hardware_active.open_voice_recorder(s)[:0]),
            ("Tes sentuh", lambda s: format_touch(hardware_active.read_touch_points(s))),
            ("Baterai", lambda s: self._format_battery(hardware_active.read_battery_capacity(s))),
        ]
        row = QHBoxLayout()
        for label, fn in actions:
            button = QPushButton(label)
            button.clicked.connect(lambda _=False, f=fn, name=label: self._run_active(name, f))
            row.addWidget(button)
        layout.addLayout(row)
        self.active_output = self._output()
        layout.addWidget(self.active_output, 1)
        return tab

    @staticmethod
    def _format_battery(info: dict) -> str:
        lines = []
        if "level" in info:
            lines.append(f"Level: {info['level']}%")
        if "temperature_c" in info:
            lines.append(f"Suhu: {info['temperature_c']:.1f} C")
        if "health" in info:
            lines.append(f"Status: {info['health']}")
        if "capacity_health_pct" in info:
            lines.append(f"Kapasitas sekarang vs desain: {info['capacity_health_pct']}%")
        else:
            lines.append("Kapasitas asli tidak terbaca di HP ini (sysfs tidak tersedia).")
        return "\n".join(lines)

    def _run_active(self, name: str, fn):
        serial = self._need_serial()
        if not serial:
            return
        extra = "\nSentuh layar HP sekarang..." if name == "Tes sentuh" else ""
        self.active_output.setPlainText(f"{name}: berjalan...{extra}")
        self._run(
            lambda: fn(serial),
            lambda text: self.active_output.setPlainText(str(text)),
            lambda message: self.active_output.setPlainText(f"{name} GAGAL: {message}"),
        )
