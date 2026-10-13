"""Build a readable, unsigend PDF report from a validated assessment record."""

from __future__ import annotations

from datetime import datetime, timezone
from html import escape
from io import BytesIO
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Image, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle


INK = colors.HexColor("#20282e")
MUTED = colors.HexColor("#68747c")
LINE = colors.HexColor("#e4e5e1")
ACCENT = colors.HexColor("#315e7b")
AMBER = colors.HexColor("#a86624")
SOFT = colors.HexColor("#f5f4f0")


def _text(value) -> str:
    return escape(str(value if value is not None else ""))


def _paragraph(value, style):
    return Paragraph(_text(value).replace("\n", "<br/>"), style)


def _bullets(values, style):
    return [Paragraph(f"• {_text(value)}", style) for value in values if value]


def _range(value, currency="INR"):
    if not isinstance(value, dict) or not isinstance(value.get("low"), (int, float)) or not isinstance(value.get("high"), (int, float)):
        return "Not provided"
    symbol = "₹" if currency == "INR" else f"{currency} "
    return f"{symbol}{value['low']:,.0f} – {symbol}{value['high']:,.0f}"


def _component(value):
    if not isinstance(value, dict):
        return "Not provided"
    if value.get("status") == "not_applicable":
        return "Not applicable"
    if value.get("status") != "provided":
        return "Not itemized"
    return _range(value.get("amount"), "INR")


def _image(path: Path | None, max_width: float, max_height: float):
    if not path or not path.is_file():
        return Paragraph("Image unavailable", ParagraphStyle("imageUnavailable", fontSize=8, textColor=MUTED))
    try:
        image = Image(str(path))
        ratio = min(max_width / image.imageWidth, max_height / image.imageHeight)
        image.drawWidth = image.imageWidth * ratio
        image.drawHeight = image.imageHeight * ratio
        return image
    except (OSError, ValueError, TypeError):
        return Paragraph("Image unavailable", ParagraphStyle("imageUnavailable", fontSize=8, textColor=MUTED))


