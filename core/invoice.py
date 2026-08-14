"""Generate dokumen cetak untuk Service Cases: nota/invoice servis untuk
pelanggan, dan label kecil untuk ditempel di device yang sedang antri.

Kenapa ini penting untuk teknisi service center: sebelumnya tidak ada
cara mencetak bukti transaksi resmi untuk pelanggan (cuma ada laporan
diagnostics teknis di report.py, bukan nota dengan info biaya/pembayaran),
dan tidak ada cara menandai fisik device yang sedang antri banyak supaya
tidak tertukar.
"""
from datetime import datetime
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import (
    SimpleDocTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
)

from .service_cases import ServiceCase


def _rupiah(value: float) -> str:
    return f"Rp {value:,.0f}".replace(",", ".")


def generate_case_invoice(case: ServiceCase, output_path: Path) -> Path:
    """Nota servis untuk diberikan ke pelanggan - beda dari
    generate_service_report() di report.py yang isinya laporan
    diagnostics teknis, ini fokus ke info transaksi (case number, nama
    pelanggan, keluhan, biaya, status pembayaran) yang bisa dijadikan
    bukti resmi."""
    output_path.parent.mkdir(parents=True, exist_ok=True)

    doc = SimpleDocTemplate(
        str(output_path),
        pagesize=A4,
        topMargin=20 * mm,
        bottomMargin=20 * mm,
        leftMargin=20 * mm,
        rightMargin=20 * mm,
    )

    styles = getSampleStyleSheet()

    title_style = ParagraphStyle(
        "InvoiceTitle", parent=styles["Title"], fontSize=18, spaceAfter=2,
    )
    subtitle_style = ParagraphStyle(
        "InvoiceSubtitle", parent=styles["Normal"], fontSize=10,
        textColor=colors.grey, spaceAfter=16,
    )
    section_style = ParagraphStyle(
        "InvoiceSection", parent=styles["Heading2"], fontSize=12,
        spaceBefore=12, spaceAfter=6, textColor=colors.HexColor("#1a1c22"),
    )
    body_style = styles["Normal"]

    elements = []

    elements.append(Paragraph("NOTA SERVIS", title_style))
    elements.append(Paragraph(f"Nexa Service Center &nbsp;|&nbsp; No. {case.case_number}", subtitle_style))

    header_data = [
        ["Tanggal Masuk", case.created_at, "Status", case.status],
        ["Nama Pelanggan", case.customer_name, "No. HP", case.customer_phone or "-"],
    ]
    header_table = Table(header_data, colWidths=[35 * mm, 55 * mm, 30 * mm, 45 * mm])
    header_table.setStyle(TableStyle([
        ("FONTSIZE", (0, 0), (-1, -1), 9.5),
        ("TEXTCOLOR", (0, 0), (0, -1), colors.grey),
        ("TEXTCOLOR", (2, 0), (2, -1), colors.grey),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("LINEBELOW", (0, 0), (-1, -1), 0.5, colors.HexColor("#e0e0e0")),
    ]))
    elements.append(header_table)

    elements.append(Paragraph("Detail Device", section_style))
    device_data = [
        ["Manufacturer / Model", f"{case.manufacturer} {case.model}".strip() or "-"],
        ["Serial / IMEI", f"{case.device_serial or '-'} / {case.imei or '-'}"],
        ["Keluhan", case.complaint],
        ["Teknisi", case.technician or "-"],
    ]
    device_table = Table(device_data, colWidths=[45 * mm, 120 * mm])
    device_table.setStyle(TableStyle([
        ("FONTSIZE", (0, 0), (-1, -1), 9.5),
        ("TEXTCOLOR", (0, 0), (0, -1), colors.grey),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("LINEBELOW", (0, 0), (-1, -1), 0.5, colors.HexColor("#e0e0e0")),
    ]))
    elements.append(device_table)

    elements.append(Paragraph("Rincian Biaya", section_style))

    sisa = max(0.0, case.estimated_cost - case.paid_amount)
    cost_data = [
        ["Estimasi Biaya", _rupiah(case.estimated_cost)],
        ["Status Pembayaran", case.payment_status],
        ["Sudah Dibayar", _rupiah(case.paid_amount)],
        ["Sisa Tagihan", _rupiah(sisa)],
    ]
    cost_table = Table(cost_data, colWidths=[45 * mm, 120 * mm])
    cost_table.setStyle(TableStyle([
        ("FONTSIZE", (0, 0), (-1, -1), 9.5),
        ("TEXTCOLOR", (0, 0), (0, -1), colors.grey),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("LINEBELOW", (0, 0), (-1, -1), 0.5, colors.HexColor("#e0e0e0")),
        ("FONTNAME", (0, 3), (-1, 3), "Helvetica-Bold"),
    ]))
    elements.append(cost_table)

    if case.estimated_completion:
        elements.append(Paragraph("Estimasi Selesai", section_style))
        elements.append(Paragraph(case.estimated_completion, body_style))

    elements.append(Spacer(1, 20 * mm))

    sig_data = [["", ""], ["", ""], ["Teknisi", "Pelanggan"]]
    sig_table = Table(sig_data, colWidths=[80 * mm, 80 * mm], rowHeights=[18 * mm, 0.3 * mm, 6 * mm])
    sig_table.setStyle(TableStyle([
        ("LINEABOVE", (0, 2), (0, 2), 0.5, colors.grey),
        ("LINEABOVE", (1, 2), (1, 2), 0.5, colors.grey),
        ("ALIGN", (0, 2), (-1, 2), "CENTER"),
        ("FONTSIZE", (0, 0), (-1, -1), 9.5),
        ("TEXTCOLOR", (0, 2), (-1, 2), colors.grey),
    ]))
    elements.append(sig_table)

    elements.append(Spacer(1, 8 * mm))
    elements.append(Paragraph(
        f"Dicetak {datetime.now().strftime('%d %B %Y, %H:%M')} - Nexa Service Tool.",
        subtitle_style,
    ))

    doc.build(elements)
    return output_path


def generate_case_label(case: ServiceCase, output_path: Path) -> Path:
    """Label kecil untuk ditempel/digantung di device fisik yang sedang
    antri servis - supaya tidak tertukar saat banyak HP masuk bersamaan.
    Ukuran kertas kecil (mirip label/struk), bukan A4 penuh."""
    output_path.parent.mkdir(parents=True, exist_ok=True)

    label_size = (80 * mm, 50 * mm)

    doc = SimpleDocTemplate(
        str(output_path),
        pagesize=label_size,
        topMargin=4 * mm,
        bottomMargin=4 * mm,
        leftMargin=5 * mm,
        rightMargin=5 * mm,
    )

    styles = getSampleStyleSheet()

    case_number_style = ParagraphStyle(
        "LabelCaseNumber", parent=styles["Title"], fontSize=16,
        alignment=1, spaceAfter=4,
    )
    name_style = ParagraphStyle(
        "LabelName", parent=styles["Normal"], fontSize=13,
        alignment=1, spaceAfter=2, fontName="Helvetica-Bold",
    )
    detail_style = ParagraphStyle(
        "LabelDetail", parent=styles["Normal"], fontSize=8.5,
        alignment=1, textColor=colors.grey,
    )

    elements = [
        Paragraph(case.case_number, case_number_style),
        Paragraph(case.customer_name, name_style),
        Paragraph(f"{case.manufacturer} {case.model}".strip() or "-", detail_style),
        Paragraph(case.complaint[:60], detail_style),
        Spacer(1, 2 * mm),
        Paragraph(case.created_at, detail_style),
    ]

    doc.build(elements)
    return output_path
