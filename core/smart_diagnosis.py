"""Rule-based Smart Diagnosis engine for Android service-center workflows.

The engine is deliberately deterministic and offline: it consumes facts already
collected by Nexa Service Tool and produces explainable findings and safe next
steps. It does not bypass device security or attempt to recover credentials.
"""

from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any


@dataclass(frozen=True)
class Finding:
    code: str
    title: str
    severity: str
    summary: str
    recommendations: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class DiagnosisReport:
    score: int
    severity: str
    findings: tuple[Finding, ...]
    recommendations: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["findings"] = [finding.to_dict() for finding in self.findings]
        return data


def _truthy(value: Any) -> bool:
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on", "failed", "fail", "error"}
    return bool(value)


def diagnose(facts: dict[str, Any]) -> DiagnosisReport:
    """Analyze normalized service facts and return an explainable report.

    Supported signals include connection state, boot state, battery, storage,
    network/baseband/IMEI, hardware checks, and security state. Unknown fields
    are ignored so callers can pass partial device data safely.
    """
    findings: list[Finding] = []

    connected = str(facts.get("connection_state", facts.get("adb_state", ""))).lower()
    if connected in {"offline", "unauthorized"}:
        findings.append(Finding(
            "ADB_UNAVAILABLE", "ADB tidak siap", "high",
            "Perangkat terdeteksi tetapi sesi ADB belum siap.",
            ("Periksa USB debugging dan otorisasi komputer pada perangkat.",
             "Coba kabel/port USB lain dan refresh device list."),
        ))

    boot = str(facts.get("boot_state", facts.get("mode", ""))).lower()
    if "fastboot" in boot or "bootloader" in boot:
        findings.append(Finding(
            "FASTBOOT_MODE", "Perangkat berada di Fastboot/Bootloader", "medium",
            "Android normal belum berjalan; operasi ADB biasa mungkin tidak tersedia.",
            ("Pastikan model dan build sudah diverifikasi sebelum operasi firmware.",
             "Gunakan reboot normal bila tidak sedang melakukan pekerjaan fastboot."),
        ))

    battery = facts.get("battery_percent")
    if isinstance(battery, (int, float)) and battery <= 15:
        findings.append(Finding(
            "LOW_BATTERY", "Baterai sangat rendah", "high",
            f"Level baterai sekitar {battery:.0f}%.",
            ("Isi daya sebelum diagnosis berat, backup, atau operasi firmware.",),
        ))

    temp = facts.get("battery_temp_c")
    if isinstance(temp, (int, float)) and temp >= 45:
        findings.append(Finding(
            "BATTERY_HOT", "Suhu baterai tinggi", "high",
            f"Suhu baterai sekitar {temp:.1f} °C.",
            ("Hentikan pekerjaan berat dan biarkan perangkat mendingin.",
             "Jangan melakukan flashing ketika perangkat mengalami overheating."),
        ))

    storage_free = facts.get("storage_free_percent")
    if isinstance(storage_free, (int, float)) and storage_free < 5:
        findings.append(Finding(
            "STORAGE_CRITICAL", "Penyimpanan hampir penuh", "medium",
            f"Ruang kosong hanya sekitar {storage_free:.1f}%.",
            ("Backup data penting lalu kosongkan ruang sebelum troubleshooting aplikasi/system.",),
        ))

    imei = str(facts.get("imei", "")).strip()
    baseband = str(facts.get("baseband", "")).strip().lower()
    if not imei or imei.lower() in {"unknown", "null", "none", "0"}:
        findings.append(Finding(
            "IMEI_MISSING", "IMEI tidak terbaca", "high",
            "Informasi IMEI tidak tersedia dari sumber yang diberikan.",
            ("Jangan menulis atau mengubah identitas radio secara sembarangan.",
             "Periksa baseband, SIM state, dan log radio untuk diagnosis lebih lanjut."),
        ))
    if baseband in {"unknown", "", "null", "none"}:
        findings.append(Finding(
            "BASEBAND_MISSING", "Baseband tidak terbaca", "high",
            "Versi modem/baseband tidak tersedia.",
            ("Periksa status modem dan log radio sebelum menyimpulkan kerusakan jaringan.",),
        ))

    hardware_failures = facts.get("hardware_failures", [])
    if isinstance(hardware_failures, (list, tuple)) and hardware_failures:
        names = ", ".join(str(item) for item in hardware_failures[:5])
        findings.append(Finding(
            "HARDWARE_FAILURE", "Pemeriksaan hardware menemukan kegagalan", "high",
            f"Komponen/check yang gagal: {names}.",
            ("Ulangi check yang gagal untuk memastikan hasil konsisten.",
             "Bandingkan dengan kondisi fisik dan hasil diagnostics sebelum penggantian komponen."),
        ))

    network = str(facts.get("network_state", "")).lower()
    if network in {"disconnected", "no_service", "no signal", "no_signal"}:
        findings.append(Finding(
            "NETWORK_UNAVAILABLE", "Jaringan seluler tidak tersedia", "medium",
            "State jaringan menunjukkan tidak ada layanan.",
            ("Periksa SIM, airplane mode, radio state, IMEI, dan baseband.",
             "Bandingkan hasil dengan SIM/operator yang diketahui normal."),
        ))

    root = facts.get("root_detected")
    if _truthy(root):
        findings.append(Finding(
            "ROOT_DETECTED", "Root terdeteksi", "medium",
            "Perangkat tampak memiliki modifikasi privileged/root.",
            ("Catat kondisi software sebelum repair dan jangan menganggap hasil diagnostics sebagai kondisi factory." ,),
        ))

    severity_weight = {"high": 25, "medium": 12, "low": 5}
    penalty = sum(severity_weight.get(item.severity, 0) for item in findings)
    score = max(0, min(100, 100 - penalty))
    if any(item.severity == "high" for item in findings):
        severity = "critical"
    elif findings:
        severity = "attention"
    else:
        severity = "healthy"

    recommendations: list[str] = []
    seen: set[str] = set()
    for finding in findings:
        for recommendation in finding.recommendations:
            if recommendation not in seen:
                recommendations.append(recommendation)
                seen.add(recommendation)

    if not findings:
        recommendations.append("Tidak ada anomali dari fakta yang diberikan. Lanjutkan pemeriksaan spesifik sesuai keluhan pelanggan.")

    return DiagnosisReport(score, severity, tuple(findings), tuple(recommendations))
