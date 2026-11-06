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
    """Pesan default berdasarkan status case saat ini - satu-satunya
    sumber template pesan status, dipakai baik oleh fitur 'Notifikasi WA'
    (buka WhatsApp langsung) maupun 'Respons ke Customer' (copy manual).
    Sebelumnya kedua fitur ini punya template terpisah yang gampang
    ketinggalan sinkron kalau salah satu diedit tapi yang lain tidak."""
    name = case.customer_name or "Bapak/Ibu"
    device_label = f"{case.manufacturer} {case.model}".strip() or "device Anda"
    ref = f"(No. Servis: {case.case_number})"

    cost_line = ""
    if case.estimated_cost:
        cost_str = f"Rp{case.estimated_cost:,.0f}".replace(",", ".")
        cost_line = f" Estimasi biaya: {cost_str}."

    total_line = ""
    if case.estimated_cost:
        total_str = f"Rp{case.estimated_cost:,.0f}".replace(",", ".")
        total_line = f" Total biaya: {total_str}."

    templates = {
        "Received": (
            f"Halo {name}, {device_label} Anda {ref} sudah kami terima dan "
            f"masuk antrian pengecekan. Kami akan kabari lagi setelah "
            f"diagnosa awal selesai. Terima kasih."
        ),
        "Diagnosing": (
            f"Halo {name}, {device_label} Anda {ref} sedang dalam proses "
            f"diagnosa oleh teknisi kami. Estimasi hasil diagnosa akan kami "
            f"informasikan segera."
        ),
        "Repairing": (
            f"Halo {name}, {device_label} Anda {ref} sedang dalam proses "
            f"perbaikan.{cost_line} Kami akan kabari begitu selesai."
        ),
        "Testing": (
            f"Halo {name}, perbaikan {device_label} Anda {ref} sudah "
            f"selesai dan sedang tahap pengujian akhir sebelum diserahkan "
            f"kembali."
        ),
        "Completed": (
            f"Halo {name}, {device_label} Anda {ref} sudah SELESAI "
            f"diperbaiki dan siap diambil.{total_line} Ditunggu "
            f"kedatangannya, terima kasih!"
        ),
        "Cancelled": (
            f"Halo {name}, servis {device_label} Anda {ref} telah "
            f"dibatalkan. Silakan hubungi kami jika ada pertanyaan."
        ),
    }

    message = templates.get(
        case.status,
        f"Halo {name}, update untuk servis {device_label} {ref}: {case.status}.",
    )

    if case.status not in ("Completed", "Cancelled") and case.estimated_completion:
        message += f" Estimasi selesai: {case.estimated_completion}."

    return message


def build_whatsapp_link(phone: str, message: str) -> str:
    normalized = normalize_phone_number(phone)

    if not normalized:
        raise ValueError("Nomor HP pelanggan kosong/tidak valid.")

    return f"https://wa.me/{normalized}?text={quote(message)}"
