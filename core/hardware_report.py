"""Service-center reporting helpers for hardware diagnostics.

This module is deliberately UI-agnostic so the same report data can be used by
Qt, CLI, or future automation without coupling the diagnostic engine to widgets.
"""

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle

from .hardware_test import HardwareTestReport


@dataclass(frozen=True)
class HardwareSnapshot:
    """Immutable snapshot suitable for before/after service comparison."""

    serial: str
    captured_at: str
    score: int
    passed: int
    warnings: int
    failed: int
    results: tuple[tuple[str, str, str, str], ...]


def snapshot_report(report: HardwareTestReport) -> HardwareSnapshot:
    return HardwareSnapshot(
        serial=report.serial,
        captured_at=datetime.now().isoformat(timespec="seconds"),
        score=report.score,
        passed=report.passed,
        warnings=report.warnings,
        failed=report.failed,
        results=tuple(
            (item.key, item.name, item.status, item.value)
            for item in report.results
        ),
    )


def compare_snapshots(
    before: HardwareSnapshot,
    after: HardwareSnapshot,
) -> list[dict[str, str]]:
    """Return only changed test statuses/values between two snapshots."""
    before_map = {row[0]: row for row in before.results}
    after_map = {row[0]: row for row in after.results}
    changes: list[dict[str, str]] = []

    for key, after_row in after_map.items():
        before_row = before_map.get(key)
        if before_row is None:
            changes.append({
                "key": key,
                "name": after_row[1],
                "before": "Not tested",
                "after": f"{after_row[2]} - {after_row[3]}",
            })
            continue

        before_text = f"{before_row[2]} - {before_row[3]}"
        after_text = f"{after_row[2]} - {after_row[3]}"
        if before_text != after_text:
            changes.append({
                "key": key,
                "name": after_row[1],
                "before": before_text,
                "after": after_text,
            })

    return changes


def generate_hardware_report(
    output_path: Path,
    snapshot: HardwareSnapshot,
    *,
    before: HardwareSnapshot | None = None,
    technician_note: str = "",
) -> Path:
    """Generate a standalone hardware/service-center PDF report."""
    output_path.parent.mkdir(parents=True, exist_ok=True)

    doc = SimpleDocTemplate(
        str(output_path),
        pagesize=A4,
        topMargin=18 * mm,
        bottomMargin=18 * mm,
        leftMargin=18 * mm,
        rightMargin=18 * mm,
    )
    styles = getSampleStyleSheet()
    title = ParagraphStyle("HardwareTitle", parent=styles["Title"], fontSize=19, spaceAfter=4)
    muted = ParagraphStyle("HardwareMuted", parent=styles["Normal"], fontSize=9, textColor=colors.grey)
    section = ParagraphStyle("HardwareSection", parent=styles["Heading2"], fontSize=12, spaceBefore=12, spaceAfter=7)

    elements = [
        Paragraph("Nexa Service Tool - Hardware Test Report", title),
        Paragraph(
            f"Serial: {snapshot.serial} &nbsp; | &nbsp; Captured: {snapshot.captured_at}",
            muted,
        ),
        Spacer(1, 5 * mm),
        Paragraph("Summary", section),
    ]

    summary = [
        ["Health Score", f"{snapshot.score}/100"],
        ["PASS", str(snapshot.passed)],
        ["WARN", str(snapshot.warnings)],
        ["FAIL", str(snapshot.failed)],
    ]
    table = Table(summary, colWidths=[55 * mm, 110 * mm])
    table.setStyle(TableStyle([
        ("FONTSIZE", (0, 0), (-1, -1), 9.5),
        ("TEXTCOLOR", (0, 0), (0, -1), colors.grey),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("LINEBELOW", (0, 0), (-1, -1), 0.5, colors.HexColor("#e0e0e0")),
    ]))
    elements.append(table)

    elements.append(Paragraph("Hardware Checks", section))
    rows = [["Component", "Status", "Value"]]
    for key, name, status, value in snapshot.results:
        rows.append([name, status, value])
    checks = Table(rows, colWidths=[65 * mm, 30 * mm, 70 * mm], repeatRows=1)
    checks.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#eeeeee")),
        ("FONTSIZE", (0, 0), (-1, -1), 8.5),
        ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#dddddd")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
    ]))
    elements.append(checks)

    if before is not None:
        elements.append(Paragraph("Before / After", section))
        changes = compare_snapshots(before, snapshot)
        if changes:
            rows = [["Component", "Before", "After"]]
            rows.extend([[item["name"], item["before"], item["after"]] for item in changes])
        else:
            rows = [["Result", "No changes detected", "No changes detected"]]
        comparison = Table(rows, colWidths=[50 * mm, 57.5 * mm, 57.5 * mm], repeatRows=1)
        comparison.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#eeeeee")),
            ("FONTSIZE", (0, 0), (-1, -1), 8.5),
            ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#dddddd")),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ]))
        elements.append(comparison)

    if technician_note.strip():
        elements.append(Paragraph("Technician Note", section))
        elements.append(Paragraph(technician_note.strip(), styles["Normal"]))

    elements.append(Spacer(1, 8 * mm))
    elements.append(Paragraph("Generated automatically by Nexa Service Tool.", muted))
    doc.build(elements)
    return output_path
