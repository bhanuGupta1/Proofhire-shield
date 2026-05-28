"""
Trust Report PDF generator using reportlab.
Produces a timestamped, single-page audit summary.
"""
from __future__ import annotations
import io
from datetime import datetime, timezone
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors
from reportlab.lib.units import cm
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from models import ScanResult

_RISK_COLOUR = {
    "GREEN": colors.HexColor("#16a34a"),
    "ORANGE": colors.HexColor("#ea580c"),
    "RED": colors.HexColor("#dc2626"),
}

_RISK_LABEL = {
    "GREEN": "Low Risk — Safe to use in AI workflow",
    "ORANGE": "Elevated Risk — Review flagged items before use",
    "RED": "High Risk — Do not use in AI workflow without manual review",
}


def build_trust_report(result: ScanResult) -> bytes:
    """Return PDF bytes for the Trust Report."""
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=A4,
        leftMargin=2*cm, rightMargin=2*cm,
        topMargin=2*cm, bottomMargin=2*cm,
    )
    styles = getSampleStyleSheet()
    h1 = ParagraphStyle("H1", parent=styles["Heading1"], fontSize=16, spaceAfter=6)
    h2 = ParagraphStyle("H2", parent=styles["Heading2"], fontSize=12, spaceAfter=4)
    body = ParagraphStyle("Body", parent=styles["Normal"], fontSize=10, spaceAfter=4)
    small = ParagraphStyle("Small", parent=styles["Normal"], fontSize=8,
                           textColor=colors.grey, spaceAfter=4)
    risk_colour = _RISK_COLOUR[result.risk_level]

    story = []

    # Header
    story.append(Paragraph("ProofHire Shield — Trust Report", h1))
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    story.append(Paragraph(f"Generated: {ts}  |  File: {result.filename}", small))
    story.append(Spacer(1, 0.3*cm))

    # Risk verdict
    verdict_style = ParagraphStyle(
        "Verdict", parent=styles["Normal"], fontSize=13, textColor=risk_colour,
        spaceAfter=8, leading=18,
    )
    story.append(Paragraph(
        f"Risk Level: <b>{result.risk_level}</b> ({result.risk_score}/100)<br/>"
        f"{_RISK_LABEL[result.risk_level]}",
        verdict_style,
    ))
    story.append(Spacer(1, 0.2*cm))

    # Prompt injection
    story.append(Paragraph("Hidden Instructions (Prompt Injection)", h2))
    if result.prompt_injection_findings:
        for f in result.prompt_injection_findings:
            story.append(Paragraph(
                f"<b>[{f.pattern_id}]</b> &quot;{f.matched_text}&quot;", body,
            ))
            story.append(Paragraph(f"Context: {f.context}", small))
    else:
        story.append(Paragraph("None detected.", body))
    story.append(Spacer(1, 0.2*cm))

    # PII
    story.append(Paragraph("Personal Data Flagged", h2))
    if result.pii_findings:
        rows = [["Type", "Value"]] + [
            [f.pii_type.replace("_", " ").title(), f.matched_text]
            for f in result.pii_findings
        ]
        tbl = Table(rows, colWidths=[5*cm, 11*cm])
        tbl.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#f3f4f6")),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 9),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#fafafa")]),
            ("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#e5e7eb")),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ]))
        story.append(tbl)
    else:
        story.append(Paragraph("No sensitive personal data flagged.", body))
    story.append(Spacer(1, 0.2*cm))

    # AI text
    story.append(Paragraph("AI-Generated Text", h2))
    story.append(Paragraph(
        f"Likelihood: <b>{result.ai_text_likelihood}</b> "
        f"(score: {result.ai_text_score:.2f})",
        body,
    ))
    story.append(Spacer(1, 0.4*cm))

    # Disclaimer
    story.append(Paragraph(
        "This report is a screening aid only. It does not constitute a final hiring decision. "
        "Claims flagged as unverified should be confirmed directly with the candidate. "
        "ProofHire Shield does not store CV data. All processing is ephemeral.",
        small,
    ))

    doc.build(story)
    return buf.getvalue()