def generate_pdf(record: dict, source_path: Path | None = None, annotated_path: Path | None = None) -> bytes:
    """Generate PDF bytes without accepting filesystem paths from HTTP input."""
    buffer = BytesIO()
    document = SimpleDocTemplate(
        buffer, pagesize=A4, rightMargin=16 * mm, leftMargin=16 * mm,
        topMargin=17 * mm, bottomMargin=15 * mm, title="Veyra assessment report",
        author="Veyra",
    )
    styles = getSampleStyleSheet()
    title = ParagraphStyle("title", parent=styles["Title"], fontName="Helvetica-Bold", fontSize=22, leading=26, textColor=INK, spaceAfter=4)
    h1 = ParagraphStyle("h1", parent=styles["Heading1"], fontName="Helvetica-Bold", fontSize=14, leading=18, textColor=INK, spaceBefore=13, spaceAfter=7)
    h2 = ParagraphStyle("h2", parent=styles["Heading2"], fontName="Helvetica-Bold", fontSize=10, leading=13, textColor=INK, spaceBefore=7, spaceAfter=4)
    body = ParagraphStyle("body", parent=styles["BodyText"], fontName="Helvetica", fontSize=8.8, leading=13, textColor=INK, spaceAfter=4)
    small = ParagraphStyle("small", parent=body, fontSize=7.5, leading=10.5, textColor=MUTED)
    label = ParagraphStyle("label", parent=small, fontName="Helvetica-Bold", textColor=MUTED, uppercase=True)
    warning = ParagraphStyle("warning", parent=body, textColor=AMBER, backColor=colors.HexColor("#f8eee0"), borderColor=colors.HexColor("#ead6b8"), borderWidth=0.5, borderPadding=7)

    stages = record.get("detection_report", {})
    severity = record.get("severity_assessment", {})
    costs = record.get("repair_cost_estimate", {})
    gemini = record.get("gemini_assessment", {})
    ai = gemini.get("assessment") if isinstance(gemini, dict) else None
    summary_result = record.get("ai_summary", {})
    summary = summary_result.get("summary") if isinstance(summary_result, dict) and summary_result.get("status") == "completed" else None
    cost_result = record.get("ai_cost_estimate", {})
    findings = severity.get("detections", []) if isinstance(severity, dict) else []
    story = []
    story.append(Paragraph("VEYRA", ParagraphStyle("brand", parent=small, fontName="Helvetica-Bold", fontSize=9, textColor=ACCENT, tracking=1.5)))
    story.append(Paragraph("Vehicle damage assessment report", title))
    story.append(_paragraph(f"Assessment ID: {record.get('assessment_id', 'Unavailable')}  |  Generated: {datetime.now(timezone.utc).isoformat()}", small))
    story.append(Spacer(1, 3 * mm))
    story.append(_paragraph("Preliminary image-based assessment. This report is not a professional inspection, guaranteed quotation, insurance approval, legal certification, or roadworthiness decision.", warning))

    story.append(Paragraph("1. Visual evidence", h1))
    evidence_table = Table([[
        _image(source_path, 82 * mm, 55 * mm), _image(annotated_path, 82 * mm, 55 * mm)
    ], [
        _paragraph("Uploaded source image", small), _paragraph("Detector-generated annotated preview", small)
    ]], colWidths=[86 * mm, 86 * mm])
    evidence_table.setStyle(TableStyle([
        ("BOX", (0, 0), (-1, -1), 0.5, LINE), ("INNERGRID", (0, 0), (-1, -1), 0.5, LINE),
        ("BACKGROUND", (0, 0), (-1, -1), SOFT), ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 6), ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 6), ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))
    story.append(evidence_table)
    story.append(_paragraph("The annotated preview is generated by the existing detector. Boxes, confidence and masks remain original detector evidence; the preview does not establish a vehicle component or hidden damage.", small))

    story.append(Paragraph("2. Detected findings and provisional severity", h1))
    rows = [[_paragraph("Finding", label), _paragraph("Confidence", label), _paragraph("Severity", label), _paragraph("Review", label)]]
    for finding in findings:
        evidence = finding.get("original_evidence", {})
        rows.append([
            _paragraph(f"{evidence.get('detection_id', '—')} · {evidence.get('class_name', 'Unclassified')}", body),
            _paragraph(f"{float(evidence.get('confidence')) * 100:.0f}%" if isinstance(evidence.get("confidence"), (int, float)) else "Unavailable", body),
            _paragraph(str(finding.get("preliminary_severity", "undetermined")).title(), body),
            _paragraph("Required" if finding.get("human_review_required") else "Not flagged", body),
        ])
    if len(rows) == 1:
        rows.append([_paragraph("No findings returned; this does not establish no damage.", body), "", "", ""])
    table = Table(rows, colWidths=[70 * mm, 30 * mm, 35 * mm, 40 * mm], repeatRows=1)
    table.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), SOFT), ("GRID", (0, 0), (-1, -1), 0.35, LINE), ("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 6), ("RIGHTPADDING", (0, 0), (-1, -1), 6), ("TOPPADDING", (0, 0), (-1, -1), 5), ("BOTTOMPADDING", (0, 0), (-1, -1), 5)]))
    story.append(table)
    for finding in findings:
        evidence = finding.get("original_evidence", {})
        story.append(Paragraph(f"Finding {evidence.get('detection_id', '—')} — {_text(evidence.get('class_name', 'Unclassified'))}", h2))
        story.extend(_bullets(finding.get("severity_reasons", []), body))
        if finding.get("human_review_required"):
            story.extend(_bullets(finding.get("human_review_reasons", []), small))

    story.append(Paragraph("3. Executive and technical summary", h1))
    if isinstance(summary, dict):
        story.append(_paragraph(summary.get("summary"), body))
        story.append(Paragraph("Technical glossary", h2))
        for entry in summary.get("technical_glossary", []):
            story.append(_paragraph(f"{entry.get('term')}: {entry.get('explanation')}", body))
    elif isinstance(summary_result, dict) and summary_result:
        story.append(_paragraph(f"AI summary request did not complete: {summary_result.get('message', 'Retry the explicit summary action.')}", body))
        story.append(_paragraph("Original detector and provisional severity results remain available in this report.", small))
    else:
        story.append(_paragraph("AI-generated summary: not completed. Use Generate AI Summary from the report to add this section.", body))
        story.append(_paragraph("The original detector and provisional severity reports remain the authoritative application outputs available in this report.", small))

    story.append(Paragraph("4. Indicative repair cost", h1))
    if isinstance(cost_result, dict) and cost_result.get("status") == "completed":
        story.append(_paragraph(f"Pricing status: {cost_result.get('pricing_status', 'estimate_unavailable')}. AI-generated indicative INR estimates, not verified market pricing or workshop quotes.", warning))
        overall_range = cost_result.get("vehicle_total") or cost_result.get("partial_subtotal")
        story.append(_paragraph(f"{cost_result.get('total_status', 'estimate_unavailable').replace('_', ' ').title()}: {_range(overall_range, 'INR')}. {cost_result.get('total_reason', '')}", body))
        breakdown = cost_result.get("cost_breakdown", {})
        if breakdown:
            story.append(_paragraph(
                "Itemized assessment — parts: " + _component(breakdown.get("parts"))
                + "; labor: " + _component(breakdown.get("labor"))
                + "; paint/materials: " + _component(breakdown.get("paint_materials"))
                + "; other charges: " + _component(breakdown.get("other_charges"))
                + "; taxes excluded unless verified.", body,
            ))
        estimate_rows = [[_paragraph("Repair scope", label), _paragraph("Range", label), _paragraph("Basis / review", label)]]
        for estimate in cost_result.get("repair_groups", []):
            range_text = _range(estimate.get("estimate_range"), "INR") if estimate.get("estimate_range") else f"Unavailable - {estimate.get('unavailable_reason') or 'additional information required'}"
            estimate_rows.append([
                _paragraph(f"{estimate.get('scope_summary')} (findings {', '.join(str(value) for value in estimate.get('finding_ids', []))})", body),
                _paragraph(range_text, body),
                _paragraph(f"Parts: {_component(estimate.get('parts'))}; labor: {_component(estimate.get('labor'))}; paint/materials: {_component(estimate.get('paint_materials'))}; other: {_component(estimate.get('other_charges'))}. Observed: {estimate.get('observed_support')} Repair hypothesis: {estimate.get('possible_repair_approach')} Basis: {estimate.get('pricing_basis')}", small),
            ])
        if not cost_result.get("repair_groups"):
            for estimate in cost_result.get("findings", []):
                estimate_rows.append([
                    _paragraph(f"Legacy finding {estimate.get('finding_id')} - {estimate.get('damage_category')}", body),
                    _paragraph(_range(estimate.get("estimate_range"), "INR"), body),
                    _paragraph(f"Repair hypothesis: {estimate.get('possible_repair_approach')} Basis: {estimate.get('pricing_basis')}", small),
                ])
        cost_table = Table(estimate_rows, colWidths=[45 * mm, 45 * mm, 85 * mm], repeatRows=1)
        cost_table.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), SOFT), ("GRID", (0, 0), (-1, -1), 0.35, LINE), ("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 6), ("RIGHTPADDING", (0, 0), (-1, -1), 6), ("TOPPADDING", (0, 0), (-1, -1), 5), ("BOTTOMPADDING", (0, 0), (-1, -1), 5)]))
        story.append(cost_table)
        story.extend(_bullets(cost_result.get("assumptions", []), small))
        story.append(_paragraph("Unknown components remain missing, not zero. Taxes are excluded unless supportable. Professional inspection is required before repair decisions.", small))
    elif isinstance(cost_result, dict) and cost_result:
        story.append(_paragraph(f"Repair-cost request did not complete: {cost_result.get('message', 'Retry the explicit cost request.')}", body))
    else:
        story.append(_paragraph("Repair-cost estimate: not completed. No Gemini cost request has been made for this assessment. The existing USD rate card is illustrative demo configuration, not market pricing.", body))

    story.append(Paragraph("5. Indian insurance guidance", h1))
    insurance = summary.get("insurance_guidance") if isinstance(summary, dict) else (ai.get("insurance_guidance") if isinstance(ai, dict) else gemini.get("fallback_insurance_guidance"))
    if isinstance(insurance, dict):
        story.append(_paragraph(insurance.get("summary"), body))
        story.append(_paragraph(insurance.get("general_coverage_context"), body))
        if isinstance(context := record.get("assessment_context"), dict) and context.get("deductible_inr") is not None:
            story.append(_paragraph(f"User-provided deductible/excess context: ₹{float(context['deductible_inr']):,.0f}. This is not an insurer-verified deductible and no payout or out-of-pocket amount is calculated.", small))
        for item in insurance.get("finding_guidance", []):
            story.append(_paragraph(f"Finding {item.get('finding_id')}: {item.get('status')} — {item.get('potential_coverage_category')}", body))
            story.extend(_bullets(item.get("conditions", []) + item.get("policy_questions", []), small))
        story.append(_paragraph(insurance.get("disclaimer"), warning))
        for source in insurance.get("source_references", []):
            story.append(_paragraph(f"Source: {source.get('title')} — {source.get('url')}. {source.get('note')}", small))

    if isinstance(summary, dict):
        story.append(Paragraph("6. Recommended next steps and limitations", h1))
        story.extend(_bullets(summary.get("recommended_next_steps", []), body))
        story.append(Paragraph("Limitations", h2))
        story.extend(_bullets(summary.get("limitations", []), small))

    story.append(Paragraph("7. Report metadata", h1))
    context = record.get("assessment_context", {})
    metadata = [
        [_paragraph("Source image", label), _paragraph(record.get("source_image", "Unavailable"), body)],
        [_paragraph("Image dimensions", label), _paragraph(f"{stages.get('image_width', '—')} × {stages.get('image_height', '—')} px", body)],
        [_paragraph("Model", label), _paragraph(stages.get("model_name", "Unavailable"), body)],
        [_paragraph("City / vehicle context", label), _paragraph(" · ".join(str(context.get(k)) for k in ("city_or_region", "vehicle_make", "vehicle_model", "vehicle_year") if context.get(k)) or "Not supplied", body)],
    ]
    metadata_table = Table(metadata, colWidths=[48 * mm, 127 * mm])
    metadata_table.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 0.35, LINE), ("VALIGN", (0, 0), (-1, -1), "TOP"), ("BACKGROUND", (0, 0), (0, -1), SOFT), ("LEFTPADDING", (0, 0), (-1, -1), 6), ("RIGHTPADDING", (0, 0), (-1, -1), 6), ("TOPPADDING", (0, 0), (-1, -1), 5), ("BOTTOMPADDING", (0, 0), (-1, -1), 5)]))
    story.append(metadata_table)
    story.append(Spacer(1, 4 * mm))
    story.append(_paragraph("Veyra is an image-based decision-support tool. Human review is required where flagged. The report does not confirm hidden damage, exact components, necessary repairs, claim eligibility, payout, safety or roadworthiness.", warning))

    def footer(canvas, _doc):
        canvas.saveState()
        canvas.setStrokeColor(LINE)
        canvas.line(16 * mm, 10 * mm, A4[0] - 16 * mm, 10 * mm)
        canvas.setFont("Helvetica", 7)
        canvas.setFillColor(MUTED)
        canvas.drawString(16 * mm, 6 * mm, "VEYRA · Preliminary assessment")
        canvas.drawRightString(A4[0] - 16 * mm, 6 * mm, f"Page {canvas.getPageNumber()}")
        canvas.restoreState()

    document.build(story, onFirstPage=footer, onLaterPages=footer)
    return buffer.getvalue()
