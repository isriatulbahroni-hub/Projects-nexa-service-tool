"""Bantuan notifikasi WhatsApp ke pelanggan lewat link "click to chat"
(wa.me). Ini BUKAN pengiriman otomatis (tidak ada integrasi WhatsApp API/
Business API yang butuh kredensial) - link ini membuka WhatsApp Desktop/
Web dengan pesan yang sudah terisi, teknisi tinggal klik "Send" secara
manual. Ini pendekatan paling aman dan realistis tanpa perlu setup
akun bisnis/API key apapun.
"""
from urllib.parse import quote

from .service_cases import ServiceCase


def normalize_phone_number(phone: str) -> str:
    """Normalisasi nomor HP Indonesia ke format internasional (62xxx)
    yang dibutuhkan wa.me - menerima format umum: 08xx, +62xx, 62xx."""
    digits = "".join(ch for ch in phone if ch.isdigit())

    if not digits:
        return ""

    if digits.startswith("0"):
        digits = "62" + digits[1:]
    elif not digits.startswith("62"):
        digits = "62" + digits

    return digits


def build_case_status_message(case: ServiceCase) -> str:
    """Pesan default berdasarkan status case saat ini - teknisi bisa edit
    dulu sebelum kirim."""
    greeting = f"Halo {case.customer_name}, ini dari Nexa Service Center."

    if case.status == "Completed":
        body = (
            f"HP {case.manufacturer} {case.model} Anda (No. Servis "
            f"{case.case_number}) sudah SELESAI diservis dan siap diambil. "
            f"Terima kasih sudah menunggu."
        )
    elif case.status == "Cancelled":
        body = (
            f"Servis untuk HP Anda (No. Servis {case.case_number}) telah "
            f"dibatalkan. Silakan hubungi kami untuk info lebih lanjut."
        )
    else:
        body = (
            f"Update status servis HP {case.manufacturer} {case.model} Anda "
            f"(No. Servis {case.case_number}): saat ini dalam tahap "
            f"'{case.status}'."
        )

    if case.status not in ("Completed", "Cancelled") and case.estimated_completion:
        body += f" Estimasi selesai: {case.estimated_completion}."

    return f"{greeting}\n\n{body}"


def build_whatsapp_link(phone: str, message: str) -> str:
    normalized = normalize_phone_number(phone)

    if not normalized:
        raise ValueError("Nomor HP pelanggan kosong/tidak valid.")

    return f"https://wa.me/{normalized}?text={quote(message)}"
