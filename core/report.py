from datetime import datetime
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import (
    SimpleDocTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
)

from .device import DeviceInfo
from .diagnostics import DiagnosticResult, health_score_label


def generate_service_report(
    output_path: Path,
    device: DeviceInfo,
    diag: DiagnosticResult,
    health_score: int,
    recommendations: list[str],
    technician_note: str = "",
) -> Path:
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
        "ReportTitle",
        parent=styles["Title"],
        fontSize=20,
        spaceAfter=4,
    )

    subtitle_style = ParagraphStyle(
        "ReportSubtitle",
        parent=styles["Normal"],
        fontSize=10,
        textColor=colors.grey,
        spaceAfter=18,
    )

    section_style = ParagraphStyle(
        "SectionHeader",
        parent=styles["Heading2"],
        fontSize=13,
        spaceBefore=14,
        spaceAfter=8,
        textColor=colors.HexColor("#1a1c22"),
    )

    body_style = styles["Normal"]

    elements = []

    elements.append(Paragraph("Nexa Service Tool - Laporan Servis", title_style))
    elements.append(
        Paragraph(
            f"Dibuat pada {datetime.now().strftime('%d %B %Y, %H:%M')} WIB",
            subtitle_style,
        )
    )

    # --- Info Device ---
    elements.append(Paragraph("Informasi Device", section_style))

    device_data = [
        ["Manufacturer", device.manufacturer],
        ["Model", device.model],
        ["Product", device.product],
        ["Device", device.device],
        ["Android Version", device.android_version],
        ["Build ID", device.build_id],
        ["Serial Number", device.serial],
    ]

    device_table = Table(device_data, colWidths=[55 * mm, 110 * mm])
    device_table.setStyle(
        TableStyle(
            [
                ("FONTSIZE", (0, 0), (-1, -1), 9.5),
                ("TEXTCOLOR", (0, 0), (0, -1), colors.grey),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("LINEBELOW", (0, 0), (-1, -1), 0.5, colors.HexColor("#e0e0e0")),
            ]
        )
    )
    elements.append(device_table)

    # --- Diagnostics ---
    elements.append(Paragraph("Hasil Diagnostics", section_style))

    diag_data = [
        ["Battery Level", diag.battery_level],
        ["Battery Status", diag.battery_status],
        ["Battery Health", diag.battery_health],
        ["Storage", diag.storage],
        ["Screen State", diag.screen_state],
        ["USB Debugging", diag.usb_debugging],
    ]

    diag_table = Table(diag_data, colWidths=[55 * mm, 110 * mm])
    diag_table.setStyle(
        TableStyle(
            [
                ("FONTSIZE", (0, 0), (-1, -1), 9.5),
                ("TEXTCOLOR", (0, 0), (0, -1), colors.grey),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("LINEBELOW", (0, 0), (-1, -1), 0.5, colors.HexColor("#e0e0e0")),
            ]
        )
    )
    elements.append(diag_table)

    # --- Health Score ---
    elements.append(Paragraph("Skor Kesehatan Device", section_style))

    score_color = colors.HexColor("#2e7d32")
    if health_score < 50:
        score_color = colors.HexColor("#c62828")
    elif health_score < 85:
        score_color = colors.HexColor("#ef6c00")

    score_style = ParagraphStyle(
        "Score",
        parent=styles["Normal"],
        fontSize=16,
        textColor=score_color,
        spaceAfter=10,
    )

    elements.append(
        Paragraph(
            f"{health_score}/100 &nbsp;-&nbsp; {health_score_label(health_score)}",
            score_style,
        )
    )

    for rec in recommendations:
        elements.append(Paragraph(f"&bull; {rec}", body_style))

    # --- Catatan Teknisi ---
    if technician_note.strip():
        elements.append(Paragraph("Catatan Teknisi", section_style))
        elements.append(Paragraph(technician_note.strip(), body_style))

    elements.append(Spacer(1, 20 * mm))
    elements.append(
        Paragraph(
            "Laporan ini dibuat otomatis oleh Nexa Service Tool.",
            subtitle_style,
        )
    )

    doc.build(elements)
    return output_path
